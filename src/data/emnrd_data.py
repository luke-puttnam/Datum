import requests
import os
import pandas as pd
import sqlite3
from clean import connect_server
from dotenv import load_dotenv
from sanity_check import missing_rows
import time

BASE = "https://api.emnrd.nm.gov/wda"
LOGIN_URL = f"{BASE}/v2/Authorization/Token/LoginCredentials"
load_dotenv()
conn = connect_server()

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

def well_formation():
    sessions = session_auth(access_token, refresh_token)
    frames = []
    for well in get_api().itertuples():
        api = str(well.APINumber)[:-4]
        url = f"{BASE}/v2/ocd/permitting/well/"
        url += api
        time.sleep(0.2)
        resp = sessions.get(url)
        resp.raise_for_status()
        body = resp.json()
        frames.append(pd.json_normalize(body))
    return pd.concat(frames, ignore_index=True)

def find_missing_tbwv(connection):
    df = missing_rows(connection)


if __name__ == "__main__":
    access_token, refresh_token = login()
    print(well_formation())
    print("Login OK — access token prefix:", access_token[:20])
    print("Refresh token present:", bool(refresh_token))

