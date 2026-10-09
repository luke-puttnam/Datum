"""Feature coverage report for model_base: which features are actually filled, and when.

A feature that is filled for old jobs but empty for recent ones hurts twice: the model
learns to lean on it, then the test set (the newest jobs) doesn't have it.

Run from src/:  python -m data.testing_features
"""
import sqlite3

import numpy as np
import pandas as pd

from data.config import (
    CATEGORICAL, DB_PATH, FEATURES, LINQ_API_COL, LINQ_MD_COL, LINQ_TABLE, LINQ_TGT_COL,
    OUT_TABLE,
)
from data.consolidate import to_nm_api

LATERAL_RANGE = (1000, 20000)      # same window XGBoost_model uses for "has a lateral"
NOT_REPORTED = [0, 99999]          # EMNRD's "not reported" depth markers
WARN_DROP = 0.30                   # flag features whose coverage falls this much, old vs recent
RECENT_YEARS = 3


def load_model_base(conn):
    df = pd.read_sql(f"SELECT * FROM {OUT_TABLE}", conn, parse_dates=["JobStartDate"])
    df["job_year"] = df["JobStartDate"].dt.year
    return df


def informative(df):
    """True where a feature carries real information. Placeholder labels count as missing."""
    has = df[FEATURES].notna()
    for col in CATEGORICAL:
        has[col] &= ~df[col].astype(str).str.upper().isin(["UNKNOWN", "NONE", "NAN", ""])
    return has


def coverage_by_year(df):
    """Share of jobs with an informative value, one row per feature, one column per year."""
    table = informative(df).groupby(df["job_year"]).mean().T
    table.insert(0, "all", informative(df).mean())
    return table


def drifting_features(coverage):
    """Features whose coverage in the last few years is well below the years before."""
    years = [c for c in coverage.columns if c != "all"]
    old, recent = years[:-RECENT_YEARS], years[-RECENT_YEARS:]
    drop = coverage[old].mean(axis=1) - coverage[recent].mean(axis=1)
    return drop[drop > WARN_DROP].sort_values(ascending=False)


def lateral_sources(conn, df):
    """Where lateral length can come from, per year: completed MD vs permitted target depth."""
    linq = pd.read_sql(
        f'SELECT "{LINQ_API_COL}" AS well_api, "{LINQ_MD_COL}" AS md, "{LINQ_TGT_COL}" AS tgt '
        f"FROM {LINQ_TABLE}", conn)
    linq["api"] = linq["well_api"].apply(to_nm_api)
    linq = linq.dropna(subset=["api"]).drop_duplicates("api")

    m = df[["api", "job_year", "tvd_ft"]].merge(linq, on="api", how="left", indicator=True)
    md_raw = pd.to_numeric(m["md"], errors="coerce")
    md = md_raw.replace(NOT_REPORTED, np.nan)
    tgt = pd.to_numeric(m["tgt"], errors="coerce").replace(NOT_REPORTED, np.nan)
    tvd = pd.to_numeric(m["tvd_ft"], errors="coerce")
    year = m["job_year"]

    table = pd.DataFrame({
        "jobs": year.value_counts().sort_index(),
        "in_linq": m["_merge"].eq("both").groupby(year).mean(),
        "md_marked_0": md_raw.isin(NOT_REPORTED).groupby(year).mean(),
        "lateral_from_md": (md - tvd).between(*LATERAL_RANGE).groupby(year).mean(),
        "lateral_from_tgt": (tgt - tvd).between(*LATERAL_RANGE).groupby(year).mean(),
        "lateral_either": (md.fillna(tgt) - tvd).between(*LATERAL_RANGE).groupby(year).mean(),
    })

    both = md.notna() & tgt.notna()
    ratio = (tgt / md)[both]
    agreement = {
        "jobs with both depths": int(both.sum()),
        "median target/MD": round(ratio.median(), 3),
        "share within 5%": round((ratio - 1).abs().lt(0.05).mean(), 3),
    }
    return table, agreement


def main():
    with sqlite3.connect(DB_PATH) as conn:
        df = load_model_base(conn)
        lateral, agreement = lateral_sources(conn, df)

    pd.set_option("display.width", 250)
    coverage = coverage_by_year(df)
    print(f"{OUT_TABLE}: {len(df):,} jobs, {df['job_year'].min()}-{df['job_year'].max()}")
    print("\nShare of jobs with an informative value (placeholders like 'unknown' count as missing):")
    print(coverage.round(2).to_string())

    drift = drifting_features(coverage)
    print(f"\nCoverage falls by more than {WARN_DROP:.0%} in the last {RECENT_YEARS} years:")
    print(drift.round(2).to_string() if len(drift) else "  none")

    print("\nLateral length sources by year (share of jobs):")
    print(lateral.round(2).to_string())
    print("\nPermitted target depth vs completed MD, where both are reported:")
    for name, value in agreement.items():
        print(f"  {name:<24}{value}")


if __name__ == "__main__":
    main()
