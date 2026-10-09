import pandas as pd
from dotenv import load_dotenv
from data import emnrd_data as e
from data.clean import connect_server
from data.config import ENV_PATH

load_dotenv(ENV_PATH)
conn = connect_server()

# 1. Login works
token, refresh = e.login()
session = e.session_auth(token, refresh)

# 2. One well, nothing written to the database
api = str(e.get_api(conn).iloc[0]["APINumber"])[:-4]
params, link = e.parameters_link("perforations")
body = e.get_json(session, f"{link[0]}/{api}", params)
print("One well:", api, type(body))
print("Keys:", list(body.keys()))

# 3. Five wells through the real function, into a throwaway table
real_get_api = e.get_api
e.get_api = lambda c: real_get_api(c).head(5)
e.emnrd_per_well(session, conn, "perforations", table="test_perforations")

test = pd.read_sql("SELECT * FROM test_perforations", conn)
print("\nRows:", len(test), "Columns:", len(test.columns))
print(test.iloc[0])

# 4. Same shape as the data you already have?
real_cols = set(pd.read_sql("SELECT * FROM emnrd_perforations LIMIT 0", conn).columns)
print("\nOnly in test table:", set(test.columns) - real_cols)
print("Only in real table:", real_cols - set(test.columns))

# 5. Clean up
conn.execute("DROP TABLE test_perforations")
conn.commit()
conn.close()