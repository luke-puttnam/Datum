import io
import sqlite3
import pandas as pd
import requests
import re
import json
import pdfplumber
import fitz
import time
import numpy as np
from data.config import DB_PATH
from data.emnrd_data import login, session_auth

from concurrent.futures import ThreadPoolExecutor

def fetch_papers(conn):
    query = """
    SELECT api, wellImagingFiles
    FROM imaging_links;
    """
    return pd.read_sql(query, conn)

def load_paper(session, url):
    if session is None:
        raise ValueError("pass in session")
    resp = session.get(url)
    if resp is None:
        return None


def open_pdf(src):
    if isinstance(src, (bytes, bytearray)):
        return fitz.open(stream=src, filetype="pdf"), pdfplumber.open(io.BytesIO(src))
    return fitz.open(src), pdfplumber.open(src)

def page_to_array(page, dpi=300):
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def simple_extract():


def main():
    main_key, refresh_key = login()
    session = session_auth(main_key, refresh_key)
    with sqlite3.connect(DB_PATH) as conn:
        df = fetch_papers(conn)

    def