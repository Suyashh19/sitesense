"""Captures screenshots of the running prototype (frontend on :5173, backend on :8000) through Chrome's DevTools protocol.
    python docs/capture.py          -> docs/img/shot_*.png
"""
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websocket

OUT = Path(__file__).resolve().parent / "img"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333
W, H = 1440, 1500

proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", f"--remote-debugging-port={PORT}",
                         f"--window-size={W},{H}", "--user-data-dir=" + str(OUT / "_profile"), "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
            page = next(t for t in tabs if t["type"] == "page")
            break
        except Exception:
            time.sleep(0.5)
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=60, max_size=None)
    mid = [0]

    def cmd(method, **params):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": method, "params": params}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == mid[0]:
                return r.get("result", {})

    def js(expr):
        r = cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def wait_for(expr, secs=90):
        t0 = time.time()
        while time.time() - t0 < secs:
            if js(expr):
                return True
            time.sleep(0.8)
        print("TIMEOUT waiting for", expr[:70])
        return False

    def shot(name, clip=None):
        p = {"format": "png"}
        if clip:
            p["clip"] = {**clip, "scale": 1}
        data = cmd("Page.captureScreenshot", **p)["data"]
        (OUT / f"shot_{name}.png").write_bytes(base64.b64decode(data))
        print("saved", name)

    def click_text(selector, text):
        return js("(()=>{const e=[...document.querySelectorAll(%s)].find(x=>x.textContent.trim().includes(%s));if(e){e.click();return true}return false})()" % (json.dumps(selector), json.dumps(text)))

    cmd("Page.enable")
    cmd("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
    cmd("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
    cmd("Page.navigate", url="http://localhost:5173/")
    wait_for("document.querySelectorAll('.cat').length>=5")
    wait_for("document.querySelectorAll('.site').length>=3 && !document.querySelector('.busy')", 180)   # let the first automatic search finish
    time.sleep(2)

    # 1. pharmacy results
    click_text(".cat", "Pharmacy")
    time.sleep(1)
    click_text("button", "Find best locations")
    time.sleep(2)
    wait_for("document.querySelectorAll('.site').length>=3 && !document.querySelector('.busy') && !document.body.innerText.includes('sports & gym equipment outlets')", 150)
    time.sleep(3)
    print("banner:", js("(document.querySelector('.err')||{}).innerText"), "| first site:", js("(document.querySelector('.site h4')||{}).innerText"))
    shot("results")
    # 2. profit layer
    click_text(".seg button", "Profit")
    time.sleep(3)
    shot("profit_map")
    click_text(".seg button", "Market fit")
    # 3. site detail crop: right column card
    time.sleep(2)
    box = js("(()=>{const e=[...document.querySelectorAll('.card')].find(x=>x.textContent.includes('Why this area'));if(!e)return null;e.scrollIntoView();const r=e.getBoundingClientRect();return {x:r.x,y:r.y+window.scrollY,w:r.width,h:r.height}})()")
    wait_for("document.querySelector('.recharts-wrapper')", 150)
    time.sleep(2)
    box = js("(()=>{const e=[...document.querySelectorAll('.card')].find(x=>x.textContent.includes('Why this area'));const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})()")
    if box:
        shot("site_detail", {"x": box["x"], "y": box["y"], "width": box["w"], "height": min(box["h"], H - box["y"] - 5)})
    # 4. what-if
    js("document.querySelector('.main, section.main').scrollTo(0,0)")
    click_text("nav.tabs button", "What-if")
    time.sleep(1)
    js("""(()=>{const r=document.querySelector('section.main input[type=range]');const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(r,30);r.dispatchEvent(new Event('input',{bubbles:true}))})()""")
    time.sleep(0.5)
    click_text("button", "Run the what-if")
    wait_for("document.body.innerText.toLowerCase().includes('rank before') && !document.body.innerText.includes('Re-running')", 200)
    time.sleep(2)
    shot("what_if")
    # 5. plan
    click_text("nav.tabs button", "Expansion plan")
    time.sleep(1)
    click_text("button", "Build the plan")
    wait_for("document.body.innerText.includes('Recommended opening order')", 120)
    time.sleep(2)
    shot("plan")
    # 6. data page
    click_text("nav.tabs button", "Data & trust")
    wait_for("document.body.innerText.includes('How well do the learned models work')", 30)
    time.sleep(2)
    shot("data_trust")
    # 7. ask box
    click_text("nav.tabs button", "Find sites")
    time.sleep(1)
    js("""(()=>{const i=document.querySelector('.ask input');const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(i,'top 3 fashion sites near Koregaon Park');i.dispatchEvent(new Event('input',{bubbles:true}))})()""")
    time.sleep(0.5)
    click_text(".ask button", "Go")
    wait_for("document.body.innerText.includes('I understood')", 90)
    wait_for("document.querySelectorAll('.site').length>=1", 90)
    time.sleep(3)
    shot("ask")
    ws.close()
finally:
    proc.terminate()
sys.exit(0)
