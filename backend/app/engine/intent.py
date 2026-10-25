"""M-11 Intent parser: plain English -> one validated call to a whitelisted tool (BR-12).

Rule-based (no model needed) and fully deterministic. Every extracted value is grounded: the category must exist in the
configuration, numbers must be inside allowed ranges, and the executed request is echoed back so the user can see and edit it.
"""
import re

from .store import store

WORDS = re.compile(r"[a-z]{3,}")
STOP = {"and", "the", "for", "with", "stores", "store", "retail", "equipment", "shops", "shop", "outlets"}


def _category_keywords() -> dict[str, set]:
    kw = {}
    for key, c in store.cats["categories"].items():
        text = f"{c['name']} {c['blurb']} " + " ".join(v for sel in c["competitors"] for vals in sel.values() for v in vals)
        kw[key] = {w for w in WORDS.findall(text.lower().replace("_", " ")) if w not in STOP}
    kw.setdefault("sports", set()).update({"gym", "fitness"})
    return kw


def parse(text: str) -> dict:
    t = text.lower()
    out = {"tool": "rank_sites", "args": {}, "missing": [], "notes": []}
    args = out["args"]
    kw = _category_keywords()
    score = {k: sum(1 for w in ws if re.search(rf"\b{w}\w*", t)) for k, ws in kw.items()}
    best = max(score, key=score.get)
    if score[best] > 0 and list(score.values()).count(score[best]) == 1:
        args["category"] = best
    elif score[best] > 0:
        out["missing"].append("category")
        out["notes"].append("more than one business type matched")
    else:
        out["missing"].append("category")

    m = re.search(r"(?:budget|under|below|within|upto|up to|max(?:imum)?)?\s*(?:rs\.?|₹|inr)?\s*(\d+(?:\.\d+)?)\s*(crore|cr|lakh|lac|lakhs)\b", t)
    if m:
        v = float(m.group(1)) * (100 if m.group(2).startswith("cr") else 1)
        if 5 <= v <= 5000:
            args["budget_lakh"] = v
        else:
            out["notes"].append(f"budget of {v:g} lakh is outside the supported range (5 to 5000 lakh) and was ignored")
    m = re.search(r"rent\s*(?:under|below|max|maximum|cap|of|<)?\s*(?:rs\.?|₹)?\s*(\d{2,4})", t)
    if m and 20 <= int(m.group(1)) <= 1000:
        args["max_rent_psf"] = float(m.group(1))
    m = re.search(r"(?:top|best|show|find|give)\s*(\d+)|(\d+)\s*(?:best|top|new)?\s*(?:locations?|sites?|spots?|stores?|shops?|places?)", t)
    if m:
        n = int(m.group(1) or m.group(2))
        if "plan" in t or "open" in t or "expansion" in t:
            out["tool"], args["k"] = "plan_expansion", max(2, min(n, 6))
        else:
            args["n_results"] = max(1, min(n, 10))
    if out["tool"] == "rank_sites" and re.search(r"\b(plan|roll ?out|expansion plan|open\s+\d+)", t):
        out["tool"] = "plan_expansion"
        args.setdefault("k", 3)
    if re.search(r"\b(safe|safer|low[- ]risk|conservative|downside)\b", t):
        args["strategy"] = "Play it safe"
    elif re.search(r"\b(max(?:imi[sz]e)? profit|most profit|highest profit|biggest return)\b", t):
        args["strategy"] = "Maximise profit"
    for loc in store.city.localities:
        if re.search(rf"\b{re.escape(loc['name'].lower())}\b", t):
            args["near"] = {"name": loc["name"], "lat": loc["lat"], "lon": loc["lon"], "radius_km": 3.0}
            break
    out["grounded"] = "category" not in out["missing"]
    if out["missing"]:
        out["clarify"] = "Which type of business do you want to open? " + ", ".join(c["name"] for c in store.cats["categories"].values())
    summary = [f"{out['tool'].replace('_', ' ')}"]
    if "category" in args:
        summary.append(store.cats["categories"][args["category"]]["name"])
    for k, label in (("budget_lakh", "budget Rs {:g} lakh"), ("max_rent_psf", "rent cap Rs {:g}/sq ft"), ("k", "{:g} stores"),
                     ("n_results", "top {:g}")):
        if k in args:
            summary.append(label.format(args[k]))
    if "near" in args:
        summary.append(f"near {args['near']['name']}")
    if "strategy" in args:
        summary.append(args["strategy"])
    out["executed_as"] = " | ".join(summary)
    return out
