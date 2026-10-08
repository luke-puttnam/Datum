import sqlite3
import pandas as pd
from data.config import DB_PATH

with sqlite3.connect(DB_PATH) as conn:
    query = """
    SELECT JobStartDate, md_minus_tvd FROM model_base;
    """
    df = pd.read_sql(query, conn, parse_dates=["JobStartDate"])

md = pd.to_numeric(df["md_minus_tvd"], errors="coerce")
year = df["JobStartDate"].dt.year

summary = pd.DataFrame({
    "jobs": year.value_counts().sort_index(),
    "any_value": md.notna().groupby(year).mean().round(2),
    "usable_lateral": md.between(1000, 20000).groupby(year).mean().round(2)
})

print(summary.to_string())