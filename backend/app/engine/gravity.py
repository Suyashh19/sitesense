"""M-4 Economics simulator (Huff gravity model + Monte Carlo) and M-8 cannibalisation estimator.

Customers in every origin zone i (effective population = residents + a share of workers/students/visitors) spend a monthly
amount on the category and choose among stores by attractiveness and distance (Huff 1963):

    P_ij = A_j^alpha * d_ij^-beta / (sum_k A_k^alpha * d_ik^-beta + O_i)
    O_i = unmapped / other stores and online: `other_density` store-equivalents per 1000 customers, placed at half the catchment radius
    revenue_j = sum_i pop_i * spend_i * P_ij            profit_j = revenue_j * margin - fixed cost - rent

Uncertain inputs (spend, margin, rent, distance decay beta, outside option) are sampled, so every result is a range (BR-05).
A new store's cannibalisation is the revenue its own stores lose: the gravity mass that shifts between them (M-8).
This module is configuration + maths only; nothing is fitted, so it is tested with conservation and monotonicity checks.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..pipeline.grid import Grid

D_FLOOR = 0.25          # km; about one hexagon: below this a store is "next door"
BETA_STEPS = np.array([-0.4, -0.2, 0.0, 0.2, 0.4])


@dataclass
class Assumptions:
    """Per-run economics (defaults come from categories.yaml; the user can override a subset)."""
    margin: float
    fixed_lakh: float
    size_sqft: float
    fitout_psf: float
    inventory_lakh: float
    spend_per_person: float
    catchment_km: float
    other_density: float
    alpha: float
    beta: float
    deposit_months: float
    brand_mult: float = 1.25
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_config(cls, cat: dict, city_est: dict, tiers: dict, tier: str = "regional_chain", **over):
        e, b = cat["econ"], cat["behaviour"]
        a = cls(margin=e["margin"], fixed_lakh=e["fixed_lakh"], size_sqft=e["size_sqft"], fitout_psf=e["fitout_psf"],
                inventory_lakh=e["inventory_lakh"], spend_per_person=e["spend_per_person"], catchment_km=e["catchment_km"],
                other_density=e["other_density"], alpha=b["alpha"], beta=b["beta"], deposit_months=city_est["deposit_months"],
                brand_mult=tiers[tier])
        for k, v in over.items():
            if v is not None and hasattr(a, k):
                setattr(a, k, float(v))
        return a


class Market:
    """Pre-computed gravity terms for one category in one city."""

    def __init__(self, grid: Grid, eff_pop: np.ndarray, affluence: np.ndarray, comp_attr: np.ndarray, a: Assumptions):
        self.g, self.a = grid, a
        cap = min(a.catchment_km, float(np.nanmax(np.where(np.isfinite(grid.dist), grid.dist, 0))))
        self.ok = (grid.nbr >= 0) & (grid.dist <= cap)
        self.nbr = np.where(self.ok, grid.nbr, 0)
        self.d = np.maximum(np.where(self.ok, grid.dist, 1.0), D_FLOOR).astype("float32")
        self.demand_i = eff_pop * a.spend_per_person * (0.6 + 0.8 * affluence) / 1e5        # Rs lakh / month at stake in zone i
        self.comp_attr = comp_attr
        # unmapped/other stores serving origin i scale with the customers living around it (its whole catchment, not just its own hex)
        self.other_unit = grid.within(eff_pop, a.catchment_km) / 1000.0 * a.other_density
        self.d_typ = max(a.catchment_km / 2, D_FLOOR)
        self.S = {}                                                                         # competitor mass per beta step

    def beta_of(self, step: int) -> float:
        return max(self.a.beta + BETA_STEPS[step], 0.6)

    def mass(self, attr: np.ndarray, step: int) -> np.ndarray:
        """Gravity mass reaching each origin i from stores with attractiveness `attr` (located at hex h)."""
        b, al = self.beta_of(step), self.a.alpha
        w = np.where(self.ok, (attr[self.nbr] ** al) * self.d ** -b, 0.0)
        return w.sum(1)

    def competitor_mass(self, step: int) -> np.ndarray:
        if step not in self.S:
            self.S[step] = self.mass(self.comp_attr, step)
        return self.S[step]

    # ------------------------------------------------------------------ vectorised simulation for a set of candidate zones
    def simulate(self, cand: np.ndarray, rent_lakh: np.ndarray, own_attr: np.ndarray | None = None, draws: int = 200,
                 seed: int = 0, rent_sigma: np.ndarray | None = None, chunk: int = 25) -> dict:
        a, rng = self.a, np.random.default_rng(seed)
        own_attr = np.zeros(self.g.n) if own_attr is None else own_attr
        n = len(cand)
        rev = np.zeros((n, draws), dtype="float32")
        cannib = np.zeros((n, draws), dtype="float32")
        # shared random draws (common random numbers keep comparisons between zones fair)
        spend = np.exp(rng.normal(0, 0.15, draws))
        step = rng.integers(0, len(BETA_STEPS), draws)
        outside = np.exp(rng.normal(0, 0.25, draws))                  # uncertainty in how many unmapped stores exist
        margin = np.clip(a.margin + rng.normal(0, 0.02, draws), 0.02, None)
        rent_z = rng.normal(0, 1, draws)
        S = {s: self.competitor_mass(s) for s in range(len(BETA_STEPS))}
        M = {s: self.mass(own_attr, s) for s in range(len(BETA_STEPS))}
        A_new = a.brand_mult ** a.alpha
        for lo in range(0, n, chunk):
            c = cand[lo:lo + chunk]
            nb, dd, ok = self.nbr[c], self.d[c], self.ok[c]
            dem = np.where(ok, self.demand_i[nb], 0.0)[:, None, :] * spend[None, :, None]                 # (m, D, K)
            Sg = np.stack([S[s][nb] for s in range(len(BETA_STEPS))])[step]                                # (D, m, K)
            Mg = np.stack([M[s][nb] for s in range(len(BETA_STEPS))])[step]
            Sg, Mg = np.transpose(Sg, (1, 0, 2)), np.transpose(Mg, (1, 0, 2))
            bet = np.array([self.beta_of(s) for s in range(len(BETA_STEPS))])[step]
            aij = A_new * dd[:, None, :] ** -bet[None, :, None]
            oth = self.other_unit[nb][:, None, :] * (self.d_typ ** -bet)[None, :, None] * outside[None, :, None]
            den0 = Sg + Mg + oth
            share_with = (Mg + aij) / (den0 + aij)                    # our firm's share with the new store
            share_wo = Mg / den0                                      # without it
            standalone = aij / (Sg + oth + aij)                       # as if we had no other stores
            rev[lo:lo + chunk] = (dem * (share_with - share_wo)).sum(2)
            cannib[lo:lo + chunk] = (dem * (standalone - (share_with - share_wo))).sum(2)
        rent_sig = np.zeros(n) if rent_sigma is None else rent_sigma
        rent = rent_lakh[:, None] * np.exp(rent_sig[:, None] * rent_z[None, :])
        opex = a.fixed_lakh + rent
        profit = rev * margin[None, :] - opex
        return {"revenue": rev, "profit": profit, "cannibalised": cannib, "opex": opex}

    # ------------------------------------------------------------------ summaries
    @staticmethod
    def summarise(sim: dict) -> pd.DataFrame:
        q = lambda x, p: np.percentile(x, p, axis=1)       # noqa: E731
        rev, pr = sim["revenue"], sim["profit"]
        stand = rev + sim["cannibalised"]
        return pd.DataFrame({
            "rev_p10": q(rev, 10), "rev_p50": q(rev, 50), "rev_p90": q(rev, 90),
            "profit_p10": q(pr, 10), "profit_p50": q(pr, 50), "profit_p90": q(pr, 90),
            "p_profit": (pr > 0).mean(1), "cannibal_pct": 100 * np.divide(sim["cannibalised"].mean(1), np.maximum(stand.mean(1), 1e-9)),
            "standalone_rev": stand.mean(1)})

    def upfront_lakh(self, rent_lakh: np.ndarray) -> np.ndarray:
        a = self.a
        return a.fitout_psf * a.size_sqft / 1e5 + a.inventory_lakh + a.deposit_months * rent_lakh

    def overlap(self, zi: int, zj: int, own_step: int = 2) -> float:
        """Share of the catchment demand two candidate stores compete for (0-1), used by the portfolio optimiser."""
        def probs(z):
            ok, nb = self.ok[z], self.nbr[z]
            b = self.beta_of(own_step)
            w = np.where(ok, self.d[z] ** -b, 0.0)
            return dict(zip(nb[ok], w[ok] / max(w[ok].sum(), 1e-9)))
        pi, pj = probs(zi), probs(zj)
        return float(sum(min(v, pj[k]) for k, v in pi.items() if k in pj))
