"""Builds docs/SiteSense_Demo_Script.pdf: a timed 5-minute presentation script mapped to the Round 2 evaluation sheet.
    python docs/build_script.py      (needs docs/img/shot_*.png from docs/capture.py)
"""
import base64
import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CHROME = os.environ.get("CHROME", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
st = json.loads((ROOT / "backend/data/artifacts/status.json").read_text(encoding="utf-8"))
M = st["meta"]
osm_total = sum(M["osm_counts"].values())
TEAL, NAVY, MUTE, LINE, SOFT = "#0e7c86", "#0b1f33", "#5d6b7e", "#dde4ec", "#e8f4f5"
WPM = 120                                                          # calm pace, including short pauses for clicks


def img64(name):
    return "data:image/png;base64," + base64.b64encode((HERE / "img" / f"shot_{name}.png").read_bytes()).decode()


def crop(name, top, h, width=1440, caption="", left=0, w=None):
    """A cropped band of a screenshot: source pixels left/top, region width w (default: rest of the image) and height h."""
    w = w or (width - left)
    return (f'<figure><div style="aspect-ratio:{w}/{h};overflow:hidden;border:1px solid {LINE};border-radius:6px">'
            f'<img src="{img64(name)}" style="width:{width / w * 100:.3f}%;max-width:none;display:block;margin-left:-{left / w * 100:.3f}%;margin-top:-{top / w * 100:.3f}%"></div>'
            f'<figcaption>{caption}</figcaption></figure>')


# ------------------------------------------------------------------------------ the script (spoken text only in `say`)
SEG = [
    dict(t="0:00", end="0:25", who="Speaker 1", title="Opening", crit="", say=(
        "Good morning. We are Team SiteSense from Walchand College of Engineering. Our problem statement is simple: help a retail chain "
        "choose the best place for its next store, using AI. Today we will show what we built since the last evaluation, how it works, "
        "and what comes next for the final submission."),
        show="Stay on the home screen. No clicking yet.", fig=""),
    dict(t="0:25", end="1:20", who="Speaker 2", title="Progress since Evaluation 1", crit="Criterion 1: Development progress (10 marks)", say=(
        "First, our progress. Our first prototype ran on made-up city data. Since then we have rebuilt it on real data. "
        f"We now use more than {osm_total // 1000} thousand real places from OpenStreetMap, like shops, offices, hospitals, bus stops and roads. "
        "We add real population data from WorldPop, about seven million people. We split Pune into six and a half thousand small hexagon zones, "
        "and we measure what surrounds each one. The app now covers five business types: sports, food, fashion, pharmacy and electronics. "
        "Nine AI parts are working, from ranking to profit simulation to explanations. We also redesigned the screen so a shop owner can follow every step. "
        "And everything about a city or a business now lives in a simple settings file, not in the code."),
        show="Open the <b>4 Data &amp; trust</b> tab and point to the pipeline list and the counts.", fig="data"),
    dict(t="1:20", end="1:50", who="Speaker 3", title="Demo 1: find the best sites", crit="Criterion 3: Demonstration (10 marks)", say=(
        "Now the demo. I choose what I sell: pharmacy. I can set limits like budget or rent, or I can simply type a sentence in the Just ask box. "
        "Then I press Find best locations. In a few seconds the map shows how good every area is. Darker means a better match. "
        "The numbered pins are the top five sites."),
        show="Click <b>Pharmacy</b>, then <b>Find best locations</b>. Point at the map, the pins and the strip that shows how the city was narrowed down.", fig="results"),
    dict(t="1:50", end="2:30", who="Speaker 3", title="Demo 2: understand one site", crit="Criterion 3: Demonstration", say=(
        "Here is site number one, near Deccan Gymkhana. It shows the expected profit as a range: a weak case, a likely case and a strong case. "
        "We never give one made-up number. On the right we explain why: many helpful businesses nearby, an affluent area, and room for another store. "
        "Below that we show the risks, a confidence level, and why this site beats number two. Every figure is labelled real or estimated."),
        show="Click pin <b>1</b>. Point at <i>Why this area</i>, <i>What could go wrong</i> and the confidence note.", fig="detail"),
    dict(t="2:30", end="2:55", who="Speaker 3", title="Demo 3: what-if", crit="Criterion 3: Demonstration", say=(
        "Next, what-if. If rents rise thirty percent, we re-run everything. Profits fall, and sites two and three swap places. "
        "An owner can also drop a new rival on the map. And if you add your own stores, we estimate how much a new store would take sales from them."),
        show="Open <b>2 What-if</b>, move the slider to +30%, press <b>Run the what-if</b>.", fig="whatif"),
    dict(t="2:55", end="3:20", who="Speaker 3", title="Demo 4: expansion plan", crit="Criterion 3: Demonstration", say=(
        "Last in the demo, the expansion plan. For three stores, the planner picks the best group together, so the stores do not steal each other's customers. "
        "The Data and trust page shows where every number comes from, and how well each model was tested."),
        show="Open <b>3 Expansion plan</b>, press <b>Build the plan</b>. Then flash the model-score table on the Data &amp; trust tab.", fig="plan"),
    dict(t="3:20", end="4:20", who="Speaker 4", title="Technology and problem solving", crit="Criterion 2: Technical quality (10 marks)", say=(
        "Now the technology. The front end is React with TypeScript and a Leaflet map. The back end is Python with FastAPI. "
        "For AI we use XGBoost, LightGBM and CatBoost, SHAP for explanations, and Google OR-Tools to plan several stores. "
        "We solved real problems along the way. The map data server kept failing, so we added retries and saved copies of the data. "
        "Our first profit numbers were too high, so we recalibrated the simulation. To stop the model from cheating, we hide the chain shops it learns from, "
        "and we test it on whole neighbourhoods it has never seen. Where data is too thin, like sports shops, the app says so and uses a simpler method. "
        "We also added tests, input checks and clear error messages."),
        show="Point at the architecture picture on the slide (or the overview PDF, page 5).", fig="arch"),
    dict(t="4:20", end="4:40", who="Speaker 4", title="Team and mentor feedback", crit="Criterion 3: Team understanding", say=(
        "Our team shared the work. [NAME 1] built the data pipeline. [NAME 2] built the models. [NAME 3] built the interface. "
        "[NAME 4] handled testing and documents. Following mentor feedback, we [ONE SENTENCE: what you changed]."),
        show="Fill the square brackets before presenting. Each member says their own part in one sentence.", fig=""),
    dict(t="4:40", end="5:00", who="Speaker 1", title="Roadmap and close", crit="Criterion 3: Roadmap", say=(
        "For the final round we will use the exact city border, retry our growth data, test with real sales from one shop chain, "
        "add live rent listings, and put the app online. Thank you. We are happy to take your questions."),
        show="Return to the results screen.", fig=""),
]
for s in SEG:
    s["words"] = len(re.sub(r"\[[^\]]*\]", "x", s["say"]).split())
total_words = sum(s["words"] for s in SEG)
total_sec = round(total_words / WPM * 60)


def figure(kind):
    if kind == "data":
        return crop("data_trust", 60, 600, left=340, caption="Data &amp; trust tab: the six pipeline steps and where each number comes from.")
    if kind == "results":
        return crop("results", 60, 800, left=340, caption="Find sites: hexagon map, ranked pins, the strip showing how 6,480 zones were narrowed down, and the first site card.")
    if kind == "detail":
        return crop("site_detail", 0, 760, width=526, caption="Site detail: reasons, risks, confidence and a comparison with the next site.")
    if kind == "whatif":
        return crop("what_if", 600, 480, left=340, caption="What-if: rents +30%. Sites 2 and 3 swap places and profits drop.")
    if kind == "plan":
        return crop("plan", 600, 600, left=340, caption="Expansion plan: three stores chosen together, with total cost and overlap.")
    if kind == "arch":
        b64 = base64.b64encode((HERE / "img" / "arch.png").read_bytes()).decode()
        return f'<figure><img src="data:image/png;base64,{b64}" style="width:100%;border:1px solid {LINE};border-radius:6px"><figcaption>Architecture: the slow work runs once; the app then answers in seconds.</figcaption></figure>'
    return ""


def seg_html(s):
    fig = figure(s["fig"])
    narrow = s["fig"] == "detail"
    crit = f'<span class="crit">{s["crit"]}</span>' if s["crit"] else ""
    return f"""<div class="seg"><div class="head"><span class="time">{s['t']} – {s['end']}</span><b>{s['title']}</b>{crit}<span class="who">{s['who']} · {s['words']} words · about {round(s['words'] / WPM * 60)} s</span></div>
<div class="body{' narrow' if narrow else ''}"><div><div class="say"><span class="lbl">SAY</span>{s['say'].replace('[', '<mark>[').replace(']', ']</mark>')}</div>
<div class="do"><span class="lbl">DO</span>{s['show']}</div></div><div>{fig}</div></div></div>"""


CSS = f"""
@page{{size:A4;margin:11mm 12mm}}
*{{box-sizing:border-box}} body{{margin:0;font:9.4pt/1.45 Arial,Helvetica,sans-serif;color:#14202e}}
h1{{font-size:22pt;margin:0}} h2{{font-size:13pt;color:{TEAL};margin:0 0 5px;padding-bottom:3px;border-bottom:2px solid {TEAL}}} p{{margin:3px 0 6px}}
.page{{page-break-after:always}} .page:last-child{{page-break-after:auto}}
.banner{{background:{NAVY};color:#fff;border-radius:10px;padding:14px 18px;margin-bottom:10px}} .banner small{{opacity:.85}} .banner b{{color:#4fd1c5}}
table.t{{border-collapse:collapse;width:100%;font-size:8.8pt;margin:4px 0 8px}} table.t th{{background:{SOFT};text-align:left;padding:4px 6px;border-bottom:1.5px solid {TEAL}}}
table.t td{{padding:4px 6px;border-bottom:1px solid {LINE};vertical-align:top}}
.seg{{border:1px solid {LINE};border-radius:8px;margin:0 0 9px;overflow:hidden;break-inside:avoid}}
.head{{background:{SOFT};padding:5px 9px;display:flex;gap:9px;align-items:center;flex-wrap:wrap;border-bottom:1px solid {LINE}}}
.time{{background:{TEAL};color:#fff;border-radius:99px;padding:1px 9px;font-weight:700;font-size:8.6pt}} .crit{{font-size:8pt;color:#0b5d65;border:1px solid #b9dfe2;border-radius:99px;padding:0 7px;background:#fff}}
.who{{margin-left:auto;font-size:8pt;color:{MUTE}}}
.body{{display:grid;grid-template-columns:1fr 1.25fr;gap:10px;padding:8px 10px;align-items:start}} .body.narrow{{grid-template-columns:1.5fr 1fr}}
.say{{border-left:4px solid {TEAL};padding:2px 0 2px 9px;margin-bottom:6px;font-size:9.6pt}}
.do{{background:#fcf1d9;border-radius:6px;padding:4px 8px;font-size:8.6pt}} .lbl{{display:inline-block;font-weight:700;font-size:7.4pt;letter-spacing:.06em;color:#fff;background:{NAVY};border-radius:3px;padding:0 5px;margin-right:6px}}
.do .lbl{{background:#b7791f}} mark{{background:#ffe9a8;padding:0 2px;border-radius:2px}}
figure{{margin:0}} figcaption{{font-size:7.6pt;color:{MUTE};margin-top:2px}} .box{{font-size:8.4pt;background:{SOFT};border-radius:6px;padding:6px 8px}}
.kpi{{display:inline-block;text-align:center;border:1px solid {LINE};border-radius:8px;padding:5px 12px;margin:0 6px 4px 0}} .kpi b{{display:block;font-size:15pt;color:{TEAL}}}
ul{{margin:3px 0 6px;padding-left:18px}} li{{margin:2px 0}}
.q{{break-inside:avoid;margin:0 0 5px}} .q b{{color:{TEAL}}}
"""

timeline = "".join(f"<tr><td><b>{s['t']} – {s['end']}</b></td><td>{s['title']}</td><td>{s['who']}</td><td>{s['crit'].split(':')[0] if s['crit'] else '–'}</td><td>{s['words']}</td></tr>" for s in SEG)

QA = [("Is the data real?", f"The map data is real (OpenStreetMap, {osm_total:,} places) and so is the population (WorldPop). Property prices, margins and spending per person are our own estimates, and the app labels them as estimates."),
      ("Where does the profit number come from?", "From a simulation of shoppers choosing between stores by distance and attractiveness, repeated 300 times with uncertain inputs. We have no real sales data, so it is decision support, not a guarantee."),
      ("How do you know the AI works?", "We tested on whole neighbourhoods the model never saw. It finds chain-like locations much better than population alone, for example pharmacy 52% against 8% (Data &amp; trust page). That shows it finds proven-looking sites, not proof of profit."),
      ("Why does Sports use a simpler method?", "Only 25 sports shops are mapped in OpenStreetMap for Pune, so there are too few examples to learn from. The app says this and lowers its confidence."),
      ("Is this just a chatbot?", "No. The AI does the analysis: ranking, simulation and explanations. The Just ask box only reads the request and fills the form; it never writes the answers."),
      ("What are the limits?", "Study area is a rectangle, not the exact city border; the growth data was unavailable at build time; rent model is basic; no zoning or online-demand data."),
      ("What will you do next?", "Exact city border, real sales from one chain to calibrate, live rent listings, deployment online, reports and accounts.")]
qa = "".join(f'<div class="q"><b>Q. {q}</b><br>{a}</div>' for q, a in QA)

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SiteSense - 5-minute demo script</title><style>{CSS}</style></head><body>
<div class="page">
<div class="banner"><h1>Site<b>Sense</b> · 5-minute presentation script</h1><small>Triwizathon · Round 2 Development Phase · Walchand College of Engineering<br>
Suyash Patil · Harshad Khatale · Tanuja Saravale · Madanaj Sagar</small></div>

<h2>How this script matches the evaluation sheet (30 marks)</h2>
<table class="t"><thead><tr><th style="width:24%">Criterion (10 marks each)</th><th>What the judges look for</th><th style="width:30%">Where we show it</th></tr></thead><tbody>
<tr><td><b>1. Development progress and implementation</b></td><td>Substantial progress since Evaluation 1; core features built as planned; milestones achieved</td><td>0:25 – 1:20 progress; the live demo proves it works</td></tr>
<tr><td><b>2. Technical quality and problem solving</b></td><td>Good technology choices, sound architecture, clean code, solving technical challenges, using mentor feedback</td><td>3:20 – 4:20 technology and problems solved; 4:20 mentor feedback</td></tr>
<tr><td><b>3. Demonstration and team understanding</b></td><td>Working features, reasons for decisions, each member's contribution, clear roadmap</td><td>1:20 – 3:20 demo; 4:20 team; 4:40 roadmap</td></tr></tbody></table>

<h2>Timeline</h2>
<table class="t"><thead><tr><th>Time</th><th>Part</th><th>Who</th><th>Criterion</th><th>Words</th></tr></thead><tbody>{timeline}
<tr><td colspan="4"><b>Total</b></td><td><b>{total_words}</b> (≈ {total_sec // 60}:{total_sec % 60:02d} at {WPM} words/min)</td></tr></tbody></table>

<h2>The problem in one line (judges already know it)</h2>
<p>“Help a retail chain choose the best location for its next store using AI, and explain why.” We say this once and move on.</p>
<h2>Numbers you can quote</h2>
<span class="kpi"><b>{osm_total:,}</b>real places used</span><span class="kpi"><b>{M['grid']['zones']:,}</b>hexagon zones</span><span class="kpi"><b>5</b>business types</span>
<span class="kpi"><b>9</b>AI parts working</span><span class="kpi"><b>17</b>product features</span><span class="kpi"><b>6.9 M</b>people covered</span>
<h2>Before you present</h2>
<ul><li><b>Fill the yellow brackets</b> on the team slide: who built what, and one sentence on mentor feedback. We did not invent these.</li>
<li>Check the claim “first prototype ran on made-up data” matches what you showed in Evaluation 1. Change it if not.</li>
<li>Start both servers (<i>run-backend.bat</i>, <i>run-frontend.bat</i>) and open http://localhost:5173. Do one practice search so the data is warm.</li>
<li>Pick <b>Pharmacy</b> for the demo: it uses all the learned models. Do not start with Sports (it uses the simple method).</li>
<li>Practise once with a timer. If you run long, shorten the technology part, not the demo.</li></ul>
</div>

<div class="page">
<h2>The script</h2>
{''.join(seg_html(s) for s in SEG[:3])}
</div>
<div class="page">
{''.join(seg_html(s) for s in SEG[3:6])}
</div>
<div class="page">
{''.join(seg_html(s) for s in SEG[6:])}
</div><div class="page"><h2>If the judges ask (short answers)</h2>{qa}
<p style="font-size:8pt;color:{MUTE}">Screenshots are from the running prototype (Pharmacy, Pune). Map © OpenStreetMap contributors.</p>
</div>
</body></html>"""

out_html, out_pdf = HERE / "SiteSense_Demo_Script.html", HERE / "SiteSense_Demo_Script.pdf"
out_html.write_text(HTML, encoding="utf-8")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", "--no-pdf-header-footer",
                f"--print-to-pdf={out_pdf}", out_html.as_uri()], check=True, timeout=180)
import pymupdf  # noqa: E402
d = pymupdf.open(out_pdf)
print("pages:", len(d), "| MB:", round(os.path.getsize(out_pdf) / 1e6, 2), "| words:", total_words, "| est. seconds:", total_sec)
for i, p in enumerate(d):
    p.get_pixmap(dpi=80).save(HERE / "img" / f"s{i + 1}.png")
