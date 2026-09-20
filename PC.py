"""
Datum — Proof of Concept: per-well fracking water-usage pipeline
================================================================

Goal of this POC (not the model — the plumbing that de-risks the model):
    1. Load FracFocus-style well data
    2. Clean it (nulls, zero/absurd water volumes, derive features)
    3. EDA — understand the target's distribution and a few drivers
    4. Baseline models — a number that "part 2" has to beat

It runs out of the box on SYNTHETIC data so you can see the whole flow.
To use REAL data, download the FracFocus registry-upload CSVs
(https://fracfocus.org/data-download — the "registryupload" header table
has APINumber, location, JobStartDate, TVD, TotalBaseWaterVolume, OperatorName)
and set REAL_CSV_PATH below. Then delete the synthetic branch when you're ready.

NOTE: metrics printed on synthetic data are MEANINGLESS — the point here is
that the pipeline runs and produces the right shapes. Real numbers come from
real data.
"""

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score

RANDOM_STATE = 42
REAL_CSV_PATH = None  # e.g. "registryupload_1.csv" — leave None to run the demo


# ----------------------------------------------------------------------
# 1. LOAD
# ----------------------------------------------------------------------
def load_real(path):
    """Load a FracFocus registry-upload header CSV. Column names below match
    the FracFocus data dictionary; adjust if your download differs."""
    df = pd.read_csv(path, low_memory=False)
    keep = {
        "APINumber": "api",
        "StateName": "state",
        "Latitude": "lat",
        "Longitude": "lon",
        "JobStartDate": "job_date",
        "TVD": "tvd",
        "TotalBaseWaterVolume": "water_gal",
        "OperatorName": "operator",
    }
    df = df[[c for c in keep if c in df.columns]].rename(columns=keep)
    return df


def make_synthetic(n=6000, seed=RANDOM_STATE):
    """FracFocus-shaped fake data so the pipeline runs end-to-end.
    The generative relationship is deliberately simple + noisy; it exists
    only so EDA/baselines have something sane to chew on."""
    rng = np.random.default_rng(seed)
    basins = np.array(["Permian", "Eagle Ford", "Bakken", "Marcellus"])
    basin = rng.choice(basins, size=n, p=[0.45, 0.2, 0.15, 0.2])
    operator = rng.choice([f"Operator_{i}" for i in range(25)], size=n)
    year = rng.integers(2015, 2025, size=n)
    tvd = rng.normal(8500, 2200, size=n).clip(3000, 15000)

    # water grows with depth and over time, varies by basin; log-normal noise
    basin_effect = pd.Series(basin).map(
        {"Permian": 1.15, "Eagle Ford": 1.0, "Bakken": 0.85, "Marcellus": 1.3}
    ).values
    log_water = (
            11.0
            + 0.00008 * tvd
            + 0.08 * (year - 2015)
            + np.log(basin_effect)
            + rng.normal(0, 0.35, size=n)
    )
    water_gal = np.exp(log_water)

    # inject the messiness real data always has
    water_gal[rng.random(n) < 0.03] = 0            # zero-volume junk rows
    water_gal[rng.random(n) < 0.02] = np.nan        # missing
    tvd[rng.random(n) < 0.02] = np.nan

    return pd.DataFrame(
        {
            "api": rng.integers(3e13, 4e13, size=n),
            "state": basin,          # stand-in; real data has state + lat/lon
            "job_date": pd.to_datetime(
                {"year": year, "month": rng.integers(1, 13, n), "day": 1}
            ),
            "tvd": tvd,
            "water_gal": water_gal,
            "operator": operator,
        }
    )


# ----------------------------------------------------------------------
# 2. CLEAN
# ----------------------------------------------------------------------
def clean(df):
    n0 = len(df)
    df = df.dropna(subset=["water_gal", "tvd"]).copy()
    df = df[df["water_gal"] > 0]

    # drop physically implausible volumes (typical frac job: ~0.1M–20M gallons)
    df = df[(df["water_gal"] > 50_000) & (df["water_gal"] < 40_000_000)]

    df["job_date"] = pd.to_datetime(df["job_date"], errors="coerce")
    df = df.dropna(subset=["job_date"])
    df["year"] = df["job_date"].dt.year

    # target is heavily right-skewed -> model in log space
    df["log_water"] = np.log(df["water_gal"])

    print(f"[clean] kept {len(df):,} of {n0:,} rows "
          f"({len(df)/n0:.0%}) after dropping nulls/zeros/outliers\n")
    return df


# ----------------------------------------------------------------------
# 3. EDA
# ----------------------------------------------------------------------
def eda(df):
    print("[eda] water volume (gallons):")
    print(df["water_gal"].describe(percentiles=[.1, .5, .9]).round(0).to_string())
    print(f"\n[eda] skew of water_gal:     {df['water_gal'].skew():.2f}")
    print(f"[eda] skew of log_water:     {df['log_water'].skew():.2f}  "
          f"(<- why we log-transform)\n")

    print("[eda] median water by basin/state:")
    print(df.groupby("state")["water_gal"].median().round(0).to_string(), "\n")

    print("[eda] median water by year:")
    print(df.groupby("year")["water_gal"].median().round(0).to_string(), "\n")

    print(f"[eda] corr(TVD, log_water):  {df['tvd'].corr(df['log_water']):.3f}\n")


# ----------------------------------------------------------------------
# 4. BASELINES
# ----------------------------------------------------------------------
def baselines(df):
    """Two baselines. Report error in gallons (back-transformed) so it's
    interpretable, plus R^2 on the log target."""
    feat = pd.get_dummies(
        df[["tvd", "year", "state"]], columns=["state"], drop_first=True
    )
    y = df["log_water"].values
    Xtr, Xte, ytr, yte = train_test_split(
        feat, y, test_size=0.2, random_state=RANDOM_STATE
    )

    # Baseline 0: predict the training-set mean for everyone
    mean_pred = np.full_like(yte, ytr.mean())
    mae0 = mean_absolute_error(np.exp(yte), np.exp(mean_pred))

    # Baseline 1: linear regression on TVD + year + basin
    lr = LinearRegression().fit(Xtr, ytr)
    pred = lr.predict(Xte)
    mae1 = mean_absolute_error(np.exp(yte), np.exp(pred))
    r2 = r2_score(yte, pred)

    print("[baseline] MAE in gallons (lower is better):")
    print(f"    predict-the-mean : {mae0:,.0f}")
    print(f"    linear regression: {mae1:,.0f}   (R^2 on log target: {r2:.3f})")
    print(f"    -> linear beats the mean by {(mae0-mae1)/mae0:.0%}\n")
    print("This linear MAE is the number part 2 (trees / GBMs + more features)\n"
          "has to beat. Add lateral length + proppant (via a state-DB join) and\n"
          "it should drop a lot.")


# ----------------------------------------------------------------------
def main():
    if REAL_CSV_PATH:
        print(f"Loading real FracFocus data from {REAL_CSV_PATH}\n")
        df = load_real(REAL_CSV_PATH)
    else:
        print("No REAL_CSV_PATH set — running on SYNTHETIC demo data.")
        print("(Metrics below are meaningless; the point is the pipeline runs.)\n")
        df = make_synthetic()

    df = clean(df)
    eda(df)
    baselines(df)


if __name__ == "__main__":
    main()