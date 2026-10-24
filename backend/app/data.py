"""Simulated city + business-domain generator.

All data is synthetic. The hidden revenue process is NOT shown to the ML model: the model only
sees the owner's existing stores (zone features -> observed monthly revenue) and must learn the
relationship, then predict revenue for every vacant candidate zone.
"""
import numpy as np
import pandas as pd

N = 20  # 20 x 20 grid of 1 km x 1 km zones

CITIES = {
    "Pune": (18.5204, 73.8567, 11),
    "Bengaluru": (12.9716, 77.5946, 23),
    "Hyderabad": (17.3850, 78.4867, 5),
    "Ahmedabad": (23.0225, 72.5714, 42),
    "Nagpur": (21.1458, 79.0882, 8),
}

# size = shop floor (sq ft); margin = gross margin on sales; fixed = staff+utilities (Rs lakh/month)
# inc_exp = how strongly sales rise with local affluence ("rich to rich" effect)
# comp_k = sales lost per nearby competitor; acc_w = weight of accessibility; cannib = overlap with own stores
DOMAINS = {
    "Luxury fashion boutique": dict(size=1500, margin=.32, capex=120, fixed=4.0, inc_exp=2.4, w_pop=.15, w_foot=.60,
                                    comp_k=.05, acc_w=.45, cannib=.30, icon="👜"),
    "Supermarket / grocery": dict(size=6000, margin=.15, capex=250, fixed=6.0, inc_exp=.5, w_pop=.85, w_foot=.20,
                                  comp_k=.22, acc_w=.50, cannib=.55, icon="🛒"),
    "Café / quick-service restaurant": dict(size=900, margin=.24, capex=60, fixed=2.5, inc_exp=1.0, w_pop=.30, w_foot=.75,
                                            comp_k=.10, acc_w=.60, cannib=.35, icon="☕"),
    "Consumer electronics": dict(size=3000, margin=.13, capex=150, fixed=4.5, inc_exp=1.4, w_pop=.40, w_foot=.50,
                                 comp_k=.12, acc_w=.50, cannib=.40, icon="📱"),
    "Pharmacy / wellness": dict(size=700, margin=.22, capex=40, fixed=1.8, inc_exp=.4, w_pop=.90, w_foot=.20,
                                comp_k=.20, acc_w=.35, cannib=.60, icon="💊"),
}

FEATURES = ["population_k", "income_index", "avg_spend_k", "footfall_k", "transit_score", "road_access",
            "competitors_1km", "own_nearest_km", "own_stores_3km", "dist_center_km"]

LABELS = {
    "population_k": "Population (thousands)", "income_index": "Neighbourhood income level",
    "avg_spend_k": "Avg. monthly spend per person (Rs '000)", "footfall_k": "Daily footfall (thousands)",
    "transit_score": "Public-transit access", "road_access": "Road accessibility",
    "competitors_1km": "Competitors within 1 km", "own_nearest_km": "Distance to our nearest store",
    "own_stores_3km": "Our stores within 3 km", "dist_center_km": "Distance from city centre",
}

# the six business factors the owner cares about -> model features that express them
FACTOR_GROUPS = {
    "Customer demand": ["population_k", "footfall_k", "dist_center_km"],
    "Spending power": ["income_index", "avg_spend_k"],
    "Competition": ["competitors_1km"],
    "Accessibility": ["transit_score", "road_access"],
    "Own-store overlap": ["own_nearest_km", "own_stores_3km"],
}


def _g(x, y, cx, cy, s):
    return np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * s ** 2))


def _direction(dx, dy):
    if abs(dx) < 1.5 and abs(dy) < 1.5:
        return "Central"
    ang = (np.degrees(np.arctan2(dy, dx)) + 360) % 360
    return ["East", "North-East", "North", "North-West", "West", "South-West", "South", "South-East"][int(((ang + 22.5) % 360) // 45)]


def make_city(city="Pune", domain="Luxury fashion boutique", n_stores=60, seed=None):
    lat_c, lon_c, base_seed = CITIES[city]
    rng = np.random.default_rng(base_seed if seed is None else seed)
    P = DOMAINS[domain]
    km_lat, km_lon = 1 / 110.6, 1 / (111.3 * np.cos(np.radians(lat_c)))
    xs, ys = np.meshgrid(np.arange(N), np.arange(N))
    x, y = xs.ravel().astype(float), ys.ravel().astype(float)
    n = N * N

    # urban structure: CBD plus 2-3 random sub-centres, affluent pockets elsewhere
    subs = rng.uniform(3, 17, size=(3, 2))
    urban = _g(x, y, 9.5, 9.5, 4.5) + sum(w * _g(x, y, cx, cy, 2.8) for w, (cx, cy) in zip([.7, .6, .45], subs))
    urban = urban / urban.max()
    rich = rng.uniform(3, 17, size=(2, 2))
    wealth = sum(_g(x, y, cx, cy, 3.5) for cx, cy in rich)

    df = pd.DataFrame({"zone_id": [f"Z{i:03d}" for i in range(n)], "gx": x, "gy": y})
    df["lat"] = lat_c + (y - 9.5) * km_lat
    df["lon"] = lon_c + (x - 9.5) * km_lon
    df["dist_center_km"] = np.hypot(x - 9.5, y - 9.5).round(1)
    df["zone_name"] = [f"{_direction(a - 9.5, b - 9.5)} sector {z}" for a, b, z in zip(x, y, df.zone_id)]

    df["population_k"] = np.clip(4 + 46 * urban + rng.normal(0, 3.5, n), 1.5, None).round(1)
    df["income_index"] = np.clip(0.50 + 0.55 * wealth + 0.12 * urban + rng.normal(0, .07, n), .25, 1.5).round(2)
    df["avg_spend_k"] = np.clip(2.5 + 11 * df.income_index ** 1.6 + rng.normal(0, .5, n), 1.5, None).round(1)
    df["footfall_k"] = np.clip(1.5 + 38 * urban ** 1.3 + 7 * rng.random(n) * urban, 1, None).round(1)
    df["transit_score"] = np.clip(0.12 + 0.85 * urban + rng.normal(0, .09, n), 0, 1).round(2)
    df["road_access"] = np.clip(0.35 + 0.3 * urban + rng.normal(0, .17, n), .05, 1).round(2)
    df["rent_psf"] = np.clip(35 + 140 * urban ** 1.2 + 30 * df.income_index + rng.normal(0, 7, n), 28, None).round(0)
    df["competitors_1km"] = rng.poisson(0.3 + 5.0 * urban * (0.6 + 0.4 * rng.random(n)) * (0.7 + 0.5 * wealth.clip(0, 1))).astype(int)
    df["vacant_units"] = rng.poisson(0.25 + 3.2 * urban * rng.random(n) + 0.8 * rng.random(n)).astype(int)

    # owner's existing stores: biased to dense, accessible zones
    p = (urban ** 1.1) * (0.25 + df.transit_score.values)
    store_idx = rng.choice(n, size=n_stores, replace=False, p=p / p.sum())
    df["has_store"] = False
    df.loc[store_idx, "has_store"] = True
    df.loc[df.has_store, "vacant_units"] = 0  # not relevant; we already operate there
    sc = df.loc[df.has_store, ["gx", "gy"]].values
    D = np.hypot(df.gx.values[:, None] - sc[:, 0][None], df.gy.values[:, None] - sc[:, 1][None])
    D = np.where(D == 0, np.inf, D)  # a store does not compete with itself
    df["own_nearest_km"] = np.minimum(D.min(1), 12).round(1)
    df["own_stores_3km"] = (D <= 3).sum(1)

    # ---- hidden ground-truth revenue process (domain-specific) ----
    spend_rel = df.avg_spend_k / df.avg_spend_k.mean()
    raw = (P["w_pop"] * df.population_k * spend_rel + P["w_foot"] * df.footfall_k * (0.5 + df.transit_score))
    raw = raw * df.income_index ** P["inc_exp"]
    raw = raw * (1 - P["acc_w"] + P["acc_w"] * (0.5 * df.transit_score + 0.5 * df.road_access) * 1.3)
    raw = raw / (1 + P["comp_k"] * df.competitors_1km)
    raw = raw * (1 - P["cannib"] * np.exp(-df.own_nearest_km / 1.6) - 0.03 * df.own_stores_3km.clip(upper=4))

    df["opex_lakh"] = (df.rent_psf * P["size"] / 1e5 + P["fixed"]).round(2)
    st = df.has_store.values
    # calibrate so a typical existing store earns gross profit = 1.5 x its operating cost
    scale = 1.5 * df.opex_lakh[st].median() / P["margin"] / raw[st].median()
    df["_true_rev"] = raw * scale
    noise = rng.lognormal(0, 0.09, n)
    df["monthly_revenue_lakh"] = np.where(st, (df._true_rev * noise).round(2), np.nan)
    return df
