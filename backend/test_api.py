"""API smoke test:  python test_api.py"""
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as c:
    meta = c.get("/api/meta").json(); print("meta:", meta["cities"], meta["db"])
    for dom in [d["name"] for d in meta["domains"]]:
        r = c.post("/api/analyze", json={"city": "Pune", "domain": dom}); assert r.status_code == 200, r.text
        j = r.json(); assert not j["empty"]
        print(dom, "| top1:", j["top"][0]["zone_name"], round(j["top"][0]["profit"], 1), "| picks:", len(j["top"]),
              "| cards:", len(j["top"][0]["cards"]), "| clusters:", len(j["clusters"]["fit"]))
    j = c.post("/api/analyze", json={"city": "Bengaluru", "domain": "Café / quick-service restaurant", "max_rent": 60, "k": 6}).json()
    print("tight rent:", "empty" if j["empty"] else len(j["top"]))
    j = c.post("/api/analyze", json={"max_rent": 40}).json(); print("impossible rent empty:", j["empty"])
    s = c.post("/api/simulate", json={"pick": 1, "extra_comp": 3, "rent_pct": 30}).json()
    print("sim:", round(s["mc"]["p_profit"], 2), len(s["mc"]["hist"]), len(s["mc"]["fan"]), s["scenario"]["profit"], len(s["resilience"]))
    t = c.post("/api/analyze", json={}).json()["top"][0]
    n = c.get("/api/nearby", params=dict(city="Pune", domain="Luxury fashion boutique", n_stores=60, lat=t["lat"], lon=t["lon"])).json()
    print("nearby stores:", len(n), c.get("/api/history").json()[0]["top5"][:2])
    assert c.get("/api/health").json()["ok"]
    print("limits:", meta["params"]["n_stores"], meta["sim_params"]["rent_pct"], "llm:", meta["llm_provider"])
    b = c.post("/api/briefing", json={"pick": 2}).json(); print("briefing:", b["source"], b["text"][:90])
    far = c.post("/api/simulate", json={"pick": 1}).json()
    near = c.post("/api/simulate", json={"pick": 1, "extra_competitors": [{"lat": t["lat"], "lon": t["lon"]}] * 3}).json()
    assert near["placed_nearby"] == 3 and near["scenario"]["profit"] < far["scenario"]["profit"]
    print("placed competitor:", round(far["scenario"]["profit"], 2), "->", round(near["scenario"]["profit"], 2))
