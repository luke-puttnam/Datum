import requests
import os
import pandas as pd
import time
import gzip
import json
import zlib
import brotli
import urllib3.exceptions

from data.clean import connect_server
from pathlib import Path
from dotenv import load_dotenv
from urllib3.util.retry import Retry

BASE = "https://api.emnrd.nm.gov/wda"
LOGIN_URL = f"{BASE}/v2/Authorization/Token/LoginCredentials"
load_dotenv()
conn = connect_server()
data_find = ["formation-tops", "production-injection", "perforations"]

retry = Retry(total=5, backoff_factor=1,
              status_forcelist=[429, 500, 502, 503, 504],
              allowed_methods=["GET"])

def login():
    resp = requests.post(LOGIN_URL, json={
        "UserName": os.environ["EMNRD_USER"],
        "Password": os.environ["EMNRD_PASS"],
    })
    resp.raise_for_status()
    body = resp.json()
    print(f'Top level keys:', list(body.keys()))
    return body["accessToken"], body["refreshToken"]

def session_auth(acc_token, ref_token, use_access = True):
    token = acc_token if use_access else ref_token
    session = requests.session()
    session.headers.update({
        "Authorization": f"Bearer {token}"
    })
    return session

def get_api():
    query = """
            SELECT DISTINCT(APINumber) FROM disclosures; \
            """
    return pd.read_sql(query, conn)

def get_json(session, link, params, retries=3):
    for attempt in range(retries):
        resp = session.get(
            link,
            params=params,
            headers={"Accept-Encoding": "identity"},
            stream=True,
            timeout=30
        )
        resp.raise_for_status()
        raw = resp.raw.read(decode_content=False)

        for decode in (lambda b: b, brotli.decompress, gzip.decompress,
                       lambda b: zlib.decompress(b, -zlib.MAX_WBITS)):
            try:
                return json.loads(decode(raw))
            except (requests.RequestException, urllib3.exceptions.HTTPError) as e:
                wait = 5 * 2 ** attempt
                print(f'request failed ({e}), retrying in {wait}s ({attempt + 1}/{retries})')
                time.sleep(wait)
                continue
            except (brotli.error, OSError, zlib.error,
                    json.JSONDecodeError, UnicodeDecodeError):
                continue
        print(f"couldn't decode response for {params}, retrying ({attempt + 1}/{retries}")
        time.sleep(2)
    raise RuntimeError(f"failed to decode for {params}")



def fetch_all_water_uses(session):
    link = "https://api.emnrd.nm.gov/wda/v2/ocd/permitting/water-uses"
    frames = []
    page = 1

    while True:
        resp = session.get(link,
                           params={"PageIndex": page},
                           headers={"Accept-Encoding": "identity"},
                           timeout=30)
        resp.raise_for_status()
        body = get_json(session, link, {"pageIndex": page})

        frames.append(pd.DataFrame(body["items"]))
        print(f"page {page} of {body['totalPages']}")

        if page >= body["totalPages"]:
            break
        page += 1
        time.sleep(0.2)

    nm_df = pd.concat(frames, ignore_index=True)
    nm_df.to_csv("nm_water_uses.csv", index=False)
    return nm_df

def to_nm_api(api):
    if pd.isna(api):
        return None
    s = str(api).split(".")[0]
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) in (12, 14):
        digits = digits[:10]
    digits = digits.zfill(10)
    return f"{digits[:2]}-{digits[2:5]}-{digits[5:]}"

def parameters_link(category):
    match category:
        case "formation-tops":
            params = {"IncludeFormationTops": "true", "IncludeHistory": "true", "IncludePointOfDispositions": "true"}
            link = ["https://api.emnrd.nm.gov/wda/v2/ocd/permitting/well", "formation-tops"]
        case "production-injection":
            params = None
            link = ["https://api.emnrd.nm.gov/wda/v2/ocd/permitting/well", "production-injection"]
        case "water-uses":
            params = {"api_number": None}
            link = ["https://api.emnrd.nm.gov/wda/v2/ocd/permitting/water_uses"]
        case "perforations":
            params = {"IncludeCompletions": True, "IncludeFormationTops": True,
                      "IncludeCasings": True, "IncludeWellProductionInjection": True}
            link = ["https://api.emnrd.nm.gov/wda/v2/ocd/permitting/wells"]
        case "linq":
            params = {"IncludeDetailedData": "true", "ExcludePluggedWells": "false",
                      "LINQFilterExpression": None}
            link = ["https://api.emnrd.nm.gov/wda/v2/ocd/permitting/wells/linq"]
        case _:
            raise ValueError("Invalid category passed in")
    return params, link

def get_page(session, link, params, page, cache_dir):
    cache = cache_dir / f'page{page:04d}.json'
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    data = get_json(session, link, dict(params, PageIndex=page))
    cache.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.8)
    return data

def linq_by_county(session, out_dir = "linq_counties.csv"):
    base_params, link = parameters_link("linq")
    PAGE_SIZE = 250
    if isinstance(link, list):
        link = link[0]

    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    counties = [f"30-{n:03d}" for n in range(1, 62, 2)] + ["30-006", "30-028"] # all 33 NM counties
    failed_pages = []

    for county in counties:
        path = out / f"{county}.csv"
        if path.exists() and path.stat().st_size > 0:
            print(f"{county} already done, skipping")
            continue

        params = dict(base_params)
        params.update({
            "LINQFilterExpression": f'WellApi.StartsWith("{county}")',
            "IncludeDetailedData": True,
            "ExcludePluggedWells": False,
            "PageSize": PAGE_SIZE,
        })

        cache_dir = out / f"{county}_pages_{PAGE_SIZE}"
        cache_dir.mkdir(exist_ok=True)

        rows = []
        page, total_pages = 1, 1
        complete = True

        while page <= total_pages:
            try:
                print(f'County: {county}; trying to get page, {page}/{total_pages}', flush=True)
                data = get_page(session, link, params, page, cache_dir)
            except Exception as e:
                print(f"{county} page {page} failed: {e}")
                failed_pages.append((county, page))
                complete = False
                break
            total_pages = data["totalPages"]
            rows.extend(data["items"])
            print(f'{county} page {page}/{total_pages}', flush=True)
            page += 1

        if not complete:
            print(f'{county} incomplete, not saved. Rerun to retry')
            continue

        if rows:
            df = pd.json_normalize(rows)
            for c in df.columns:
                if df[c].apply(lambda x: isinstance(x, (list, dict))).any():
                    df[c] = df[c].apply(lambda x: json.dumps(x) if isinstance(x, (list, dict)) else x)
            df.to_csv(path, index=False)
        else:
            path.touch()

    parts = [pd.read_csv(p, low_memory=False) for p in sorted(out.glob("*.csv")) if p.stat().st_size > 0]
    full = pd.concat(parts, ignore_index=True)
    try:
        old_count = conn.execute("""
                                 SELECT COUNT(*) FROM emnrd_linq
                                 """).fetchone()[0]
    except:
        old_count = 0

    if len(full) < old_count:
        raise RuntimeError(
            f'new table has {len(full)} wells but the existing one has {old_count}; not replacing'
        )
    full.to_sql("emnrd_linq", conn, if_exists="replace", index=False)

    pd.DataFrame(failed_pages, columns=["county", "page"]).to_csv("linq_failed.csv", index=False)
    print(f"{len(full)} wells saved, {len(failed_pages)} pages failed")
    return full, failed_pages

def emnrd_per_well(session, category, table = None, batch_size=300):
    table = table or f'emnrd_{category}'
    parameters, url = parameters_link(category)
    try:
        done = set(pd.read_sql(f"SELECT DISTINCT _api FROM {table}", conn)["_api"])
    except Exception:
        done = set()
    print(f'{len(done)} wells already in {table}', flush=True)
    frames = []
    failed = []
    fails_ina_row = 0
    for well in get_api().itertuples():
        api = str(well.APINumber)[:-4]
        if api in done:
            continue
        params = dict(parameters) if parameters else {}
        if len(url) < 2:
            if category.lower() == "perforations":
                link = f'{url[0]}/{api}'
            else:
                link = url[0]
                params["WellApi"] = api
        else:
            p1,p2 = url
            link = f"{p1}/{api}/{p2}"
        try:
            print(f'Sending get request for {category}. API: {api}')
            body = get_json(session, link, params or None)
            df = pd.json_normalize(body)
            if category == "perforations":
                for c in df.columns:
                    if df[c].apply(lambda x: isinstance(x, (list, dict))).any():
                        df[c] = df[c].apply(lambda x: json.dumps(x) if isinstance(x, (list, dict)) else x)
            df["_api"] = api
            frames.append(df)
            fails_ina_row = 0
        except Exception as e:
            print(f'failed for {category}, api {api}: {e}', flush=True)
            failed.append((api, str(e)))
            fails_ina_row += 1
            if fails_ina_row >= 20:
                print(f'20 failures in a row, stopping')
                break
        time.sleep(0.2)

        if len(frames) >= batch_size:
            append_frames(frames, table, conn)
            frames = []
    if frames:
        append_frames(frames, table, conn)
    if failed:
        pd.DataFrame(failed, columns=["api", "error"]).to_csv(
            f'failed_{category}.csv', index=False
        )
        print(f'{len(failed)} wells failed; check failed_{category}.csv')

def try_filter(session, link, base_params, expr):
    p = dict(base_params)
    p.update({"LINQFilterExpression": expr, "IncludeDetailedData": True,
              "ExcludePluggedWells": False, "PageSize": 500, "PageIndex": 1})
    r = session.get(link, params=p, timeout=60)
    print(r.status_code, len(r.url), r.text[:200])

def append_frames(frames, table, conn):
    df = pd.concat(frames, ignore_index=True).astype(str)
    existing = {r[1].lower() for r in conn.execute(f'PRAGMA table_info("{table}")')}
    if existing:   # table already exists: add any columns it's missing
        for col in df.columns:
            if col.lower() not in existing:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" TEXT')
    df.to_sql(table, conn, if_exists="append", index=False)

def main():
    access_token, refresh_token = login()
    session_authentication = session_auth(access_token, refresh_token)
    full, failed_pages = linq_by_county(session_authentication)
    ALREADY_DONE = ["formation-tops", "production-injection"]
    for cat in data_find:
        if cat in set(ALREADY_DONE):
            continue
        emnrd_per_well(session_authentication, cat)
    nm_df = fetch_all_water_uses(session_authentication)
    conn.close()

if __name__ == "__main__":
    main()