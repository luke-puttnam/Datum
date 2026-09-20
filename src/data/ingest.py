from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW = PROJECT_ROOT / "Data" / "Raw"
raw = Path("data/raw")

if __name__ == "__main__":
    for f in sorted(RAW.rglob("*.csv")):
        print(f.name, f.stat().st_size // 1_000_000, "MB")


