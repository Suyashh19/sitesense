"""M-1 Rent regressor (PRD section 12): generalises ~35 locality reference rents to every zone.

Target: reference rent (Rs per sq ft per month) = locality price x commercial multiplier x monthly yield (ES-02, an estimate).
CatBoost learns how rent varies with activity and access beyond the smooth price surface. The prediction interval comes from
leave-one-locality-out residuals (conformal-style), so it widens far from any reference locality.
"""
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from ..catalog import CityConfig
from ..pipeline.grid import Grid, haversine

FEATS = ["price_idw", "poi_total_1km", "transit_km", "road_idx_1km", "dist_centre_km", "pop_density", "anchors_1km"]


def _price_idw(grid_lat, grid_lon, loc, bw, exclude=None):
    d = haversine(grid_lat[:, None], grid_lon[:, None], loc.lat.values[None], loc.lon.values[None])
    w = np.exp(-(d / bw) ** 2) + 1e-9
    if exclude is not None:
        w[np.arange(len(grid_lat)), exclude] = 0.0
    return (w * loc.price_psf.values[None]).sum(1) / w.sum(1)


def fit_predict(city: CityConfig, grid: Grid, df: pd.DataFrame) -> dict:
    est = city.estimates
    loc = pd.DataFrame(city.localities)
    scale = est["commercial_multiplier"] * est["monthly_yield"]
    idx = np.array([grid.locate(la, lo) for la, lo in zip(loc.lat, loc.lon)])
    keep = idx >= 0
    li, loc_k = idx[keep], loc[keep].reset_index(drop=True)
    X_all = df.assign(pop_density=df["pop"] / grid.area_km2, price_idw=df.price_psf)[FEATS]
    X_loc = X_all.iloc[li].copy()
    # leave-one-out price surface so a locality's own price never leaks into its own training row
    X_loc["price_idw"] = _price_idw(grid.lat[li], grid.lon[li], loc_k, est["idw_bandwidth_km"], exclude=np.arange(len(li)))
    y = np.log(loc_k.price_psf.values * scale)
    params = dict(iterations=250, depth=3, learning_rate=0.06, loss_function="RMSE", verbose=False, random_seed=0)

    loo = np.zeros(len(y))
    for i in range(len(y)):                                                   # leave-one-locality-out validation
        tr = np.arange(len(y)) != i
        loo[i] = CatBoostRegressor(**params).fit(X_loc[tr], y[tr]).predict(X_loc.iloc[[i]])[0]
    resid = y - loo
    q_lo, q_hi = np.quantile(resid, [0.10, 0.90])
    baseline_resid = y - np.log(X_loc.price_idw.values * scale)               # baseline: price x yield only
    model = CatBoostRegressor(**params).fit(X_loc, y)

    nl = np.exp(np.minimum(df.nearest_locality_km.values / 3.0, 1.0))         # unfamiliar zones get wider intervals
    mid = np.exp(model.predict(X_all))
    out = pd.DataFrame({"rent_psf": mid, "rent_p10": mid * np.exp(q_lo * nl), "rent_p90": mid * np.exp(q_hi * nl)}, index=df.index)
    metrics = {"n_localities": int(len(y)), "loo_mape": float(np.mean(np.abs(np.exp(loo) / np.exp(y) - 1))),
               "baseline_mape": float(np.mean(np.abs(np.exp(baseline_resid) - 1))), "model": "CatBoost (leave-one-locality-out)"}
    return {"rent": out, "metrics": metrics}
