import re
import pandas as pd
import numpy as np
import time
import sqlite3


from data.emnrd_data import emnrd_per_well, login, session_auth
from data.config import DB_PATH

def parse_federal():
    raise NotImplementedError()

def parse_state():
    raise NotImplementedError()

def federal_or_state(text):
    t = text.upper()
    if "APPLICATION FOR PERMIT TO DRILL" in t or "3160-3" in t:
        return "federal",


def fetch_missing_laterals():
    query = """
    SELECT DISTINCT api
    FROM model_base
        WHERE md_minus_tvd IS NULL;
    """
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql(query, conn)
        return df


if __name__ == "main":
    auth_key, refresh_key = login()
    auth = session_auth(auth_key, refresh_key)
