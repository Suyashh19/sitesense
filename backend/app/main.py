"""SiteSense API (FastAPI).  Run:  uvicorn app.main:app --port 8000

Serves the pipeline artifacts and the request-time engine. Nothing about a city, category, tag or parameter is hardcoded here:
all of it comes from backend/config/*.yaml and backend/data/artifacts (built by `python -m app.pipeline.build`).
"""
import math
import threading
import time
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db, llm
from .config import CORS_ORIGINS
from .engine import gravity, intent, optimise, service
from .engine.service import STRATEGIES, Request
from .engine.store import store

_job = {"running": False, "log": [], "error": None, "finished": None}
_lock = threading.Lock()
_heavy = threading.Lock()      # one heavy simulation at a time keeps memory bounded


@asynccontextmanager
async def lifespan(_):
    db.init()
    if store.ready:
        db.load_zones(store.base)
    yield


app = FastAPI(title="SiteSense - Retail Expansion Intelligence API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Near(BaseModel):
    lat: float
    lon: float
    radius_km: float = Field(3.0, ge=0.5, le=15)


class Overrides(BaseModel):
    margin: float | None = Field(None, ge=0.02, le=0.8)
    fixed_lakh: float | None = Field(None, ge=0.2, le=30)
    size_sqft: float | None = Field(None, ge=100, le=20000)
    spend_per_person: float | None = Field(None, ge=5, le=2000)


class AnalyzeParams(BaseModel):
    category: str
    budget_lakh: float | None = Field(None, ge=5, le=5000)
    max_rent_psf: float | None = Field(None, ge=20, le=1000)
    min_pop_1km: float = Field(0, ge=0, le=100000)
    strategy: str = "Balanced"
    brand_tier: str = "regional_chain"
    own_stores: list[Point] = []
    extra_competitors: list[Point] = []
    rent_change_pct: float = Field(0, ge=-30, le=100)
    n_results: int = Field(5, ge=1, le=10)
    min_spacing_km: float = Field(1.5, ge=0.3, le=6)
    keep_away_km: float = Field(0.8, ge=0, le=5)
    near: Near | None = None
    overrides: Overrides = Overrides()

    def to_request(self) -> Request:
        if self.category not in store.cats["categories"]:
            raise HTTPException(400, f"unknown category '{self.category}'")
        if self.strategy not in STRATEGIES:
            raise HTTPException(400, f"unknown strategy '{self.strategy}'")
        if self.brand_tier not in store.cats["tiers"]:
            raise HTTPException(400, f"unknown brand tier '{self.brand_tier}'")
        return Request(category=self.category, budget_lakh=self.budget_lakh, max_rent_psf=self.max_rent_psf, min_pop_1km=self.min_pop_1km,
                       strategy=self.strategy, brand_tier=self.brand_tier, own_stores=[(p.lat, p.lon) for p in self.own_stores],
                       extra_competitors=[(p.lat, p.lon) for p in self.extra_competitors], rent_change_pct=self.rent_change_pct,
                       n_results=self.n_results, min_spacing_km=self.min_spacing_km, keep_away_km=self.keep_away_km,
                       near=(self.near.lat, self.near.lon, self.near.radius_km) if self.near else None,
                       overrides=self.overrides.model_dump(exclude_none=True))


class ZoneParams(AnalyzeParams):
    h3: str


class ScenarioParams(AnalyzeParams):
    """The base ranking uses the fields above; the scenario adds the changes below on top of them."""
    new_rent_change_pct: float = Field(0, ge=-30, le=100)
    new_competitors: list[Point] = []


class PlanParams(AnalyzeParams):
    k: int = Field(3, ge=2, le=6)
    total_budget_lakh: float | None = Field(None, ge=10, le=20000)


class AskParams(BaseModel):
    text: str = Field(min_length=3, max_length=400)


class BriefingParams(AnalyzeParams):
    rank: int = Field(1, ge=1)


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def need_data():
    if not store.ready:
        raise HTTPException(503, "The data pipeline has not been run yet. Open 'Data & pipeline' and press Build, or run: python -m app.pipeline.build")


def limits(model: type[BaseModel]):
    out = {}
    for k, v in model.model_json_schema()["properties"].items():
        d = {x: v[x] for x in ("default", "minimum", "maximum") if x in v}
        for alt in v.get("anyOf", []):
            d.update({x: alt[x] for x in ("minimum", "maximum") if x in alt})
        out[k] = d
    return out


# ------------------------------------------------------------------------------------------------ meta
@app.get("/api/health")
def health():
    return {"ok": True, "data_ready": store.ready}


@app.get("/api/meta")
def meta():
    c = store.cats
    city = store.city
    out = {"ready": store.ready, "city": {"name": city.name, "bbox": city.bbox, "h3_resolution": city.h3_resolution,
                                         "localities": [{"name": l["name"], "lat": l["lat"], "lon": l["lon"]} for l in city.localities]},
           "categories": [{"key": k, "name": v["name"], "icon": v["icon"], "blurb": v["blurb"], "dna": v["dna"], "behaviour": v["behaviour"]["type"],
                           "defaults": {"size_sqft": v["econ"]["size_sqft"], "margin": v["econ"]["margin"], "fixed_lakh": v["econ"]["fixed_lakh"],
                                        "spend_per_person": v["econ"]["spend_per_person"]}}
                          for k, v in c["categories"].items()],
           "factor_groups": c["factor_groups"], "strategies": STRATEGIES, "tiers": c["tiers"], "limits": limits(AnalyzeParams),
           "db": {"engine": db.engine.dialect.name, "postgis": db.HAS_POSTGIS}, "llm_provider": llm.provider_label(), "dna_version": c["version"]}
    if store.ready:
        u = store.base.urban.values
        out["center"] = [float(store.base.lat.values[u].mean()), float(store.base.lon.values[u].mean())]
    return out


@app.get("/api/pipeline")
def pipeline_status():
    return {"ready": store.ready, "status": store.status if store.ready else None, "job": {k: _job[k] for k in ("running", "error", "finished")},
            "log": _job["log"][-60:]}


def _run_build():
    from .pipeline import build
    try:
        build.run(log=lambda m: _job["log"].append(m))
        store.load()
        db.load_zones(store.base)
        _job["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:  # noqa: BLE001
        _job["error"] = f"{type(e).__name__}: {e}"
    finally:
        _job["running"] = False


@app.post("/api/pipeline/run")
def pipeline_run():
    with _lock:
        if _job["running"]:
            return {"started": False, "message": "A build is already running."}
        _job.update(running=True, log=[], error=None)
    threading.Thread(target=_run_build, daemon=True).start()
    return {"started": True}


# ------------------------------------------------------------------------------------------------ analysis
@app.get("/api/layer/{category}")
def layer(category: str):
    need_data()
    if category not in store.cat:
        raise HTTPException(404, "unknown category")
    return clean(service.layer(category))


@app.post("/api/analyze")
def analyze(p: AnalyzeParams):
    need_data()
    with _heavy:
        r = service.analyse(p.to_request())
    if not r["empty"]:
        db.save_run(p.category, p.model_dump(), r["top"], r["model_used"])
    return clean(r)


@app.get("/api/zone/{h3_id}")
def zone(h3_id: str, category: str):
    need_data()
    try:
        return clean(service.zone_profile(h3_id, category))
    except KeyError:
        raise HTTPException(404, "zone not found") from None


@app.post("/api/economics")
def economics(p: ZoneParams):
    need_data()
    try:
        with _heavy:
            return clean(service.zone_economics(p.to_request(), p.h3))
    except KeyError:
        raise HTTPException(404, "zone not found") from None


@app.post("/api/scenario")
def scenario(p: ScenarioParams):
    """What-if (F-15): the same ranking with a rent change and/or new rivals; reports who moved."""
    need_data()
    base_req = p.to_request()
    scen_req = p.to_request()
    scen_req.rent_change_pct = p.rent_change_pct + p.new_rent_change_pct
    scen_req.extra_competitors = base_req.extra_competitors + [(q.lat, q.lon) for q in p.new_competitors]
    with _heavy:
        a, b = service.analyse(base_req), service.analyse(scen_req)
    if a["empty"] or b["empty"]:
        return clean({"empty": True, "message": (a if a["empty"] else b)["message"]})
    pos_a = {t["h3"]: t for t in a["top"]}
    rows = []
    for t in b["top"]:
        o = pos_a.get(t["h3"])
        rows.append({"h3": t["h3"], "name": t["name"], "rank_after": t["rank"], "rank_before": o["rank"] if o else None,
                     "profit_before": o["profit"]["p50"] if o else None, "profit_after": t["profit"]["p50"], "survives": t["profit"]["p50"] > 0})
    after = {x["h3"] for x in b["top"]}
    dropped = [{"name": t["name"], "rank_before": t["rank"]} for t in a["top"] if t["h3"] not in after]
    return clean({"empty": False, "before": a["top"], "after": b["top"], "rows": rows, "dropped": dropped})


@app.post("/api/plan")
def plan(p: PlanParams):
    """Expansion plan (F-14): which k sites to open together, with cannibalisation, via CP-SAT (M-9)."""
    need_data()
    req = p.to_request()
    req.n_results, req.min_spacing_km = 25, 0.4
    with _heavy:
        r = service.analyse(req)
    if r["empty"]:
        return clean({"feasible": False, "message": r["message"]})
    cat = store.category(p.category)
    a = gravity.Assumptions.from_config(cat, store.city.estimates, store.cats["tiers"], p.brand_tier, **req.overrides)
    mk = gravity.Market(store.grid, store.base.eff_pop.values, store.base.affluence.values, store.cat[p.category].attr_here.values, a)
    cands = [{"z": store.grid.index[t["h3"]], "h3": t["h3"], "name": t["name"], "lat": t["lat"], "lon": t["lon"], "profit_p50": t["profit"]["p50"],
              "rev_p50": t["revenue"]["p50"], "upfront": t["upfront_lakh"], "confidence": t["confidence"], "band": t["band"], "boi": t["boi"]}
             for t in r["top"]]
    res = optimise.plan(mk, store.grid, cands, p.k, p.total_budget_lakh or p.budget_lakh, p.min_spacing_km)
    return clean(res | {"candidates_considered": len(cands)})


@app.post("/api/ask")
def ask(p: AskParams):
    """Natural-language request (M-11): parsed into a whitelisted tool call and executed; the interpretation is echoed back."""
    need_data()
    parsed = intent.parse(p.text)
    if not parsed["grounded"]:
        return clean(parsed | {"result": None})
    a = parsed["args"]
    body = {k: v for k, v in a.items() if k in ("category", "budget_lakh", "max_rent_psf", "strategy", "n_results")}
    if "near" in a:
        body["near"] = {k: a["near"][k] for k in ("lat", "lon", "radius_km")}
    if parsed["tool"] == "plan_expansion":
        res = plan(PlanParams(**body, k=a.get("k", 3)))
    else:
        res = analyze(AnalyzeParams(**body))
    return clean(parsed | {"result": res, "request": body})


@app.post("/api/briefing")
def briefing(p: BriefingParams):
    """One-paragraph briefing for a pick. Text is assembled from computed facts; an LLM (if configured) may only rephrase it."""
    need_data()
    with _heavy:
        r = service.analyse(p.to_request())
    if r["empty"] or p.rank > len(r["top"]):
        raise HTTPException(400, "no such recommendation")
    t = r["top"][p.rank - 1]
    cat = store.category(p.category)
    text = (f"Open a {cat['name'].lower()} store near {t['name']}. Expected profit is about Rs {t['profit']['p50']:.1f} lakh a month "
            f"(realistic range Rs {t['profit']['p10']:.1f} to {t['profit']['p90']:.1f} lakh), with sales of about Rs {t['revenue']['p50']:.1f} lakh. "
            f"Main reasons: " + "; ".join(d["text"] for d in t["drivers"]) + ". Watch out for: " + "; ".join(x["text"] for x in t["risks"]) +
            f". Confidence: {t['confidence']}.")
    if llm.active_provider():
        out = llm.generate("Rewrite this retail site recommendation for a shop owner in 4-5 plain sentences. Use ONLY the facts and numbers given; "
                           "add none. No markdown.", text)
        if out:
            return {"text": out, "source": llm.provider_label()}
    return {"text": text, "source": "template"}


@app.get("/api/nearby")
def nearby(lat: float, lon: float, radius_km: float = 1.0):
    need_data()
    return clean(db.zones_near(lat, lon, radius_km))


@app.get("/api/history")
def history():
    return clean(db.history())


@app.get("/api/dna")
def dna():
    c = store.cats
    return {"version": c["version"], "factor_groups": c["factor_groups"],
            "categories": {k: {"name": v["name"], "icon": v["icon"], "dna": v["dna"], "behaviour": v["behaviour"]["type"],
                               "complementors": v["complementors"], "chains": v["chains"]} for k, v in c["categories"].items()}}
