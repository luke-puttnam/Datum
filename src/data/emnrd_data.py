import requests
import os
import pandas as pd
import time
import gzip
import json
import zlib
import brotli
import sqlite3
from pathlib import Path
from requests.exceptions import ContentDecodingError

from clean import connect_server
from dotenv import load_dotenv
from sanity_check import missing_water_2020
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://api.emnrd.nm.gov/wda"
LOGIN_URL = f"{BASE}/v2/Authorization/Token/LoginCredentials"
load_dotenv()
conn = connect_server()
data_find = ["formation-tops", "production-injection", "linq", "perforations"]

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
    SELECT DISTINCT(APINumber) FROM disclosures;
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
    s = str(api).split(".")[0]
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) in (12, 14):      # FracFocus-style with sidetrack/event
        digits = digits[:10]
    digits = digits.zfill(10)        # pad only up to 10, not 14
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
            params = {"IncludeDetailedData": "true", "WellApi": None}
            link = ["https://api.emnrd.nm.gov/wda/v2/ocd/permitting/wells"]
        case "linq":
            params = {"IncludeDetailedData": "true", "ExcludePluggedWells": "false",
                      "LINQFilterExpression": None}
            link = ["https://api.emnrd.nm.gov/wda/v2/ocd/permitting/wells/linq"]
        case _:
            raise ValueError("Invalid category passed in")
    return params, link


def linq_by_county(session, out_dir = "linq_counties.csv", db_path = "datum.db"):
    base_params, link = parameters_link(session)
    if isinstance(link, list):
        link = link[0]

    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    counties = [f"30-{n:03d}" for n in range(1, 62, 2)]   # all 33 NM counties
    failed_pages = []

    for county in counties:
        path = out / f"{county}.csv"
        if path.exists():
            print(f"{county} already done, skipping")
            continue

        params = dict(base_params)
        params.update({
            "LINQFilterExpression": f'WellApi.StartsWith("{county}")',
            "IncludeDetailedData": True,
            "ExcludePluggedWells": False,
            "PageSize": 500,
        })

        rows, page, total_pages = [], 1, 1
        while page <= total_pages:
            params["PageIndex"] = page
            try:
                r = session.get(link, params=params, timeout=120)
                r.raise_for_status()
                data = r.json()
                total_pages = data["totalPages"]
                rows.extend(data["items"])
                print(f"{county} page {page}/{total_pages}")
            except Exception as e:
                print(f"{county} page {page} failed: {e}")
                failed_pages.append((county, page))
            page += 1
            time.sleep(0.5)

        if rows:
            df = pd.json_normalize(rows)
            for c in df.columns:
                if df[c].apply(lambda x: isinstance(x, (list, dict))).any():
                    df[c] = df[c].apply(lambda x: json.dumps(x) if isinstance(x, (list, dict)) else x)
            df.to_csv(path, index=False)
        else:
            path.touch()

    parts = [pd.read_csv(p) for p in sorted(out.glob("*.csv")) if p.stat().st_size > 0]
    full = pd.concat(parts, ignore_index=True)
    with sqlite3.connect(db_path) as conn:
        full.to_sql("emnrd_linq", conn, if_exists="replace", index=False)

    pd.DataFrame(failed_pages, columns=["county", "page"]).to_csv("linq_failed.csv", index=False)
    print(f"{len(full)} wells saved, {len(failed_pages)} pages failed")
    return full, failed_pages


# def linq(session):
#     if session is None:
#         raise ValueError("Missing session")
#
#     BATCH_SIZE = 50
#     PAGE_SIZE = 500
#
#     base_params, url = parameters_link("linq")
#     if isinstance(url, list):
#         url = url[0]
#
#     raw = get_api()
#     apis = sorted(set(raw["APINumber"].apply(to_nm_api)))
#
#     frames = []
#     failed = []
#
#     for i in range(0, len(apis), BATCH_SIZE):
#         #batch = apis[i:i + BATCH_SIZE]
#         batch = apis[:100]
#         params = dict(base_params)
#         params.update({
#             "LINQFilterExpression": " or ".join(f'WellApi = "{a}"' for a in batch),
#             "IncludeDetailedData": True,
#             "ExcludePluggedWells": False,
#             "PageSize": PAGE_SIZE,
#         })
#
#         page = 1
#         try:
#             while True:
#                 params["PageIndex"] = page
#                 r = session.get(url, params=params, timeout=60)
#                 r.raise_for_status()
#                 records = r.json()
#                 if records:
#                     frames.append(pd.json_normalize(records))
#                 if len(records) < PAGE_SIZE:
#                     break
#                 page += 1
#         except Exception as e:
#             print(f"Batch {i // BATCH_SIZE} failed {e}")
#             failed.extend(batch)
#         time.sleep(0.5)
#
#     df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
#     failed_df = pd.DataFrame({"api": failed})
#     failed_df.to_csv("linq_failed.csv")
#
#     if df.empty:
#         print(f'No data returned. {len(failed)} APIs failed.')
#         return df, failed_df
#
#     list_cols = [
#         c for c in df.columns
#         if df[c].apply(lambda x: isinstance(x, (list, dict))).any()
#     ]
#     print("Nested columns", list_cols)
#
#     for c in list_cols:
#         df[c] = df[c].apply(lambda x: json.dumps(x) if isinstance(x, (list, dict)) else x)
#
#     df.to_csv("linq_success.csv", index=False)
#     df.to_sql("emnrd_linq", conn, if_exists="replace", index=False)
#     return df, failed

def emnrd_per_well(session, category, table = None, batch_size=300):
    table = table or f'emnrd_{category}'
    parameters, url = parameters_link(category)
    try:
        done = set(pd.read_sql(f"SELECT DISTINCT _api FROM {table}", conn)["_api"])
    except Exception:
        done = set()
    frames = []
    failed = []
    for well in get_api().itertuples():
        api = str(well.APINumber)[:-4]
        if api in done:
            continue

        params = dict(parameters) if parameters else {}
        if len(url) < 2:
            link = url[0]
            params["WellApi"] = api
        else:
            p1,p2 = url
            link = f"{p1}/{api}/{p2}"
        try:
            print(f'Sending get request for {category}.')
            body = get_json(session, link, params or None)
            df = pd.json_normalize(body)
            df["_api"] = api
            frames.append(df)
        except Exception as e:
            print(f'failed for {category}')
            failed.append((api, str(e)))
        time.sleep(0.2)

        if len(frames) >= batch_size:
            pd.concat(frames, ignore_index=True).astype(str).to_sql(
                table, conn, if_exists="append", index=False
            )
            frames = []
    if frames:
        pd.concat(frames, ignore_index=True).astype(str).to_sql(
            table, conn, if_exists="append", index=False)
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


def main():
    access_token, refresh_token = login()
    session_authentication = session_auth(access_token, refresh_token)
    session_authentication.mount("https://", HTTPAdapter(max_retries=retry))
    # has_run = False
    # if has_run:
    #     water_df = missing_water_2020(conn)
    #     water_df["wellApi"] = water_df["APINumber"].apply(to_nm_api)
    #     nm_df = fetch_all_water_uses(session_authentication)
    #     merged = water_df.merge(nm_df, on="wellApi", how="left")
    #     merged.to_csv("check.csv", index=False)
    #     print(f'{merged["totalWater"].notna().sum()} of {len(merged)} wells matched')
    #
    # print("Starting!")
    # for cat in data_find:
    #     emnrd_per_well(session_authentication, cat, True)
    #     if cat == "linq":
    #         linq(session_authentication)
    # print("Done")

    full, failed_pages = linq_by_county(session_authentication)

    conn.close()


if __name__ == "__main__":
    main()


    # print("Login OK — access token prefix:", access_token[:20])
    # print("Refresh token present:", bool(refresh_token))
    # for val in data_find:
    #     cat = parameters_link(val)
    #     df = emnrd_per_well(session_authent, cat)
    #     print(df.shape)
    #     df.to_csv()

