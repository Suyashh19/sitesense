"""Request-time engine: constraints -> ranking (F-10) -> economics (F-08) -> explanation (F-11) -> scenarios (F-15) -> plan (F-14)."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..pipeline.grid import haversine, percentile
from . import gravity, learn, scoring
from .store import store

STRATEGIES = {   # weights over: opportunity (learned + index), expected profit, downside safety, confidence
    "Balanced": {"opportunity": .35, "profit": .30, "downside": .20, "confidence": .15},
    "Maximise profit": {"opportunity": .15, "profit": .60, "downside": .15, "confidence": .10},
    "Play it safe": {"opportunity": .20, "profit": .15, "downside": .40, "confidence": .25},
    "Best market fit": {"opportunity": .60, "profit": .15, "downside": .10, "confidence": .15},
}
CANDIDATE_POOL = 220


@dataclass
class Request:
    category: str
    budget_lakh: float | None = None
    max_rent_psf: float | None = None
    min_pop_1km: float = 0.0
    strategy: str = "Balanced"
    brand_tier: str = "regional_chain"
    own_stores: list = field(default_factory=list)          # [(lat, lon)]
    extra_competitors: list = field(default_factory=list)   # [(lat, lon)] scenario: new rival opens
    rent_change_pct: float = 0.0
    n_results: int = 5
    min_spacing_km: float = 1.5
    keep_away_km: float = 0.8                                # min distance from our existing stores
    near: tuple | None = None                                # (lat, lon, radius_km) restrict search area
    overrides: dict = field(default_factory=dict)            # margin, fixed_lakh, size_sqft, spend_per_person


def _own_attr(grid, stores, mult):
    a = np.zeros(grid.n)
    for la, lo in stores:
        i = grid.locate(la, lo)
        if i >= 0:
            a[i] += mult
    return a


def _scenario_features(S, key, req, cf: pd.DataFrame):
    """Apply scenario changes (new rivals) to the competitor terms; returns a modified copy of the category frame."""
    cf = cf.copy()
    if req.extra_competitors:
        add = np.zeros(S.grid.n)
        for la, lo in req.extra_competitors:
            i = S.grid.locate(la, lo)
            if i >= 0:
                add[i] += 1.0
        cf["attr_here"] = cf["attr_here"] + add
        cf["comp_here"] = cf["comp_here"] + add
        for col, r in (("comp_n500", .5), ("comp_n1km", 1.0), ("comp_n2km", 2.0), ("comp_nonchain_500", .5), ("comp_nonchain_1km", 1.0),
                       ("comp_nonchain_count_1km", 1.0), ("comp_count_1km", 1.0)):
            cf[col] = cf[col] + S.grid.within(add, r)
    return cf


def analyse(req: Request) -> dict:
    S = store
    cat = S.category(req.category)
    base, g = S.base, S.grid
    cf0 = S.cat[req.category]
    scen = bool(req.extra_competitors)
    urban = base.urban.values
    # --- the category frame (precomputed), possibly modified by a scenario
    cf = _scenario_features(S, req.category, req, cf0) if scen else cf0
    if scen:
        fs = scoring.factor_scores(base, cf, cat)
        bo = scoring.boi(fs, cat)
        cf = cf.copy()
        for c in fs.columns:
            cf["s_" + c] = fs[c]
        cf["boi"], cf["band"] = bo.boi, bo.band
    boi_v = cf["boi"].values.astype(float)

    # --- learned ranker (M-3) score; in a scenario add the full-fit model's change to the out-of-fold score
    enabled = req.category in S.models and "rank_score" in cf0
    rank_pct = np.full(g.n, np.nan)
    if enabled:
        rs = cf0["rank_score"].values.copy()
        if scen:
            m = S.models[req.category]
            def pred(frame):
                X = pd.concat([base, frame], axis=1)[learn.MODEL_FEATURES].values.astype(float)
                v = np.nan_to_num(frame["viability"].values, nan=0.0)
                return m["ranker"].predict(np.c_[X, v])
            rs = rs + (pred(cf.assign(viability=cf0["viability"])) - pred(cf0))
        rank_pct = percentile(np.nan_to_num(rs, nan=-9), urban & ~np.isnan(rs))
        opp = np.where(np.isnan(rank_pct), boi_v, 0.5 * rank_pct + 0.5 * percentile(np.nan_to_num(boi_v), urban))
    else:
        opp = percentile(np.nan_to_num(boi_v), urban)

    # --- hard constraints (BR-03, F-10)
    rent_mult = 1 + req.rent_change_pct / 100
    rent_psf = base.rent_psf.values * rent_mult
    mask = urban.copy()
    reasons = {"analysed zones": int(mask.sum())}
    if req.min_pop_1km:
        mask &= base.pop_1km.values >= req.min_pop_1km
        reasons["enough residents nearby"] = int(mask.sum())
    if req.max_rent_psf:
        mask &= rent_psf <= req.max_rent_psf
        reasons["rent within your cap"] = int(mask.sum())
    if req.own_stores and req.keep_away_km > 0:
        own_ll = np.array(req.own_stores)
        mask &= g.nearest_km(own_ll[:, 0], own_ll[:, 1]) >= req.keep_away_km
        reasons["away from your existing stores"] = int(mask.sum())
    if req.near:
        mask &= haversine(g.lat, g.lon, req.near[0], req.near[1]) <= req.near[2]
        reasons["inside the chosen area"] = int(mask.sum())

    a = gravity.Assumptions.from_config(cat, S.city.estimates, S.cats["tiers"], req.brand_tier, **req.overrides)
    rent_lakh_all = rent_psf * a.size_sqft / 1e5
    upfront = a.fitout_psf * a.size_sqft / 1e5 + a.inventory_lakh + a.deposit_months * rent_lakh_all
    cheapest = float(upfront[mask].min()) if mask.any() else None
    if req.budget_lakh:
        mask &= upfront <= req.budget_lakh
        reasons["upfront cost within budget"] = int(mask.sum())
    if not mask.any():
        msg = _binding(reasons)
        if req.budget_lakh and cheapest is not None and not (mask.any()) and reasons.get("upfront cost within budget") == 0:
            msg = (f"Your budget of Rs {req.budget_lakh:g} lakh is too small: the cheapest {cat['name'].lower()} site would cost about Rs {cheapest:.0f} lakh "
                   f"to start (fit-out, opening stock and deposit). Raise the budget to at least that, or choose a smaller store size.")
        return {"empty": True, "message": msg, "funnel": reasons}

    # --- economics for the strongest candidates (M-4/M-8, exact Monte Carlo incl. cannibalisation of our own stores)
    cand = np.where(mask)[0]
    pre = np.nan_to_num(opp[cand], nan=0) + 0.15 * percentile(cf0["profit_p50"].fillna(-1e9).values, urban)[cand]
    cand = cand[np.argsort(-pre)[:CANDIDATE_POOL]]
    mk = gravity.Market(g, base.eff_pop.values, base.affluence.values, cf["attr_here"].values, a)
    own = _own_attr(g, req.own_stores, a.brand_mult)
    sig = np.log(base.rent_p90.values[cand] / np.maximum(base.rent_p10.values[cand], 1e-6)) / 2.563
    sim = mk.simulate(cand, rent_lakh_all[cand], own_attr=own, draws=300, rent_sigma=sig, seed=7)
    eco = gravity.Market.summarise(sim)
    eco.index = cand

    ok = eco.profit_p50 > 0
    if not ok.any():
        return {"empty": True, "message": "No zone is expected to make a profit under these assumptions. Try a lower rent, a smaller store or a larger catchment.",
                "funnel": {**reasons, "expected to be profitable": 0}}
    cand, eco = cand[ok.values], eco[ok]

    # --- confidence (BR-08)
    cov = base.coverage.values[cand]
    pc = percentile(np.nan_to_num(boi_v), urban)[cand]
    disagree = np.abs(np.nan_to_num(rank_pct[cand], nan=np.nan) - pc) if enabled else np.zeros(len(cand))
    width = (eco.profit_p90 - eco.profit_p10).values / np.maximum(np.abs(eco.profit_p50.values), 0.5)
    conf = (0.45 * cov + 0.35 * eco.p_profit.values + 0.20 * np.clip(1 - width / 4, 0, 1))
    conf_label = np.where((cov < 0.35) | (np.nan_to_num(disagree) > 40) | (eco.p_profit.values < 0.6), "Low",
                          np.where((cov > 0.6) & (eco.p_profit.values > 0.85) & (np.nan_to_num(disagree) < 25), "High", "Medium"))

    thin = float(cf0["comp_here"].sum()) < 60                 # very few outlets of this type are mapped: competition is likely under-counted
    if thin:
        conf_label = np.where(conf_label == "High", "Medium", conf_label)

    # --- final ordering by strategy (user-visible weights)
    w = STRATEGIES.get(req.strategy, STRATEGIES["Balanced"])
    comp = (w["opportunity"] * percentile(opp[cand]) + w["profit"] * percentile(eco.profit_p50.values)
            + w["downside"] * percentile(eco.profit_p10.values) + w["confidence"] * percentile(conf))
    order = np.argsort(-comp)
    picked = []
    for o in order:                                          # greedy spacing so picks do not eat each other
        z = cand[o]
        if all(haversine(g.lat[z], g.lon[z], g.lat[cand[p]], g.lon[cand[p]]) >= req.min_spacing_km for p in picked):
            picked.append(o)
        if len(picked) == req.n_results:
            break
    funnel = {**reasons, "expected to be profitable": int(ok.sum())}

    # --- explanations (M-10): SHAP of the ranker, grouped by factor group, only for the picks
    sel = cand[picked]
    shap_fg = None
    if enabled:
        X = pd.concat([base, cf], axis=1)[learn.MODEL_FEATURES].values.astype(float)
        Xr = np.c_[X, np.nan_to_num(cf0["viability"].values, nan=0.0)]
        bg_idx = np.where(urban)[0][::65]
        _, shap_fg = learn.explain(S.models[req.category]["ranker"], Xr[sel], S.models[req.category]["feats"], Xr[bg_idx])
    fg_names = S.cats["factor_groups"]

    top = []
    for rank, o in enumerate(picked, start=1):
        z = cand[o]
        e = eco.iloc[o]
        zone = _zone_row(S, req.category, cf, z)
        drivers = _drivers(zone, cat, fg_names, None if shap_fg is None else shap_fg.iloc[rank - 1])
        risks = _risks(zone, e, cat, upfront[z], rent_lakh_all[z], conf_label[o], disagree[o])
        if thin and risks[0]["type"] == "None detected":
            risks = []
        if thin:
            risks.append({"type": "Data quality", "text": f"only {int(cf0['comp_here'].sum())} {cat['name'].lower()} outlets are mapped in OpenStreetMap, so competition is probably under-counted"})
        top.append({
            "rank": rank, "h3": base.h3[z], "lat": float(g.lat[z]), "lon": float(g.lon[z]), "name": _place_name(S, z),
            "fit_score": round(float(comp[o]), 1), "boi": round(float(boi_v[z]), 1), "band": scoring.band(boi_v[z]),
            "rank_pct": None if not enabled or np.isnan(rank_pct[z]) else round(float(rank_pct[z]), 1),
            "archetype": base.archetype[z], "confidence": conf_label[o], "confidence_score": round(float(conf[o]), 2),
            "revenue": _rng(e, "rev"), "profit": _rng(e, "profit"), "p_profit": round(float(e.p_profit), 3),
            "cannibalisation_pct": round(float(e.cannibal_pct), 1),
            "rent_psf": round(float(rent_psf[z]), 0), "rent_lakh": round(float(rent_lakh_all[z]), 2), "upfront_lakh": round(float(upfront[z]), 1),
            "payback_months": None if e.profit_p50 <= 0 else round(float(upfront[z] / e.profit_p50), 0),
            "population_1km": int(base.pop_1km[z]), "competitors_1km": int(zone["comp_count_1km"]),
            "factors": {k: (None if np.isnan(zone["s_" + k]) else round(float(zone["s_" + k]), 0)) for k in scoring.FG},
            "drivers": drivers, "risks": risks, "coverage": round(float(base.coverage[z]), 2),
            "label": "estimated" if True else "",
        })
    contrasts = _contrast(top, cat)
    for t, c in zip(top, contrasts):
        t["why_over_next"] = c
    return {"empty": False, "category": req.category, "funnel": funnel, "top": top, "strategy": req.strategy, "strategy_weights": w,
            "n_candidates": int(len(cand)), "scenario": scen, "model_used": "LightGBM LambdaRank + BOI consensus" if enabled else "Business Opportunity Index only",
            "assumptions": _assumptions(a, cat), "dna_version": S.cats["version"]}


def _rng(e, p):
    return {"p10": round(float(e[f"{p}_p10"]), 2), "p50": round(float(e[f"{p}_p50"]), 2), "p90": round(float(e[f"{p}_p90"]), 2)}


def _binding(reasons: dict) -> str:
    items = list(reasons.items())
    for (a, na), (b, nb) in zip(items, items[1:]):
        if nb == 0:
            return f"No zone is left after “{b}” ({na:,} zones passed the filters before it). Relax that limit and try again."
    return "No zone satisfies all constraints - relax one of them."


def _assumptions(a, cat):
    return [
        {"name": "Store size", "value": f"{a.size_sqft:,.0f} sq ft", "source": "category default (editable)", "kind": "assumption"},
        {"name": "Gross margin", "value": f"{a.margin * 100:.0f}%", "source": "category default (editable)", "kind": "assumption"},
        {"name": "Fixed monthly cost (staff, utilities)", "value": f"Rs {a.fixed_lakh:.1f} lakh", "source": "category default (editable)", "kind": "assumption"},
        {"name": "Spend per person per month", "value": f"Rs {a.spend_per_person:.0f} (scaled by local affluence)", "source": "approximation", "kind": "assumption"},
        {"name": "Customers reached", "value": f"within {a.catchment_km:.1f} km", "source": "category default", "kind": "assumption"},
        {"name": "Fit-out and opening stock", "value": f"Rs {a.fitout_psf * a.size_sqft / 1e5 + a.inventory_lakh:.0f} lakh + {a.deposit_months:.0f} months deposit", "source": "category default", "kind": "assumption"},
    ]


def _place_name(S, z) -> str:
    """Nearest named reference locality - a human-readable label for a hexagon."""
    loc = S.city.localities
    d = haversine(S.grid.lat[z], S.grid.lon[z], np.array([l["lat"] for l in loc]), np.array([l["lon"] for l in loc]))
    i = int(np.argmin(d))
    return f"Near {loc[i]['name']}" if d[i] > 0.6 else loc[i]["name"]


def _zone_row(S, key, cf, z) -> dict:
    r = {**S.base.iloc[z].to_dict(), **cf.iloc[z].to_dict()}
    r["pct"] = {}
    return r


# ---------------------------------------------------------------------------------------------- explanation text
def _fmt_pct_rank(S, col, v, urban_mask):
    arr = S.base[col].values[urban_mask] if col in S.base else None
    return None if arr is None else float((arr < v).mean() * 100)


def _drivers(z, cat, fg_names, shap_row) -> list:
    """Top reasons (from SHAP if available, else from weight x score), written in plain language with the underlying numbers."""
    S = store
    w = cat["dna"]
    if shap_row is not None:
        tmp = {g: float(v) for g, v in shap_row.items()}
        scale = max(np.abs(list(tmp.values())).max(), 1e-9)
        contrib = {g: v / scale for g, v in tmp.items()}
    else:
        contrib = {g: (np.nan_to_num(z.get("s_" + g), nan=50) - 50) / 50 * w[g] / 20 for g in w}
    ordered = sorted(contrib.items(), key=lambda kv: -kv[1])
    out = []
    for g, v in ordered[:3]:
        if v <= 0:
            continue
        out.append({"group": g, "name": fg_names[g], "strength": round(float(v), 2), "text": _sentence(g, z, positive=True),
                    "weight": w[g], "score": None if np.isnan(z.get("s_" + g, np.nan)) else round(float(z["s_" + g]), 0)})
    if not out:
        g, v = ordered[0]
        out.append({"group": g, "name": fg_names[g], "strength": round(float(v), 2), "text": _sentence(g, z, True), "weight": w[g], "score": None})
    return out


def _sentence(g, z, positive=True) -> str:
    n0 = lambda v: f"{int(round(v, -1 if v > 100 else 0)):,}"      # noqa: E731
    s = z.get("s_" + g, np.nan)
    top = "" if np.isnan(s) else f" (better than {s:.0f}% of Pune zones)"
    if g == "FG1":
        return f"{n0(z['pop_1km'])} people live within 1 km{top}"
    if g == "FG2":
        return f"about {n0(z['workers_1km'])} office workers are within 1 km{top}"
    if g == "FG3":
        return f"about {n0(z['students_1km'])} students are within 1 km{top}"
    if g == "FG4":
        return f"affluent neighbourhood - local property prices around Rs {z['price_psf']:,.0f}/sq ft{top}"
    if g == "FG5":
        return f"strong footfall anchors (malls, markets, cinemas) nearby{top}"
    if g == "FG6":
        return f"{int(z['compl_1km'])} complementary businesses within 1 km that bring in the right customers{top}"
    if g == "FG7":
        return f"easy to reach - {z['transit_km']:.1f} km from metro/rail, {int(z['bus_stops_500m'])} bus stops within 500 m{top}"
    if g == "FG8":
        return f"{int(z['comp_count_1km'])} competing outlets within 1 km - {'room for another store' if positive else 'crowded'}{top}"
    if g == "FG9":
        return f"estimated rent of about Rs {z['rent_psf']:.0f} per sq ft per month is {'lower than most zones' if positive else 'high'}{top}"
    return f"the area is growing faster than most of the city{top}"


def _risks(z, e, cat, upfront, rent_lakh, conf, disagree) -> list:
    r = []
    s = lambda k: z.get("s_" + k, np.nan)      # noqa: E731
    if z["comp_count_1km"] >= 8 or (not np.isnan(s("FG8")) and s("FG8") < 30):
        r.append({"type": "Competition", "text": f"{int(z['comp_count_1km'])} competing outlets within 1 km - shoppers have many alternatives"})
    burden = rent_lakh / max(e.rev_p50, 1e-6)
    if burden > 0.2:
        r.append({"type": "Rent burden", "text": f"rent would take about {burden * 100:.0f}% of expected sales (healthy is below 15-20%)"})
    if not np.isnan(s("FG7")) and s("FG7") < 30:
        r.append({"type": "Access", "text": f"weak accessibility - {z['transit_km']:.1f} km to the nearest metro or rail station"})
    if z["coverage"] < 0.4:
        r.append({"type": "Data quality", "text": "OpenStreetMap coverage is thin here, so competition and demand may be under-counted"})
    if e.profit_p10 < 0:
        r.append({"type": "Downside", "text": f"in a weak scenario (1 in 10) the store loses about Rs {-e.profit_p10:.1f} lakh per month"})
    if e.cannibal_pct > 25:
        r.append({"type": "Cannibalisation", "text": f"about {e.cannibal_pct:.0f}% of this store's sales would come from your own nearby stores"})
    if disagree and np.nan_to_num(disagree) > 40:
        r.append({"type": "Model disagreement", "text": "the learned ranker and the transparent index disagree about this zone - treat it with care"})
    if z["pop_1km"] < 3000:
        r.append({"type": "Thin demand", "text": f"only about {int(z['pop_1km']):,} residents within 1 km"})
    return r or [{"type": "None detected", "text": "no major risk flags were triggered"}]


def _contrast(top, cat) -> list:
    out = []
    for i, t in enumerate(top):
        if i + 1 >= len(top):
            out.append(None)
            continue
        n = top[i + 1]
        diffs = sorted(((k, (t["factors"][k] or 0) - (n["factors"][k] or 0)) for k in t["factors"]), key=lambda kv: -kv[1] * cat["dna"][kv[0]])
        best = [k for k, d in diffs if d > 5][:2]
        names = store.cats["factor_groups"]
        dp = t["profit"]["p50"] - n["profit"]["p50"]
        if best:
            out.append(f"Beats #{n['rank']} ({n['name']}) mainly on {' and '.join(names[k].lower() for k in best)}; "
                       f"expected profit is Rs {abs(dp):.1f} lakh/month {'higher' if dp >= 0 else 'lower'}.")
        else:
            out.append(f"Close call with #{n['rank']} ({n['name']}); ordering is decided by risk and confidence rather than one clear advantage.")
    return out


# ---------------------------------------------------------------------------------------------- zone economics (F-08)
def zone_economics(req: Request, h3_id: str) -> dict:
    """Full unit-economics for one zone: profit distribution, sources of every number, and a sensitivity (tornado) table."""
    S = store
    z = S.grid.index.get(h3_id, -1)
    if z < 0:
        raise KeyError(h3_id)
    cat = S.category(req.category)
    cf = _scenario_features(S, req.category, req, S.cat[req.category]) if req.extra_competitors else S.cat[req.category]
    base = S.base
    a = gravity.Assumptions.from_config(cat, S.city.estimates, S.cats["tiers"], req.brand_tier, **req.overrides)

    def run(a_, rent_mult=1.0, comp=None, draws=600):
        mk = gravity.Market(S.grid, base.eff_pop.values, base.affluence.values, cf["attr_here"].values if comp is None else comp, a_)
        rent_l = base.rent_psf.values[z] * rent_mult * a_.size_sqft / 1e5
        sig = np.log(base.rent_p90.values[z] / max(base.rent_p10.values[z], 1e-6)) / 2.563
        return mk, mk.simulate(np.array([z]), np.array([rent_l]), own_attr=_own_attr(S.grid, req.own_stores, a_.brand_mult), draws=draws,
                               rent_sigma=np.array([sig]), seed=11), rent_l

    mk, sim, rent_l = run(a)
    e = gravity.Market.summarise(sim).iloc[0]
    profit = sim["profit"][0]
    hist, edges = np.histogram(profit, bins=24)
    margin_lakh = float(sim["revenue"][0].mean() * a.margin)
    breakdown = {"revenue": float(sim["revenue"][0].mean()), "gross_margin": margin_lakh, "fixed_costs": a.fixed_lakh, "rent": float(rent_l),
                 "profit": float(profit.mean())}
    base_p = float(np.median(profit))
    sens = []
    import copy as _c
    def variant(label, **kw):
        a2 = _c.copy(a)
        rm = kw.pop("rent_mult", 1.0)
        for k, v in kw.items():
            setattr(a2, k, v)
        _, s2, _ = run(a2, rent_mult=rm, draws=300)
        return {"factor": label, "profit": float(np.median(s2["profit"][0])) - base_p}
    for label, lo, hi in (("Rent", dict(rent_mult=1.2), dict(rent_mult=.8)),
                          ("Gross margin", dict(margin=a.margin - .04), dict(margin=a.margin + .04)),
                          ("Spend per customer", dict(spend_per_person=a.spend_per_person * .8), dict(spend_per_person=a.spend_per_person * 1.2)),
                          ("Customer reach", dict(catchment_km=max(a.catchment_km - .7, .8)), dict(catchment_km=min(a.catchment_km + .7, 3.2))),
                          ("Number of other stores", dict(other_density=a.other_density * 1.4), dict(other_density=a.other_density * .7))):
        sens.append({"factor": label, "down": variant(label, **lo)["profit"], "up": variant(label, **hi)["profit"]})
    comps = S.comps.get(req.category)
    near = []
    if comps is not None and len(comps):
        d = haversine(S.grid.lat[z], S.grid.lon[z], comps.lat.values, comps.lon.values)
        for i in np.argsort(d)[:12]:
            if d[i] <= 1.5:
                near.append({"name": comps.name.iloc[i] or "(unnamed outlet)", "km": round(float(d[i]), 2), "tier": comps.tier.iloc[i],
                             "lat": float(comps.lat.iloc[i]), "lon": float(comps.lon.iloc[i])})
    return {"h3": h3_id, "revenue": _rng(e, "rev"), "profit": _rng(e, "profit"), "p_profit": float(e.p_profit), "cannibalisation_pct": float(e.cannibal_pct),
            "hist": [{"x": float((edges[i] + edges[i + 1]) / 2), "n": int(hist[i])} for i in range(len(hist))], "breakdown": breakdown,
            "sensitivity": sens, "competitors": near, "upfront_lakh": float(mk.upfront_lakh(np.array([rent_l]))[0]),
            "assumptions": _assumptions(a, cat)}


# ---------------------------------------------------------------------------------------------- map layer + zone profile
def layer(category: str) -> dict:
    """Compact per-zone arrays for the map (analysed zones only). Greenfield view: no user constraints applied."""
    S = store
    cf, base = S.cat[category], S.base
    m = base.urban.values
    rp = cf["rank_pct"].values if "rank_pct" in cf else np.full(S.grid.n, np.nan)
    pr = percentile(np.nan_to_num(cf["boi"].values), m)
    fit = np.where(np.isnan(rp), pr, 0.5 * np.nan_to_num(rp) + 0.5 * pr)
    r = lambda a, d=1: [None if not np.isfinite(v) else round(float(v), d) for v in np.asarray(a)[m]]    # noqa: E731
    return {"h3": base.h3[m].tolist(), "boi": r(cf["boi"]), "fit": r(fit), "profit": r(cf["profit_p50"], 2),
            "competitors": [int(v) for v in cf["comp_count_1km"].values[m]], "pop": [int(v) for v in base.pop_1km.values[m]],
            "rent": r(base.rent_psf, 0), "arch": base.archetype.values[m].tolist()}


def zone_profile(h3_id: str, category: str) -> dict:
    """F-02: everything known about one zone, each value labelled real or estimated; category fit for all five categories."""
    S = store
    z = S.grid.index.get(h3_id, -1)
    if z < 0:
        raise KeyError(h3_id)
    b = S.base.iloc[z]
    fit = []
    for key, c in S.cats["categories"].items():
        if key in S.cat:
            fit.append({"key": key, "name": c["name"], "icon": c["icon"], "boi": float(S.cat[key]["boi"].iloc[z]), "band": S.cat[key]["band"].iloc[z]})
    cf = S.cat[category]
    return {"h3": h3_id, "lat": float(b.lat), "lon": float(b.lon), "name": _place_name(S, z), "archetype": b.archetype,
            "values": [
                {"label": "Residents within 1 km", "value": f"{int(b.pop_1km):,}", "kind": "modelled", "source": "WorldPop 2020 (1 km grid), redistributed by OSM activity"},
                {"label": "Office workers within 1 km", "value": f"{int(b.workers_1km):,}", "kind": "estimated", "source": "OSM office count x workers per office"},
                {"label": "Students within 1 km", "value": f"{int(b.students_1km):,}", "kind": "estimated", "source": "OSM colleges x students per campus"},
                {"label": "Competing outlets within 1 km", "value": f"{int(cf.comp_count_1km.iloc[z])}", "kind": "real", "source": "OpenStreetMap"},
                {"label": "Nearest metro / rail", "value": f"{b.transit_km:.1f} km", "kind": "real", "source": "OpenStreetMap + curated metro list"},
                {"label": "Bus stops within 500 m", "value": f"{int(b.bus_stops_500m)}", "kind": "real", "source": "OpenStreetMap"},
                {"label": "Local property price", "value": f"Rs {b.price_psf:,.0f}/sq ft", "kind": "estimated", "source": "approximate listing-portal averages for ~35 localities"},
                {"label": "Estimated commercial rent", "value": f"Rs {b.rent_psf:.0f}/sq ft/month (range {b.rent_p10:.0f}-{b.rent_p90:.0f})", "kind": "estimated", "source": "CatBoost M-1 on locality rents"},
                {"label": "Map completeness here", "value": f"{b.coverage * 100:.0f}%", "kind": "indicator", "source": "named OSM places per area"}],
            "factors": {k: None if np.isnan(cf["s_" + k].iloc[z]) else round(float(cf["s_" + k].iloc[z]), 0) for k in scoring.FG},
            "boi": float(cf["boi"].iloc[z]), "band": cf["band"].iloc[z], "category_fit": sorted(fit, key=lambda x: -x["boi"])}
