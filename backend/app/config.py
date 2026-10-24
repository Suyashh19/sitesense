"""Runtime settings, read from the environment. A `.env` file in the project root is loaded if present (never commit it)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./retail.db")
# Comma-separated list to restrict; defaults to any origin (no cookies/credentials are used).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
