import json
import sqlite3

import pandas as pd

from data.config import DB_PATH
from data.consolidate import to_nm_api

with sqlite3.connect(DB_PATH) as conn:
    recent = pd.read_sql("SELECT api FROM model_base WHERE JobStartDate >= '2024-01-01'", conn)
    wells = pd.read_sql("SELECT _api, wellCompletions FROM emnrd_perforations", conn)

wells["api"] = wells["_api"].apply(to_nm_api)
row = wells[wells["api"].isin(recent["api"])].iloc[0]
comps = json.loads(row["wellCompletions"])

print(row["api"], "-", len(comps), "completion record(s)")
print("Keys:", list(comps[0].keys()))
print(json.dumps(comps[0], indent=2)[:3000])