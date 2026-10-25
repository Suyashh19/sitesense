"""F-09 Business Opportunity Index: ten factor scores (percentiles 0-100 across analysed zones) weighted by the category DNA.

BOI = sum_g w_g * s_g / 100 (PRD appendix A). Bands: Prime 80+, Strong 65-79, Viable 50-64, Marginal 35-49, Avoid < 35.
"""
import numpy as np
import pandas as pd

from ..pipeline.grid import percentile

FG = [f"FG{i}" for i in range(1, 11)]
BANDS = [(80, "Prime"), (65, "Strong"), (50, "Viable"), (35, "Marginal"), (-1, "Avoid")]
CLUSTER_SHARE = {"spacing": 0.0, "mild_clustering": 0.25, "clustering": 0.45, "strong_clustering": 0.6}


def band(score: float) -> str:
    return next(name for lo, name in BANDS if score >= lo)


def factor_scores(base: pd.DataFrame, cf: pd.DataFrame, cat: dict, masked: bool = False) -> pd.DataFrame:
    """Raw features -> FG1..FG10 percentile scores (0-100) for one category."""
    m = base["urban"].values
    P = lambda v: percentile(np.asarray(v), m)      # noqa: E731
    f = pd.DataFrame(index=base.index)
    f["FG1"] = P(base.pop_1km)
    f["FG2"] = P(base.workers_1km)
    f["FG3"] = P(base.students_1km)
    f["FG4"] = P(base.affluence)
    f["FG5"] = P(base.anchors_1km)
    f["FG6"] = P(cf.compl_1km)
    f["FG7"] = P(base.access_idx)
    # FG8 competition headroom: saturation (competitor weight per 1000 effective customers nearby) with a category-specific
    # curve - spacing categories want few rivals, clustering categories profit from an established cluster up to a point.
    c_w = cf.comp_nonchain_1km if masked else cf.comp_n1km                  # masked = defining chain outlets removed
    c_n = cf.comp_nonchain_count_1km if masked else cf.comp_count_1km
    sat = c_w.values / np.maximum(base.eff_pop_1km.values, 1) * 1000
    headroom = 100 - P(sat)
    share = CLUSTER_SHARE.get(cat["behaviour"]["type"], 0.3)
    n_opt = max(float(np.nanmedian(c_n[cf.chain_here > 0])) if (cf.chain_here > 0).any() else 3.0, 1.0)   # data-driven optimum
    bump = 100 * np.exp(-(np.log1p(c_n) - np.log1p(n_opt)) ** 2 / (2 * 0.7 ** 2))
    f["FG8"] = (1 - share) * headroom + share * bump
    f["FG9"] = 100 - P(base.rent_psf * cat["econ"]["size_sqft"])
    f["FG10"] = base["growth"].fillna(50).values
    f.loc[~m, :] = np.nan
    return f


def boi(f: pd.DataFrame, cat: dict) -> pd.DataFrame:
    w = pd.Series(cat["dna"], dtype=float)
    s = (f[FG] * w[FG].values[None]).sum(1) / w.sum()
    return pd.DataFrame({"boi": s.round(2), "band": s.map(lambda v: band(v) if np.isfinite(v) else "n/a")})
