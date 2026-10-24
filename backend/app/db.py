"""Persistence + spatial queries.

PostgreSQL/PostGIS when DATABASE_URL=postgresql+psycopg://user:pass@host/db is set (geometry column, GiST index,
ST_DWithin / ST_Distance). Otherwise a local SQLite file is used so the project runs with zero setup
(spatial queries then fall back to a haversine formula).
"""
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import (Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, Text, create_engine, text)

URL = os.getenv("DATABASE_URL", "sqlite:///./retail.db")
engine = create_engine(URL, future=True)
IS_PG = engine.dialect.name == "postgresql"
HAS_POSTGIS = False

meta = MetaData()
zones = Table("zones", meta,
              Column("run_key", String(120), index=True), Column("zone_id", String(10)), Column("zone_name", String(60)),
              Column("lat", Float), Column("lon", Float), Column("has_store", Boolean), Column("population_k", Float),
              Column("income_index", Float), Column("rent_psf", Float), Column("competitors_1km", Integer),
              Column("vacant_units", Integer), Column("pred_revenue", Float), Column("profit", Float))
runs = Table("recommendation_runs", meta,
             Column("id", Integer, primary_key=True, autoincrement=True), Column("created_at", DateTime),
             Column("run_key", String(120)), Column("params", Text), Column("top5", Text))


def init():
    """Create tables; enable PostGIS (geometry + GiST index) when available."""
    global HAS_POSTGIS
    meta.create_all(engine)
    if IS_PG:
        try:
            with engine.begin() as c:
                c.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
                c.execute(text("ALTER TABLE zones ADD COLUMN IF NOT EXISTS geom geometry(Point,4326)"))
                c.execute(text("CREATE INDEX IF NOT EXISTS zones_geom_gix ON zones USING GIST (geom)"))
            HAS_POSTGIS = True
        except Exception as e:  # noqa: BLE001
            print("PostGIS unavailable, using plain SQL:", e)


def save_zones(run_key: str, df: pd.DataFrame):
    with engine.begin() as c:
        if c.execute(text("SELECT 1 FROM zones WHERE run_key=:k LIMIT 1"), {"k": run_key}).first():
            c.execute(text("DELETE FROM zones WHERE run_key=:k"), {"k": run_key})
        cols = ["zone_id", "zone_name", "lat", "lon", "has_store", "population_k", "income_index", "rent_psf",
                "competitors_1km", "vacant_units", "pred_revenue", "profit"]
        rows = df[cols].astype(object).where(df[cols].notna(), None).to_dict("records")
        for r in rows:
            r.update(run_key=run_key, has_store=bool(r["has_store"]))
        c.execute(zones.insert(), rows)
        if HAS_POSTGIS:
            c.execute(text("UPDATE zones SET geom=ST_SetSRID(ST_MakePoint(lon,lat),4326) WHERE run_key=:k"), {"k": run_key})


def save_run(run_key: str, params: dict, top: list):
    with engine.begin() as c:
        c.execute(runs.insert().values(created_at=datetime.now(timezone.utc).replace(tzinfo=None), run_key=run_key,
                                       params=json.dumps(params), top5=json.dumps(top)))


def history(limit=10):
    with engine.connect() as c:
        rows = c.execute(text("SELECT id, created_at, run_key, params, top5 FROM recommendation_runs ORDER BY id DESC LIMIT :n"),
                         {"n": limit}).mappings().all()
    return [dict(id=r["id"], created_at=str(r["created_at"]), run_key=r["run_key"], params=json.loads(r["params"]),
                 top5=[t["zone_name"] for t in json.loads(r["top5"])]) for r in rows]


def nearby_stores(run_key: str, lat: float, lon: float, radius_km: float = 3.0):
    """Our existing stores within radius_km of a point, nearest first."""
    if HAS_POSTGIS:
        q = text("""SELECT zone_name, lat, lon,
                    ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography)/1000 AS km
                    FROM zones WHERE run_key=:k AND has_store AND
                    ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, :r)
                    ORDER BY km""")
        with engine.connect() as c:
            return [dict(r) for r in c.execute(q, {"k": run_key, "lat": lat, "lon": lon, "r": radius_km * 1000}).mappings()]
    with engine.connect() as c:
        rows = c.execute(text("SELECT zone_name, lat, lon FROM zones WHERE run_key=:k AND has_store"), {"k": run_key}).mappings().all()
    out = []
    for r in rows:  # haversine
        p1, p2 = np.radians(lat), np.radians(r["lat"])
        a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(r["lon"] - lon) / 2) ** 2
        km = float(2 * 6371 * np.arcsin(np.sqrt(a)))
        if km <= radius_km:
            out.append(dict(zone_name=r["zone_name"], lat=r["lat"], lon=r["lon"], km=km))
    return sorted(out, key=lambda x: x["km"])
