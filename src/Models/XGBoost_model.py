"""XGBoost model for frac water volume, trained on model_base.

Lives in src/Models. Run consolidate.py first so model_base exists.
"""
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.inspection import permutation_importance
from xgboost import XGBRegressor

from data.config import DB_PATH
from data.consolidate import CATEGORICAL, FEATURES, OUT_TABLE, TARGET
from Models.loss_curve import LossCurve

VAL_SHARE = 0.15      # used to choose the number of trees
TEST_SHARE = 0.15     # most recent jobs, scored once at the end
SEED = 42

SHOW_PERMUTATION = True
LATERAL_COL = "md_minus_tvd"
LATERAL_RANGE = (1000, 20000)

def load():
    """Read model_base and give every column the type XGBoost expects."""
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql(f"SELECT * FROM {OUT_TABLE}", conn, parse_dates=["JobStartDate"])
    for col in CATEGORICAL:
        df[col] = df[col].fillna("UNKNOWN").astype("category")
    numeric = [c for c in FEATURES if c not in CATEGORICAL]
    df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")
    return df.sort_values("JobStartDate").reset_index(drop=True)


def split_by_date(df):
    """Oldest jobs train, the next slice validates, the newest slice tests."""
    n = len(df)
    val_start = int(n * (1 - VAL_SHARE - TEST_SHARE))
    test_start = int(n * (1 - TEST_SHARE))
    parts = {"train": df.iloc[:val_start], "val": df.iloc[val_start:test_start],
             "test": df.iloc[test_start:]}
    for name, part in parts.items():
        print(f"{name:<6}{len(part):>7,} jobs  "
              f"{part['JobStartDate'].min():%Y-%m-%d} to {part['JobStartDate'].max():%Y-%m-%d}")
    return parts["train"], parts["val"], parts["test"]

def has_lateral(df):
    return df[df[LATERAL_COL].between(*LATERAL_RANGE)]

def build_model():
    return XGBRegressor(
        n_estimators=2000,            # upper limit; early stopping picks the real number
        early_stopping_rounds=50,     # stop when validation hasn't improved for 50 trees
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="rmse",
        enable_categorical=True,
        tree_method="hist",
        random_state=SEED,
    )

def train(name, train_df, val_df):
    """Fit one model and report its loss curve."""
    model = build_model()
    model.fit(train_df[FEATURES], train_df[TARGET],
              eval_set=[(train_df[FEATURES], train_df[TARGET]),
                        (val_df[FEATURES], val_df[TARGET])],
              verbose=False)
    curve = LossCurve.from_model(model, name)
    print(f'\n{name}: trained on {len(train_df):,} jobs, validated on {len(val_df):,}')
    print(f'  {curve}\n {curve.diagnose()}')
    return model, curve

def score(label, model, df, baseline):
    """Errors in gallons, after undoing the log."""
    y_true = df[TARGET]
    y_pred = model.predict(df[FEATURES]) if model is not None else np.full(len(df), baseline)
    actual, predicted = np.expm1(y_true), np.expm1(y_pred)
    return {
        "model / test jobs": label,
        "jobs": len(df),
        "R2 (log)": r2_score(y_true, y_pred),
        "MAE (million gal)": mean_absolute_error(actual, predicted) / 1e6,
        "typical % error": np.median(np.abs(predicted - actual) / actual) * 100,
        "median pred/actual": np.median(predicted / actual),
    }

def permutation_table(model, val_df):
    r = permutation_importance(model, val_df[FEATURES], val_df[TARGET], n_repeats=5,
                               random_state=SEED, scoring="neg_root_mean_squared_error")
    return pd.DataFrame({"mean": r.importances_mean, "std": r.importances_std},
                        index=FEATURES).sort_values("mean", ascending=False)

def main():
    train_all, val_all, test_all = split_by_date(load())
    train_lat, val_lat, test_lat = has_lateral(train_all), has_lateral(val_all), has_lateral(test_all)
    print(f"\nWith a lateral length ({LATERAL_COL}): "
          f"{len(train_lat):,} train, {len(val_lat):,} val, {len(test_lat):,} test")

    model_all, curve_all = train("all jobs", train_all, val_all)
    model_lat, curve_lat = train("lateral required", train_lat, val_lat)

    # The fair comparison is the last two rows: both models on the same test jobs.
    rows = [
        score("naive guess / all", None, test_all, train_all[TARGET].median()),
        score("all-jobs model / all", model_all, test_all, None),
        score("naive guess / with lateral", None, test_lat, train_lat[TARGET].median()),
        score("all-jobs model / with lateral", model_all, test_lat, None),
        score("lateral model / with lateral", model_lat, test_lat, None),
    ]
    print("\nTest results:")
    print(pd.DataFrame(rows).set_index("model / test jobs").round(3).to_string())

    if SHOW_PERMUTATION:
        perm = pd.concat({"all jobs": permutation_table(model_all, val_all),
                          "lateral required": permutation_table(model_lat, val_lat)}, axis=1)
        print("\nPermutation importance (validation, increase in RMSE when shuffled):")
        print(perm.sort_values(("lateral required", "mean"), ascending=False).round(4).to_string())

    fig, axes = plt.subplots(1, 2, figsize=(13, 4), sharey=True)
    curve_all.plot(axes[0])
    curve_lat.plot(axes[1])
    fig.savefig(Path(__file__).with_name("xgboost_loss_curves.png"), dpi=120, bbox_inches="tight")
    plt.show()


if __name__ == "__main__":
    main()