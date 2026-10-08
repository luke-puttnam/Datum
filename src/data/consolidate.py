"""Build model_base: one row per frac job, with the features needed for a first model.

Sources (both in datum.db):
    frac_nm     - FracFocus disclosures, one row per ingredient
    emnrd_linq  - EMNRD well records, one row per well

Run:  python consolidate.py
"""
import sqlite3

import numpy as np
import pandas as pd

from data.config import DB_PATH
from data.config import DB_PATH, LINQ_API_COL, LINQ_MD_COL, LINQ_SPUD_COL, LINQ_TVD_COL
from FeatureEngineering.build_features import (
    CATEGORICAL, FEATURES, TARGET, build_features, classify_fluid,
)

FF_TABLE = "frac_nm"
LINQ_TABLE = "emnrd_linq"
OUT_TABLE = "model_base"

COUNTY_CODES = {"015": "EDDY", "025": "LEA"}   # API county code -> FracFocus county name
MIN_JOB_DATE = "2011-01-01"                    # FracFocus began collecting disclosures in 2011

# FracFocus columns that describe the job (they repeat on every ingredient row).
# JobEndDate and TotalBaseNonWaterVolume are left out on purpose: both are only
# known after the job, so they would leak the target.
FF_JOB_COLS = [
    "DisclosureId", "JobStartDate", "APINumber", "CountyName", "OperatorName",
    "WellName", "Latitude", "Longitude", "TVD", "TotalBaseWaterVolume",
    "FederalWell", "IndianWell",
]

def to_nm_api(api):
    """'30015123450000' or '30-015-12345' -> '30-015-12345'. None if unusable."""
    if pd.isna(api):
        return None
    s = str(api).split(".")[0]
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) in (12, 14):
        digits = digits[:10]
    if len(digits) != 10:
        return None
    return f"{digits[:2]}-{digits[2:5]}-{digits[5:]}"


def to_date(col):
    """Text -> datetime, whatever the format. Unparseable values become NaT."""
    parsed = pd.to_datetime(col, errors="coerce", utc=True, format="mixed")
    return parsed.dt.tz_localize(None)


def load_fracfocus(conn):
    """One row per frac job in the target counties."""
    counties = ", ".join(f"'{c}'" for c in COUNTY_CODES.values())
    query = (
        f"SELECT DISTINCT {', '.join(FF_JOB_COLS)} FROM {FF_TABLE} "
        f"WHERE UPPER(CountyName) IN ({counties})"
    )
    ff = pd.read_sql(query, conn)
    steps = {"jobs read": len(ff)}

    ff["api"] = ff["APINumber"].apply(to_nm_api)
    ff = ff.dropna(subset=["api"])
    steps["with a usable API"] = len(ff)

    # FracFocus has typo dates (year 3012, 1900). Keep the plausible ones.
    ff["JobStartDate"] = to_date(ff["JobStartDate"])
    ff = ff[ff["JobStartDate"].between(MIN_JOB_DATE, pd.Timestamp.today())]
    steps["with a plausible start date"] = len(ff)

    # No usable target -> no use for training.
    ff = ff[ff["TotalBaseWaterVolume"] > 0]
    steps["with a water volume"] = len(ff)

    # Resubmitted disclosures: same well and start date under two ids. Keep one.
    ff = ff.sort_values("DisclosureId").drop_duplicates(["api", "JobStartDate"], keep="last")
    steps["after dropping resubmissions"] = len(ff)

    print("FracFocus rows kept at each step:")
    for name, n in steps.items():
        print(f"  {name:<30}{n:>8,}")

    assert ff["DisclosureId"].is_unique, "a job column differs between ingredient rows"
    return ff.reset_index(drop=True)


def load_linq(conn):
    """One row per well in the target counties, depths cleaned."""
    available = pd.read_sql(f"SELECT * FROM {LINQ_TABLE} LIMIT 0", conn).columns
    actual = {c.lower(): c for c in available}            # 'wellapi' -> the table's own spelling

    wanted = [LINQ_API_COL, LINQ_TVD_COL, LINQ_MD_COL, LINQ_SPUD_COL]
    found = {actual[w.lower()]: w for w in wanted if w.lower() in actual}
    missing = [w for w in wanted if w.lower() not in actual]
    if missing:
        print(f"Not in {LINQ_TABLE}, skipped: {missing}")
    if LINQ_API_COL in missing:
        raise KeyError(f"No '{LINQ_API_COL}' column in {LINQ_TABLE}. It has: {list(available)}")

    select = ", ".join(f'"{c}"' for c in found)
    linq = pd.read_sql(f"SELECT {select} FROM {LINQ_TABLE}", conn).rename(columns=found)

    linq["api"] = linq[LINQ_API_COL].apply(to_nm_api)
    linq = linq.dropna(subset=["api"])
    linq = linq[linq["api"].str[3:6].isin(COUNTY_CODES)]

    # 0 and 99999 are EMNRD's "not reported" markers.
    depth_cols = [c for c in (LINQ_TVD_COL, LINQ_MD_COL) if c in linq]
    linq[depth_cols] = linq[depth_cols].apply(pd.to_numeric, errors="coerce")
    linq[depth_cols] = linq[depth_cols].replace([0, 99999], np.nan)

    if LINQ_SPUD_COL in linq:
        linq[LINQ_SPUD_COL] = to_date(linq[LINQ_SPUD_COL])

    linq = linq.drop(columns=[LINQ_API_COL]).drop_duplicates("api")
    return linq.reset_index(drop=True)

def load_formation(conn):
    query = """
            SELECT wellApi, formationName AS target_formation,
                   MAX(CAST(top AS REAL)) AS target_top_depth
            FROM "emnrd_formation-tops"
            WHERE producing = 'True'
              AND CAST(top AS REAL) BETWEEN 1 AND 30000
            GROUP BY wellApi \
            """
    df = pd.read_sql(query, conn)
    df["api"] = df["wellApi"].apply(to_nm_api)
    df = df.dropna(subset=["api"]).drop_duplicates("api")
    return df.drop(columns="wellApi")

def load_chemicals(conn):
    query = f"""
    SELECT DisclosureId, IngredientName, IngredientCommonName, CASNumber, Purpose
    FROM {FF_TABLE}
    WHERE DisclosureId IS NOT NULL
    """
    return pd.read_sql(query, conn)


def add_features(df, formation):
    """Derived columns. Everything here is known before the frac job starts."""
    df = df.copy()

    # Target, log-scaled because a few jobs use enormous volumes.
    df[TARGET] = np.log1p(df["TotalBaseWaterVolume"])

    # Depth: FracFocus TVD first, EMNRD TVD where FracFocus has none.
    ff_tvd = df["TVD"].where(df["TVD"].between(1, 20000))
    emnrd_tvd = df[LINQ_TVD_COL] if LINQ_TVD_COL in df else np.nan
    df["tvd_ft"] = ff_tvd.fillna(emnrd_tvd)

    # Rough lateral length. Negative values are data errors.
    if LINQ_MD_COL in df:
        diff = df[LINQ_MD_COL] - df["tvd_ft"]
        df["md_minus_tvd"] = diff.where(diff >= 0)
    else:
        df["md_minus_tvd"] = np.nan
    df["is_horizontal"] = (df["md_minus_tvd"] > 2000).astype(float)
    df.loc[df["md_minus_tvd"].isna(), "is_horizontal"] = np.nan

    # Time.
    df["job_year"] = df["JobStartDate"].dt.year
    if LINQ_SPUD_COL in df:
        days = (df["JobStartDate"] - df[LINQ_SPUD_COL]).dt.days
        df["days_spud_to_frac"] = days.where(days >= 0)
    else:
        df["days_spud_to_frac"] = np.nan

    # Refracs: a later job on the same well, or a first recorded job long after spud.
    df = df.sort_values(["api", "JobStartDate"])
    df["job_number"] = df.groupby("api").cumcount() + 1
    df["days_since_prev_job"] = df.groupby("api")["JobStartDate"].diff().dt.days
    df["is_refrac"] = (
            (df["days_since_prev_job"] > 365)
            | (df["days_since_prev_job"].isna() & (df["days_spud_to_frac"] > 3 * 365))
    ).astype(int)

    #formation
    df = df.merge(
        formation,
        left_on="api",
        right_on="wellApi",
        how="left",
        validate="m:1"
    ).drop(columns="wellApi")

    return df


def report(df, n_jobs):
    print(f"\n{OUT_TABLE}: {len(df):,} jobs, {df['api'].nunique():,} wells")
    print(f"Jobs with a LINQ match: {df['_merge'].eq('both').mean():.1%}")
    print("\nShare of jobs with a value, per feature:")
    print(df[FEATURES].notna().mean().round(3).to_string())
    assert len(df) == n_jobs, "the merge changed the row count"


def show_consolidated_table():
    return f"SELECT * FROM {OUT_TABLE} ORDER BY RANDOM() LIMIT 2000;"


def main():
    with sqlite3.connect(DB_PATH) as conn:
        ff = load_fracfocus(conn)
        linq = load_linq(conn)
        formation = load_formation(conn)
        fluid = classify_fluid(load_chemicals(conn))

        df = ff.merge(linq, on="api", how="left", validate="m:1", indicator=True)
        df = df.merge(formation, on="api", how="left", validate="m:1")
        df = df.merge(fluid, on="DisclosureId", how="left", validate="m:1")
        df = build_features(df)

        print("formation coverage:", df["target_formation"].notna().mean())
        report(df, n_jobs=len(ff))

        keep = ["DisclosureId", "api", "WellName", "JobStartDate",
                "TotalBaseWaterVolume", TARGET] + FEATURES
        df[keep].to_sql(OUT_TABLE, conn, if_exists="replace", index=False)
        print(f"\nSaved {OUT_TABLE} to {DB_PATH}")

        checked_df = pd.read_sql(show_consolidated_table(), conn, parse_dates=["JobStartDate"])
        checked_df.to_csv(DB_PATH.parent / "model_base.csv", index=False)
        print(checked_df.head().T)


if __name__ == "__main__":
    main()