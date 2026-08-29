"""Quick probe: log in, reach iframe, then sample the round DOM every second
for ~30s to discover how the crash multiplier / history updates per round.
NO real bets."""
import sys, time, json
from playwright.sync_api import sync_playwright
import aviator_bot as ab

phone = sys.argv[1]
password = sys.argv[2]

pw = sync_playwright().start()
browser = pw.firefox.launch(headless=False)
ctx = browser.new_context(
    viewport={"width": 420, "height": 900},
    user_agent="Mozilla/5.0 (Android 11; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
    locale="en-US", timezone_id="Africa/Nairobi",
)
ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
page = ctx.new_page()
page.set_default_timeout(15000)
url = ab.SITES["Betika"]["url"]
print("[probe] nav", url, flush=True)
page.goto(url, wait_until="domcontentloaded", timeout=45000)
bot = ab.AviatorMartingaleBot(phone=phone, password=password, site="Betika")
bot._page = page
try:
    bot._login_betika()
except Exception as e:
    print("[probe] login err", e, flush=True)
time.sleep(3)
if "aviator" not in page.url:
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

frame = None
for sel in ["#app iframe","iframe[src*='spribe']","iframe[src*='aviator']","iframe[src*='betika']","iframe"]:
    try:
        h = page.locator(sel).first.element_handle(timeout=5000)
        if h:
            f = h.content_frame()
            if f:
                frame = f; print("[probe] iframe", sel, flush=True); break
    except Exception:
        continue
if not frame:
    print("[probe] NO IFRAME", flush=True); sys.exit(1)

# Probe selectors that may expose the round result / current multiplier
SELECTOR_PROBES = [
    "[class*='coef']", "[class*='multiplier']", "[class*='crash']",
    "[class*='fly']", "[class*='round']", "[class*='history'] span",
    ".result-history span", "[class*='bets'] span",
]

def sample():
    out = {}
    for s in SELECTOR_PROBES:
        try:
            vals = frame.evaluate(
                "(s)=>{const els=document.querySelectorAll(s);return els.length?"+
                "[...els].slice(0,8).map(e=>({t:(e.innerText||'').trim(),h:e.children.length})):[]}", s)
            if vals:
                out[s] = vals
        except Exception:
            pass
    return out

print("[probe] sampling 30s:", flush=True)
for i in range(30):
    snap = sample()
    print(f"[probe] t={i}s", json.dumps(snap), flush=True)
    time.sleep(1)

ctx.close(); browser.close(); pw.stop()
print("[probe] done", flush=True)
