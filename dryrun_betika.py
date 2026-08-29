"""
DRY-RUN TEST — Betika Aviator (NO REAL MONEY)
============================================
Purpose: verify that the tool can:
  1. Launch Firefox + navigate to Betika Aviator
  2. Log in
  3. Reach the Spribe game iframe
  4. On BOTH bet panels: click Auto, enable Auto Cash Out, set odds = 1.01
  5. Detect when a round ends and track 50 rounds on EACH panel

IMPORTANT: This script NEVER clicks the real "Bet" button and never places
any wager. It only configures the panel UI (auto + cash-out odds) and
passively observes rounds.
"""

import sys
import time
import json

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Reuse the existing bot helpers where possible.
import aviator_bot as ab

AUTO_CASHOUT_TEST = 1.01
ROUNDS_TO_observe = 50


def log(msg):    print(f"[DRYRUN] {msg}", flush=True)


def setup_panel(frame_text, panel_idx):
    """
    Set Auto tab + Auto Cash Out toggle + cashout odds = 1.01 on one panel.
    panel_idx: 0 = first .bet-control, 1 = second .bet-control.
    Returns the value that landed in the cashout input (string) or None.
    """
    label = f"{panel_idx+1}"
    log(f"=== Configuring panel {label} ===")

    # 1. Click the Auto tab (within that specific panel)
    panel_target = "document.querySelectorAll('.bet-control')[%d]" % panel_idx
    frame_text.evaluate(
        """(p) => {
            const panel = document.querySelectorAll('.bet-control')[p];
            if (!panel) return;
            const btns = panel.querySelectorAll('button');
            for (const b of btns) {
                if (b.textContent.trim().toLowerCase() === 'auto') { b.click(); return; }
            }
        }""",
        panel_idx,
    )
    time.sleep(1.2)

    # 2. Enable Auto Cash Out toggle if currently OFF (within that panel)
    frame_text.evaluate(
        """(p) => {
            const panel = document.querySelectorAll('.bet-control')[p];
            if (!panel) return;
            const toggle_div = panel.querySelector('.cash-out-switcher');
            if (!toggle_div) return;
            const sw = toggle_div.querySelector('.input-switch');
            if (sw && sw.className.includes('off')) {
                const oval = toggle_div.querySelector('.oval');
                if (oval) oval.click();
            }
        }""",
        panel_idx,
    )
    time.sleep(0.8)

    # 3. Set cashout odds in the second input of that panel via Angular setter
    result = frame_text.evaluate(
        """(args) => {
            const p = args.p, val = args.val;
            const panel = document.querySelectorAll('.bet-control')[p];
            if (!panel) return 'no-panel';
            const inputs = panel.querySelectorAll('input');
            const ci = inputs[1];
            if (!ci || ci.offsetParent === null) return 'hidden';
            ci.focus();
            ci.select();
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(ci, val);
            ci.dispatchEvent(new Event('input',  { bubbles: true }));
            ci.dispatchEvent(new Event('change', { bubbles: true }));
            ci.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
            ci.blur();
            return ci.value;
        }""",
        {"p": panel_idx, "val": str(AUTO_CASHOUT_TEST)},
    )
    log(f"Panel {label} cashout input now = {result}")
    return result


def read_history_text(frame_text):
    """Return the full result-history innerText (most recent multiplier first)."""
    try:
        return frame_text.evaluate(
            """() => {
                const el = document.querySelector('.result-history');
                return el ? el.innerText : '';
            }"""
        )
    except Exception:
        return ""


def count_history_entries(text):
    """Number of multiplier entries in the history text (one per line, e.g. '2.60x')."""
    if not text:
        return 0
    return sum(1 for line in text.splitlines() if line.strip())


def main():
    phone = sys.argv[1] if len(sys.argv) > 1 else input("Betika phone: ")
    password = sys.argv[2] if len(sys.argv) > 2 else input("Betika password: ")
    target_rounds = int(sys.argv[3]) if len(sys.argv) > 3 else ROUNDS_TO_observe

    pw = sync_playwright().start()
    browser = pw.firefox.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 420, "height": 900},
        user_agent="Mozilla/5.0 (Android 11; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
        locale="en-US",
        timezone_id="Africa/Nairobi",
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )
    page = context.new_page()
    page.set_default_timeout(15000)

    url = ab.SITES["Betika"]["url"]
    log(f"Navigating to {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    log(f"URL after load: {page.url}")

    # ---- Login flow (reuse the bot's method logic by driving a bot instance) ----
    bot = ab.AviatorMartingaleBot(phone=phone, password=password, site="Betika")
    bot._page = page
    bot._context = context
    try:
        bot._login_betika()
        log("Login flow executed")
    except Exception as e:
        log(f"Login flow raised: {e}")
    time.sleep(3)
    log(f"URL after login: {page.url}")

    # If redirected away, go back to aviator
    if "aviator" not in page.url:
        log("Redirected away from aviator — navigating back")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

    # ---- Find the game iframe ----
    log("Looking for Aviator game iframe...")
    frame = None
    for sel in ["#app iframe", "iframe[src*='spribe']", "iframe[src*='aviator']",
                "iframe[src*='betika']", "iframe"]:
        try:
            handle = page.locator(sel).first.element_handle(timeout=5000)
            if handle:
                f = handle.content_frame()
                if f:
                    frame = f
                    log(f"Found iframe via selector: {sel}")
                    break
        except Exception:
            continue
    if frame is None:
        log("!! Could not find game iframe — dump page to dryrun_page.html")
        page.content() and None
        with open("dryrun_page.html", "w", encoding="utf-8") as fh:
            fh.write(page.content())
        raise SystemExit("Aborted: no game iframe")

    # Give the game a moment to boot its DOM
    time.sleep(4)
    log("Game iframe accessible")

    # ---- Count how many .bet-control panels exist ----
    try:
        n_panels = frame.evaluate(
            "() => document.querySelectorAll('.bet-control').length"
        )
    except Exception:
        n_panels = 0
    log(f"Detected {n_panels} .bet-control panel(s)")
    if n_panels == 0:
        log("!! No .bet-control panels found — dumping iframe DOM snapshot")
        with open("dryrun_frame_dom.json", "w", encoding="utf-8") as fh:
            json.dump(
                frame.evaluate(
                    """() => {
                        const info = {};
                        const classes = new Set();
                        document.querySelectorAll('*').forEach(el => {
                            if (el.className && typeof el.className === 'string')
                                el.className.split(' ').forEach(c=>{if(c)classes.add(c);});
                        });
                        info.classes=[...classes].slice(0,120);
                        info.buttons=[...document.querySelectorAll('button')].map(b=>b.textContent.trim().slice(0,30)).filter(t=>t);
                        info.inputs=[...document.querySelectorAll('input')].map(i=>({type:i.type,placeholder:i.placeholder,value:i.value,class:(i.className||'').slice(0,50)}));
                        return info;
                    }"""
                ),
                fh,
                indent=2,
            )
        raise SystemExit("Aborted: no bet panels found")

    # ---- Configure BOTH panels ----
    panels = n_panels
    for i in range(panels):
        setup_panel(frame, i)

    # Verify final panel state (auto selected, cashout = 1.01)
    log("Verifying final panel state...")
    time.sleep(1)
    verify = frame.evaluate("""() => {
        const out = [];
        const panels = document.querySelectorAll('.bet-control');
        panels.forEach((p, i) => {
            const tabs = [...p.querySelectorAll('button.tab')].map(b => b.textContent.trim());
            const cash = p.querySelectorAll('input')[1] ? p.querySelectorAll('input')[1].value : null;
            out.push({ panel: i+1, tabs, cashout_value: cash });
        });
        return out;
    }""")
    for v in verify:
        log(f"Panel {v['panel']} — tabs={v['tabs']} | cashout input value={v['cashout_value']}")

    # ---- Round-end detection + 50 rounds ----
    # Aviator runs ONE shared game: both panels (double-bet) see the SAME
    # round results, appended to the shared .result-history (newest first).
    # We detect a round ENDING by watching that history text change and grow.
    # Passive only — no bets placed.
    log("NOTE: Not placing any real bets — observing rounds passively.")
    log(f"Tracking {ROUNDS_TO_observe} rounds. Both panels share the same game "
        f"rounds, so this applies to each panel simultaneously.")

    SEEN_LIMIT = target_rounds
    rounds_seen = 0
    last_hist = read_history_text(frame)
    baseline = count_history_entries(last_hist)
    log(f"Initial history: {baseline} prior round(s) in memory. "
        f"Waiting for {SEEN_LIMIT} NEW round(s)...")
    last_round_multi = None

    while rounds_seen < SEEN_LIMIT:
        cur_hist = read_history_text(frame)
        if cur_hist != last_hist:
            # History changed => at least one round has ended.
            # Newest multiplier is the first line of the history text.
            first_line = (cur_hist.splitlines() or [""])[0].strip()
            this_multi = first_line
            new_total = count_history_entries(cur_hist)
            delta = new_total - baseline
            rounds_seen = max(rounds_seen, delta)
            last_hist = cur_hist
            log(f"Round ended — latest multiplier {this_multi} | "
                f"NEW rounds tracked: {rounds_seen}/{SEEN_LIMIT} "
                f"(both panels at {rounds_seen}/{SEEN_LIMIT})")
        time.sleep(1.0)

    log(f"Reached {SEEN_LIMIT} rounds on BOTH panels — done.")

    try:
        context.close()
        browser.close()
        pw.stop()
    except Exception:
        pass
    log("Dry-run complete (no real bets placed).")


if __name__ == "__main__":
    main()
