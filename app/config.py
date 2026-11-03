import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'energy_monitoring.db'}")
DATA_DIR = BASE_DIR / "data"
