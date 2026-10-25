"""API smoke test on real artifacts:  python test_api.py"""
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as c:
    m = c.get("/api/meta").json(); assert m["ready"]
    print("categories:", [x["key"] for x in m["categories"]])
    for k in [x["key"] for x in m["categories"]]:
        r = c.post("/api/analyze", json={"category": k}); assert r.status_code == 200, r.text
        j = r.json(); assert not j["empty"], j
        t = j["top"][0]
        print(k, "|", t["name"], "| BOI", t["boi"], "| profit", t["profit"], "| conf", t["confidence"], "|", j["model_used"], "| funnel", j["funnel"])
    j = c.post("/api/analyze", json={"category": "food", "budget_lakh": 5}).json(); print("tiny budget ->", j.get("message"))
    top = c.post("/api/analyze", json={"category": "pharmacy", "own_stores": [{"lat": 18.52, "lon": 73.85}]}).json()["top"]
    print("zone:", c.get(f"/api/zone/{top[0]['h3']}", params={"category": "pharmacy"}).status_code)
    e = c.post("/api/economics", json={"category": "pharmacy", "h3": top[0]["h3"]}); print("economics:", e.status_code, e.json()["sensitivity"][:2])
    s = c.post("/api/scenario", json={"category": "pharmacy", "new_rent_change_pct": 30, "new_competitors": [{"lat": top[0]["lat"], "lon": top[0]["lon"]}]}).json(); print("scenario:", s["rows"][:2])
    p = c.post("/api/plan", json={"category": "fashion", "k": 3}).json(); print("plan:", p.get("feasible"), p.get("net_profit"), p.get("greedy_net_profit"), p.get("binding"))
    a = c.post("/api/ask", json={"text": "best 3 pharmacy sites near Baner under 60 lakh"}).json(); print("ask:", a["executed_as"], a["result"]["empty"] if a["result"] else None)
    print("briefing:", c.post("/api/briefing", json={"category": "food"}).json()["text"][:160])
    print("layer:", len(c.get("/api/layer/food").json()["h3"]), "| history:", len(c.get("/api/history").json()), "| pipeline ready:", c.get("/api/pipeline").json()["ready"])
