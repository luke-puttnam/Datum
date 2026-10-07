import pandas as pd
from data import emnrd_data as e

# 1. Login works
token, refresh = e.login()
session = e.session_auth(token, refresh)

# 2. One well, nothing written to the database
api = str(e.get_api().iloc[0]["APINumber"])[:-4]
params, link = e.parameters_link("perforations")
body = e.get_json(session, f"{link[0]}/{api}", params)
print("One well:", api, type(body))
print("Keys:", list(body.keys()))

# 3. Five wells through the real function, into a throwaway table
real_get_api = e.get_api
e.get_api = lambda: real_get_api().head(5)
e.emnrd_per_well(session, "perforations", table="test_perforations")

test = pd.read_sql("SELECT * FROM test_perforations", e.conn)
print("\nRows:", len(test), "Columns:", len(test.columns))
print(test.iloc[0])

# 4. Same shape as the data you already have?
real_cols = set(pd.read_sql("SELECT * FROM emnrd_perforations LIMIT 0", e.conn).columns)
print("\nOnly in test table:", set(test.columns) - real_cols)
print("Only in real table:", real_cols - set(test.columns))

# 5. Clean up
e.conn.execute("DROP TABLE test_perforations")
e.conn.commit()
e.conn.close()