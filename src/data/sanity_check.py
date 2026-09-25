import pandas as pd
from clean import connect_server

def general(connection):
    query = """
            SELECT COUNT(*)
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
            SELECT APINumber, TotalBaseWaterVolume
            FROM disclosures
            GROUP BY APINumber
            HAVING MAX(COALESCE(TotalBaseWaterVolume, 0)) = 0; \
            """
    return pd.read_sql(query, connection)

def find_missing_tbwv(connection):
    query = """
            WITH missing AS (
                SELECT APINumber,
                       MIN(CAST(substr(JobStartDate, instr(JobStartDate, ' ') - 4, 4) AS INTEGER)) AS first_year
                FROM disclosures
                GROUP BY APINumber
                HAVING MAX(COALESCE(TotalBaseWaterVolume, 0)) = 0
            )
            SELECT first_year AS year, COUNT(*) AS n_wells
            FROM missing
            GROUP BY first_year
            ORDER BY first_year; \
            """
    return pd.read_sql(query, connection)

def check_distinct(connection):
    query = """
    SELECT COUNT(DISTINCT APINumber) FROM disclosures;
    """
    return pd.read_sql(query, connection)

def merge_dist(connection):
    query = """
    SELECT APINumber,
        COUNT(*) AS n_disclosures,
        COUNT(DISTINCT JobStartDate) As n_dates,
        COUNT(DISTINCT TotalBaseWaterVolume) AS n_volumes
    FROM disclosures
    GROUP BY APINumber
    HAVING COUNT(*) > 1
    """
    return pd.read_sql(query, connection)


def missing_water_2020(connection):
    query = """
    SELECT APINumber, DisclosureID, TotalBaseWaterVolume,
        CAST(substr(JobStartDate, instr(JobStartDate, ' ') - 4, 4) AS INTEGER) AS year
    FROM disclosures
    WHERE year > 2020
        AND (TotalBaseWaterVolume IS NULL OR TotalBaseWaterVolume = 0)
    ORDER BY year;
    """
    return pd.read_sql(query, connection)

def check_2(connection):
    query = """
    SELECT JobStartDate, strftime('%Y', JobStartDate) AS year
    FROM disclosures
    LIMIT 5
    """
    return pd.read_sql(query, connection)

if __name__ == "__main__":
    conn = connect_server()
    print(general(conn))
    print(check_2(conn))
    # print(general(conn))
    # df = find_missing_tbwv(conn)
    # print(df)
    print(check_distinct(conn).iloc[0, 0])
    # print(missing_rows(conn))
    # print(wells_missing(conn))
    conn.close()
