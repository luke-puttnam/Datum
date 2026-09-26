import os
from pathlib import Path

class Config:
    def __init__(
            self,
            data_dir=Path("data"),
            raw_dir=Path("data/raw"),
            processed_dir=Path("data/processed"),
            state="New Mexico",
            counties=("Eddy", "Lea"),
            start_year=2014,
            end_year=2025,
            nm_api_base="https://...",
            nm_api_key="",
            request_timeout=30,
            random_seed=42,
            test_size=0.2,
    ):
        if not 0 < test_size < 1:
            raise ValueError("test_size must be between 0 and 1")

        self.data_dir = data_dir
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
        self.state = state
        self.counties = counties
        self.start_year = start_year
        self.end_year = end_year
        self.nm_api_base = nm_api_base
        self.nm_api_key = nm_api_key
        self.request_timeout = request_timeout
        self.random_seed = random_seed
        self.test_size = test_size

    @classmethod
    def load(cls):
        return cls(nm_api_key=os.environ.get("NM_API_KEY", ""))