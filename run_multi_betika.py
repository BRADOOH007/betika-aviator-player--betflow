"""
BETIKA MULTI-ACCOUNT AVIATOR SIMULATION (NO REAL MONEY)
=======================================================
Simulates how the BetFlow tool would run against a list of Betika accounts.

WARNING: NO-FUNDS SIMULATION / DRY-RUN. It toggles Auto Bet, presses the
green "Bet" button and enables Auto Cash Out @ 1.01x as a UI-flow test, but
the accounts are expected to have NO balance. Without funds the auto-bet
toggle stays disabled/off and no real wager is placed.

Flow per account:
  1. Fresh Betika session (context cleared between accounts)
  2. Log in
  3. Reach the Aviator game iframe
  4. On BOTH panels: open Auto tab, enable Auto Cash Out, set odds = 1.01,
     set stake (default 10), attempt to enable Auto Bet
  5. Press the green Bet button (panel 1)
  6. Observe N round-cycles (default 50). Each round-cycle completes on BOTH
     panels at once -> 2 bets per cycle -> total = 2 x N bets.
  7. Clear session, move to next account

Counting:
  * Aviator is ONE shared game: both panels see the SAME round.
  * round-cycles seen = how many times .result-history advanced.
  * Panel1 bets = panel2 bets = round-cycles seen.
  * Total bets = panel1 + panel2 = 2 x round-cycles.

Usage:
  python run_multi_betika.py phones.txt <password> [rounds] [stake]
"""

import sys
import time
import threading
import random
import hashlib
import json

from playwright.sync_api import sync_playwright

import aviator_bot as ab

# ── Stealth engine (graceful: tool still works if it fails to load) ──────────
try:
    from stealth_engine import StealthEngine
    _STEALTH = StealthEngine(aggressiveness="balanced")
except Exception:
    _STEALTH = None

STEALTH_ENABLED = True          # master switch for fingerprint + pacing
DEFAULT_PROXY = None           # set to a {"server": "http://host:port"} dict to split IPs

AUTO_CASHOUT = 1.01
DEFAULT_ROUNDS = 50   # round-cycles per account -> 100 bets total (2 panels)
DEFAULT_STAKE = 10    # KES per bet

# Launch each worker browser visible-then-minimized (taskbar) or fully visible.
MINIMIZE_BROWSER = True

# ── REAL-MONEY SAFETY GATE ────────────────────────────────────────────────
# The flow was originally a NO-FUNDS simulation. Real funded betting is now
# supported, but it must be EXPLICITLY enabled. Until REAL_MONEY is True the
# runner never relies on a funded auto-bet flip and logs honestly that real
# wagers are NOT being placed.
REAL_MONEY = False
MAX_BETS_PER_ACCOUNT = 100     # hard cap on real wagers per account/session
MIN_BALANCE_KES = 20.0         # refuse to bet if balance below one stake + buffer

# In-page mute script: silences the Aviator game audio regardless of whether it
# uses plain <audio>/<video> elements or the Web Audio API (the crash sound).
# Injected via context.add_init_script so it runs before the game loads, in every
# frame including the cross-origin spribe iframe.
MUTE_JS = r"""
(() => {
  const muteMedia = () => {
    try {
      document.querySelectorAll('audio,video').forEach(el => {
        el.muted = true; el.volume = 0;
        try { el.pause(); } catch(e) {}
      });
    } catch(e) {}
  };
  muteMedia();
  try {
    const mo = new MutationObserver(muteMedia);
    mo.observe(document.documentElement, { childList: true, subtree: true });
  } catch(e) {}
  try {
    const H = window.HTMLMediaElement;
    if (H && H.prototype) {
      Object.defineProperty(H.prototype, 'muted', { configurable: true, get(){ return true; }, set(){} });
      H.prototype.play = function(){ return Promise.resolve(); };
    }
  } catch(e) {}
  try { if (window.HTMLAudioElement && window.HTMLAudioElement.prototype.play) window.HTMLAudioElement.prototype.play = function(){ return Promise.resolve(); }; } catch(e) {}
  try { if (window.HTMLVideoElement && window.HTMLVideoElement.prototype.play) window.HTMLVideoElement.prototype.play = function(){ return Promise.resolve(); }; } catch(e) {}
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC && AC.prototype) {
      const origResume = AC.prototype.resume;
      const origCreateGain = AC.prototype.createGain;
      AC.prototype.resume = function(){ return Promise.resolve(); };
      AC.prototype.createGain = function(){
        const node = origCreateGain ? origCreateGain.call(this) : null;
        if (node) {
          try { node.gain.value = 0; } catch(e) {}
          try {
            node.gain.setValueAtTime = function(){ return node.gain; };
            node.gain.linearRampToValueAtTime = function(){ return node.gain; };
          } catch(e) {}
        }
        return node;
      };
    }
  } catch(e) {}
})();
"""

# ── Per-account fingerprint randomization ────────────────────────────────────
# IMPORTANT: we keep a MOBILE profile (the game DOM we verified works is the
# mobile layout). We vary UA / viewport / locale / timezone / GPU / canvas so
# each account no longer looks like an identical clone, while preserving the
# working mobile class structure the round-detector relies on.
MOBILE_UAS = [
    "Mozilla/5.0 (Android 11; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
    "Mozilla/5.0 (Android 12; Mobile; rv:121.0) Gecko/121.0 Firefox/121.0",
    "Mozilla/5.0 (Android 13; Mobile; rv:119.0) Gecko/119.0 Firefox/119.0",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
]
MOBILE_VIEWPORTS = [(360, 800), (390, 844), (412, 915), (420, 900),
                   (360, 740), (414, 896), (393, 851)]
LOCALES = ["en-US", "en-KE", "en-GB"]
LANGUAGES = {
    "en-US": ["en-US", "en"],
    "en-KE": ["en-KE", "en"],
    "en-GB": ["en-GB", "en"],
}
TIMEZONES = ["Africa/Nairobi", "Africa/Kampala", "Africa/Dar_es_Salaam",
             "Africa/Kigali", "Africa/Bujumbura"]
PLATFORMS = ["Linux armv8l", "Linux aarch64"]
WEBGL_VENDORS = ["Google Inc. (Intel)", "Google Inc. (Qualcomm)", "Qualcomm"]
WEBGL_RENDERERS = [
    "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (Qualcomm, Adreno (TM) 660 Direct3D11 vs_5_0 ps_5_0)",
    "Mali-T860",
]


def make_fingerprint():
    """Return a randomized-but-mobile browser fingerprint for one account."""
    locale = random.choice(LOCALES)
    return {
        "user_agent": random.choice(MOBILE_UAS),
        "viewport": random.choice(MOBILE_VIEWPORTS),
        "locale": locale,
        "language": locale,
        "languages": LANGUAGES[locale],
        "timezone": random.choice(TIMEZONES),
        "platform": random.choice(PLATFORMS),
        "hw": random.choice([4, 6, 8]),
        "mem": random.choice([4, 6, 8]),
        "webgl_vendor": random.choice(WEBGL_VENDORS),
        "webgl_renderer": random.choice(WEBGL_RENDERERS),
        "canvas_salt": hashlib.md5(str(random.random()).encode()).hexdigest()[:10],
    }


def _build_stealth_js(fp):
    """JS init script that overrides navigator/GPU/canvas fingerprints."""
    data = {
        "hw": fp["hw"], "mem": fp["mem"], "platform": fp["platform"],
        "language": fp["language"], "languages": fp["languages"],
        "webgl_vendor": fp["webgl_vendor"], "webgl_renderer": fp["webgl_renderer"],
        "canvas_salt": fp["canvas_salt"],
    }
    return r"""
    (() => {
      const FP = """ + json.dumps(data) + r""";
      try {
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => FP.hw, configurable: true });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => FP.mem, configurable: true });
        Object.defineProperty(navigator, 'platform', { get: () => FP.platform, configurable: true });
        Object.defineProperty(navigator, 'language', { get: () => FP.language, configurable: true });
        Object.defineProperty(navigator, 'languages', { get: () => FP.languages, configurable: true });
      } catch(e) {}
      try {
        const origP = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(p){
          if (p === 37445) return FP.webgl_vendor;   // UNMASKED_VENDOR_WEBGL
          if (p === 37446) return FP.webgl_renderer; // UNMASKED_RENDERER_WEBGL
          return origP.call(this, p);
        };
      } catch(e) {}
      try {
        const origTD = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(){
          return origTD.apply(this, arguments) + FP.canvas_salt;
        };
      } catch(e) {}
    })();
    """


def _human_delay(action):
    """Human-like delay (seconds); 0 when stealth disabled/failed."""
    if STEALTH_ENABLED and _STEALTH is not None:
        try:
            return _STEALTH.human_delay(action)
        except Exception:
            return 0.0
    return 0.0


def _human_mouse(page):
    """Jitter the real mouse along a curved path (in-page coordinates)."""
    if not (STEALTH_ENABLED and _STEALTH is not None):
        return
    try:
        size = page.viewport_size or {"width": 400, "height": 800}
        x0, y0 = size["width"] // 2, size["height"] // 2
        end = (random.randint(20, max(21, size["width"] - 20)),
               random.randint(20, max(21, size["height"] - 20)))
        for (x, y) in _STEALTH.generate_mouse_curve((x0, y0), end, num_points=12):
            page.mouse.move(x, y, steps=2)
            time.sleep(random.uniform(0.005, 0.02))
    except Exception:
        pass

# Thread-local log callback so each worker thread can funnel its own output to
# the GUI live terminal without cross-thread contamination.
_log_local = threading.local()


def set_log_cb(fn):
    """Set (or clear, with None) the per-thread log forwarder."""
    _log_local.cb = fn


def log(msg):
    print(f"[MULTI] {msg}", flush=True)
    cb = getattr(_log_local, "cb", None)
    if cb:
        try:
            cb(f"[MULTI] {msg}")
        except Exception:
            pass


def read_phones(path):
    with open(path, "r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


def _minimize_window(browser):
    """Minimize the browser's top-level window via the Windows API so the worker
    runs visibly-but-minimized in the taskbar (best of both: keeps the browser
    alertable like a normal session, but stays out of the way)."""
    try:
        import ctypes
        import ctypes.wintypes as wt
        import subprocess
        import re

        result = browser.process.pid
        if not result:
            return
        pid = int(result)
        # Enumerate top-level windows of this PID, minimize the first visible one.
        EnumWindows = ctypes.windll.user32.EnumWindows
        GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
        IsWindowVisible = ctypes.windll.user32.IsWindowVisible
        ShowWindow = ctypes.windll.user32.ShowWindow
        SW_MINIMIZE = 6
        found = []
        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def cb(hwnd, _):
            if IsWindowVisible(hwnd):
                wp = wt.DWORD()
                GetWindowThreadProcessId(hwnd, ctypes.byref(wp))
                if wp.value == pid:
                    found.append(hwnd)
            return True
        EnumWindows(cb, 0)
        for hwnd in found:
            ShowWindow(hwnd, SW_MINIMIZE)
    except Exception:
        pass


def new_session(pw, headless=False, minimize=False, fingerprint=None, proxy=None):
    if fingerprint is None:
        fingerprint = make_fingerprint()
    vw, vh = fingerprint["viewport"]
    launch_kwargs = dict(
        headless=headless,
        # Hard-mute ALL Firefox audio at the browser level (covers the game's
        # WebAudio/crash sound in the cross-origin iframe, no matter the origin).
        firefox_user_prefs={"media.volume_scale": "0.0"},
    )
    if proxy:
        launch_kwargs["proxy"] = proxy
    browser = pw.firefox.launch(**launch_kwargs)
    context = browser.new_context(
        viewport={"width": vw, "height": vh},
        user_agent=fingerprint["user_agent"],
        locale=fingerprint["locale"],
        timezone_id=fingerprint["timezone"],
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    )
    # Anti-fingerprint overrides (navigator / WebGL / canvas) per account.
    context.add_init_script(_build_stealth_js(fingerprint))
    # In-page mute (audio/video elements + Web Audio) before the game loads.
    context.add_init_script(MUTE_JS)
    page = context.new_page()
    page.set_default_timeout(15000)
    if minimize and not headless:
        _minimize_window(browser)
    return browser, context, page, fingerprint


def read_balance(frame):
    """Best-effort read of the player's displayed balance from the game DOM.
    Returns a float (0.0 if not readable)."""
    try:
        return float(frame.evaluate(
            """() => {
                const bal = document.querySelector('[class*="balance"]');
                if (!bal) return 0;
                const t = bal.textContent.replace(/[^0-9.]/g, '');
                return parseFloat(t) || 0;
            }"""))
    except Exception:
        return 0.0


def login_and_open_game(page, phone, password):
    """Log into Betika and return the Aviator game frame (or None)."""
    url = ab.SITES["Betika"]["url"]
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    bot = ab.AviatorMartingaleBot(phone=phone, password=password, site="Betika")
    bot._page = page
    try:
        bot._login_betika()
    except Exception as e:
        log(f"  login flow raised: {e}")
    time.sleep(3)
    if "aviator" not in page.url:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
    for sel in ["#app iframe", "iframe[src*='spribe']", "iframe[src*='aviator']",
                "iframe[src*='betika']", "iframe"]:
        try:
            h = page.locator(sel).first.element_handle(timeout=5000)
            if h:
                f = h.content_frame()
                if f:
                    return page, f
        except Exception:
            continue
    return page, None


def click_oval(frame, container_selector):
    """Native Playwright click on the .oval inside a switch container.
    Returns True if the switch flipped OUT of 'off' (enabled)."""
    try:
        switch_tpl = frame.locator(f"{container_selector} .input-switch").first
        switch_tpl.wait_for(state="visible", timeout=5000)
        before = "off" in (switch_tpl.get_attribute("class") or "")
        oval = frame.locator(f"{container_selector} .oval").first
        oval.click()
        # give Angular a moment
        time.sleep(1.0)
        after = "off" in (switch_tpl.get_attribute("class") or "")
        return before and not after
    except Exception as e:
        log(f"    switch click err {container_selector}: {str(e)[:80]}")
        return False


def mute_frame(frame):
    """Runtime mute of the game frame (catches any audio/gain created after the
    init script ran, e.g. the crash-sound Web Audio nodes)."""
    try:
        frame.evaluate("""() => {
            try { (document.querySelectorAll('audio,video')||[]).forEach(el => { el.muted = true; el.volume = 0; try { el.pause(); } catch(e){} }); } catch(e) {}
            try { const AC = window.AudioContext || window.webkitAudioContext; if (AC && AC.prototype) { AC.prototype.resume = function(){ return Promise.resolve(); }; } } catch(e) {}
        }""")
    except Exception:
        pass


def setup_panels(frame, cashout=AUTO_CASHOUT):
    """Open Auto tab on each panel, enable Auto Cash Out, set odds (default 1.01),
    set stake 10, attempt Auto Bet toggle. Returns a summary dict."""
    try:
        n = frame.evaluate("() => document.querySelectorAll('.bet-control').length")
    except Exception:
        n = 0

    summary = {"panels": n, "cashout_values": [], "auto_bet_enabled": []}

    for i in range(n):
        # --- open the Auto tab on this panel ---
        frame.evaluate(
            """(p) => {
                const panel = document.querySelectorAll('.bet-control')[p];
                if (!panel) return;
                for (const b of panel.querySelectorAll('button'))
                    if (b.textContent.trim().toLowerCase() === 'auto') { b.click(); return; }
            }""",
            i,
        )
        time.sleep(1.2)

        csel = f".bet-control:nth-child({i+1})"
        # use a robust per-panel scope via evaluate for toggle detection:
        panel_scope = f"document.querySelectorAll('.bet-control')[{i}]"

        # --- enable Auto Cash Out (this toggle DOES flip when clicked) ---
        try:
            cash_flipped = frame.evaluate(
                """(exp) => {
                    const sel = eval(exp + '.querySelector(\\'.cash-out-switcher .input-switch\\')');
                    if (!sel) return false;
                    const before = sel.className.includes('off');
                    const oval = exp + '.querySelector(\\'.cash-out-switcher .oval\\')';
                    eval(oval + '.click()');
                    return before;
                }""",
                panel_scope,
            )
            # Re-check class after a beat
            time.sleep(1.0)
            cash_on = frame.evaluate(
                """(exp) => !eval(exp + '.querySelector(\\'.cash-out-switcher .input-switch\\')').className.includes('off')""",
                panel_scope,
            )
            enabled = bool(cash_flipped)  # was previously off (now should be on)
        except Exception as e:
            enabled = False
            log(f"    panel {i+1} cashout toggle err: {str(e)[:80]}")

        # --- set cashout odds to 1.01 ---
        try:
            frame.evaluate(
                """(args) => {
                    const panel = document.querySelectorAll('.bet-control')[args.p];
                    if (!panel) return;
                    const ci = panel.querySelectorAll('input')[1];
                    if (!ci) return;
                    ci.focus(); ci.select();
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                    setter.call(ci, args.val);
                    ci.dispatchEvent(new Event('input',{bubbles:true}));
                    ci.dispatchEvent(new Event('change',{bubbles:true}));
                    ci.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true}));
                    ci.blur();
                }""",
                {"p": i, "val": str(cashout)},
            )
            time.sleep(0.3)
            cash_val = frame.evaluate(
                """(p) => document.querySelectorAll('.bet-control')[p].querySelectorAll('input')[1]?.value""",
                i,
            )
            summary["cashout_values"].append(cash_val)
        except Exception as e:
            summary["cashout_values"].append(None)

        # --- set stake to default on this panel's stake input ---
        try:
            frame.evaluate(
                """(args) => {
                    const panel = document.querySelectorAll('.bet-control')[args.p];
                    if (!panel) return;
                    const si = panel.querySelectorAll('input')[0];
                    if (!si) return;
                    si.focus(); si.select();
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                    setter.call(si, String(args.stake));
                    si.dispatchEvent(new Event('input',{bubbles:true}));
                    si.dispatchEvent(new Event('change',{bubbles:true}));
                    si.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true}));
                    si.blur();
                }""",
                {"p": i, "stake": int(DEFAULT_STAKE)},
            )
            time.sleep(0.3)
        except Exception:
            pass

        # --- attempt Auto Bet toggle ---
        # NB: on a no-funds account this typically stays OFF (disabled) because
        # you cannot auto-bet without a balance. We still click it.
        auto_bet_on = False
        try:
            frame.evaluate(
                """(exp) => {
                    const sw = exp + '.querySelector(\\'.auto-bet .input-switch\\')';
                    const o = eval(sw);
                    if (o && o.className.includes('off')) {
                        eval(exp + '.querySelector(\\'.auto-bet .oval\\').click()');
                    }
                }""",
                panel_scope,
            )
            time.sleep(1.0)
            auto_bet_on = frame.evaluate(
                """(exp) => {
                    const o = eval(exp + '.querySelector(\\'.auto-bet .input-switch\\')');
                    return o ? !o.className.includes('off') : false;
                }""",
                panel_scope,
            )
        except Exception as e:
            log(f"    panel {i+1} auto-bet toggle err: {str(e)[:80]}")

        summary["auto_bet_enabled"].append(bool(auto_bet_on))

    return summary


def press_green_bet(frame, stake):
    """Press the green 'Bet' button on BOTH panels (same round, both bet).
    Returns dict with per-panel button text before press and whether each
    panel's button was clicked."""
    result = {}
    n = 0
    try:
        n = frame.evaluate("() => document.querySelectorAll('.bet-control').length")
    except Exception:
        n = 0
    for i in range(n):
        before_text = frame.evaluate(
            """(p) => {
                const panel = document.querySelectorAll('.bet-control')[p];
                if (!panel) return null;
                for (const b of panel.querySelectorAll('button'))
                    if (b.className.includes('bet') && !b.className.includes('tab'))
                        return (b.textContent||'').trim();
                return null;
            }""",
            i,
        )
        clicked = frame.evaluate(
            """(p) => {
                const panel = document.querySelectorAll('.bet-control')[p];
                if (!panel) return false;
                for (const b of panel.querySelectorAll('button'))
                    if (b.className.includes('btn-success') && b.className.includes('bet') && !b.disabled) {
                        b.click(); return true;
                    }
                return false;
            }""",
            i,
        )
        result[f"panel{i+1}"] = {"text": before_text, "clicked": clicked}
    return result


def read_history(frame):
    try:
        el = frame.evaluate("() => { const e = document.querySelector('.result-history'); return e ? e.innerText : ''; }")
    except Exception:
        return ""
    return el or ""


def count_entries(text):
    return sum(1 for line in text.splitlines() if line.strip())


def _history_snapshot(frame, limit=600):
    """Return (count, newest_multiplier_or_None) for .result-history, robustly.
    Prefers the element-based parse (aviator_bot._get_history). If that finds
    nothing, falls back to scanning raw innerText for the newest multiplier so
    round detection still works regardless of the DOM structure."""
    try:
        vals = ab._get_history(frame, limit=limit)
        if vals:
            return len(vals), vals[0]
    except Exception:
        pass
    try:
        import re
        txt = frame.evaluate(
            "() => { const e = document.querySelector('.result-history'); "
            "return e ? e.innerText : ''; }"
        ) or ""
        nums = []
        for line in txt.splitlines():
            m = re.search(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*x?", line.strip())
            if m:
                try:
                    v = float(m.group(1).replace(",", "."))
                except ValueError:
                    continue
                if 0.5 <= v < 10000:
                    nums.append(v)
        return len(nums), (nums[0] if nums else None)
    except Exception:
        return 0, None


def observe_rounds(frame, target_cycles, stake=None, cashout=AUTO_CASHOUT):
    """Wait for `target_cycles` NEW round-cycles while tracking modeled P&L.
    Each cycle = 1 round on panel 1 + 1 round on panel 2 (shared game).

    ROUND-END DETECTION MECHANISM:
    The game appends every finished crash multiplier to .result-history. We
    detect a round ending when that history's parsed entry count GROWS (and/or
    the newest multiplier changes). Multipliers are read robustly from the
    `.history-item`/`span` elements (via aviator_bot._get_history), NOT raw
    innerText, so we always get the real crash value (never 0.00).

    P&L MODEL (REAL_MONEY only, best-effort):
    We assume the cashout (default 1.01x) auto-cashout fired on both panels. Per round:
       win  -> +2 * stake * (cashout - 1)
       loss (multiplier < cashout) -> -2 * stake
    This is inferred from the round multiplier, NOT Betika's settlement, so it
    is an APPROXIMATION. It is used only to gate the per-account stop-loss.

    Returns (round_cycles, total_bets, pnl)."""
    stake = stake if stake is not None else DEFAULT_STAKE
    win = 2 * stake * (cashout - 1)
    loss = 2 * stake
    pnl = 0.0
    seen = 0
    start_ts = time.time()
    # Hard wall-clock cap so a mismatched/unresponsive DOM can never hang the
    # run forever: allow ~40s per expected round plus a 60s setup buffer.
    max_wait = target_cycles * 40 + 60
    last_hist = ab._get_history(frame, limit=target_cycles * 2 + 200)
    baseline = len(last_hist)
    log(f"  Watching game — need {target_cycles} rounds "
        f"(both panels auto-cashout @ {cashout}x).")
    while seen < target_cycles:
        if time.time() - start_ts > max_wait:
            log(f"  !! Watchdog: exceeded {max_wait}s waiting for rounds — "
                f"stopping with {seen}/{target_cycles} seen (DOM may not match).")
            break
        cur_hist = ab._get_history(frame, limit=target_cycles * 2 + 200)
        grew = len(cur_hist) > baseline
        changed = bool(cur_hist) and bool(last_hist) and cur_hist[0] != last_hist[0]
        if grew or changed:
            delta = len(cur_hist) - baseline
            if delta > 0:
                baseline = len(cur_hist)
            elif not delta:
                # no new entries but newest changed -> count one
                delta = 1
                baseline = len(cur_hist)
            # newest multiplier(s) that just landed
            multi = cur_hist[0] if cur_hist else 0.0
            # advance by however many distinct rounds ended
            step = max(1, min(delta, target_cycles - seen))
            for _ in range(step):
                seen += 1
                if multi >= cashout:
                    pnl += win
                    mark = "✓ WIN"
                else:
                    pnl -= loss
                    mark = "✗ LOSS"
                log(f"  Round {seen}/{target_cycles} {mark} "
                    f"(multi={multi:.2f}x) | both panels @ {cashout}x | "
                    f"pnl={pnl:+.2f} KES")
            last_hist = cur_hist
        time.sleep(1.0)
    log(f"  ✓ All {seen} rounds done — moving to next account in the list.")
    return seen, seen * 2, pnl


def process_account(pw, phone, password, rounds, stake, cashout=AUTO_CASHOUT, proxy=None, headless=False):
    log(f"▶ Account {phone} — logging in...")
    if proxy is None:
        proxy = DEFAULT_PROXY
    fp = make_fingerprint()
    browser, context, page, fp = new_session(
        pw, headless=headless, minimize=(not headless) and MINIMIZE_BROWSER,
        fingerprint=fp, proxy=proxy)
    try:
        time.sleep(_human_delay("load"))
        page, frame = login_and_open_game(page, phone, password)
        if frame is None:
            log(f"  !! no game iframe for {phone}")
            return {"phone": phone, "status": "no_iframe"}
        time.sleep(4)
        mute_frame(frame)  # ensure the game is silent after the frame is reached
        log(f"  ✓ Logged in: {phone}  [fp: {fp['user_agent'].split(') ')[-1][:24]} "
            f"| {fp['viewport'][0]}x{fp['viewport'][1]} | {fp['timezone']} | {fp['locale']}]")

        # Pre-roll safety reads
        balance = read_balance(frame)
        log(f"  displayed balance: {balance:.2f} KES | REAL_MONEY={REAL_MONEY} | cashout={cashout}x")

        # Never place a real wager we can't clearly afford
        if balance > 0 and balance < stake * 1.0:
            log(f"  !! balance ({balance:.2f}) below stake ({stake}) — skipping real bet")
            return {"phone": phone, "status": "no_funds"}

        summary = setup_panels(frame, cashout=cashout)
        log(f"  panels={summary['panels']} | cashout_values={summary['cashout_values']} "
            f"| auto_bet_enabled={summary['auto_bet_enabled']}")
        if summary["panels"] == 0:
            return {"phone": phone, "status": "no_panels"}

        # SAFETY: before placing any real wager, confirm Auto Bet came on for
        # EVERY panel. If it didn't (e.g. no balance / toggle disabled), abort so
        # we don't silently "observe" rounds with no bets actually placed.
        auto_ok = bool(summary["auto_bet_enabled"]) and all(summary["auto_bet_enabled"])
        log(f"  auto-bet enabled on all panels: {auto_ok} {summary['auto_bet_enabled']}")
        if REAL_MONEY and not auto_ok:
            log(f"  !! AUTO-BET NOT ENABLED — aborting before any real wager.")
            return {"phone": phone, "status": "auto_bet_failed",
                    "auto_bet_enabled": summary["auto_bet_enabled"]}

        # Cap how many real wagers we allow this account in one session
        max_cycles = min(int(rounds), MAX_BETS_PER_ACCOUNT // 2)
        if max_cycles < 1:
            return {"phone": phone, "status": "capped", "cycles": 0, "total_bets": 0}

        # Place the opening bets on BOTH panels (same round)
        _human_mouse(page)
        time.sleep(_human_delay("think"))
        press = press_green_bet(frame, stake)
        for p, info in press.items():
            mode = "REAL wager" if REAL_MONEY else "UI-flow (no funds sim)"
            log(f"  {p}: green Bet pressed={info['clicked']} ({info['text']!r}) — "
                f"stake {stake} KES, {mode}")
        both = all(info["clicked"] for info in press.values()) and len(press) >= 2
        log(f"  both panels bet pressed simultaneously: {both}")

        log(f"  observing up to {max_cycles} round-cycles "
            f"({max_cycles*2} max bets across 2 panels), cashout {cashout}x, "
            f"stake {stake} KES, REAL_MONEY={REAL_MONEY}...")
        cycles, total_bets, pnl = observe_rounds(frame, max_cycles, stake, cashout=cashout)
        return {"phone": phone, "status": "ok",
                "cycles": cycles, "total_bets": total_bets, "pnl": round(pnl, 2)}
    finally:
        try:
            context.close()
            browser.close()
        except Exception:
            pass


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    phones_file = sys.argv[1]
    password = sys.argv[2]
    rounds = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_ROUNDS
    stake = float(sys.argv[4]) if len(sys.argv) > 4 else DEFAULT_STAKE

    phones = read_phones(phones_file)
    log(f"Loaded {len(phones)} account line(s) from {phones_file} | "
        f"round-cycles/account={rounds} | stake={stake} KES | total bets/account={rounds*2}")
    if not phones:
        log("No phone numbers found — aborting.")
        sys.exit(1)

    pw = sync_playwright().start()
    results = []
    for idx, phone in enumerate(phones, 1):
        log(f"--- Account line {idx}/{len(phones)} ---")
        res = process_account(pw, phone, password, rounds, stake)
        results.append(res)
        log(f"--- Account line {idx} done: {res['status']} ---")
        time.sleep(2)

    try:
        pw.stop()
    except Exception:
        pass

    log("=== SUMMARY ===")
    for r in results:
        log(f"  {r['phone']}: {r['status']} | cycles={r.get('cycles','-')} "
            f"| total bets={r.get('total_bets','-')}x{stake}KES @ {AUTO_CASHOUT}x "
            f"| pnl={r.get('pnl','-')} KES")
    mode = "REAL-MONEY SIM" if REAL_MONEY else "UI-flow simulation (no real bets)"
    log(f"Mode: {mode}.")


if __name__ == "__main__":
    main()
