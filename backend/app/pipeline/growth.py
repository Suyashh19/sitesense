"""FG10 growth: change in the number of mapped shops and amenities per ~5 km block between two dates (ohsome API, HeiGIT).

A trend indicator (L-08): OSM counts partly reflect mapping effort, so growth is only ever used as a relative score and its
weight in every category is small. If the service is unreachable the factor falls back to a neutral value and is flagged.
"""
import time

import h3
import numpy as np
import requests

OHSOME = "https://api.ohsome.org/v1/elements/count/groupBy/boundary"
FILTER = "(shop=* or amenity in (restaurant, cafe, fast_food, pharmacy, clinic, bank)) and type:node"


def block_growth(cells: list[str], res: int = 7, t0="2021-01-01", t1="2026-01-01", log=print):
    """Return a dict {parent_cell: log growth ratio} or None if ohsome is unavailable."""
    parents = sorted({h3.cell_to_parent(c, res) for c in cells})
    feats = []
    for p in parents:
        ring = [[lon, lat] for lat, lon in h3.cell_to_boundary(p)]
        ring.append(ring[0])
        feats.append({"type": "Feature", "id": p, "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}})
    body = {"bpolys": __import__("json").dumps({"type": "FeatureCollection", "features": feats}),
            "time": f"{t0},{t1}", "filter": FILTER, "format": "json"}
    for attempt in range(4):
        try:
            r = requests.post(OHSOME, data=body, timeout=(15, 180), headers={"User-Agent": "SiteSense/1.0 (student project)"})
            if r.status_code == 200:
                res_ = {}
                for g in r.json()["groupByResult"]:
                    v0, v1 = (x["value"] for x in g["result"])
                    res_[g["groupByObject"]] = float(np.log((v1 + 5) / (v0 + 5)))
                return res_
            log(f"    ohsome HTTP {r.status_code}; retrying")
        except (requests.RequestException, KeyError, ValueError) as e:
            log(f"    ohsome {type(e).__name__}; retrying")
        time.sleep(4 * (attempt + 1))
    return None
