"""Runtime settings, read from the environment. A `.env` file in the project root is loaded if present (never commit it)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BACKEND / 'data' / 'sitesense.db').as_posix()}")
# Comma-separated list to restrict; defaults to any origin (no cookies/credentials are used).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
CONFIG_DIR = Path(os.getenv("CONFIG_DIR", BACKEND / "config"))
DATA_DIR = Path(os.getenv("DATA_DIR", BACKEND / "data"))
CITY = os.getenv("CITY", "pune")
