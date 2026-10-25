"""Stage 2 - population: WorldPop 1 km raster (CC BY 4.0) sampled to the H3 grid.

People per hex = interpolated density at the hex centre x hex area. Because a 1 km raster is coarse (A-05, L-03), the
people of each raster cell are then redistributed over the hexes inside it in proportion to a built-up weight (OSM
activity), which keeps each cell's total unchanged. The result is a modelled estimate, labelled as such in the app.
"""
from pathlib import Path

import numpy as np
import requests

from ..config import DATA_DIR

RAW = DATA_DIR / "raw"


def download(url: str, log=print) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    f = RAW / Path(url).name
    if f.exists() and f.stat().st_size > 1_000_000:
        log(f"  cached  WorldPop raster {f.name} ({f.stat().st_size / 1e6:.1f} MB)")
        return f
    log(f"  downloading WorldPop raster {f.name} ...")
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        tmp = f.with_suffix(".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        tmp.replace(f)
    log(f"  downloaded {f.stat().st_size / 1e6:.1f} MB")
    return f


def sample(tif: Path, lat: np.ndarray, lon: np.ndarray, hex_area_km2: float):
    """Return (people per hex, raster-cell id per hex). Values <0 (nodata) are treated as 0."""
    import rasterio
    with rasterio.open(tif) as ds:
        arr = ds.read(1).astype("float64")
        nod = ds.nodata
        if nod is not None:
            arr[arr == nod] = 0.0
        arr[arr < 0] = 0.0
        rows, cols = rasterio.transform.rowcol(ds.transform, lon, lat)
        rows, cols = np.asarray(rows), np.asarray(cols)
        px_w_deg, px_h_deg = ds.transform.a, -ds.transform.e
    h, w = arr.shape
    rows, cols = np.clip(rows, 1, h - 2), np.clip(cols, 1, w - 2)
    cell_km2 = (px_w_deg * 111.32 * np.cos(np.radians(lat))) * (px_h_deg * 110.57)
    dens = arr[rows, cols] / cell_km2
    # smooth with the 4 neighbours (cell-centre jitter would otherwise create visible 1 km blocks)
    nb = (arr[rows - 1, cols] + arr[rows + 1, cols] + arr[rows, cols - 1] + arr[rows, cols + 1]) / (4 * cell_km2)
    dens = 0.7 * dens + 0.3 * nb
    return dens * hex_area_km2, rows * 100000 + cols


def redistribute(pop: np.ndarray, cell_id: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Keep the total of each raster cell, but shift people towards hexes with more built-up activity (A-05)."""
    out = pop.copy()
    for cid in np.unique(cell_id):
        m = cell_id == cid
        if m.sum() < 2:
            continue
        tot, w = pop[m].sum(), weight[m]
        out[m] = tot * w / w.sum()
    return out
