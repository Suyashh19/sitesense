"""Stage 3 - prepare: the H3 hexagon grid, neighbour tables and small spatial helpers shared by the whole engine."""
from dataclasses import dataclass

import h3
import numpy as np

EARTH_KM = 6371.0088
MAX_RADIUS_KM = 3.2          # largest catchment used anywhere (category `catchment_km` is capped to this)


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(np.asarray(lon2) - lon1) / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


@dataclass
class Grid:
    res: int
    cells: list
    lat: np.ndarray
    lon: np.ndarray
    index: dict
    nbr: np.ndarray      # (n, K) neighbour indices within MAX_RADIUS_KM (self first), -1 padded
    dist: np.ndarray     # (n, K) km, inf where padded
    area_km2: float

    @property
    def n(self):
        return len(self.cells)

    def locate(self, lat, lon):
        """Hex index for a coordinate, or -1 when it falls outside the study area."""
        return self.index.get(h3.latlng_to_cell(float(lat), float(lon), self.res), -1)

    def count(self, lat, lon, weight=None) -> np.ndarray:
        out = np.zeros(self.n)
        w = np.ones(len(lat)) if weight is None else np.asarray(weight, dtype=float)
        for la, lo, wi in zip(lat, lon, w):
            i = self.index.get(h3.latlng_to_cell(float(la), float(lo), self.res), -1)
            if i >= 0:
                out[i] += wi
        return out

    def within(self, values: np.ndarray, radius_km: float) -> np.ndarray:
        """Sum of `values` over all hexes whose centre lies within radius_km (includes the hex itself)."""
        ok = (self.nbr >= 0) & (self.dist <= radius_km)
        return np.where(ok, values[np.clip(self.nbr, 0, None)], 0.0).sum(1)

    def nearest_km(self, lat, lon, cap=30.0) -> np.ndarray:
        """Distance from each hex centre to the nearest of the given points."""
        if len(lat) == 0:
            return np.full(self.n, cap)
        d = haversine(self.lat[:, None], self.lon[:, None], np.asarray(lat)[None, :], np.asarray(lon)[None, :])
        return np.minimum(d.min(1), cap)


def build_grid(bbox: dict, res: int) -> Grid:
    poly = h3.LatLngPoly([(bbox["south"], bbox["west"]), (bbox["south"], bbox["east"]),
                          (bbox["north"], bbox["east"]), (bbox["north"], bbox["west"])])
    cells = sorted(h3.polygon_to_cells(poly, res))
    ll = np.array([h3.cell_to_latlng(c) for c in cells])
    index = {c: i for i, c in enumerate(cells)}
    k = int(np.ceil(MAX_RADIUS_KM / (h3.average_hexagon_edge_length(res, "km") * 1.7320508))) + 1
    rows = []
    for c in cells:
        near = [index[x] for x in h3.grid_disk(c, k) if x in index]
        rows.append(near)
    K = max(len(r) for r in rows)
    nbr = np.full((len(cells), K), -1, dtype=np.int32)
    for i, r in enumerate(rows):
        r = sorted(r, key=lambda j: j != i)       # self first
        nbr[i, :len(r)] = r
    safe = np.clip(nbr, 0, None)
    dist = haversine(ll[:, 0][:, None], ll[:, 1][:, None], ll[safe, 0], ll[safe, 1]).astype("float32")
    dist = np.where((nbr >= 0) & (dist <= MAX_RADIUS_KM), dist, np.inf).astype("float32")
    nbr = np.where(np.isfinite(dist), nbr, -1).astype("int32")
    return Grid(res, cells, ll[:, 0], ll[:, 1], index, nbr, dist, h3.average_hexagon_area(res, "km^2"))


def percentile(values: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Percentile score 0-100 of each value among the masked (valid) zones; ties share the average rank."""
    from scipy.stats import rankdata
    v = np.asarray(values, dtype=float)
    m = np.ones(len(v), bool) if mask is None else mask
    out = np.zeros(len(v))
    if m.sum() > 1:
        out[m] = (rankdata(v[m]) - 1) / (m.sum() - 1) * 100
    out[~m] = np.nan
    return out
