"""Probe #2: dump bet-control panel internals + detect betting-window state.
NO real bets."""
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

def dump_panels():
    return frame.evaluate("""() => {
        const out = [];
        const panels = document.querySelectorAll('.bet-control');
        panels.forEach((p, i) => {
            const info = { index: i, classList: p.className };
            const btns = [...p.querySelectorAll('button')].map(b => ({
                txt: (b.textContent||'').trim().slice(0,25),
                disabled: b.disabled,
                cls: (b.className||'').slice(0,40),
            }));
            const inputs = [...p.querySelectorAll('input')].map(inp => ({
                val: inp.value, placeholder: inp.placeholder, cls: (inp.className||'').slice(0,40),
            }));
            const shall = [...document.querySelectorAll('*')].filter(el => el.className && String(el.className).match(/round|time|count|wait|cancel|active|result/i) && el.children.length===0).slice(0,15).map(el => ({t:(el.textContent||'').trim().slice(0,30), c:String(el.className).slice(0,50)}));
            info.buttons = btns; info.inputs = inputs;
            info.live_indicators = shall;
            out.push(info);
        });
        return out;
    }""")

print("=== initial panel dump ===", flush=True)
print(json.dumps(dump_panels(), indent=2), flush=True)

# Betting-window detection via existing helper
try:
    print("betting_window_open =", ab._is_betting_window_open(frame), flush=True)
except Exception as e:
    print("betting helper err", e, flush=True)

print("=== sampling 20s of button states + any changing text ===", flush=True)
prev = None
for i in range(20):
    snap = frame.evaluate("""() => {
        const p = document.querySelector('.bet-control');
        if (!p) return {btns:[]};
        return {
          btns: [...p.querySelectorAll('button')].map(b => (b.textContent||'').trim().slice(0,25)),
          resultHist: (document.querySelector('.result-history')||{}).innerText?.slice(0,200) || '',
          anyHistorySpans: document.querySelectorAll('.result-history span, [class*="history"] span').length,
        };
    }""")
    if json.dumps(snap) != prev:
        print(f"t={i}s", json.dumps(snap), flush=True)
        prev = json.dumps(snap)
    time.sleep(1)

ctx.close(); browser.close(); pw.stop()
print("done", flush=True)
