import io
import sqlite3
import easyocr
import pandas as pd
import requests
import re
import math
import pdfplumber
import fitz
import time
import numpy as np
from contextlib import contextmanager

from data.config import DB_PATH
from data.emnrd_data import login, session_auth
from FeatureEngineering.C_102 import parse_c102, plss_xy, ocr_words


READER = easyocr.Reader(["en"], gpu=True)

def create_results_table(conn):
    conn.execute("""
                 CREATE TABLE IF NOT EXISTS ocr_laterals (
                                                             api          TEXT,
                                                             url          TEXT,
                                                             lateral_ft   REAL,
                                                             source_form  TEXT,
                                                             status       TEXT,
                                                             page         INTEGER,
                                                             PRIMARY KEY (api, url)
                     );
                 """)

def save_result(conn, api, url, res):
    conn.execute("""
        INSERT OR REPLACE INTO ocr_laterals (api, url, lateral_ft, source_form, status, page)
        VALUES (?, ?, ?, ?, ?, ?);
    """, (api, url, res.get("lateral_ft"), res.get("source_form"),
          res.get("status"), res.get("page")))

def fetch_papers(conn):
    query = """
            SELECT DISTINCT
                i.api,
                i.wellImagingFiles
            FROM imaging_links AS i
                     JOIN model_base AS m
                          ON m.api = i.api
            WHERE i.wellImagingFiles IS NOT NULL
              AND m.TVD IS NULL; 
            """
    return pd.read_sql(query, conn)

def read_ocr(img):
    return READER.readtext(img)

def words_to_text(words):
    words = sorted(words, key=lambda w: (round(w[0][0][1] / 15), w[0][0][0]))
    return " ".join(w[1] for w in words)

def simple_extract(fitz_page, plumb_page, dpi=150):
    text = plumb_page.extract_text() or ""
    if len(text.strip()) > 50:
        return text, "text"
    return words_to_text(read_ocr(page_to_array(fitz_page, dpi))), 'ocr'

def is_apd(text):
    return bool(re.search(r"Form\s+3160-3", text[:300], re.I))

def is_c102(text):
    return bool(re.search(r"C-?102|ACREAGE\s+DEDICATION\s+PLAT", text, re.I))

LATLON_RE = re.compile(r"At\s+(surface|proposed\s+prod\.?\s+zone).*?LAT\s*(-?\d+\.\d+)\s*/\s*LONG\s*(-?\d+\.\d+)", re.I | re.S)
FOOT_RE   = re.compile(r"At\s+(surface|proposed\s+prod\.?\s+zone)\D*?(\d{1,4})['’]?\s*F([NS])L\s*&?\s*(\d{1,4})['’]?\s*F([EW])L", re.I | re.S)
SAME_RE   = re.compile(r"proposed\s+prod\.?\s+zone\s*SAME", re.I)
STR_RE    = re.compile(r"\b(\d{1,2})\s*-\s*(\d{1,2})\s*([NS])\s*-\s*(\d{1,2})\s*([EW])\b", re.I)

def feet_between(lat1, lon1, lat2, lon2):
    R = 20_902_231
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))

def parse_apd(text):
    if SAME_RE.search(text):
        return {"lateral_ft": 0, "status": "vertical"}

    ll = {m[0].split()[0].lower(): (float(m[1]), float(m[2])) for m in LATLON_RE.findall(text)}
    if "at" in ll: ll.pop("at")
    surf = next((v for k, v in ll.items() if k == "surface"), None)
    bh = next((v for k, v in ll.items() if k.startswith("proposed")), None)
    if surf and bh:
        ft = round(feet_between(*surf, *bh))
        return {"lateral_ft": ft, "status": "ok" if 0 <= ft <= 16000 else "implausible lateral"}

    # older APDs: footages + section/township/range
    feet = {m[0].split()[0].lower(): m[1:] for m in FOOT_RE.findall(text)}
    strm = STR_RE.search(text)
    if strm and "surface" in feet and "proposed" in feet:
        sec, twp, _, rng, _ = strm.groups()
        def xy(f):
            ns_ft, ns, ew_ft, ew = f
            return plss_xy(int(sec), int(twp), int(rng), int(ns_ft), ns.upper(), int(ew_ft), ew.upper())
        (sx, sy), (bx, by) = xy(feet["surface"]), xy(feet["proposed"])
        ft = round(math.hypot(bx - sx, by - sy))
        return {"lateral_ft": ft, "status": "ok" if 0 <= ft <= 16000 else "implausible lateral"}

    return {"lateral_ft": None, "status": "apd unreadable"}


def load_paper(session, url, retries=3, timeout=30):
    if session is None:
        raise ValueError("pass in session")
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f'[{attempt}/{retries}] network error: {e}')
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (401, 403):
            raise PermissionError(f'auth failed ({resp.status_code}); token has likely expired')
        if resp.status_code == 404:
            return None
        if resp.status_code >= 500 or resp.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        if not resp.ok:
            return None

        data = resp.content
        if not data.startswith(b"%PDF"):
            print(f'not a PDF ({resp.headers.get("Content-Type")}): {url}')
            return None
        return data
    return None

@contextmanager
def open_pdf(src):
    doc = plumb = None
    try:
        if isinstance(src, (bytes, bytearray)):
            doc = fitz.open(stream=src, filetype="pdf")
            plumb = pdfplumber.open(io.BytesIO(src))
        else:
            doc = fitz.open(src)
            plumb = pdfplumber.open(src)

        if doc.needs_pass:
            raise ValueError("encrypted pdf")
        if doc.page_count == 0:
            raise ValueError("empty pdf")

        yield doc, plumb
    finally:
        if plumb is not None:
            plumb.close()
        if doc is not None:
            doc.close()

def page_to_array(page, dpi=300):
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)

def header_text(fitz_page, dpi=100, frac=0.25):
    """OCR just the top quarter of a scanned page to identify the form."""
    img = page_to_array(fitz_page, dpi)
    return words_to_text(ocr_words(img[: int(img.shape[0] * frac)]))

def fitz_words(fitz_page):
    """Positioned words from the text layer, in ocr_words format."""
    return [((x0 + x1) / 2, (y0 + y1) / 2, y1 - y0, w, 1.0)
            for x0, y0, x1, y1, w, *_ in fitz_page.get_text("words")]

def extract_lateral(doc, plumb=None, max_pages=10):
    fallback = None
    order = list(range(min(max_pages, doc.page_count))) + list(range(max_pages, doc.page_count))

    for i in order:
        fp = doc[i]
        text = fp.get_text()
        has_text = len(text.strip()) > 50
        if not has_text:
            text = header_text(fp)                       # cheap identification only

        if is_apd(text):
            full = text if has_text else words_to_text(ocr_words(page_to_array(fp, 300)))
            res = {**parse_apd(full), "source_form": "APD", "page": i + 1}
        elif is_c102(text):
            words = fitz_words(fp) if has_text else ocr_words(page_to_array(fp, 300))
            res = {**parse_c102(words), "source_form": "C-102", "page": i + 1}
        else:
            continue

        if res.get("lateral_ft") is not None:
            return res
        fallback = fallback or res

    return fallback or {"lateral_ft": None, "status": "no form found", "source_form": None, "page": None}

    return fallback or {"lateral_ft": None, "status": "no form found", "source_form": None, "page": None}

def test_one(src, session=None):
    """Run extraction on one PDF (local path or URL) and print each step. No DB writes."""
    if src.startswith("http"):
        if session is None:
            main_key, refresh_key = login()
            session = session_auth(main_key, refresh_key)
        data = load_paper(session, src)
        if data is None:
            print("download failed")
            return
        print(f"downloaded {len(data):,} bytes")
    else:
        with open(src, "rb") as f:
            data = f.read()

    with open_pdf(data) as (doc, plumb):
        print(f"{doc.page_count} pages")
        for i, (fp, pp) in enumerate(zip(doc, plumb.pages), 1):
            text, method = simple_extract(fp, pp)
            form = "APD" if is_apd(text) else "C-102" if is_c102(text) else "-"
            print(f"  page {i:>2}: {method:<4} form={form:<5} {text[:80]!r}")

        result = extract_lateral(doc, plumb)

    print("\nRESULT:")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return result
# ---------- main ----------
def main():
    main_key, refresh_key = login()
    session = session_auth(main_key, refresh_key)

    with sqlite3.connect(DB_PATH) as conn:
        create_results_table(conn)
        df = fetch_papers(conn)
        done = {r[0] + r[1] for r in conn.execute("SELECT api, url FROM ocr_laterals")}
        print(f"{len(df)} files, {len(done)} already done")

        for i, (api, url) in enumerate(zip(df["api"], df["wellImagingFiles"]), 1):
            if api + url in done:
                continue
            try:
                data = load_paper(session, url)
            except PermissionError:
                main_key, refresh_key = login()
                session = session_auth(main_key, refresh_key)
                data = load_paper(session, url)

            if data is None:
                res = {"status": "download failed"}
            else:
                try:
                    with open_pdf(data) as (doc, plumb):
                        res = extract_lateral(doc, plumb)
                except (fitz.FileDataError, ValueError) as e:
                    res = {"status": f"bad pdf: {e}"}

            save_result(conn, api, url, res)
            if i % 25 == 0:
                conn.commit()
                print(f"{i}/{len(df)}")
        conn.commit()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_one(sys.argv[1])
    else:
        main()