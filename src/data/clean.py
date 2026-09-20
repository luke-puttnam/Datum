import pandas as pd
from ingest import  RAW
import sqlite3

nm_df = pd.DataFrame()
nm_disc_df = pd.DataFrame()
FRAC = RAW / "FracFocusCSV"

def connect_server():
    connection = sqlite3.connect("datum.db")
    return connection

def gather(file_name, disc=False):
    df = pd.read_csv(file_name, low_memory=False)
    df["APINumber"] = df["APINumber"].astype(str).str.replace("-", "").str.strip()
    mask = df["StateName"].str.contains("new mexico", case=False, na=False)
    if disc:
        mask &= df["TotalBaseWaterVolume"].notna()
    return df[mask]

def duplicate_check(df):
    df = df.drop_duplicates(subset=['DisclosureId'])
    return df

def to_sqlite(connection, df, table):
    df.to_sql(table, connection, if_exists="replace", index=False)

def check_database(connection, table):
    print(f"--- {table} ---")
    print(pd.read_sql(f"SELECT COUNT(*) FROM {table}", connection))
    print(pd.read_sql(f"SELECT * FROM {table} LIMIT 5", connection))

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

if __name__ == "__main__":
    conn = connect_server()
    for f in FRAC.iterdir():
        if f.suffix.lower() != ".csv":
            continue
        if "FracFocusRegistry" in f.name:
            nm_df = pd.concat([nm_df, gather(f)], ignore_index=True)          # registry -> nm_df
        elif "DisclosureList" in f.name:
            nm_disc_df = pd.concat([nm_disc_df, gather(f, True)], ignore_index=True)  # header -> nm_disc_df
            nm_disc_df = duplicate_check(nm_disc_df)

    print("nm_df:", nm_df.shape)
    print("nm_disc_df:", nm_disc_df.shape)

    to_sqlite(conn, nm_df, "frac_nm")
    to_sqlite(conn, nm_disc_df, "disclosures")
    check_database(conn, "frac_nm")
    check_database(conn, "disclosures")
    conn.close()
    # result = join(conn)
    # print(result.shape)
    # print(result.head())
