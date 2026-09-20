import sqlite3
import pandas as pd

conn = sqlite3.connect("datum.db")
df = pd.read_sql("select * from frac_nm", conn)
conn.close()

