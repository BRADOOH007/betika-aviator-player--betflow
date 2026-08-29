"""Probe #4: get innerHTML of auto-bet toggle and cash-out toggle (live),
and toggle auto-bet to confirm the class change (NO real bets)."""
import sys, time, json
from playwright.sync_api import sync_playwright
import aviator_bot as ab

phone = sys.argv[1]; password = sys.argv[2]
pw = sync_playwright().start()
browser = pw.firefox.launch(headless=False)
ctx = browser.new_context(
    viewport={"width": 420, "height": 900},
    user_agent="Mozilla/5.0 (Android 11; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
    locale="en-US", timezone_id="Africa/Nairobi",
)
ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
page = ctx.new_page(); page.set_default_timeout(15000)
url = ab.SITES["Betika"]["url"]
page.goto(url, wait_until="domcontentloaded", timeout=45000)
bot = ab.AviatorMartingaleBot(phone=phone, password=password, site="Betika")
bot._page = page
try: bot._login_betika()
except Exception as e: print("login err", e, flush=True)
time.sleep(3)
if "aviator" not in page.url:
    page.goto(url, wait_until="domcontentloaded", timeout=30000); time.sleep(3)
frame = None
for sel in ["#app iframe","iframe[src*='spribe']","iframe[src*='aviator']","iframe[src*='betika']","iframe"]:
    try:
        h = page.locator(sel).first.element_handle(timeout=5000)
        if h:
            f = h.content_frame()
            if f: frame = f; break
    except Exception: continue
if not frame: print("NO IFRAME", flush=True); sys.exit(1)
time.sleep(5)

# click Auto tab
frame.evaluate("""() => { const p=document.querySelectorAll('.bet-control')[0]; for(const b of p.querySelectorAll('button')) if(b.textContent.trim().toLowerCase()==='auto'){b.click();return;} }""")
time.sleep(2)

def snap():
    return frame.evaluate("""() => {
        const out = {};
        const p = document.querySelectorAll('.bet-control')[0];
        function g(sel){ const e = p.querySelector(sel); return e? {html:e.outerHTML.slice(0,400), cls:e.className} : null; }
        out.auto_bet = g('.auto-bet');
        out.cash = g('.cash-out-switcher');
        return out;
    }""")

print("=== BEFORE toggle ===", flush=True)
s1 = snap()
print(json.dumps(s1, indent=2), flush=True)

# Toggle auto-bet with a REAL Playwright coordinates click (native mouse events)
def pw_click(sel):
    try:
        el = frame.locator(sel).first
        el.wait_for(state="visible", timeout=5000)
        el.click()
        return True
    except Exception as e:
        print("  click err", sel, str(e)[:80], flush=True)
        return False

print("auto-bet oval clicked:", pw_click(".bet-control .auto-bet .oval"), flush=True)
time.sleep(1.5)
print("cashout oval clicked:", pw_click(".bet-control .cash-out-switcher .oval"), flush=True)
time.sleep(2.0)

print("=== AFTER auto-bet toggle ===", flush=True)
print(json.dumps(snap(), indent=2), flush=True)

ctx.close(); browser.close(); pw.stop()
print("done", flush=True)
