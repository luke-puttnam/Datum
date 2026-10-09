from data.config import RAW_DIR


if __name__ == "__main__":
    for f in sorted(RAW_DIR.rglob("*.csv")):
        print(f.name, f.stat().st_size // 1_000_000, "MB")
