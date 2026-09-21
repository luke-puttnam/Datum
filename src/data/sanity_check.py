import pandas as pd
from clean import connect_server

def general(connection):
    query = """
            SELECT COUNT(*) AS disclosures
            FROM disclosures
            WHERE StateName = "New Mexico"; \
            """
    return pd.read_sql(query, connection)

def summary(connection):
    query = """
            SELECT COUNT(*) AS disclosures,
                   SUM(CASE WHEN TotalBaseWaterVolume IS NULL OR TotalBaseWaterVolume = 0 THEN 1 ELSE 0 END) AS missing
            FROM disclosures; \
            """
    return pd.read_sql(query, connection)

def missing_rows(connection):
    query = """
            SELECT APINumber, JobStartDate, StateName, CountyName, TotalBaseWaterVolume
            FROM disclosures
            WHERE TotalBaseWaterVolume IS NULL OR TotalBaseWaterVolume = 0
            ORDER BY APINumber; \
            """
    return pd.read_sql(query, connection)

def wells_missing(connection):
    query = """
            SELECT APINumber
            FROM disclosures
            GROUP BY APINumber
            HAVING MAX(COALESCE(TotalBaseWaterVolume, 0)) = 0; \
            """
    return pd.read_sql(query, connection)

if __name__ == "__main__":
    conn = connect_server()
    print(general(conn))
    # print(summary(conn))
    # print(missing_rows(conn))
    # print(wells_missing(conn))
    conn.close()
