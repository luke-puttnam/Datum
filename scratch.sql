-- ============================================================================
-- Datum — DuckDB data pipeline
-- Layers:  raw  ->  staging  ->  core  ->  mart
--   raw     : source files landed as-is (no cleaning)
--   staging : one cleaned view per source (typed, API normalized, deduped)
--   core    : joined analysis tables (dims + facts)
--   mart    : single flat well-level view the model reads
--
-- Run:  duckdb datum.duckdb < datum_schema.sql
-- Swap the CSV paths below for your real downloads. Nothing downstream changes.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;

-- Reusable API-number normalizer: strip non-digits, take the 10-digit
-- state+county+well core so 10/12/14-digit forms join across sources.
CREATE OR REPLACE MACRO api10(x) AS
    substr(regexp_replace(CAST(x AS VARCHAR), '[^0-9]', '', 'g'), 1, 10);

-- ============================================================================
-- 1. RAW  — land files exactly as downloaded
-- ============================================================================
CREATE OR REPLACE TABLE raw.fracfocus AS
SELECT * FROM read_csv_auto('data/fracfocus_registry.csv', header = true);

CREATE OR REPLACE TABLE raw.completions AS
SELECT * FROM read_csv_auto('data/completions.csv', header = true);

-- Optional, only if you pull production (start with NM = well-level):
-- CREATE OR REPLACE TABLE raw.production AS
--     SELECT * FROM read_csv_auto('data/production_monthly.csv', header = true);

-- ============================================================================
-- 2. STAGING  — all cleaning lives here, one view per source
-- ============================================================================

-- FracFocus: dedup to one disclosure per well (latest job).
-- If you want to model refracs as separate events, drop the QUALIFY instead.
CREATE OR REPLACE VIEW staging.fracfocus AS
SELECT
    api10(APINumber)                          AS api,
    CAST(TotalBaseWaterVolume AS DOUBLE)      AS water_gal,   -- target
    CAST(TVD AS DOUBLE)                        AS tvd,
    TRY_CAST(JobStartDate AS DATE)             AS job_date,
    UPPER(TRIM(OperatorName))                  AS operator,
    CAST(Latitude  AS DOUBLE)                  AS lat,
    CAST(Longitude AS DOUBLE)                  AS lon,
    UPPER(TRIM(StateName))                     AS state
FROM raw.fracfocus
WHERE TotalBaseWaterVolume IS NOT NULL
  AND CAST(TotalBaseWaterVolume AS DOUBLE) BETWEEN 50000 AND 40000000  -- drop junk/outliers
        QUALIFY ROW_NUMBER() OVER (PARTITION BY api10(APINumber)
                           ORDER BY TRY_CAST(JobStartDate AS DATE) DESC) = 1;

-- Completions: the features FracFocus lacks. Column names vary by source —
-- rename to these canonical names in this view and the rest of the pipeline is stable.
CREATE OR REPLACE VIEW staging.completions AS
SELECT
    api10(APINumber)                          AS api,
    CAST(LateralLength AS DOUBLE)             AS lateral_ft,
    CAST(ProppantMass  AS DOUBLE)             AS proppant_lb,
    CAST(StageCount    AS INTEGER)            AS stages,
    UPPER(TRIM(Formation))                     AS formation
FROM raw.completions
    QUALIFY ROW_NUMBER() OVER (PARTITION BY api10(APINumber) ORDER BY api) = 1;

-- ============================================================================
-- 3. CORE  — joined analysis tables
-- ============================================================================
CREATE OR REPLACE TABLE core.dim_operator AS
SELECT DISTINCT operator FROM staging.fracfocus WHERE operator IS NOT NULL;

CREATE OR REPLACE TABLE core.fact_frac_job AS
SELECT
    f.api,
    f.water_gal,
    f.tvd,
    f.job_date,
    year(f.job_date)  AS job_year,
    f.operator,
    f.state,
    f.lat,
    f.lon
FROM staging.fracfocus f;

-- ============================================================================
-- 4. MART  — one row per well, target + features. This is what pandas reads.
-- ============================================================================
CREATE OR REPLACE VIEW mart.well_water AS
SELECT
    j.api,
    j.water_gal,          -- target
    j.tvd,
    j.job_year,
    j.state,
    j.operator,
    c.lateral_ft,         -- NULL until completions data is joined in
    c.proppant_lb,
    c.stages,
    c.formation
FROM core.fact_frac_job j
         LEFT JOIN staging.completions c USING (api);   -- LEFT so water rows survive before enrichment

-- Sanity checks — run after building
-- SELECT count(*) AS wells, count(lateral_ft) AS with_completion FROM mart.well_water;
-- SELECT state, median(water_gal) FROM mart.well_water GROUP BY state ORDER BY 2 DESC;