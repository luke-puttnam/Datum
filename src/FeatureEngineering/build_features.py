import numpy as np
import pandas as pd

from data.config import LINQ_MD_COL, LINQ_SPUD_COL, LINQ_TVD_COL, TARGET

GEL_CAS   = {"9000-30-0", "39421-75-5", "68130-15-4"}               # guar, HPG, CMHPG
XLINK_CAS = {"10043-35-3", "1303-96-4", "1330-43-4", "1319-33-1"}   # boric acid, borates, ulexite
FR_CAS    = {"9003-05-8"}                                           # polyacrylamide


def add_target(df):
    df = df.copy()
    df[TARGET] = np.log1p(df["TotalBaseWaterVolume"])
    return df

def add_geometry(df):
    """lateral_length_ft, lateral_source, is_horizontal"""
    df = df.copy()
    ff_tvd = df["TVD"].where(df["TVD"].between(1, 20000))
    emnrd_tvd = df[LINQ_TVD_COL] if LINQ_TVD_COL in df else np.nan
    df["tvd_ft"] = ff_tvd.fillna(emnrd_tvd)

    if LINQ_MD_COL in df:
        diff = df[LINQ_MD_COL] - df["tvd_ft"]
        df["md_minus_tvd"] = diff.where(diff >= 0)
    else:
        df["md_minus_tvd"] = np.nan
    df["is_horizontal"] = (df["md_minus_tvd"] > 2000).astype(float)
    df.loc[df["md_minus_tvd"].isna(), "is_horizontal"] = np.nan
    return df

def add_time(df):
    """job_year, days_spud_to_frac."""
    df = df.copy()
    df["job_year"] = df["JobStartDate"].dt.year
    if LINQ_SPUD_COL in df:
        days = (df["JobStartDate"] - df[LINQ_SPUD_COL]).dt.days
        df["days_spud_to_frac"] = days.where(days >= 0)
    else:
        df["days_spud_to_frac"] = np.nan
    return df

def add_refrac(df):
    """job_number, days_since_prev_job, is_refrac. Needs add_time first."""
    df = df.sort_values(["api", "JobStartDate"]).copy()
    df["job_number"] = df.groupby("api").cumcount() + 1
    df["days_since_prev_job"] = df.groupby("api")["JobStartDate"].diff().dt.days
    df["is_refrac"] = (
            (df["days_since_prev_job"] > 365)
            | (df["days_since_prev_job"].isna() & (df["days_spud_to_frac"] > 3 * 365))
    ).astype(int)
    return df

def add_formation(df):
    """Tidy formation names so spelling variants count as one formation."""
    df = df.copy()
    df["target_formation"] = (df["target_formation"].str.upper()
                              .str.replace(r"\s+", " ", regex=True).str.strip())
    return df

def add_fluid(df):
    """Jobs with no ingredient rows get 0 for each fluid flag."""
    df = df.copy()
    for c in ["is_fr", "is_gel", "is_xlink"]:
        df[c] = df[c].fillna(False).astype(int)
    return df

STEPS = [add_target, add_geometry, add_time, add_refrac, add_formation, add_fluid]

def build_features(df):
    """Run every feature step in order. Comment a step out to measure what it's worth."""
    for step in STEPS:
        df = step(df)
    return df

def classify_fluid(df):
    purpose = df["Purpose"].fillna("").str.lower()
    name    = df["IngredientCommonName"].fillna("").str.lower()
    cas     = df["CASNumber"].fillna("").str.strip()

    df = df.assign(
        is_fr    = purpose.str.contains("friction") | cas.isin(FR_CAS)    | name.str.contains("polyacrylamide"),
        is_gel   = purpose.str.contains("gel")      | cas.isin(GEL_CAS)   | name.str.contains("guar"),
        is_xlink = purpose.str.contains("cross")    | cas.isin(XLINK_CAS) | name.str.contains("borate|zircon"),
    )
    flags = df.groupby("DisclosureId")[["is_fr", "is_gel", "is_xlink"]].any()

    def label(r):
        if r.is_gel and r.is_fr:
            return "hybrid"
        if r.is_gel and r.is_xlink:
            return "crosslinked gel"
        if r.is_gel:
            return "linear gel"
        if r.is_fr:
            return "slickwater"
        return "unknown"

    flags["fluid_system"] = flags.apply(label, axis=1)
    return flags.reset_index()