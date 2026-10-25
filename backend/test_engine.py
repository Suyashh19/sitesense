"""Engine tests (no network, no artifacts needed):  python -m pytest -q   or   python test_engine.py"""
import numpy as np

from app import catalog
from app.engine import gravity
from app.pipeline.grid import build_grid


def _market(comp_extra=0.0):
    city, cats = catalog.city(), catalog.categories()
    g = build_grid({"south": 18.50, "west": 73.82, "north": 18.56, "east": 73.88}, city.h3_resolution)
    a = gravity.Assumptions.from_config(cats["categories"]["pharmacy"], city.estimates, cats["tiers"])
    comp = np.zeros(g.n)
    comp[g.n // 2] = 1.0 + comp_extra
    return g, gravity.Market(g, np.full(g.n, 800.0), np.full(g.n, 0.5), comp, a), a


def test_dna_weights_sum_to_100():
    for c in catalog.categories()["categories"].values():
        assert sum(c["dna"].values()) == 100


def test_gravity_revenue_positive_and_cannibalisation_nonnegative():
    g, m, _ = _market()
    sim = m.simulate(np.array([10, 50]), np.array([1.0, 1.0]), draws=50)
    assert (sim["revenue"] > 0).all() and (sim["cannibalised"] >= -1e-6).all()


def test_more_competition_never_raises_revenue():
    g, m1, _ = _market(0.0)
    _, m2, _ = _market(4.0)
    z = np.array([g.n // 2 + 3])
    r1 = m1.simulate(z, np.array([1.0]), draws=80, seed=1)["revenue"].mean()
    r2 = m2.simulate(z, np.array([1.0]), draws=80, seed=1)["revenue"].mean()
    assert r2 <= r1


def test_own_store_nearby_causes_cannibalisation():
    g, m, a = _market()
    z = g.n // 2 + 2
    own = np.zeros(g.n)
    own[z + 1] = a.brand_mult
    base = m.simulate(np.array([z]), np.array([1.0]), draws=80, seed=2)
    with_own = m.simulate(np.array([z]), np.array([1.0]), own_attr=own, draws=80, seed=2)
    assert with_own["revenue"].mean() < base["revenue"].mean()          # incremental revenue is lower
    assert with_own["cannibalised"].mean() > base["cannibalised"].mean()


def test_ring_sum_includes_self_and_respects_radius():
    g, _, _ = _market()
    ones = np.ones(g.n)
    assert (g.within(ones, 0.1) == 1).all()
    assert (g.within(ones, 1.0) >= g.within(ones, 0.5)).all()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
