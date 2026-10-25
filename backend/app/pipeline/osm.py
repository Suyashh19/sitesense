"""Stage 1 - ingest: fetch OpenStreetMap features for the city bounding box through the Overpass API.

Queries are generated from the category configuration (no tags are hardcoded here). Raw responses are cached on disk so the
pipeline can be re-run offline and the data lineage is auditable. Data (c) OpenStreetMap contributors, ODbL.
"""
import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import requests

from ..catalog import CityConfig, collect_selectors
from ..config import DATA_DIR

RAW = DATA_DIR / "raw"
OPTIONAL = {"tourism", "public_transport"}      # minor layers: the pipeline continues without them
UA = {"User-Agent": "SiteSense/1.0 (student hackathon project; Walchand College of Engineering)"}


def _query(bbox: dict, key: str, values: list[str] | None, way_only=False) -> str:
    box = f'({bbox["south"]},{bbox["west"]},{bbox["north"]},{bbox["east"]})'
    flt = f'["{key}"]' if not values or "*" in values else f'["{key}"~"^({"|".join(values)})$"]'
    kind = "way" if way_only else "nwr"
    return f"[out:json][timeout:240];{kind}{flt}{box};out tags center;"


def build_queries(city: CityConfig, categories: dict) -> dict[str, str]:
    """One Overpass query per OSM key (shop, amenity, ...) plus roads; values are the union of every configured selector."""
    sel = collect_selectors(categories)
    out = {k: _query(city.bbox, k, sorted(v)) for k, v in sel.items()}
    out["highway_major"] = _query(city.bbox, "highway", categories["roads"], way_only=True)
    out["highway_bus"] = _query(city.bbox, "highway", ["bus_stop"])
    out["railway"] = _query(city.bbox, "railway", ["station", "subway_entrance", "halt"])
    return out


def _post(endpoints: list[str], query: str, log) -> dict:
    last = None
    for attempt in range(8):
        url = endpoints[attempt % len(endpoints)]
        try:
            r = requests.post(url, data={"data": query}, headers=UA, timeout=(15, 240))
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                return r.json()
            last = f"{url} -> HTTP {r.status_code}"
        except requests.RequestException as e:
            last = f"{url} -> {type(e).__name__}"
        wait = min(5 * 2 ** (attempt // 2), 60)
        log(f"    Overpass busy ({last}); retrying in {wait}s")
        time.sleep(wait)
    raise RuntimeError(f"Overpass unavailable after retries: {last}")


def fetch_all(city: CityConfig, categories: dict, log=print, refresh=False) -> dict[str, pd.DataFrame]:
    RAW.mkdir(parents=True, exist_ok=True)
    frames = {}
    for name, q in build_queries(city, categories).items():
        f = RAW / f"{city.key}_{name}_{hashlib.md5(q.encode()).hexdigest()[:8]}.json"
        if f.exists() and not refresh:
            data = json.loads(f.read_text(encoding="utf-8"))
            log(f"  cached  {name:<14} {len(data['elements']):>6} elements")
        else:
            log(f"  fetching {name} from OpenStreetMap ...")
            try:
                data = _post(city.overpass_endpoints, q, log)
            except RuntimeError:
                if name not in OPTIONAL:
                    raise
                log(f"  skipped optional layer {name} (Overpass unavailable); it is left empty and flagged")
                frames[name] = pd.DataFrame(columns=["osm_id", "lat", "lon", "name", "brand", "tags"])
                continue
            f.write_text(json.dumps(data), encoding="utf-8")
            log(f"  fetched {name:<14} {len(data['elements']):>6} elements")
        rows = []
        for e in data["elements"]:
            lat = e.get("lat") or (e.get("center") or {}).get("lat")
            lon = e.get("lon") or (e.get("center") or {}).get("lon")
            if lat is None or lon is None:
                continue
            t = e.get("tags", {})
            rows.append({"osm_id": f'{e["type"][0]}{e["id"]}', "lat": lat, "lon": lon, "name": t.get("name", ""),
                         "brand": t.get("brand", ""), "tags": t})
        frames[name] = pd.DataFrame(rows, columns=["osm_id", "lat", "lon", "name", "brand", "tags"])
    return frames
