"""Probe #3: Open Auto tab on panel 1 and dump its full internal DOM.
Focus: auto-bet toggle, auto-cashout toggle, rounds field, stake field.
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

# Click Auto tab on panel 1
try:
    frame.evaluate("""() => {
        const panel = document.querySelectorAll('.bet-control')[0];
        if (!panel) return;
        for (const b of panel.querySelectorAll('button'))
            if (b.textContent.trim().toLowerCase() === 'auto') { b.click(); return; }
    }""")
    print("clicked Auto tab", flush=True)
except Exception as e:
    print("auto tab click err", e, flush=True)
time.sleep(2)

# Dump the ENTIRE panel DOM with element details (tags, classes, text, attrs)
dump = frame.evaluate("""() => {
    function desc(el, depth) {
        if (depth > 6) return null;
        const out = {
            tag: el.tagName.toLowerCase(),
            cls: typeof el.className === 'string' ? el.className.slice(0,80) : '',
            txt: (el.innerText||el.textContent||'').trim().slice(0,40),
        };
        const kids = [...el.children].slice(0, 30).map(c => desc(c, depth+1)).filter(Boolean);
        if (kids.length) out.children = kids;
        return out;
    }
    const panel = document.querySelectorAll('.bet-control')[0];
    return panel ? desc(panel, 0) : null;
}""")
with open("probe3_autotab_panel.json","w",encoding="utf-8") as f:
    json.dump(dump, f, indent=2)
print("panel dump saved. Top-level:", flush=True)
print(json.dumps(dump.get('children', []), indent=2)[:4000], flush=True)

# Also list all input elements and their attributes across the auto tab area
print("=== ALL INPUTS in panel 1 after Auto tab ===", flush=True)
inputs = frame.evaluate("""() => [...document.querySelectorAll('.bet-control')[0].querySelectorAll('input')].map(i => ({
    type:i.type, value:i.value, placeholder:i.placeholder, name:i.name,
    cls:(i.className||'').slice(0,50), id:i.id
}))""")
print(json.dumps(inputs, indent=2), flush=True)

print("=== ALL buttons in panel 1 after Auto tab ===", flush=True)
btns = frame.evaluate("""() => [...document.querySelectorAll('.bet-control')[0].querySelectorAll('button')].map(b => ({
    txt:(b.textContent||'').trim().slice(0,30), cls:(b.className||'').slice(0,60),
    disabled:b.disabled
}))""")
print(json.dumps(btns, indent=2), flush=True)

ctx.close(); browser.close(); pw.stop()
print("done", flush=True)
