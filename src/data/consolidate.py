import sqlite3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from debugpy.adapter import access_token

from emnrd_data import login, session_auth

conn = sqlite3.connect("datum.db")

# use for future applications (map all information about a certain well to its disclosure information).
# def join(connection):
#     q = """
#         SELECT d.APINumber, d.TotalBaseWaterVolume, d.CountyName,
#                i.IngredientCommonName, i.MassIngredient
#         FROM disclosures d
#                  JOIN frac_nm i ON d.DisclosureId = i.DisclosureId
#         WHERE i.IngredientCommonName = 'Hydrochloric acid'
#         """
#     return pd.read_sql(q, connection)

def join_wells():
    raise NotImplementedError("thign")


# OLD LINQ
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