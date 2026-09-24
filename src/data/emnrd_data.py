import requests
import os
import pandas as pd
import sqlite3
from clean import connect_server
from dotenv import load_dotenv
from sanity_check import wells_missing
import time

BASE = "https://api.emnrd.nm.gov/wda"
LOGIN_URL = f"{BASE}/v2/Authorization/Token/LoginCredentials"
load_dotenv()
conn = connect_server()
data_find = ["formation-tops", "production-injection", "linq", "perforations"]

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
    SELECT APINumber, DisclosureID FROM disclosures;
    """
    return pd.read_sql(query, conn)

def find_missing_water(session):
    water_df = wells_missing(conn)
    print(water_df)

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
        case _:
            raise ValueError("Invalid category passed in")
    return params, link


def emnrd_per_well(session, category, per_well=True):
    parameters, url = parameters_link(category)
    if per_well:
        frames = []
        for well in get_api().itertuples():
            api = str(well.APINumber)[:-4]
            # handle perforations
            if len(url) < 2:
                link = url[0]
                parameters["WellApi"] = api
            else:
                p1,p2 = url
                link = f"{p1}/{api}/{p2}"

            if parameters:
                resp = session.get(link, params=parameters)
            else:
                resp = session.get(link)
            time.sleep(0.2)
            resp.raise_for_status()
            body = resp.json()
            frames.append(pd.json_normalize(body))
        return pd.concat(frames, ignore_index=True)
    else:
        return pd.DataFrame()



if __name__ == "__main__":
    access_token, refresh_token = login()
    session_authent = session_auth(access_token, refresh_token)
    print("Login OK — access token prefix:", access_token[:20])
    print("Refresh token present:", bool(refresh_token))
    for val in data_find:
        cat = parameters_link(val)
        df = emnrd_per_well(session_authent, cat)
        print(df.shape)
        df.to_csv()

