"""XGBoost model for frac water volume, trained on model_base.

Lives in src/Models. Run consolidate.py first so model_base exists.
"""
import sqlite3
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from xgboost import XGBRegressor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))   # src/data

from data.config import DB_PATH
from data.consolidate import CATEGORICAL, FEATURES, OUT_TABLE, TARGET
from loss_curve import LossCurve

VAL_SHARE = 0.15      # used to choose the number of trees
TEST_SHARE = 0.15     # most recent jobs, scored once at the end
SEED = 42


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


def build_model():
    return XGBRegressor(
        n_estimators=2000,            # upper limit; early stopping picks the real number
        early_stopping_rounds=50,     # stop when validation hasn't improved for 50 trees
        learning_rate=0.05,           # how much each tree is allowed to correct
        max_depth=6,                  # how complex each tree can be
        subsample=0.8,                # each tree sees 80% of the rows
        colsample_bytree=0.8,         # ...and 80% of the features
        eval_metric="rmse",
        enable_categorical=True,      # use the category columns directly
        tree_method="hist",
        random_state=SEED,
    )


def score(name, y_true, y_pred):
    """Errors in gallons, after undoing the log."""
    actual, predicted = np.expm1(y_true), np.expm1(y_pred)
    return {
        "model": name,
        "R2 (log)": r2_score(y_true, y_pred),
        "MAE (million gal)": mean_absolute_error(actual, predicted) / 1e6,
        "typical % error": np.median(np.abs(predicted - actual) / actual) * 100,
    }


def main():
    train, val, test = split_by_date(load())
    X_train, y_train = train[FEATURES], train[TARGET]
    X_val, y_val = val[FEATURES], val[TARGET]
    X_test, y_test = test[FEATURES], test[TARGET]

    model = build_model()
    model.fit(X_train, y_train,
              eval_set=[(X_train, y_train), (X_val, y_val)],    # training first, then validation
              verbose=False)

    curve = LossCurve.from_model(model, "xgboost")
    print(f"\n{curve}\n{curve.diagnose()}\n")

    naive = np.full(len(y_test), y_train.median())
    results = [score("naive (median)", y_test, naive),
               score("xgboost", y_test, model.predict(X_test))]
    print(pd.DataFrame(results).set_index("model").round(2).to_string())

    importance = pd.Series(model.feature_importances_, index=FEATURES)
    print("\nFeature importance (share of total gain):")
    print(importance.sort_values(ascending=False).round(3).to_string())

    curve.plot()
    plt.savefig(Path(__file__).with_name("xgboost_loss_curve.png"), dpi=120, bbox_inches="tight")
    plt.show()


if __name__ == "__main__":
    main()