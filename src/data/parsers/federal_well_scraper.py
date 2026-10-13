import re
import pandas as pd
import numpy as np
import time
import sqlite3
import json
from pathlib import Path

import pdfplumber, fitz
import requests

from data.emnrd_data import emnrd_per_well, login, session_auth
from data.config import DB_PATH

OUT = Path("data/well_pdfs")

def parse_federal():
    raise NotImplementedError()

def parse_state():
    raise NotImplementedError()

def federal_or_state(text):
    t = text.upper()
    if "APPLICATION FOR PERMIT TO DRILL" in t or "3160-3" in t:
        return "federal",

def fetch_papers(api, files, session):
    if isinstance(files, str):
        files = json.loads(files)
    folder = OUT / api
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for f in files:
        if f.get("mimeType") != "application/pdf":
            continue
        path = folder / f["fileName"]
        if not path.exists():
            r = session.get(f["url"], stream=True, timeout=120)
            r.raise_for_status()
            tmp = path.with_suffix(".part")
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(1 << 16):
                    fh.write(chunk)
                tmp.rename(path)
                time.sleep(0.2)
            paths.append(path)
        return paths

def open_paper(path):
    with pdfplumber.open(path) as pdf:
        text = pdf.pages[0].extract_text()
    page = fitz.open(path)[0]
    page.get_pixmap(dpi=300).save("page.png")
    return text

def check_plumber():
    raise NotImplementedError("plumber search has not been implemented yet")

def check_tesseract():


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
    session_main = requests.Session()
    session_main.headers["Authorization"] = f'Bearer {auth_key}'
    fetch_papers(session_main)
