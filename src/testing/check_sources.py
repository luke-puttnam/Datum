import sqlite3

import pandas as pd

from data.config import DB_PATH
from data.consolidate import to_nm_api

with sqlite3.connect(DB_PATH) as conn:
    jobs = pd.read_sql("SELECT api, JobStartDate FROM model_base", conn,
                       parse_dates=["JobStartDate"])
    wells = pd.read_sql("SELECT _api, dpthMvdNum, wellCompletions FROM emnrd_perforations", conn)

wells["api"] = wells["_api"].apply(to_nm_api)
wells = wells.dropna(subset=["api"]).drop_duplicates("api")
wells["md"] = pd.to_numeric(wells["dpthMvdNum"], errors="coerce")
comp = wells["wellCompletions"].fillna("")
wells["has_completions"] = comp.str.len().gt(10) & ~comp.isin(["nan", "None", "[]"])

df = jobs.merge(wells[["api", "md", "has_completions"]], on="api", how="left", indicator=True)
year = df["JobStartDate"].dt.year
print(pd.DataFrame({
    "jobs": year.value_counts().sort_index(),
    "fetched": df["_merge"].eq("both").groupby(year).mean().round(2),
    "md > 0": df["md"].gt(0).groupby(year).mean().round(2),
    "has completions": df["has_completions"].fillna(False).astype(bool).groupby(year).mean().round(2),
}).to_string())