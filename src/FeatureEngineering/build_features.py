import numpy as np
import pandas as pd
import sqlite3

from data.config import DB_PATH
from data.consolidate import

GEL_CAS   = {"9000-30-0", "39421-75-5", "68130-15-4"}               # guar, HPG, CMHPG
XLINK_CAS = {"10043-35-3", "1303-96-4", "1330-43-4", "1319-33-1"}   # boric acid, borates, ulexite
FR_CAS    = {"9003-05-8"}                                           # polyacrylamide


def add_geometry(df):
    """lateral_length_ft, lateral_source, is_horizontal"""
    raise NotImplementedError("w1")

def add_time(df):
    raise NotImplementedError("w2")

def add_formation(df):
    raise NotImplementedError("w3")

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