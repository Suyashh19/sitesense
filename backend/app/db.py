"""Persistence + spatial queries.

PostgreSQL/PostGIS when DATABASE_URL=postgresql+psycopg://user:pass@host/db is set (geometry column, GiST index, ST_DWithin).
Otherwise a local SQLite file is used so the project runs with zero setup (spatial queries fall back to haversine).
Tables: zones (one row per H3 cell, loaded from the pipeline artifacts), analysis_runs (history of every ranking, F-10 AC-10.4).
"""
import json
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, Text, create_engine, text

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, future=True)
IS_PG = engine.dialect.name == "postgresql"
HAS_POSTGIS = False

meta = MetaData()
zones = Table("zones", meta, Column("h3", String(20), primary_key=True), Column("lat", Float), Column("lon", Float),
              Column("archetype", String(40)), Column("pop_1km", Float), Column("rent_psf", Float))
runs = Table("analysis_runs", meta, Column("id", Integer, primary_key=True, autoincrement=True), Column("created_at", DateTime),
             Column("category", String(40)), Column("params", Text), Column("top", Text), Column("model_used", String(80)))


def init():
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


def load_zones(df):
    """(Re)load the zone table from the pipeline output."""
    cols = ["h3", "lat", "lon", "archetype", "pop_1km", "rent_psf"]
    rows = df[cols].astype(object).where(df[cols].notna(), None).to_dict("records")
    with engine.begin() as c:
        c.execute(text("DELETE FROM zones"))
        c.execute(zones.insert(), rows)
        if HAS_POSTGIS:
            c.execute(text("UPDATE zones SET geom=ST_SetSRID(ST_MakePoint(lon,lat),4326)"))


def save_run(category: str, params: dict, top: list, model_used: str):
    slim = [{k: t[k] for k in ("rank", "h3", "name", "fit_score", "boi", "confidence")} | {"profit_p50": t["profit"]["p50"]} for t in top]
    with engine.begin() as c:
        c.execute(runs.insert().values(created_at=datetime.now(timezone.utc).replace(tzinfo=None), category=category,
                                       params=json.dumps(params, default=str), top=json.dumps(slim), model_used=model_used))


def history(limit=12):
    with engine.connect() as c:
        rows = c.execute(text("SELECT id, created_at, category, params, top, model_used FROM analysis_runs ORDER BY id DESC LIMIT :n"),
                         {"n": limit}).mappings().all()
    return [dict(id=r["id"], created_at=str(r["created_at"]), category=r["category"], params=json.loads(r["params"]),
                 top=json.loads(r["top"]), model_used=r["model_used"]) for r in rows]


def zones_near(lat: float, lon: float, radius_km: float = 1.0, limit: int = 20):
    """Zones within radius_km of a point, nearest first (PostGIS ST_DWithin when available)."""
    if HAS_POSTGIS:
        q = text("""SELECT h3, archetype, pop_1km,
                    ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography)/1000 AS km
                    FROM zones WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, :r)
                    ORDER BY km LIMIT :n""")
        with engine.connect() as c:
            return [dict(r) for r in c.execute(q, {"lat": lat, "lon": lon, "r": radius_km * 1000, "n": limit}).mappings()]
    with engine.connect() as c:
        rows = c.execute(text("SELECT h3, lat, lon, archetype, pop_1km FROM zones")).mappings().all()
    la, lo = np.array([r["lat"] for r in rows]), np.array([r["lon"] for r in rows])
    p1, p2 = np.radians(lat), np.radians(la)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lo - lon) / 2) ** 2
    km = 2 * 6371 * np.arcsin(np.sqrt(a))
    return [dict(h3=rows[i]["h3"], archetype=rows[i]["archetype"], pop_1km=rows[i]["pop_1km"], km=float(km[i]))
            for i in np.argsort(km)[:limit] if km[i] <= radius_km]
