"""Builds docs/SiteSense_Project_Overview.pdf (6 pages) from the real pipeline output.

    python docs/build_overview.py        (needs backend/data/artifacts and docs/img/app.png)

All numbers come from backend/data/artifacts/status.json and the YAML config, so the document cannot drift from the app.
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ART = ROOT / "backend" / "data" / "artifacts"
CHROME = os.environ.get("CHROME", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
st = json.loads((ART / "status.json").read_text(encoding="utf-8"))
M = st["meta"]
cats = yaml.safe_load((ROOT / "backend/config/categories.yaml").read_text(encoding="utf-8"))
city = yaml.safe_load((ROOT / "backend/config/city_pune.yaml").read_text(encoding="utf-8"))
zones = pd.read_parquet(ART / "zones.parquet")
cat_cols = len(pd.read_parquet(ART / "cat_food.parquet").columns)
CK = list(cats["categories"])
NAME = {k: cats["categories"][k]["name"] for k in CK}
TEAL, NAVY, MUTE, LINE, SOFT = "#0e7c86", "#0b1f33", "#5d6b7e", "#dde4ec", "#e8f4f5"
n = lambda v: f"{int(round(v)):,}"                                    # noqa: E731
osm_total = sum(M["osm_counts"].values())
img = "data:image/png;base64," + base64.b64encode((HERE / "img" / "app.png").read_bytes()).decode()


def comp_stats(k):
    c = pd.read_parquet(ART / f"comps_{k}.parquet")
    return len(c), int((c.tier == "national_chain").sum()), int((c.tier == "regional_chain").sum())


# ------------------------------------------------------------------ diagrams (inline SVG)
def box(x, y, w, h, title, sub="", fill=SOFT, stroke=TEAL, tc=NAVY):
    t = f'<text x="{x + w / 2}" y="{y + (h / 2 - 2 if sub else h / 2 + 4)}" text-anchor="middle" font-size="11.5" font-weight="700" fill="{tc}">{title}</text>'
    s = f'<text x="{x + w / 2}" y="{y + h / 2 + 12}" text-anchor="middle" font-size="9.5" fill="{MUTE}">{sub}</text>' if sub else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>{t}{s}'


def arrow(x1, y1, x2, y2, c=TEAL):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="1.8" marker-end="url(#a)"/>'


DEFS = f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="{TEAL}"/></marker></defs>'


def d_problem():
    fs = [("Population", "many people nearby", 20, 14), ("Competitors", "who else sells here", 265, 14), ("Rent & costs", "what the shop costs to run", 510, 14),
          ("Accessibility", "metro, bus, roads", 20, 150), ("Your own stores", "do they overlap?", 265, 150), ("Customer spending", "how much people can spend", 510, 150)]
    s = ""
    for t, sub, x, y in fs:
        s += box(x, y, 210, 46, t, sub, fill="#fff")
        s += arrow(x + 105, y + (46 if y < 100 else 0), 375, 88 if y < 100 else 112)
    s += f'<rect x="255" y="86" width="240" height="28" rx="14" fill="{TEAL}"/><text x="375" y="105" text-anchor="middle" font-size="12" font-weight="700" fill="#fff">One candidate location: is it good?</text>'
    return f'<svg viewBox="0 0 740 200" width="100%">{DEFS}{s}</svg>'


def d_pipeline():
    steps = [("1 Collect", "OpenStreetMap +\nWorldPop"), ("2 Divide", "city into small\nhexagons"), ("3 Score", "10 factors, weighted\nper business"),
             ("4 Learn", "what proven sites\nlook like"), ("5 Simulate", "customers choosing\nstores: profit range"), ("6 Explain", "reasons, risks,\nconfidence, plan")]
    s, w, g = "", 108, 14
    for i, (t, sub) in enumerate(steps):
        x = 6 + i * (w + g)
        l1, l2 = sub.split("\n")
        s += f'<rect x="{x}" y="10" width="{w}" height="78" rx="10" fill="{SOFT if i % 2 == 0 else "#fff"}" stroke="{TEAL}" stroke-width="1.4"/>'
        s += f'<text x="{x + w / 2}" y="34" text-anchor="middle" font-size="12.5" font-weight="700" fill="{NAVY}">{t}</text>'
        s += f'<text x="{x + w / 2}" y="54" text-anchor="middle" font-size="9.5" fill="{MUTE}">{l1}</text><text x="{x + w / 2}" y="67" text-anchor="middle" font-size="9.5" fill="{MUTE}">{l2}</text>'
        if i < 5:
            s += arrow(x + w + 1, 49, x + w + g - 1, 49)
    return f'<svg viewBox="0 0 740 98" width="100%">{DEFS}{s}</svg>'


def d_funnel():
    z = M["grid"]["zones"]
    rows = [(f"{n(z)} hexagons cover Pune", 1.0, "#9fd3d6"), (f"{n(M['grid']['analysed'])} are built-up and analysed", 0.99, "#6fbcc2"),
            ("~220 strongest candidates get a full simulation", 0.8, "#3a9ba4"), ("Top 5 sites after your limits and spacing", 0.62, TEAL)]
    s = ""
    for i, (t, f, c) in enumerate(rows):
        w = 700 * f
        s += f'<rect x="{(740 - w) / 2}" y="{8 + i * 30}" width="{w}" height="25" rx="5" fill="{c}"/><text x="370" y="{25 + i * 30}" text-anchor="middle" font-size="11" font-weight="700" fill="#fff">{t}</text>'
    return f'<svg viewBox="0 0 740 132" width="100%">{s}</svg>'


def d_dna():
    fg = cats["factor_groups"]
    cw, ch, x0, y0 = 92, 21, 170, 34
    s = ""
    for j, k in enumerate(CK):
        s += f'<text x="{x0 + j * cw + cw / 2}" y="22" text-anchor="middle" font-size="10" font-weight="700" fill="{NAVY}">{NAME[k].split(" ")[0].replace("&", "")}</text>'
    for i, (g, gn) in enumerate(fg.items()):
        s += f'<text x="{x0 - 8}" y="{y0 + i * ch + 14}" text-anchor="end" font-size="10" fill="{NAVY}">{gn}</text>'
        for j, k in enumerate(CK):
            v = cats["categories"][k]["dna"][g]
            a = min(v / 24, 1)
            col = f"rgba(14,124,134,{0.08 + 0.85 * a:.2f})"
            s += f'<rect x="{x0 + j * cw}" y="{y0 + i * ch}" width="{cw - 3}" height="{ch - 3}" rx="4" fill="{col}"/>'
            s += f'<text x="{x0 + j * cw + cw / 2 - 1}" y="{y0 + i * ch + 13}" text-anchor="middle" font-size="10" font-weight="700" fill="{"#fff" if a > .5 else NAVY}">{v}</text>'
    return f'<svg viewBox="0 0 640 {y0 + 10 * ch + 4}" width="100%">{s}</svg>'


def d_layers():
    labels = {"amenity": "Amenities (food, health, banks, colleges)", "highway_major": "Main roads (trunk to tertiary)", "leisure": "Leisure (gyms, parks, pitches)",
              "healthcare": "Healthcare places", "shop": "Shops", "highway_bus": "Bus stops", "office": "Offices", "public_transport": "Public-transport stations",
              "railway": "Railway / metro entrances", "tourism": "Tourist attractions"}
    items = sorted(M["osm_counts"].items(), key=lambda kv: -kv[1])
    mx, s = max(v for _, v in items), ""
    for i, (k, v) in enumerate(items):
        w = 330 * v / mx
        s += f'<text x="232" y="{16 + i * 21}" text-anchor="end" font-size="10" fill="{NAVY}">{labels.get(k, k)}</text>'
        s += f'<rect x="240" y="{6 + i * 21}" width="{max(w, 2)}" height="15" rx="3" fill="{TEAL}"/><text x="{245 + w}" y="{18 + i * 21}" font-size="10" font-weight="700" fill="{NAVY}">{n(v)}</text>'
    return f'<svg viewBox="0 0 640 {len(items) * 21 + 10}" width="100%">{s}</svg>'


def d_arch():
    s = DEFS
    s += box(10, 8, 220, 62, "Browser (React + TypeScript)", "Leaflet map · Recharts · guided UI", fill="#fff")
    s += box(260, 8, 230, 62, "API (FastAPI, Python)", "analyse · economics · what-if · plan · ask", fill=SOFT)
    s += box(520, 8, 210, 62, "Models and maths (engine)", "XGBoost · LightGBM · CatBoost · SHAP", fill="#fff")
    s += arrow(232, 39, 258, 39) + arrow(492, 39, 518, 39)
    s += box(10, 110, 220, 56, "Data pipeline (run once)", "Overpass · WorldPop · ohsome", fill="#fff")
    s += box(260, 110, 230, 56, "Stored results", "Parquet + joblib files; SQL history", fill=SOFT)
    s += box(520, 110, 210, 56, "Database (optional)", "SQLite, or PostgreSQL + PostGIS", fill="#fff")
    s += arrow(232, 138, 258, 138) + arrow(490, 138, 518, 138)
    s += f'<line x1="375" y1="72" x2="375" y2="108" stroke="{TEAL}" stroke-width="1.8" marker-end="url(#a)"/>'
    s += f'<text x="383" y="94" font-size="9.5" fill="{MUTE}">loads at start-up</text>'
    s += box(10, 190, 720, 34, "Configuration (YAML): city, five business categories, OSM tags, weights, economics - no code changes to add a city or category", fill="#fff", stroke=MUTE)
    return f'<svg viewBox="0 0 740 232" width="100%">{s}</svg>'


def d_valid():
    keys = [k for k in CK if M["categories"][k]["enabled"]]
    gw, s = 150, ""
    x0, base, H = 60, 150, 120
    for gy in (0, .25, .5, .75, 1.0):
        y = base - gy * H
        s += f'<line x1="{x0 - 6}" y1="{y}" x2="640" y2="{y}" stroke="{LINE}"/><text x="{x0 - 10}" y="{y + 3}" text-anchor="end" font-size="9" fill="{MUTE}">{int(gy * 100)}%</text>'
    series = [("SiteSense model", TEAL, lambda m: m["m2"]["recall_top10"]), ("Index only", "#9fb3c8", lambda m: m["m2"]["baseline_index_top10"]),
              ("Population only", "#d7a24a", lambda m: m["m2"]["baseline_population_top10"]), ("Random guess", "#c9ced6", lambda m: m["m2"]["random_top10"])]
    for gi, k in enumerate(keys):
        m = M["categories"][k]
        for si, (nm, col, f) in enumerate(series):
            v = float(f(m))
            x = x0 + 10 + gi * gw + si * 31
            s += f'<rect x="{x}" y="{base - v * H}" width="26" height="{v * H}" rx="3" fill="{col}"/><text x="{x + 13}" y="{base - v * H - 3}" text-anchor="middle" font-size="8.5" font-weight="700" fill="{NAVY}">{v * 100:.0f}</text>'
        s += f'<text x="{x0 + 10 + gi * gw + 62}" y="{base + 14}" text-anchor="middle" font-size="10" font-weight="700" fill="{NAVY}">{NAME[k].split(" ")[0]}</text>'
    for si, (nm, col, _) in enumerate(series):
        s += f'<rect x="{70 + si * 140}" y="182" width="11" height="11" rx="2" fill="{col}"/><text x="{86 + si * 140}" y="191" font-size="10" fill="{NAVY}">{nm}</text>'
    return f'<svg viewBox="0 0 660 200" width="100%">{s}</svg>'


# ------------------------------------------------------------------ tables
def t_ai():
    rows = [("Opportunity index (BOI)", "Scores every zone 0-100 on 10 factors; the weights differ per business (the “Retail DNA”).", "Simple weighted formula - fully explainable"),
            ("Viability model", "Learns what proven locations look like. “Proven” = an established chain outlet already trades in the zone.", "XGBoost, positive-unlabeled learning"),
            ("Location ranker", "Orders zones from best to worst for each business; higher rent never raises a score.", "LightGBM LambdaRank"),
            ("Rent model", f"Spreads {M['rent']['n_localities']} known locality rents to every zone, with a likely range.", "CatBoost + validation on unseen localities"),
            ("Profit simulation", "Shoppers split their spending between stores by distance and attractiveness; repeated 300 times with uncertain inputs.", "Huff gravity model + Monte Carlo"),
            ("Cannibalisation", "Estimates how much of a new store’s sales would come from your own nearby stores.", "Same gravity model"),
            ("Explanations", "Turns model contributions into plain reasons, risk flags and a confidence level.", "SHAP + rules"),
            ("Zone types", "Groups areas into 6 types (office hub, student belt, high street…).", "K-means on PCA"),
            ("Expansion planner", "Chooses the best set of stores together, within budget and spacing.", "OR-Tools CP-SAT"),
            ("Ask in English", "Turns a sentence into a safe, whitelisted search.", "Rule-based parser (no chatbot)")]
    h = "".join(f"<tr><td><b>{a}</b></td><td>{b}</td><td>{c}</td></tr>" for a, b, c in rows)
    return f'<table class="t"><thead><tr><th>Part</th><th>What it does</th><th>Technique</th></tr></thead><tbody>{h}</tbody></table>'


def t_sources():
    rows = [("OpenStreetMap (Overpass API)", f"{n(osm_total)} map features in 10 queries", "Shops, amenities, offices, healthcare, leisure, tourism, bus stops, rail, roads", "Real", "ODbL"),
            ("WorldPop 2020, India 1 km raster", f"1 raster (19.1 MB) → {n(zones['pop'].sum())} people over the area", "Residents per zone (then spread by OSM activity)", "Modelled", "CC BY 4.0"),
            ("ohsome API (HeiGIT)", "history of mapped shops, 2021 → 2026", "Area growth trend", "Real (service was down at build time; flagged)", "ODbL"),
            ("Locality price table", f"{len(city['localities'])} Pune localities listed ({M['rent']['n_localities']} fall inside the grid)", "Property price per sq ft → affluence and rent", "Estimate (our table)", "Own"),
            ("Metro stations list", f"{len(city['metro_stations'])} stations (+145 OSM rail)", "Distance to metro / rail", "Curated + real", "Own / ODbL"),
            ("Category settings (YAML)", "5 businesses", "Margins, fixed costs, store size, spend per person, chain names", "Assumptions", "Own"),
            ("Basemap tiles", "OpenStreetMap standard", "Map background", "Real", "ODbL")]
    h = "".join(f"<tr><td><b>{a}</b></td><td>{b}</td><td>{c}</td><td>{d}</td><td>{e}</td></tr>" for a, b, c, d, e in rows)
    return f'<table class="t"><thead><tr><th>Source</th><th>Size</th><th>Used for</th><th>Type</th><th>Licence</th></tr></thead><tbody>{h}</tbody></table>'


def t_cats():
    h = ""
    for k in CK:
        c, nat, reg = comp_stats(k)
        m = M["categories"][k]
        h += (f"<tr><td><b>{NAME[k]}</b></td><td>{n(c)}</td><td>{nat} / {reg}</td><td>{len(cats['categories'][k]['chains'])}</td>"
              f"<td>{m['labels']['positives']}</td><td>{'Learned models + index' if m['enabled'] else 'Index only (too few labels)'}</td></tr>")
    return ('<table class="t"><thead><tr><th>Business</th><th>Competitors mapped</th><th>National / regional chains</th><th>Chain names listed</th>'
            f'<th>Proven (positive) zones</th><th>Ranking method</th></tr></thead><tbody>{h}</tbody></table>')


FEATURES = [("Ask in plain English", "Type a sentence; see how it was understood"), ("5 business types", "Sports, food, fashion, pharmacy, electronics"),
            ("Your limits", "Start-up budget, rent cap, area, store size"), ("4 strategies", "Balanced, max profit, play safe, best fit"),
            ("Your existing stores", "Click the map; avoids stealing own sales"), ("Brand strength", "New shop, regional or national chain"),
            ("Hexagon map, 4 layers", "Market fit, profit, competition, population"), ("Ranked top sites", "Profit as weak / likely / strong range"),
            ("Reasons for each site", "Top 3 drivers from SHAP"), ("Risks and confidence", "Competition, rent, access, data quality, downside"),
            ("Why #1 beats #2", "Plain-language comparison"), ("Zone profile", "Every number labelled real or estimated"),
            ("Unit economics", "Where the money goes + sensitivity table"), ("What-if", "Rent change or a new rival on the map"),
            ("Expansion plan", "Best set of 2-6 stores, compared with greedy"), ("Briefing", "Short summary for a manager"),
            ("Data and trust page", "Build log, lineage, model scores, Retail DNA")]


def t_features():
    h = "".join(f'<span class="tag" title="{b}"><b>{i + 1}</b> {a}</span>' for i, (a, b) in enumerate(FEATURES))
    return f'<h3>The 17 product features</h3><div>{h}</div>'


CSS = f"""
@page{{size:A4;margin:11mm 12mm 12mm 12mm}}
*{{box-sizing:border-box}}
body{{margin:0;font:8.9pt/1.42 Arial,Helvetica,sans-serif;color:#14202e}}
h1{{font-size:21pt;margin:0}} h2{{font-size:13pt;color:{TEAL};margin:0 0 4px;padding-bottom:3px;border-bottom:2px solid {TEAL}}}
h3{{font-size:10pt;margin:8px 0 3px;color:{NAVY}}} p{{margin:3px 0 5px}} ul,ol{{margin:3px 0 5px;padding-left:17px}} li{{margin:1px 0}}
.page{{page-break-after:always;min-height:272mm}} .page:last-child{{page-break-after:auto}}
.banner{{background:{NAVY};color:#fff;border-radius:10px;padding:13px 18px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center}}
.banner small{{opacity:.8;font-size:9pt}} .banner b{{color:#4fd1c5}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:12px}} .cols3{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
.card{{border:1px solid {LINE};border-radius:8px;padding:7px 10px;background:#fff}} .card.soft{{background:{SOFT};border-color:#b9dfe2}}
.kpi{{text-align:center;border:1px solid {LINE};border-radius:8px;padding:6px 4px;background:#fff}} .kpi b{{display:block;font-size:15pt;color:{TEAL}}} .kpi span{{font-size:7.8pt;color:{MUTE}}}
table.t{{border-collapse:collapse;width:100%;font-size:8.1pt;margin:3px 0 6px}} table.t th{{background:{SOFT};text-align:left;padding:3px 5px;border-bottom:1.5px solid {TEAL};font-size:7.8pt}}
table.t td{{padding:3px 5px;border-bottom:1px solid {LINE};vertical-align:top}}
.fig{{text-align:center;margin:4px 0}} .cap{{font-size:7.8pt;color:{MUTE};text-align:center;margin:0 0 6px}}
.quote{{border-left:4px solid {TEAL};background:{SOFT};padding:6px 10px;border-radius:0 6px 6px 0;font-size:8.6pt}}
.warn{{border-left:4px solid #b7791f;background:#fcf1d9;padding:5px 10px;border-radius:0 6px 6px 0;font-size:8.4pt}}
img.shot{{width:100%;border:1px solid {LINE};border-radius:8px}}
.tag{{display:inline-block;background:{SOFT};color:#0b5d65;border:1px solid #b9dfe2;border-radius:99px;padding:0 7px;font-size:7.8pt;margin:1px 1px}}
.ref li{{font-size:8.1pt}}
"""

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SiteSense - Project Overview</title><style>{CSS}</style></head><body>

<!-- ===================== PAGE 1: PROBLEM ===================== -->
<div class="page">
<div class="banner"><div><h1>Site<b>Sense</b></h1><small>AI-powered Retail Expansion Intelligence Platform · Pune</small></div>
<div style="text-align:right"><small>Triwizathon · Problem Statement 1<br>Suyash Patil · Harshad Khatale · Tanuja Saravale · Madanaj Sagar<br>Walchand College of Engineering</small></div></div>

<h2>1. The problem statement</h2>
<div class="quote"><b>Problem Statement 1 - Retail Expansion Intelligence Platform.</b> Choosing the right place for a new store is hard. A location may have many people
but also strong competition, high rent or poor access. Doing this by manual research or gut feeling leads to poor investments and missed chances.</div>
<h3>In simple words</h3>
<p>A retail chain wants to open its next shop. There are thousands of possible places in a city. <b>Which place will earn the most, which are risky, and why?</b>
We must build software that answers this with data and AI, and explains its answer.</p>
<div class="fig">{d_problem()}</div>
<p class="cap">Figure 1. A location is never good or bad on one factor. The platform must weigh all of these together.</p>

<h3>What the challenge asks, and where we answer it</h3>
<table class="t"><thead><tr><th>The challenge asks for</th><th>Our answer in SiteSense</th></tr></thead><tbody>
<tr><td>Use geographic and demographic data, competitors, existing stores, access and operating costs</td><td>Real OpenStreetMap + WorldPop data, {M['rent']['n_localities']} locality prices, metro/bus/road access, your own stores, estimated rent</td></tr>
<tr><td>Estimate customer demand and predict commercial viability</td><td>Gravity-model simulation (demand → sales → profit) and a viability model learned from where chains already trade</td></tr>
<tr><td>Rank candidate locations</td><td>Opportunity index + learned ranker, ordered by the strategy you choose</td></tr>
<tr><td>Evidence-based explanations: strengths, risks, comparison with alternatives</td><td>Top reasons, risk flags, confidence level and a “why #1 beats #2” sentence for every site</td></tr>
<tr><td>AI must do real analysis (not just a chatbot)</td><td>Five trained or optimised models do the work; language is only used to read your request, never to invent answers</td></tr>
<tr><td>State assumptions, data sources and limitations</td><td>Every number is labelled real, modelled or estimated; a Data &amp; trust page lists sources, assumptions and model scores</td></tr>
</tbody></table>
<div class="cols3" style="margin-top:6px">
<div class="kpi"><b>5</b><span>business types</span></div><div class="kpi"><b>{n(M['grid']['zones'])}</b><span>hexagon zones (≈10 ha each)</span></div>
<div class="kpi"><b>{n(osm_total)}</b><span>real map features used</span></div></div>
</div>

<!-- ===================== PAGE 2: SOLUTION ===================== -->
<div class="page">
<h2>2. Our solution</h2>
<p><b>SiteSense tells a retail owner where to open the next store.</b> It splits Pune into small hexagons, measures what surrounds each one, learns what successful locations look like,
simulates how customers would choose between stores, and explains every recommendation in plain language. The owner picks a business type and limits; the app does the rest.</p>
<div class="fig">{d_pipeline()}</div><p class="cap">Figure 2. The six steps from raw data to an explained recommendation.</p>

<div class="fig"><img class="shot" src="{img}" style="max-height:92mm;object-fit:cover;object-position:top"></div>
<p class="cap">Figure 3. The working app: guided steps (left), hexagon map with ranked pins, and plain-language results.</p>
<div class="cols">
<div>
<h3>What the owner does</h3>
<ol><li><b>Choose</b> the business (or just type: “best 3 pharmacy sites near Baner under 60 lakh”).</li>
<li><b>Set limits</b>: start-up money, highest rent, area, store size.</li>
<li><b>Pick what matters</b>: balanced, max profit, play it safe, or best market fit.</li>
<li><b>Add existing stores</b> by clicking the map, so new sites do not steal their sales.</li>
<li><b>Read the answer</b>: top sites with a weak / likely / strong profit range, reasons, risks and confidence.</li>
<li><b>Test it</b>: what if rent rises 30%, or a rival opens next door? Or plan 2-6 stores together.</li></ol>
</div>
<div>
<h3>Why it is different</h3>
<ul><li><b>Honest ranges</b>, never a single made-up number.</li><li><b>Explainable</b>: each site lists its top reasons and risks.</li>
<li><b>Category-aware</b>: a pharmacy and a fashion store need different things (the “Retail DNA”).</li>
<li><b>Transparent data</b>: every value says if it is real or estimated.</li></ul>
<div class="fig">{d_funnel()}</div><p class="cap">Figure 4. How the engine narrows the whole city to a short list (shown live in the app).</p>
</div></div>
</div>

<!-- ===================== PAGE 3: HOW AI WORKS ===================== -->
<div class="page">
<h2>2.1 How the AI works</h2>
<p>There is <b>no sales data</b> for any shop in the area, so we avoid pretending. We learn from <i>where established chains already trade</i> (a weak but real signal),
test the models on whole neighbourhoods they never saw, and simulate sales with stated assumptions.</p>
{t_ai()}
<div class="cols"><div>
<h3>The “Retail DNA”: what matters for each business</h3>
<div class="fig">{d_dna()}</div><p class="cap">Figure 5. Weights (0-100, each column adds up to 100). Darker = matters more. Stored in a config file, shown in the app.</p></div>
<div><h3>How a score and a profit are made</h3>
<div class="card soft"><b>Opportunity score</b> = Σ weight × factor score ÷ 100, for the 10 factors.<br>
Bands: <span class="tag">Prime 80+</span><span class="tag">Strong 65-79</span><span class="tag">Viable 50-64</span><span class="tag">Marginal 35-49</span><span class="tag">Avoid &lt;35</span></div>
<div class="card" style="margin-top:6px"><b>Profit</b> = sales × margin − rent − fixed costs.<br><b>Sales</b> = what each nearby neighbourhood spends × the share this store wins against rivals, summed over the catchment.
Repeated 300 times with varied spend, margin, rent, distance sensitivity and number of unmapped stores. We report the 10th, 50th and 90th percentile and the chance of profit.</div>
<div class="card" style="margin-top:6px"><b>Safeguards</b>: the defining chain outlet is hidden from the model’s inputs (no cheating); every zone is scored by a model that never saw its neighbourhood;
rent can only lower a score; a plain-index fallback is used when labels are too few.</div></div></div>
<div class="cols"><div>
<h2 style="margin-top:8px">2.2 Feature counts</h2>
<table class="t"><tbody>
<tr><td><b>17</b></td><td>product features a user can use (list on the right)</td></tr>
<tr><td><b>{len(zones.columns)}</b></td><td>measured or estimated values stored for every zone (people, workers, students, prices, rent, access, growth…)</td></tr>
<tr><td><b>{cat_cols}</b></td><td>values per zone and business (competition, complementors, 10 factor scores, index, profit range, model scores)</td></tr>
<tr><td><b>10</b></td><td>factor groups (FG1-FG10) that feed the opportunity index</td></tr>
<tr><td><b>19</b></td><td>inputs the viability and ranking models learn from (18 zone features + the viability score)</td></tr>
<tr><td><b>9</b></td><td>AI components built (of 11 in the plan; the fast surrogate model and a learned growth forecaster are left for later)</td></tr></tbody></table></div>
<div>{t_features()}</div></div>
</div>

<!-- ===================== PAGE 4: DATA & FEATURES ===================== -->
<div class="page">
<h2>3. Datasets and features</h2>
<h3>Data sources</h3>{t_sources()}
<div class="cols"><div>
<h3>What was collected from OpenStreetMap</h3><div class="fig">{d_layers()}</div><p class="cap">Figure 6. Map features fetched for the study area ({osm_total:,} in total).</p></div>
<div><h3>The study area</h3>
<table class="t"><tbody>
<tr><td>Area covered</td><td>Pune, Pimpri-Chinchwad, Hinjewadi, Kharadi (rectangle {city['bbox']['south']}-{city['bbox']['north']}°N, {city['bbox']['west']}-{city['bbox']['east']}°E)</td></tr>
<tr><td>Zone shape and size</td><td>H3 hexagons, resolution {M['grid']['res']}, about 10.5 hectares each</td></tr>
<tr><td>Zones</td><td>{n(M['grid']['zones'])} total, {n(M['grid']['analysed'])} built-up and analysed</td></tr>
<tr><td>Population in area</td><td>{zones['pop'].sum() / 1e6:.2f} million (WorldPop 2020)</td></tr>
<tr><td>Median residents within 1 km</td><td>{n(zones['pop_1km'].median())}</td></tr>
<tr><td>Local property prices</td><td>Rs {n(zones['price_psf'].min())} to {n(zones['price_psf'].max())} per sq ft (smoothed estimate)</td></tr>
<tr><td>Estimated shop rent</td><td>Rs {zones['rent_psf'].min():.0f} to {zones['rent_psf'].max():.0f} per sq ft per month</td></tr>
<tr><td>Zone types found</td><td>6 (office hub, student belt, dense residential, transit node, high street, emerging periphery)</td></tr>
<tr><td>Build time</td><td>about {st['seconds'] / 60:.0f} minutes from cached downloads; stored results about 11 MB</td></tr></tbody></table></div></div>
<h3>Data by business type</h3>{t_cats()}
</div>

<!-- ===================== PAGE 5: TECH + FEASIBILITY ===================== -->
<div class="page">
<h2>4. Tech stack</h2>
<div class="fig">{d_arch()}</div><p class="cap">Figure 7. Architecture. The slow work (downloading, training, simulating all zones) runs once; the app then answers in seconds.</p>
<table class="t"><thead><tr><th>Layer</th><th>Technology</th><th>Why we chose it</th></tr></thead><tbody>
<tr><td>Frontend</td><td>React, TypeScript, Vite, Leaflet, h3-js, Recharts, Lucide icons</td><td>Fast, typed UI; Leaflet draws the hexagon map; h3-js converts zone ids to shapes</td></tr>
<tr><td>Backend</td><td>Python, FastAPI, Pydantic, Uvicorn</td><td>Validated inputs, automatic API docs, easy to run with the ML code</td></tr>
<tr><td>Data and geo</td><td>Pandas, NumPy, SciPy, Uber H3, Rasterio, PyArrow (Parquet)</td><td>Hexagon grid, raster reading, compact fast storage</td></tr>
<tr><td>Machine learning</td><td>XGBoost, LightGBM, CatBoost, scikit-learn, SHAP</td><td>Strong on small tabular data; SHAP gives explanations</td></tr>
<tr><td>Optimisation</td><td>Google OR-Tools (CP-SAT)</td><td>Picks the best group of stores under budget and spacing</td></tr>
<tr><td>Storage</td><td>SQLite by default; PostgreSQL + PostGIS optional (SQLAlchemy, GeoAlchemy2)</td><td>Run history and spatial queries; zero set-up locally</td></tr>
<tr><td>Delivery</td><td>Docker Compose, YAML config, optional LLM key (rephrases only)</td><td>One-command run; add a city or business by editing YAML</td></tr></tbody></table>

<h2 style="margin-top:8px">5. Feasibility</h2>
<div class="cols"><div>
<h3>Technical feasibility: it already runs</h3>
<ul><li>Full pipeline works end to end on real Pune data and builds in about {st['seconds'] / 60:.0f} minutes.</li>
<li>A search finishes in seconds on a laptop; unit tests cover the gravity maths (more rivals never raise sales, own stores cause overlap).</li>
<li>Only free tools and open data are used - no paid API is needed.</li></ul>
<h3>Does the learning work? (tested on unseen neighbourhoods)</h3>
<p>“Of the zones that really host an established chain, how many land in the model’s top 10%?”</p></div>
<div><div class="fig">{d_valid()}</div><p class="cap">Figure 8. Share of proven zones found in the top 10% (higher is better). Random guessing scores 10%. Sports has too few labels to test.</p></div></div>
<p>The learned model beats a population-only rule and a plain index in every business it was tested on
(e.g. pharmacy {float(M['categories']['pharmacy']['m2']['recall_top10']) * 100:.0f}% vs {float(M['categories']['pharmacy']['m2']['baseline_population_top10']) * 100:.0f}% for population only). These checks show the model finds
<i>chain-like</i> locations; they are not proof of profit.</p>
</div>

<!-- ===================== PAGE 6: VIABILITY, LIMITS, REFERENCES ===================== -->
<div class="page">
<h2>5.1 Viability: would it be useful and sustainable?</h2>
<div class="cols"><div>
<h3>Who needs it and why</h3>
<ul><li><b>Retail chains and franchise owners</b> who open stores every year and today rely on brokers and gut feeling.</li>
<li><b>Small entrepreneurs</b> choosing a first shop, who cannot afford consultants.</li>
<li><b>Real-estate and mall teams</b> who want to judge which tenant fits a location.</li></ul>
<p>It saves research time, makes trade-offs visible (rent vs footfall vs rivals) and shows <i>why</i>, so decisions can be defended to investors.</p>
<h3>How it can sustain itself</h3>
<ul><li>Software subscription per chain or per city.</li><li>Paid reports for a single location decision.</li><li>Premium data upload: a client’s real sales make the model far better.</li></ul>
<h3>Why it can scale</h3>
<ul><li>A new city = one YAML file and a rebuild; a new business = one block of weights, tags and economics.</li><li>Open data, no per-user data cost; all heavy work is pre-computed.</li></ul></div>
<div><h3>Honest limitations</h3>
<div class="warn"><ul style="margin:0">
<li><b>No real sales data.</b> Profit comes from a simulation with our assumptions (spend per person, margins, store density). It is decision support, not a guarantee.</li>
<li><b>“Proven” means a chain is there</b>, not that it is profitable.</li>
<li><b>OpenStreetMap is incomplete.</b> Only 25 sports shops are mapped in Pune, so sports uses the plain index and shows lower confidence.</li>
<li><b>Rent model is basic.</b> On unseen localities it is off by about {M['rent']['loo_mape'] * 100:.0f}%, similar to a simple price rule ({M['rent']['baseline_mape'] * 100:.0f}%).</li>
<li><b>Growth data</b> was unavailable at build time, so the growth factor is neutral and flagged.</li>
<li>Population is a modelled 1 km raster; prices come from a {M['rent']['n_localities']}-locality table; the study area is a rectangle (not the exact city border); no zoning, lease or online-demand data.</li></ul></div>
<h3>Next steps</h3>
<ul><li>Clip the grid to the real city boundary; retry growth data.</li><li>Calibrate with real sales from one pilot chain.</li>
<li>Add live rent listings and footfall data; more cities.</li><li>Fast surrogate models, a learned growth forecaster, user accounts and PDF reports.</li></ul></div></div>

<h2 style="margin-top:6px">6. References</h2>
<ol class="ref">
<li>Triwizathon, <i>Problem Statement 1: Retail Expansion Intelligence Platform</i>.</li>
<li>Huff, D. L. (1963). A probabilistic analysis of shopping center trade areas. <i>Land Economics</i>, 39(1). &nbsp;Reilly, W. J. (1931). <i>The Law of Retail Gravitation</i>.</li>
<li>Lundberg, S. &amp; Lee, S.-I. (2017). A unified approach to interpreting model predictions (SHAP). <i>NeurIPS</i>.</li>
<li>Chen, T. &amp; Guestrin, C. (2016). XGBoost. <i>KDD</i>. &nbsp;Ke, G. et al. (2017). LightGBM. <i>NeurIPS</i>. &nbsp;Prokhorenkova, L. et al. (2018). CatBoost. <i>NeurIPS</i>.</li>
<li>Burges, C. (2010). From RankNet to LambdaRank to LambdaMART. <i>Microsoft Research TR-2010-82</i>.</li>
<li>Elkan, C. &amp; Noto, K. (2008). Learning classifiers from only positive and unlabeled data. <i>KDD</i>.</li>
<li>Roberts, D. R. et al. (2017). Cross-validation strategies for data with spatial structure. <i>Ecography</i>, 40(8).</li>
<li>OpenStreetMap contributors, ODbL 1.0, openstreetmap.org/copyright; Overpass API; ohsome API (HeiGIT).</li>
<li>WorldPop (2020). Gridded population, India 1 km, CC BY 4.0, worldpop.org.</li>
<li>Uber H3 hexagonal index, h3geo.org. &nbsp;Google OR-Tools CP-SAT. &nbsp;FastAPI, React, Leaflet, scikit-learn, PostGIS.</li>
<li>Government of India, Digital Personal Data Protection Act 2023 (no personal data about shoppers is used).</li></ol>
<p class="cap" style="text-align:left">Map data © OpenStreetMap contributors. All figures in this document are produced by the project’s own build ({st['finished'].replace('T', ' ')} UTC) and are estimates unless marked real.</p>
</div>
</body></html>"""

out_html = HERE / "SiteSense_Project_Overview.html"
out_pdf = HERE / "SiteSense_Project_Overview.pdf"
out_html.write_text(HTML, encoding="utf-8")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", "--no-pdf-header-footer",
                f"--print-to-pdf={out_pdf}", out_html.as_uri()], check=True, timeout=180)
import pymupdf  # noqa: E402
d = pymupdf.open(out_pdf)
d.set_metadata({"title": "SiteSense - Project Overview", "author": "Suyash Patil, Harshad Khatale, Tanuja Saravale, Madanaj Sagar"})
print("pages:", len(d), "| size MB:", round(os.path.getsize(out_pdf) / 1e6, 2))
for i, p in enumerate(d):
    p.get_pixmap(dpi=70).save(HERE / "img" / f"page{i + 1}.png")
sys.exit(0)
