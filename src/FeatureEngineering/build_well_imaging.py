import sqlite3
from data.config import DB_PATH

def create_imaging_table(conn):
    conn.execute("DROP TABLE IF EXISTS imaging_links;")
    conn.execute("""
    CREATE TABLE imaging_links AS
    SELECT DISTINCT
        m.api,
        p.wellImagingFiles
    FROM model_base AS m
             LEFT JOIN emnrd_perforations AS p
                       ON SUBSTR(REPLACE(p.wellApi, '-', ''), 1, 10)
                           = SUBSTR(REPLACE(m.api,     '-', ''), 1, 10)
    WHERE m.md_minus_tvd IS NULL
      AND (m.api LIKE '30025%' OR m.api LIKE '30015%'
        OR m.api LIKE '30-025%' OR m.api LIKE '30-015%'); \
                 """
    )
    conn.commit()

    n_wells, n_missing = conn.execute("""
                                      SELECT COUNT(DISTINCT api),
                                             SUM(wellImagingFiles IS NULL)
                                      FROM imaging_links;
                                      """).fetchone()
    print(f"imaging_links: {n_wells} wells, {n_missing} rows without a link")

def main():
    with sqlite3.connect(DB_PATH) as conn:
        create_imaging_table(conn)

if __name__ == "__main__":
    main()