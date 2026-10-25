"""Loads the pipeline artifacts into memory once and exposes them to the API."""
import json
from threading import Lock

import joblib
import numpy as np
import pandas as pd

from .. import catalog
from ..config import DATA_DIR
from ..pipeline.grid import Grid, build_grid

ART = DATA_DIR / "artifacts"


class Store:
    def __init__(self):
        self.lock = Lock()
        self.ready = False
        self.load()

    def load(self):
        self.city, self.cats = catalog.city(), catalog.categories()
        if not (ART / "status.json").exists():
            self.ready = False
            return
        self.status = json.loads((ART / "status.json").read_text(encoding="utf-8"))
        self.grid: Grid = build_grid(self.city.bbox, self.city.h3_resolution)
        self.base = pd.read_parquet(ART / "zones.parquet")
        assert list(self.base.h3) == self.grid.cells, "artifacts do not match the grid - re-run the pipeline"
        self.cat = {k: pd.read_parquet(ART / f"cat_{k}.parquet") for k in self.cats["categories"] if (ART / f"cat_{k}.parquet").exists()}
        self.comps = {k: pd.read_parquet(ART / f"comps_{k}.parquet") for k in self.cat if (ART / f"comps_{k}.parquet").exists()}
        self.models = joblib.load(ART / "models.joblib") if (ART / "models.joblib").exists() else {}
        self.arch_centroids = joblib.load(ART / "archetypes.joblib") if (ART / "archetypes.joblib").exists() else None
        self.transit = pd.read_parquet(ART / "transit.parquet") if (ART / "transit.parquet").exists() else pd.DataFrame(columns=["lat", "lon", "name"])
        self.ready = True

    def category(self, key: str) -> dict:
        if key not in self.cats["categories"]:
            raise KeyError(key)
        return self.cats["categories"][key]


store = Store()
