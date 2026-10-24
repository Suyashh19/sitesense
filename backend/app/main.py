"""FastAPI service: exposes the AI engine to the React frontend.  Run: uvicorn app.main:app --reload --port 8000"""
import math
import os
import re
import threading
from contextlib import asynccontextmanager

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db
from .data import CITIES, DOMAINS, FEATURES, LABELS, make_city
from .model import WEIGHT_PRESETS, ExpansionModel, factor_cards, summary

_models: dict = {}
_lock = threading.Lock()  # cluster() mutates the cached model frame


@asynccontextmanager
async def lifespan(_):
    db.init()
    yield


app = FastAPI(title="Retail Expansion Intelligence API", lifespan=lifespan)
# Comma-separated list in CORS_ORIGINS to restrict; defaults to any origin (no cookies/credentials are used).
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])


class Params(BaseModel):
    city: str = "Pune"
    domain: str = "Luxury fashion boutique"
    n_stores: int = Field(60, ge=30, le=100)
    preset: str = "Balanced"
    weights: dict[str, float] | None = None
    max_rent: float = 250
    max_capex: float = 300
    min_units: int = Field(1, ge=0, le=5)
    min_own_km: float = 1.0
    min_sep_km: float = 3.0
    k: int = Field(5, ge=3, le=7)


class SimParams(Params):
    pick: int = 1
    extra_comp: int = 0
    rent_pct: float = 0
    own_km: float = 0


def clean(o):
    """Make numpy/pandas values JSON-safe (inf/nan -> None)."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def run_key(p: Params):
    return f"{p.city}|{p.domain}|{p.n_stores}"


def context(p: Params):
    if p.city not in CITIES or p.domain not in DOMAINS:
        raise HTTPException(400, "unknown city or domain")
    key = run_key(p)
    with _lock:
        if key not in _models:
            _models[key] = ExpansionModel(make_city(p.city, p.domain, p.n_stores), p.domain)
            db.save_zones(key, _models[key].df)
        m = _models[key]
        cl = m.cluster(p.k)
        weights = {**WEIGHT_PRESETS.get(p.preset, WEIGHT_PRESETS["Balanced"]), **(p.weights or {})}
        ranked = m.rank(weights, max_rent=p.max_rent, min_own_km=p.min_own_km, min_units=p.min_units, max_capex=p.max_capex)
        top = m.top_n(ranked, 5, p.min_sep_km) if not ranked.empty else ranked
        contrib = m.attribute(top) if not top.empty else None
        top = top.copy()
        zdf = m.df.copy()
    return m, cl, ranked, top, contrib, weights, zdf


def briefing(p, r, why, risks, n_viable):
    verdict = "a strong" if r["score"] >= 70 else "a solid" if r["score"] >= 45 else "a moderate"
    strip = lambda s: re.sub(r"\*\*", "", s.split(" -> ")[0])  # noqa: E731
    out = [f"Recommendation: open a {p.domain.lower()} in {r['zone_name']} ({p.city}). It is {verdict} choice "
           f"(suitability {r['score']:.0f}/100, rank {r['pick']} of {n_viable} viable zones).",
           f"Expected economics: sales ~Rs {r['pred_revenue']:.1f} L/month, profit ~Rs {r['profit']:.1f} L/month, "
           f"payback ~{r['payback_months']:.0f} months. In a pessimistic case (P10) profit is Rs {r['profit_p10']:+.1f} L/month."]
    if why:
        out.append("Main reasons: " + "; ".join(strip(w) for w in why) + ".")
    if risks:
        out.append("Watch out for: " + "; ".join(strip(x) for x in risks) + ".")
    return " ".join(out)


@app.get("/api/meta")
def meta():
    return {"cities": list(CITIES), "domains": [{"name": k, "icon": v["icon"]} for k, v in DOMAINS.items()],
            "presets": WEIGHT_PRESETS, "labels": LABELS, "db": {"engine": db.engine.dialect.name, "postgis": db.HAS_POSTGIS}}


@app.post("/api/analyze")
def analyze(p: Params):
    m, cl, ranked, top, contrib, weights, zdf = context(p)
    if ranked.empty:
        return {"empty": True, "message": "No commercially viable site satisfies your constraints. Relax rent, budget, vacancy or distance limits."}
    cand_n = int((~zdf.has_store).sum())
    tops = []
    for i, (idx, r) in enumerate(top.iterrows()):
        alt_idx = top.index[1] if i == 0 and len(top) > 1 else top.index[0]
        alt = top.loc[alt_idx] if alt_idx != idx else None
        head, why, risks, cmp = summary(m, r, contrib.loc[idx], alt, contrib.loc[alt_idx] if alt is not None else None)
        row = {c: r[c] for c in ["pick", "zone_id", "zone_name", "lat", "lon", "score", "pred_revenue", "rev_p10", "rev_p90", "profit",
                                 "profit_p10", "payback_months", "roi_pct", "archetype", "rent_psf", "vacant_units", "competitors_1km",
                                 "own_nearest_km", "population_k", "income_index", "novelty", "opex_lakh"]}
        tot = sum(weights.values())
        row["components"] = {k: 100 * weights[k] / tot * float(r[f"s_{k}"]) for k in weights}
        row["headline"] = head
        row["why"], row["risks"], row["comparison"] = why, risks, cmp
        row["cards"] = factor_cards(m, r, contrib.loc[idx])
        row["contrib"] = {LABELS[f]: float((np.exp(contrib.loc[idx, f]) - 1) * 100) for f in FEATURES}
        row["briefing"] = briefing(p, row, why, risks, len(ranked))
        tops.append(row)
    db.save_run(run_key(p), p.model_dump(), clean(tops))

    zcols = ["zone_id", "zone_name", "lat", "lon", "has_store", "profit", "pred_revenue", "competitors_1km", "rent_psf", "income_index",
             "population_k", "archetype", "pc1", "pc2", "vacant_units"]
    fit = cl["fit"].reset_index().rename(columns={"archetype": "name"})
    full = ranked[["rank", "zone_id", "zone_name", "archetype", "score", "pred_revenue", "profit", "profit_p10", "roi_pct", "rent_psf",
                   "competitors_1km", "own_nearest_km", "vacant_units"]]
    c = zdf[~zdf.has_store]
    return clean({
        "empty": False,
        "kpis": {"best_profit": tops[0]["profit"], "portfolio_profit": sum(t["profit"] for t in tops),
                 "avg_payback": float(np.mean([t["payback_months"] for t in tops])), "viable": len(ranked), "vacant": cand_n},
        "top": tops, "weights": weights, "half": {"lat": 0.5 / 110.6, "lon": 0.5 / (111.3 * np.cos(np.radians(zdf.lat.mean())))},
        "zones": zdf[zcols].round(3).to_dict("records"),
        "clusters": {"silhouette": cl["sil"], "fit": fit.round(2).to_dict("records"),
                     "radar": {"dims": [d.replace("_", " ") for d in cl["cols"]],
                               "series": [{"name": n, "values": [float(v) for v in row.values]} for n, row in cl["z"].iterrows()]}},
        "ranking": full.round(2).to_dict("records"),
        "model": {"metrics": m.metrics, "spearman": m.sanity_check(),
                  "coverage_80": float(c._true_rev.between(c.rev_p10, c.rev_p90).mean()),
                  "importance": [{"feature": LABELS[f], "value": float(v)} for f, v in m.importance.items()],
                  "cv": [{"actual": float(a), "pred": float(b)} for a, b in zip(m.cv_actual, m.cv_pred)],
                  "assumptions": {k: m.P[k] for k in ("size", "margin", "fixed", "capex")}},
    })


@app.post("/api/simulate")
def simulate(p: SimParams):
    m, _, _, top, _, _, _ = context(p)
    if top.empty:
        raise HTTPException(400, "no recommended sites")
    cs = top[top.pick == p.pick]
    if cs.empty:
        raise HTTPException(400, "pick not found")
    cs = cs.iloc[0]
    mc = m.monte_carlo(cs)
    counts, edges = np.histogram(mc["steady"], bins=40)
    pct = np.percentile(mc["cum"], [10, 50, 90], axis=0)
    own = p.own_km if p.own_km > 0 else None
    wi = m.what_if(cs, p.extra_comp, p.rent_pct, own)
    resil = []
    for idx, r in top.iterrows():
        w = m.what_if(r, p.extra_comp, p.rent_pct, own)
        resil.append({"pick": int(r.pick), "zone_name": r.zone_name, "base": r.profit, "scenario": w["profit"],
                      "change": w["profit"] - r.profit, "survives": w["profit"] > 0})
    return clean({
        "mc": {"p_profit": mc["p_profit"], "p_break_even": mc["p_break_even"], "be_median": mc["be_median"], "var5": mc["var5"], "roi24": mc["roi24"],
               "hist": [{"x": float((edges[i] + edges[i + 1]) / 2), "n": int(counts[i])} for i in range(len(counts))],
               "fan": [{"month": i + 1, "p10": float(pct[0][i]), "p50": float(pct[1][i]), "p90": float(pct[2][i])} for i in range(pct.shape[1])]},
        "base": {"rev": cs.pred_revenue, "profit": cs.profit, "profit_p10": cs.profit_p10},
        "scenario": {"rev": wi["rev"], "profit": wi["profit"], "profit_p10": wi["profit_p10"]}, "resilience": resil})


@app.get("/api/nearby")
def nearby(city: str, domain: str, n_stores: int, lat: float, lon: float, radius_km: float = 3.0):
    return clean(db.nearby_stores(f"{city}|{domain}|{n_stores}", lat, lon, radius_km))


@app.get("/api/history")
def history():
    return db.history()
