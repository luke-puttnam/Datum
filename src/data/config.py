"""Shared paths, constants and settings for Datum. Lives in src/data."""
import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------- Paths ----------
DATA_DIR = Path(__file__).resolve().parent          # src/data
PROJECT_ROOT = DATA_DIR.parents[1]                  # Datum/
DB_PATH = DATA_DIR / "datum.db"
LINQ_DIR = DATA_DIR / "linq_counties.csv"           # folder of per-county LINQ pulls
ENV_PATH = PROJECT_ROOT / ".env"
RAW_DIR = PROJECT_ROOT / "Data" / "Raw"
FRACFOCUS_DIR = RAW_DIR / "FracFocusCSV"

# ---------- Constants ----------
NM_COUNTIES = {
    "001": "Bernalillo", "003": "Catron", "005": "Chaves", "006": "Cibola",
    "007": "Colfax", "009": "Curry", "011": "De Baca", "013": "Dona Ana",
    "015": "Eddy", "017": "Grant", "019": "Guadalupe", "021": "Harding",
    "023": "Hidalgo", "025": "Lea", "027": "Lincoln", "028": "Los Alamos",
    "029": "Luna", "031": "McKinley", "033": "Mora", "035": "Otero",
    "037": "Quay", "039": "Rio Arriba", "041": "Roosevelt", "043": "Sandoval",
    "045": "San Juan", "047": "San Miguel", "049": "Santa Fe", "051": "Sierra",
    "053": "Socorro", "055": "Taos", "057": "Torrance", "059": "Union",
    "061": "Valencia",
}

FF_TABLE = "frac_nm"
LINQ_TABLE = "emnrd_linq"
OUT_TABLE = "model_base"

LINQ_API_COL = "WellApi"
LINQ_TVD_COL = "DpthTvdNum"
LINQ_MD_COL = "DpthMvdNum"
LINQ_SPUD_COL = "SpudDate"
LINQ_TGT_COL = "DpthTgtNum"                    # permitted target depth, known before the frac
LINQ_FORMATION_COL = "PropFmDescription"       # proposed formation, free text from the permit

# The counties the model covers.
COUNTY_CODES = {"015": "EDDY", "025": "LEA"}   # API county code -> FracFocus county name
MIN_JOB_DATE = "2011-01-01"                    # FracFocus began collecting disclosures in 2011

# FracFocus columns that describe the job (they repeat on every ingredient row).
# JobEndDate and TotalBaseNonWaterVolume are left out on purpose: both are only
# known after the job, so they would leak the target.
FF_JOB_COLS = [
    "DisclosureId", "JobStartDate", "APINumber", "CountyName", "OperatorName",
    "WellName", "Latitude", "Longitude", "TVD", "TotalBaseWaterVolume",
    "FederalWell", "IndianWell",
]

# What the training script should use.
TARGET = "log_water"
FEATURES = [
    "tvd_ft", "md_minus_tvd", "is_horizontal", "Latitude", "Longitude",
    "OperatorName", "CountyName", "job_year", "days_spud_to_frac",
    "job_number", "days_since_prev_job", "is_refrac",
    "FederalWell", "IndianWell", "target_formation", "target_top_depth",
    "fluid_system", "is_fr", "is_gel", "is_xlink",
]
CATEGORICAL = ["OperatorName", "CountyName", "target_formation", "fluid_system"]

# ---------- Settings ----------
@dataclass(frozen=True)
class APIConfig:
    base_url: str = "https://api.emnrd.nm.gov/wda/v2/ocd/permitting"
    page_size: int = 250
    timeout: int = 30
    sleep_between: float = 0.2
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)

    @classmethod
    def load(cls):
        """Credentials come from the environment (.env), never from this file."""
        return cls(
            username=os.environ.get("EMNRD_USER", ""),
            password=os.environ.get("EMNRD_PASS", ""),
        )

