import requests
import os
import pandas as pd
import sqlite3
from clean import connect_server
from dotenv import load_dotenv

BASE = "https://api.emnrd.nm.gov"
LOGIN_URL = f"{BASE}/wda/v2/Authorization/Token/LoginCredentials"
load_dotenv()

def login():
    resp = requests.post(LOGIN_URL, json={
        "UserName": os.environ["EMNRD_USER"],
        "Password": os.environ["EMNRD_PASS"],
    })
    resp.raise_for_status()
    body = resp.json()
    print(f'Top level keys:', list(body.keys()))
    return body["accessToken"], body["refreshToken"]

if __name__ == "__main__":
    access_token, refresh_token = login()
    print("Login OK — access token prefix:", access_token[:20])
    print("Refresh token present:", bool(refresh_token))
