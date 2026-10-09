import sqlite3

import pandas as pd

from data.completions import load_completions
from data.config import DB_PATH

with sqlite3.connect(DB_PATH) as conn:
    jobs = pd.read_sql("SELECT api, JobStartDate FROM model_base", conn, parse_dates=["JobStartDate"])
    comp = load_completions(conn)

df = jobs.merge(comp, on="api", how="left")
lateral = df["perf_lateral_ft"].where(df["perf_lateral_ft"].between(1000, 20000))

print("Median lateral by spacing unit size (units with 20+ jobs):")
print(lateral.groupby(df["spacing_acres"]).agg(["count", "median"]).query("count >= 20").round(0))

print("\nMedian spacing acres by year:")
print(df.groupby(df["JobStartDate"].dt.year)["spacing_acres"].median())