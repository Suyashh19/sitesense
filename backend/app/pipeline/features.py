"""Stage 4 - features: zone-level raw features (city-wide) and category-specific features (competition, complementors, labels).

Every feature maps to one factor group FG1..FG10 (PRD section 7). Nothing here names a category: tags, chains and
parameters come from categories.yaml. Real values (from OSM / WorldPop) are kept apart from estimates (curated tables,
modelled rent) so the UI can label them.
"""
import numpy as np
import pandas as pd

from ..catalog import CityConfig, matches
from .grid import Grid, haversine, percentile
from . import population as pop_mod

ANCHOR_WEIGHT = {"mall": 5, "department_store": 3, "marketplace": 2, "supermarket": 1, "cinema": 2, "bank": 0.5, "attraction": 2}
ROAD_WEIGHT = {"trunk": 3, "primary": 2.5, "secondary": 1.5, "tertiary": 1}
DAYTIME_WEIGHT = 0.35        # share of workers/students/visitors counted as customers in the demand origin (A-02)


def unique_pois(frames: dict) -> pd.DataFrame:
    p = pd.concat([f for k, f in frames.items() if not k.startswith(("highway", "railway"))], ignore_index=True)
    return p.drop_duplicates("osm_id").reset_index(drop=True)


def _tier_mult(row_tags: dict, name: str, brand: str, chains: list[str], tiers: dict) -> tuple[float, str]:
    s = f"{name} {brand}".lower()
    if any(c in s for c in chains):
        return tiers["national_chain"], "national_chain"
    if brand:
        return tiers["regional_chain"], "regional_chain"
    return tiers["independent"], "independent"


def city_features(city: CityConfig, cats: dict, grid: Grid, frames: dict, tif, log=print) -> pd.DataFrame:
    """Category-independent features for every zone."""
    est, n = city.estimates, grid.n
    pois = unique_pois(frames)
    tags = pois["tags"].tolist()
    df = pd.DataFrame({"h3": grid.cells, "lat": grid.lat, "lon": grid.lon})

    # --- activity (used for coverage and for redistributing population) ---
    poi_cnt = grid.count(pois.lat.values, pois.lon.values)
    named = grid.count(pois.lat.values[pois.name != ""], pois.lon.values[pois.name != ""])
    df["poi_total_1km"] = grid.within(poi_cnt, 1.0)
    df["named_share"] = np.where(df.poi_total_1km > 0, grid.within(named, 1.0) / np.maximum(df.poi_total_1km, 1), 0.0)

    hw = frames["highway_major"]
    rw = np.array([ROAD_WEIGHT.get(t.get("highway"), 1) for t in hw["tags"]]) if len(hw) else np.array([])
    road_cnt = grid.count(hw.lat.values, hw.lon.values, rw) if len(hw) else np.zeros(n)
    df["road_idx_1km"] = grid.within(road_cnt, 1.0)

    # --- FG1 residential demand: WorldPop, redistributed by built-up activity ---
    raw_pop, cell_id = pop_mod.sample(tif, grid.lat, grid.lon, grid.area_km2)
    built = 0.5 + percentile(grid.within(poi_cnt, 0.6) + 0.5 * grid.within(road_cnt, 0.6)) / 100
    df["pop"] = pop_mod.redistribute(raw_pop, cell_id, built)
    df["pop_1km"], df["pop_3km"] = grid.within(df["pop"].values, 1.0), grid.within(df["pop"].values, 3.0)

    # --- FG2 / FG3 workforce, students, hospital visitors ---
    off = np.array([("office" in t) for t in tags])
    edu = np.array([matches(t, cats["education"]) for t in tags])
    hos = np.array([matches(t, cats["hospitals"]) for t in tags])
    workers = grid.count(pois.lat.values[off], pois.lon.values[off], np.full(off.sum(), est["workers_per_office"]))
    students = grid.count(pois.lat.values[edu], pois.lon.values[edu], np.full(edu.sum(), est["students_per_college"]))
    visitors = grid.count(pois.lat.values[hos], pois.lon.values[hos], np.full(hos.sum(), est["visitors_per_hospital"]))
    df["workers_1km"], df["students_1km"] = grid.within(workers, 1.0), grid.within(students, 1.0)
    df["visitors_1km"] = grid.within(visitors, 1.0)
    df["eff_pop"] = df["pop"] + DAYTIME_WEIGHT * (workers + students + visitors)   # demand origin for the gravity model
    df["eff_pop_1km"] = grid.within(df["eff_pop"].values, 1.0)

    # --- FG4 affluence + FG9 rent inputs: IDW over curated locality prices (ES-01) ---
    loc = pd.DataFrame(city.localities)
    d = haversine(grid.lat[:, None], grid.lon[:, None], loc.lat.values[None], loc.lon.values[None])
    w = np.exp(-(d / est["idw_bandwidth_km"]) ** 2) + 1e-9
    df["price_psf"] = (w * loc.price_psf.values[None]).sum(1) / w.sum(1)
    df["nearest_locality_km"] = d.min(1)
    lo, hi = df.price_psf.min(), df.price_psf.max()
    df["affluence"] = (df.price_psf - lo) / (hi - lo)

    # --- FG5 footfall anchors ---
    aw = np.zeros(len(pois))
    for i, t in enumerate(tags):
        for key in ("shop", "amenity", "tourism"):
            if key in t and t[key] in ANCHOR_WEIGHT and matches(t, cats["anchors"]):
                aw[i] = max(aw[i], ANCHOR_WEIGHT[t[key]])
    anchors = grid.count(pois.lat.values[aw > 0], pois.lon.values[aw > 0], aw[aw > 0])
    df["anchors_1km"] = grid.within(anchors, 1.0)

    # --- FG7 accessibility ---
    metro = pd.DataFrame(city.metro_stations)
    rail = frames["railway"]
    stn = pd.concat([metro[["lat", "lon"]], rail[["lat", "lon"]]]) if len(rail) else metro[["lat", "lon"]]
    df["transit_km"] = grid.nearest_km(stn.lat.values, stn.lon.values)
    bus = frames["highway_bus"]
    bus_cnt = grid.count(bus.lat.values, bus.lon.values) if len(bus) else np.zeros(n)
    df["bus_stops_500m"] = grid.within(bus_cnt, 0.5)
    df["access_idx"] = 0.45 * np.exp(-df.transit_km / 1.8) + 0.25 * np.minimum(df.bus_stops_500m / 6, 1) + \
        0.30 * np.minimum(df.road_idx_1km / np.maximum(df.road_idx_1km.quantile(.9), 1e-6), 1)

    df["dist_centre_km"] = haversine(grid.lat, grid.lon, loc.lat.values[loc.name == "Shivajinagar"][0], loc.lon.values[loc.name == "Shivajinagar"][0])
    # a zone is "urban" (analysed) when people or places are there; the rest (hills, farmland, water) are excluded
    df["urban"] = (df["pop"] >= 25) | (df.poi_total_1km >= 3)
    # OSM coverage indicator (L-02): more named POIs per person nearby = better mapped
    df["coverage"] = np.clip(0.5 * np.minimum(df.poi_total_1km / 25, 1) + 0.5 * df.named_share, 0, 1)
    log(f"  grid: {n} zones, {int(df.urban.sum())} urban; population total {df['pop'].sum() / 1e6:.2f} M")
    return df


def competitors(pois: pd.DataFrame, cat: dict, tiers: dict) -> pd.DataFrame:
    """Same-category outlets with their brand tier and gravity attractiveness (ES-07)."""
    comp = pois[np.array([matches(t, cat["competitors"]) for t in pois["tags"]], dtype=bool)].copy()
    tier = [_tier_mult(t, n, b, cat["chains"], tiers) for t, n, b in zip(comp.tags, comp.name, comp.brand)]
    comp["attr"], comp["tier"] = [t[0] for t in tier], [t[1] for t in tier]
    return comp


def category_features(grid: Grid, base: pd.DataFrame, pois: pd.DataFrame, cat: dict, tiers: dict) -> pd.DataFrame:
    """Competition, complementors and weak labels for one category."""
    cmp_mask = np.array([matches(t, cat["complementors"]) for t in pois["tags"]], dtype=bool)
    comp = competitors(pois, cat, tiers)
    chain = comp[comp.tier == "national_chain"]
    nonchain = comp[comp.tier != "national_chain"]

    out = pd.DataFrame(index=base.index)
    a_all = grid.count(comp.lat.values, comp.lon.values, comp.attr.values)
    a_non = grid.count(nonchain.lat.values, nonchain.lon.values, nonchain.attr.values)
    out["attr_here"] = a_all                                   # competitor attractiveness located in the zone
    out["comp_n500"], out["comp_n1km"], out["comp_n2km"] = grid.within(a_all, .5), grid.within(a_all, 1.0), grid.within(a_all, 2.0)
    out["comp_count_1km"] = grid.within(grid.count(comp.lat.values, comp.lon.values), 1.0)
    # leakage mask (PRD 12.x): the defining chain outlets are removed from the features that the viability model sees
    out["comp_nonchain_500"], out["comp_nonchain_1km"] = grid.within(a_non, .5), grid.within(a_non, 1.0)
    out["compl_1km"] = grid.within(grid.count(pois.lat.values[cmp_mask], pois.lon.values[cmp_mask]), 1.0)
    out["compl_500"] = grid.within(grid.count(pois.lat.values[cmp_mask], pois.lon.values[cmp_mask]), 0.5)

    chain_here = grid.count(chain.lat.values, chain.lon.values)
    out["chain_here"] = chain_here
    out["chain_near"] = grid.within(chain_here, 0.45) - chain_here         # chain in an adjacent zone (k-ring 1)
    out["comp_here"] = grid.count(comp.lat.values, comp.lon.values)
    branded = comp[(comp.tier != "independent")]
    out["branded_here"] = grid.count(branded.lat.values, branded.lon.values)
    out["comp_nonchain_count_1km"] = grid.within(grid.count(nonchain.lat.values, nonchain.lon.values), 1.0)
    return out
