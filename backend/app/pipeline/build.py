"""Orchestrates the offline pipeline:  ingest -> prepare -> features -> models -> economics -> artifacts.

    python -m app.pipeline.build            # use cached raw downloads when present
    python -m app.pipeline.build --refresh  # re-download OpenStreetMap data

Artifacts land in backend/data/artifacts and are what the API serves. `status.json` records every stage, its source,
counts and time, which the app shows on its 'Data & pipeline' page (data lineage, F-18).
"""
import json
import sys
import time
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from .. import catalog
from ..config import DATA_DIR
from ..engine import gravity, learn, rent, scoring
from . import features, growth, osm, population
from .grid import build_grid, percentile

ART = DATA_DIR / "artifacts"


def run(log=print, refresh=False):
    t0 = time.time()
    ART.mkdir(parents=True, exist_ok=True)
    city, cats = catalog.city(), catalog.categories()
    status = {"city": city.name, "started": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stages": []}

    def stage(name, detail, **kw):
        status["stages"].append({"name": name, "detail": detail, "seconds": round(time.time() - t0, 1), **kw})
        log(f"[{name}] {detail}")

    log("Stage 1/6  Ingest: OpenStreetMap")
    frames = osm.fetch_all(city, cats, log, refresh)
    stage("Ingest OpenStreetMap", f"{sum(len(f) for f in frames.values()):,} map features fetched in {len(frames)} queries",
          source="OpenStreetMap contributors (ODbL) via Overpass API", real=True)
    log("Stage 2/6  Ingest: WorldPop")
    tif = population.download(city.worldpop_url, log)
    stage("Ingest WorldPop", f"population raster {tif.name}", source="WorldPop 2020, 1 km (CC BY 4.0)", real=True)

    log("Stage 3/6  Prepare: H3 grid + zone features")
    grid = build_grid(city.bbox, city.h3_resolution)
    base = features.city_features(city, cats, grid, frames, tif, log)
    stage("H3 grid", f"{grid.n:,} hexagons at resolution {grid.res} ({grid.area_km2 * 100:.1f} ha each); {int(base.urban.sum()):,} analysed", real=True)

    g = growth.block_growth(base.h3.tolist(), log=log)
    if g:
        raw = np.array([g.get(__import__("h3").cell_to_parent(c, 7), np.nan) for c in base.h3])
        raw = np.where(np.isnan(raw), np.nanmedian(raw), raw)
        base["growth"] = percentile(grid.within(raw, 1.5) / np.maximum(grid.within(np.ones(grid.n), 1.5), 1), base.urban.values)
        base["growth_real"] = True
        stage("Growth trend", f"{len(g)} blocks from the ohsome API (2021 to 2026)", source="ohsome API (HeiGIT), OSM history", real=True)
    else:
        base["growth"], base["growth_real"] = 50.0, False
        stage("Growth trend", "ohsome unreachable - neutral value used and flagged", real=False)

    log("Stage 4/6  Rent model (M-1)")
    r = rent.fit_predict(city, grid, base)
    base[["rent_psf", "rent_p10", "rent_p90"]] = r["rent"][["rent_psf", "rent_p10", "rent_p90"]]
    stage("Rent model M-1", f"CatBoost on {r['metrics']['n_localities']} locality reference rents; leave-one-locality-out error "
          f"{100 * r['metrics']['loo_mape']:.0f}% vs {100 * r['metrics']['baseline_mape']:.0f}% for price x yield", real=False,
          source="curated locality prices (estimate)")

    log("Stage 5/6  Zone archetypes (M-6)")
    arch = learn.archetypes(base, base.urban.values)
    base["archetype"], base["archetype_margin"] = arch["archetype"], arch["margin"]
    stage("Archetypes M-6", f"6 zone types, silhouette {arch['silhouette']:.2f}", real=False)

    log("Stage 6/6  Per-category factors, BOI, learned models, economics")
    pois = features.unique_pois(frames)
    urban = base.urban.values
    meta = {"categories": {}}
    models = {}
    for key, cat in cats["categories"].items():
        log(f"  - {cat['name']}")
        cf = features.category_features(grid, base, pois, cat, cats["tiers"])
        fs = scoring.factor_scores(base, cf, cat)
        bo = scoring.boi(fs, cat)
        X = pd.concat([base, cf], axis=1)
        L = learn.viability_and_rank(X, cf, base.h3.tolist(), urban, bo.boi.fillna(0).values, log)
        a = gravity.Assumptions.from_config(cat, city.estimates, cats["tiers"])
        mk = gravity.Market(grid, base.eff_pop.values, base.affluence.values, cf.attr_here.values, a)
        zi = np.where(urban)[0]
        rent_lakh = base.rent_psf.values[zi] * a.size_sqft / 1e5
        sig = np.log(base.rent_p90.values[zi] / np.maximum(base.rent_p10.values[zi], 1e-6)) / 2.563
        eco = gravity.Market.summarise(mk.simulate(zi, rent_lakh, draws=120, rent_sigma=sig))
        eco.index = zi
        out = pd.concat([cf, fs.add_prefix("s_"), bo], axis=1)
        out = out.join(eco)
        out["upfront_lakh"] = mk.upfront_lakh(base.rent_psf.values * a.size_sqft / 1e5)
        if L.get("enabled"):
            out["viability"], out["rank_score"] = L["viability"], L["rank_score"]
            out["rank_pct"] = percentile(np.nan_to_num(L["rank_score"], nan=-9), urban & ~np.isnan(L["rank_score"]))
            out["label_graded"], out["label_pos"] = L["graded"], L["positives"]
        out.to_parquet(ART / f"cat_{key}.parquet")
        features.competitors(pois, cat, cats["tiers"])[["lat", "lon", "name", "brand", "tier", "attr"]].to_parquet(ART / f"comps_{key}.parquet")
        if L.get("enabled"):
            models[key] = {k: L[k] for k in ("ranker", "pu_models", "c", "feats")}
        meta["categories"][key] = {
            "labels": L["labels"], "enabled": bool(L.get("enabled")), "reason": L.get("reason"),
            "m2": L.get("m2_metrics"), "m3": L.get("m3_metrics"), "importance": L.get("importance"),
            "competitors": int((cf.comp_here).sum()), "chains": int(cf.chain_here.sum()),
            "median_profit_lakh": float(eco.profit_p50.median()), "viable_share": float((eco.profit_p50 > 0).mean())}
        stage(f"Models: {cat['name']}", f"{int(cf.comp_here.sum())} competitors mapped; "
              + (f"{L['labels']['positives']} positive zones ({L['labels']['source']})" if L.get("enabled") else L["reason"]))

    base.to_parquet(ART / "zones.parquet")
    metro = pd.DataFrame(city.metro_stations).assign(kind="metro")
    rail = frames["railway"].assign(kind="rail")[["lat", "lon", "name", "kind"]] if len(frames["railway"]) else metro.iloc[0:0]
    pd.concat([metro, rail], ignore_index=True).to_parquet(ART / "transit.parquet")
    joblib.dump(models, ART / "models.joblib")
    joblib.dump(arch["centroids"], ART / "archetypes.joblib")
    meta.update(rent=r["metrics"], archetype_silhouette=arch["silhouette"], grid={"zones": grid.n, "analysed": int(urban.sum()), "res": grid.res},
                osm_counts={k: len(v) for k, v in frames.items()}, config_version=cats["version"])
    status.update(finished=datetime.now(timezone.utc).isoformat(timespec="seconds"), seconds=round(time.time() - t0, 1), meta=meta)
    (ART / "status.json").write_text(json.dumps(status, indent=2, default=float), encoding="utf-8")
    log(f"Done in {time.time() - t0:.0f}s. Artifacts in {ART}")
    return status


if __name__ == "__main__":
    run(refresh="--refresh" in sys.argv)
