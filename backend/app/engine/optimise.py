"""M-9 Expansion planner: choose which k sites to open together (F-14), using OR-Tools CP-SAT.

    maximise   sum_z profit_z * x_z  -  sum_{z<z'} kappa_{zz'} * y_{zz'}
    subject to sum_z x_z = k,  sum_z upfront_z * x_z <= budget,  x_z + x_z' <= 1 for stores closer than the minimum spacing,
               y_{zz'} >= x_z + x_z' - 1                         (pairwise cannibalisation is paid only when both are opened)

kappa is the revenue two new stores take from each other, from the gravity-model catchment overlap (M-8). The plan is compared
with the greedy "just take the top-k" plan so the benefit of optimising jointly is visible.
"""
import numpy as np
from ortools.sat.python import cp_model

from ..pipeline.grid import haversine
from . import gravity

SCALE = 1000


def plan(market: gravity.Market, g, cands: list[dict], k: int, budget: float | None, min_spacing_km: float) -> dict:
    n = len(cands)
    idx = [c["z"] for c in cands]
    profit = np.array([c["profit_p50"] for c in cands])
    rev = np.array([c["rev_p50"] for c in cands])
    cost = np.array([c["upfront"] for c in cands])
    kappa = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine(g.lat[idx[i]], g.lon[idx[i]], g.lat[idx[j]], g.lon[idx[j]])
            if d < 2 * market.a.catchment_km:
                kappa[i, j] = kappa[j, i] = gravity.Market.overlap(market, idx[i], idx[j]) * 0.5 * min(rev[i], rev[j]) * market.a.margin
    m = cp_model.CpModel()
    x = [m.NewBoolVar(f"x{i}") for i in range(n)]
    m.Add(sum(x) == k)
    if budget:
        m.Add(sum(int(cost[i] * 10) * x[i] for i in range(n)) <= int(budget * 10))
    y = {}
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine(g.lat[idx[i]], g.lon[idx[i]], g.lat[idx[j]], g.lon[idx[j]])
            if d < min_spacing_km:
                m.Add(x[i] + x[j] <= 1)
            elif kappa[i, j] > 1e-3:
                y[i, j] = m.NewBoolVar(f"y{i}_{j}")
                m.Add(y[i, j] >= x[i] + x[j] - 1)
    m.Maximize(sum(int(profit[i] * SCALE) * x[i] for i in range(n)) - sum(int(kappa[i, j] * SCALE) * v for (i, j), v in y.items()))
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = 8
    s.parameters.num_workers = 4
    st = s.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"feasible": False, "message": "No set of that many stores satisfies the budget and spacing limits. Lower the number of stores or relax the limits."}
    chosen = [i for i in range(n) if s.Value(x[i])]

    def net(sel):
        return float(sum(profit[i] for i in sel) - sum(kappa[i, j] for a, i in enumerate(sel) for j in sel[a + 1:]))
    greedy = []
    for i in np.argsort(-profit):                                     # naive plan: best individual sites that fit
        if all(haversine(g.lat[idx[i]], g.lon[idx[i]], g.lat[idx[j]], g.lon[idx[j]]) >= min_spacing_km for j in greedy) \
                and (not budget or cost[greedy + [i]].sum() <= budget):
            greedy.append(int(i))
        if len(greedy) == k:
            break
    order = sorted(chosen, key=lambda i: -profit[i])                   # opening order: strongest first
    binding = []
    if budget and cost[chosen].sum() > 0.97 * budget:
        binding.append("budget")
    if any(haversine(g.lat[idx[a]], g.lon[idx[a]], g.lat[idx[b]], g.lon[idx[b]]) < 1.25 * min_spacing_km for a in chosen for b in chosen if a < b):
        binding.append("minimum spacing")
    return {"feasible": True, "chosen": [cands[i] | {"step": n_ + 1} for n_, i in enumerate(order)],
            "net_profit": net(chosen), "greedy_net_profit": net(greedy) if len(greedy) == k else None,
            "upfront": float(cost[chosen].sum()), "cannibalisation_cost": float(sum(kappa[a, b] for a in chosen for b in chosen if a < b)),
            "binding": binding, "solver": s.StatusName(st)}
