"""Per-well facts from the EMNRD completion records (the wellCompletions column).

load_completions(conn) returns one row per well:
    api              '30-025-40173'
    perf_top_md      shallowest perforation, measured depth (ft)
    perf_bottom_md   deepest perforation, measured depth (ft)
    perf_lateral_ft  perf_bottom_md - perf_top_md
    pool_formation   formation part of the pool name, e.g. 'BONE SPRING'
    spacing_acres    size of the spacing unit dedicated to the well

Only design and geometry fields are read. Test volumes, production dates and
completion dates are filed after the frac, so they would leak the answer.

Run from src to see coverage by job year:  python -m data.completions
"""
import json
import sqlite3

import pandas as pd

from data.config import DB_PATH

PERF_TABLE = "emnrd_perforations"
MISSING = {0, 99999}            # EMNRD's "not reported" values


def _clean(values):
    out = []
    for v in values:
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v not in MISSING and v > 0:
            out.append(v)
    return out


def parse_completions(text):
    """One well's wellCompletions JSON -> dict of features (empty if nothing usable)."""
    try:
        comps = json.loads(text)
    except (TypeError, ValueError):
        return {}
    if not isinstance(comps, list):
        return {}

    tops, bottoms, pools, acreages = [], [], [], []
    for c in comps:
        if not isinstance(c, dict):
            continue
        # The summary depths on the completion, plus every listed perforation interval.
        tops += _clean([c.get("depthPerfTopNum")])
        bottoms += _clean([c.get("depthPerfBottomNum")])
        for p in c.get("wellCompletionPerforations") or []:
            tops += _clean([p.get("topMeasuredDepth")])
            bottoms += _clean([p.get("bottomMeasuredDepth")])

        if c.get("poolName"):
            pools.append(str(c["poolName"]))
        # A unit spanning two sections lists both; their acreages add up.
        unit = sum(_clean([a.get("acreage") for a in c.get("satialAcreages") or []]))
        if unit:
            acreages.append(unit)

    out = {}
    if tops and bottoms:
        out["perf_top_md"], out["perf_bottom_md"] = min(tops), max(bottoms)
        out["perf_lateral_ft"] = out["perf_bottom_md"] - out["perf_top_md"]
    if pools:
        # 'CRUZ; BONE SPRING' -> 'BONE SPRING'
        out["pool_formation"] = pools[0].split(";")[-1].strip().upper()
    if acreages:
        out["spacing_acres"] = max(acreages)
    return out


def load_completions(conn):
    """One row per well, keyed by api, ready to merge onto the jobs table."""
    # Imported here, not at the top, so consolidate.py can import this file
    # without the two files importing each other at load time.
    from data.consolidate import to_nm_api

    wells = pd.read_sql(f'SELECT _api, wellCompletions FROM "{PERF_TABLE}"', conn)
    wells["api"] = wells["_api"].apply(to_nm_api)
    wells = wells.dropna(subset=["api"]).drop_duplicates("api")
    parsed = pd.DataFrame(wells["wellCompletions"].apply(parse_completions).tolist(),
                          index=wells.index)
    return pd.concat([wells[["api"]], parsed], axis=1).reset_index(drop=True)


def coverage_by_year():
    with sqlite3.connect(DB_PATH) as conn:
        jobs = pd.read_sql("SELECT api, JobStartDate FROM model_base", conn,
                           parse_dates=["JobStartDate"])
        comp = load_completions(conn)

    df = jobs.merge(comp, on="api", how="left")
    year = df["JobStartDate"].dt.year
    lateral = df.get("perf_lateral_ft", pd.Series(index=df.index, dtype=float))

    def share(mask):
        return mask.groupby(year).mean().round(2)

    print(pd.DataFrame({
        "jobs": year.value_counts().sort_index(),
        "any perf depth": share(df.get("perf_top_md", lateral).notna()),
        "usable lateral": share(lateral.between(1000, 20000)),
        "median lateral": lateral.where(lateral.between(1000, 20000)).groupby(year).median().round(0),
        "pool formation": share(df.get("pool_formation", lateral).notna()),
        "spacing acres": share(df.get("spacing_acres", lateral).notna()),
    }).to_string())


if __name__ == "__main__":
    coverage_by_year()