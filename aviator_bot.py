"""
Aviator Martingale Bot
======================
Multi-site support: OdiBets, Betika
"""

import os
import time
import csv
import json
import threading
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False

# ─── Config ──────────────────────────────────────────────────────────────────

MARTINGALE_STEPS = [10, 40, 174, 754, 3267]
AUTO_CASHOUT     = 1.3
CSV_DIR          = "results"

# Safety thresholds
EMERGENCY_STOP_CONDITIONS = {
    "max_consecutive_losses": 8,
    "max_session_loss": 5000,  # KES
    "min_balance_threshold": 100,  # KES
    "max_session_duration": 7200,  # 2 hours
    "max_stake_percent": 0.15,  # Never bet more than 15% of balance
    "stop_loss_threshold": -1000,  # Stop if session loss exceeds this
    "take_profit_target": 2000,  # Stop when profit reaches this
}

# ─── Site definitions ────────────────────────────────────────────────────────

SITES = {
    "OdiBets": {
        "url": "https://odibets.com/aviator",
        "in_iframe": True,   # game lives inside #app iframe
    },
    "Betika": {
        "url": "https://www.betika.com/en-ke/aviator",
        "in_iframe": True,   # Spribe iframe embedded
    },
}

# ─── DOM selectors (Spribe game — same engine on both sites) ─────────────────
# Panel 1 = frame.locator(".bet-control").first
# Inputs:  nth(0)=stake panel1, nth(1)=cashout panel1

HISTORY_SELECTORS = [
    ".result-history .payout",
    ".result-history .history-item",
    ".result-history span",
    "[class*='result-history'] span",
]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_history(frame, limit=200):
    """
    Read historical multipliers from DOM.
    Returns list of floats, newest first.
    """
    results = []
    for sel in HISTORY_SELECTORS:
        try:
            items = frame.locator(sel).all()
            if items:
                for el in items[:limit]:
                    try:
                        txt = el.inner_text().strip().replace("x", "").replace(",", ".")
                        results.append(float(txt))
                    except Exception:
                        pass
                if results:
                    break
        except Exception:
            pass
    return results


def _is_betting_window_open(frame):
    """
    Returns True when the big green Bet button is active (betting window open).
    When round is active the button changes color/state — we detect via JS.
    """
    try:
        return frame.evaluate("""() => {
            const panel = document.querySelector('.bet-control');
            if (!panel) return false;
            const btn = panel.querySelector('button');
            if (!btn) return false;
            const txt = btn.textContent.trim().toLowerCase();
            const disabled = btn.disabled;
            // Green button = betting open. Non-green or disabled = round active.
            // "Bet X KES" = open, "Cancel" or disabled = active
            if (disabled) return false;
            if (txt.includes('cancel')) return false;
            if (txt.includes('bet') && !disabled) return true;
            return false;
        }""")
    except Exception:
        return False




def _wait_for_round_end(frame, timeout_s=120):
    """Wait until betting window opens (round ended)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _is_betting_window_open(frame):
            return True
        time.sleep(0.4)
    return False


def _wait_for_round_start(frame, timeout_s=60):
    """Wait until round starts (betting window closes)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _is_betting_window_open(frame):
            return True
        time.sleep(0.3)
    return False


# ─── Analyzer (passive) ──────────────────────────────────────────────────────

def analyze(history: list, cashout_target: float = AUTO_CASHOUT) -> dict:
    """
    Passive stats only — NO predictions, NO betting signals.
    Tracks last 50 / 100 / 200 multipliers and calculates:
      - % of results below the cashout target
      - average multiplier
      - loss streak lengths (current, max, average)
    Returns raw stats dict only.
    """
    def _stats(data):
        if not data:
            return {}
        below   = sum(1 for x in data if x < cashout_target)
        pct_below = round(below / len(data) * 100, 1)
        avg     = round(sum(data) / len(data), 3)
        hi      = round(max(data), 3)
        lo      = round(min(data), 3)

        # Compute all loss streak lengths
        streaks, cur = [], 0
        for x in data:
            if x < cashout_target:
                cur += 1
            else:
                if cur:
                    streaks.append(cur)
                cur = 0
        if cur:
            streaks.append(cur)

        # Current streak = how many consecutive losses at the START of data (newest first)
        current_streak = 0
        for x in data:
            if x < cashout_target:
                current_streak += 1
            else:
                break

        return {
            "count":           len(data),
            "pct_below_target": pct_below,
            "avg_multiplier":  avg,
            "max_multiplier":  hi,
            "min_multiplier":  lo,
            "current_loss_streak": current_streak,
            "max_loss_streak": max(streaks) if streaks else 0,
            "avg_loss_streak": round(sum(streaks) / len(streaks), 1) if streaks else 0,
        }

    return {
        "cashout_target": cashout_target,
        "last_50":  _stats(history[:50]),
        "last_100": _stats(history[:100]),
        "last_200": _stats(history[:200]),
    }


# ─── CSV Logger ──────────────────────────────────────────────────────────────

class RoundLogger:
    def __init__(self):
        os.makedirs(CSV_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(CSV_DIR, f"aviator_martingale_{ts}.csv")
        self._rows = []
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["timestamp", "step", "bet_amount", "multiplier", "outcome"])

    def log(self, step: int, bet: float, multiplier: float, outcome: str):
        row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), step, bet, multiplier, outcome]
        self._rows.append(row)
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

    def export_path(self):
        return self.path


# ─── Overlay (injected JS) ───────────────────────────────────────────────────

OVERLAY_JS = """
(function() {
  // Only inject once per page load
  if (document.getElementById('_bf_overlay')) return;

  const d = document.createElement('div');
  d.id = '_bf_overlay';

  // Position using left/top from the start so drag math is always correct
  d.style.cssText = [
    'position:fixed',
    'top:60px',
    'left:calc(100vw - 196px)',   // right-aligned but using left so drag works
    'z-index:2147483647',          // max z-index — always on top
    'background:rgba(15,15,25,0.95)',
    'color:#fff',
    'border:1px solid #555',
    'border-radius:10px',
    'padding:12px 14px',
    'font-family:monospace',
    'font-size:12px',
    'width:168px',
    'box-sizing:border-box',
    'user-select:none',
    'box-shadow:0 6px 24px rgba(0,0,0,0.6)',
  ].join(';');

  d.innerHTML = [
    '<div id="_bf_title" style="font-weight:bold;font-size:13px;margin-bottom:6px;',
    'cursor:move;padding-bottom:6px;border-bottom:1px solid #444;">',
    '✈️ BetFlow Bot</div>',

    // Status line — shows current bot state
    '<div id="_bf_status" style="margin:6px 0;color:#aaa;font-size:11px;',
    'min-height:14px;">Idle</div>',

    // Step/stake info line
    '<div id="_bf_step" style="margin-bottom:8px;color:#7cf;font-size:11px;',
    'min-height:14px;"></div>',

    // Buttons — no profit/loss shown, user sees balance on site
    '<button id="_bf_stop" style="width:100%;margin-bottom:4px;padding:6px 0;',
    'background:#8b1a1a;color:#fff;border:none;border-radius:5px;',
    'cursor:pointer;font-size:12px;">⏹ Stop Bot</button>',

    '<button id="_bf_sound" style="width:100%;margin-bottom:4px;padding:6px 0;',
    'background:#4a4a1a;color:#fff;border:none;border-radius:5px;',
    'cursor:pointer;font-size:12px;">� Sound Off</button>',

    '<button id="_bf_csv" style="width:100%;padding:6px 0;',
    'background:#1a3a7a;color:#fff;border:none;border-radius:5px;',
    'cursor:pointer;font-size:12px;">📁 Export CSV</button>',
  ].join('');

  document.body.appendChild(d);

  // ── Drag (title bar only, not buttons) ─────────────────────────────────
  const titleBar = document.getElementById('_bf_title');
  let dragging = false, startX = 0, startY = 0, origX = 0, origY = 0;

  titleBar.addEventListener('mousedown', function(e) {
    dragging = true;
    startX = e.clientX;
    startY = e.clientY;
    origX  = d.getBoundingClientRect().left;
    origY  = d.getBoundingClientRect().top;
    e.preventDefault();
  });

  document.addEventListener('mousemove', function(e) {
    if (!dragging) return;
    const nx = origX + (e.clientX - startX);
    const ny = origY + (e.clientY - startY);
    // Clamp to viewport
    const maxX = window.innerWidth  - d.offsetWidth;
    const maxY = window.innerHeight - d.offsetHeight;
    d.style.left = Math.max(0, Math.min(nx, maxX)) + 'px';
    d.style.top  = Math.max(0, Math.min(ny, maxY)) + 'px';
  });

  document.addEventListener('mouseup', function() { dragging = false; });

  // ── Command bus ─────────────────────────────────────────────────────────
  // Python polls window._bf_cmd every loop iteration
  window._bf_cmd = null;

  function _setCmd(cmd) {
    window._bf_cmd = cmd;
    const btn = cmd === 'stop'
      ? document.getElementById('_bf_stop')
      : cmd === 'sound'
      ? document.getElementById('_bf_sound')
      : document.getElementById('_bf_csv');
    if (btn) {
      const orig = btn.style.background;
      btn.style.background = '#fff';
      btn.style.color = '#000';
      setTimeout(function() {
        btn.style.background = orig;
        btn.style.color = '#fff';
      }, 180);
    }
  }

  document.getElementById('_bf_stop').onclick = function(e) {
    e.stopPropagation(); _setCmd('stop');
  };
  document.getElementById('_bf_sound').onclick = function(e) {
    e.stopPropagation();
    const btn = document.getElementById('_bf_sound');
    const isOff = btn.innerText.includes('Off');
    btn.innerText = isOff ? '🔊 Sound On' : '🔇 Sound Off';
    _setCmd('sound');
  };
  document.getElementById('_bf_csv').onclick = function(e) {
    e.stopPropagation(); _setCmd('csv');
  };
})();
"""

def inject_overlay(page):
    """Inject the floating overlay into the page. Safe to call multiple times."""
    try:
        page.evaluate(OVERLAY_JS)
    except Exception:
        pass

def _overlay_set(page, element_id: str, text: str):
    """Safely update an overlay element's text content."""
    try:
        page.evaluate(
            """(function(id, txt) {
                var el = document.getElementById(id);
                if (el) el.innerText = txt;
            })(%s, %s)""" % (json.dumps(element_id), json.dumps(text))
        )
    except Exception:
        pass

def overlay_status(page, msg: str):
    """Update the status line on the overlay."""
    _overlay_set(page, "_bf_status", msg)

def overlay_step(page, msg: str):
    """Update the step/stake info line on the overlay."""
    _overlay_set(page, "_bf_step", msg)

def poll_overlay_cmd(page):
    """
    Poll for a command from the overlay buttons.
    Returns 'stop' | 'csv' | None and resets the flag.
    """
    try:
        cmd = page.evaluate("window._bf_cmd")
        if cmd:
            page.evaluate("window._bf_cmd = null")
            return cmd
    except Exception:
        pass
    return None


# ─── Core Bot ────────────────────────────────────────────────────────────────

class AviatorMartingaleBot:
    """
    Martingale bot for Aviator — OdiBets & Betika (same Spribe engine).

    One-time setup (_setup_auto_tab):
      1. Click the "Auto" tab on panel 1
      2. Enable the Auto Cash Out toggle
      3. Type 1.3 into the cashout odds input
      (stake is NOT set here — it is set fresh before every single bet)

    Per-round loop:
      1. Wait for betting window (green Bet button visible & enabled)
      2. Type current step stake into stake input
      3. Click Bet button
      4. Wait for round to start (button goes disabled/cancel)
      5. Wait for round to end (button goes green again)
      6. Read crash multiplier from result-history
      7. >= 1.3 → WIN  → reset step_idx to 0 (stake back to 10)
         <  1.3 → LOSS → advance step_idx (10→40→174→754→3267)
      8. Last step loss → stop or reset per on_exhaustion config
    """

    def __init__(self, phone: str, password: str, progress_cb=None,
                 steps=None, auto_cashout=AUTO_CASHOUT, headless=False,
                 on_exhaustion="stop", site="OdiBets", simulation_mode=False):
        self.phone         = phone
        self.password      = password
        self.cb            = progress_cb or print
        self.steps         = steps or MARTINGALE_STEPS
        self.auto_cashout  = auto_cashout
        self.headless      = headless
        self.on_exhaustion = on_exhaustion
        self.site          = site
        self._site_cfg     = SITES.get(site, SITES["OdiBets"])
        self.simulation_mode = simulation_mode  # NEW: Dry run mode

        self._running  = False
        self._stop_evt = threading.Event()
        self.logger    = RoundLogger()
        self._step_idx = 0
        self._history  = []
        self._last_stake = None
        self._muted    = True  # game starts muted
        
        # Enhanced tracking
        self._session_start = None
        self._consecutive_losses = 0
        self._session_profit = 0.0
        self._last_balance = 0.0
        self._error_count = 0
        self._recovery_attempts = 0
        self._last_bet_amount = None  # Track actual bet amount used
        
        # Simulation mode tracking
        if simulation_mode:
            self._virtual_balance = 10000.0  # Start with 10k virtual KES

    # ── logging ──────────────────────────────────────────────────────────────

    def _log(self, msg):
        self.cb(f"[Bot] {msg}")

    # ── browser / login ──────────────────────────────────────────────────────

    def _launch(self):
        from playwright.sync_api import sync_playwright
        self._pw      = sync_playwright().start()
        self._browser = self._pw.firefox.launch(headless=self.headless)
        self._context = self._browser.new_context(
            viewport={"width": 414, "height": 896},
            user_agent="Mozilla/5.0 (Android 11; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
            locale="en-US",
            timezone_id="Africa/Nairobi",
        )
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(15000)

        url = self._site_cfg["url"]
        self._log(f"Navigating to {self.site} — {url}")
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)

        if self.site == "Betika":
            self._login_betika()
        else:
            self._login_odibets()

        # Wait for the Spribe game iframe to appear
        self._page.wait_for_selector(
            "#app iframe, iframe[src*='aviator'], iframe[src*='spribe'], iframe[src*='betika']",
            timeout=30000,
        )
        frame = self._get_frame()
        try:
            frame.locator("button").first.wait_for(state="visible", timeout=20000)
        except Exception:
            pass

        self._log("Game loaded — ready")
        # Mute game audio by default
        self._mute_game(muted=True)
        # Position browser on the LEFT half of the screen
        try:
            self._page.evaluate("""() => {
                const sw = window.screen.width;
                const sh = window.screen.height;
                window.moveTo(0, 0);
                window.resizeTo(Math.floor(sw / 2), sh);
            }""")
        except Exception:
            pass
        inject_overlay(self._page)
        # Re-inject after any post-login navigation (Betika redirects away then back)
        self._page.on("load", lambda _: inject_overlay(self._page))

    def _login_odibets(self):
        """OdiBets login flow."""
        self._page.wait_for_selector("button", timeout=10000)
        # Dismiss any cookie/consent banner first
        for dismiss_sel in ["button:has-text('Accept')", "button:has-text('OK')", "[id*='cookie'] button", "[class*='consent'] button"]:
            try:
                self._page.locator(dismiss_sel).first.click(timeout=2000)
                time.sleep(0.5)
            except Exception:
                pass

        # Click Login — use force=True since the button may be obscured by iframe overlay
        try:
            self._page.get_by_role("button", name="Login to play").click(force=True, timeout=8000)
        except Exception:
            try:
                self._page.locator(".iframe-login").click(force=True, timeout=5000)
            except Exception:
                self._page.locator("button:has-text('Login')").first.click(force=True, timeout=5000)
        self._log("Login dialog opened")
        time.sleep(1)

        try:
            self._page.get_by_role("textbox", name="07xxxxxxxx").fill(self.phone)
        except Exception:
            self._page.locator("input[type='tel'], input[placeholder*='07']").first.fill(self.phone)
        self._log("Phone entered")

        try:
            self._page.get_by_role("textbox", name="• • • • • • • •").fill(self.password)
        except Exception:
            self._page.locator("input[type='password']").first.fill(self.password)
        self._log("Password entered")
        
        # Small delay to ensure form is ready
        time.sleep(0.5)
        
        # Check if automation is being detected/blocked
        try:
            detection_check = self._page.evaluate("""() => {
                return {
                    webdriver: navigator.webdriver,
                    plugins: navigator.plugins.length,
                    languages: navigator.languages,
                    platform: navigator.platform,
                    userAgent: navigator.userAgent.substring(0, 50)
                };
            }""")
            self._log(f"Detection check: webdriver={detection_check.get('webdriver')}, plugins={detection_check.get('plugins')}")
            if detection_check.get('webdriver') == True:
                self._log("⚠️ WARNING: Automation detected by site!")
        except Exception:
            pass

        # Click the green "Login to Odibets" button
        self._log("Clicking login button...")
        
        # Check if button is actually enabled before clicking
        try:
            btn_state = self._page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const loginBtn = buttons.find(b => b.textContent.includes('Login to Odibets'));
                if (!loginBtn) return {found: false};
                return {
                    found: true,
                    disabled: loginBtn.disabled,
                    text: loginBtn.textContent.trim(),
                    className: loginBtn.className
                };
            }""")
            self._log(f"Button state: {btn_state}")
            
            if btn_state.get('disabled'):
                self._log("⚠️ WARNING: Login button is DISABLED! Check if credentials are valid.")
        except Exception:
            pass
        
        # Add human-like delay before clicking (important!)
        time.sleep(0.8)
        
        try:
            # EXACT same method as diagnostic script that worked
            self._page.locator("button:has-text('Login to Odibets')").first.click(timeout=5000)
            self._log("✅ Login button clicked")
            
            # Give it a moment to process
            time.sleep(1.5)
            
        except Exception as e:
            self._log(f"❌ Click failed: {str(e)[:100]}")
            # Try JavaScript as fallback
            try:
                self._page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const loginBtn = buttons.find(b => b.textContent.trim() === 'Login to Odibets');
                    if (loginBtn) loginBtn.click();
                }""")
                self._log("✅ Login button clicked (JavaScript)")
                time.sleep(1.5)
            except Exception as e2:
                self._log(f"❌ JavaScript click also failed: {str(e2)[:100]}")
        
        # MANDATORY: Wait for login dialog to close before proceeding
        self._log("Waiting for login dialog to close...")
        dialog_closed = False
        for attempt in range(15):  # 15 seconds max
            try:
                # Check if phone input is gone (dialog closed)
                phone_count = self._page.locator("input[type='tel'], input[placeholder*='07']").count()
                if phone_count == 0:
                    dialog_closed = True
                    self._log("✅ Login dialog closed successfully")
                    break
                else:
                    self._log(f"Attempt {attempt+1}/15: Dialog still open (phone inputs: {phone_count})")
            except Exception:
                pass
            time.sleep(1)
        
        if not dialog_closed:
            self._log("❌ ERROR: Login dialog did not close - login button was NOT clicked!")
            self._log("Taking screenshot for debugging...")
            try:
                os.makedirs("debug_screenshots", exist_ok=True)
                self._page.screenshot(path="debug_screenshots/login_failed_dialog_still_open.png")
            except:
                pass
            raise RuntimeError("Login failed - dialog still open after 15 seconds. Check debug_screenshots/")
        
        # Wait for page to settle after login
        try:
            self._page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            time.sleep(3)

    def _login_betika(self):
        """Betika login flow."""
        try:
            self._page.locator("button:has-text('Login for real play')").click(timeout=10000)
        except Exception:
            try:
                self._page.locator("a:has-text('Login for real play')").click(timeout=5000)
            except Exception:
                self._page.locator("a:has-text('Login'), button:has-text('Login')").first.click(timeout=5000)
        self._log("Betika login clicked")
        time.sleep(2)

        try:
            phone_input = self._page.locator(
                "input[type='tel'], input[name*='phone'], input[name*='user'], "
                "input[placeholder*='07'], input[placeholder*='phone']"
            ).first
            phone_input.wait_for(state="visible", timeout=8000)
            phone_input.fill(self.phone)
        except Exception:
            self._page.locator("input").first.fill(self.phone)
        self._log("Phone entered")

        try:
            self._page.locator("input[type='password']").first.fill(self.password)
        except Exception:
            self._page.locator("input").nth(1).fill(self.password)
        self._log("Password entered")

        try:
            self._page.locator("button:has-text('Login')").last.click(timeout=8000)
        except Exception:
            try:
                self._page.locator("button[type='submit']").first.click(timeout=8000)
            except Exception:
                pass
        self._log("Betika login submitted")
        time.sleep(3)

        # If redirected away from aviator, go back
        if "aviator" not in self._page.url:
            self._page.goto(self._site_cfg["url"], wait_until="domcontentloaded", timeout=20000)

    # ── frame helpers ────────────────────────────────────────────────────────

    def _get_frame(self):
        """
        Re-fetch the live Spribe game frame.
        Tries OdiBets (#app iframe) first, then Betika-specific selectors,
        then generic fallbacks.
        """
        selectors = [
            "#app iframe",
            "iframe[src*='spribe']",
            "iframe[src*='aviator']",
            "iframe[src*='betika']",
            "iframe",
        ]
        for sel in selectors:
            try:
                handle = self._page.locator(sel).first.element_handle(timeout=5000)
                if handle:
                    frame = handle.content_frame()
                    if frame:
                        return frame
            except Exception:
                continue
        raise RuntimeError("Game iframe not found")

    def _mute_game(self, muted: bool = True):
        """Mute or unmute all audio in the game iframe via JS."""
        try:
            frame = self._get_frame()
            frame.evaluate("""(muted) => {
                // Mute all audio/video elements
                document.querySelectorAll('audio, video').forEach(el => {
                    el.muted = muted;
                    if (muted) el.pause();
                });
                // Override AudioContext to silence new sounds
                if (muted) {
                    if (!window._bf_gain_node && window.AudioContext) {
                        try {
                            const ctx = new AudioContext();
                            const gain = ctx.createGain();
                            gain.gain.value = 0;
                            gain.connect(ctx.destination);
                            window._bf_gain_node = gain;
                        } catch(e) {}
                    }
                } else {
                    if (window._bf_gain_node) {
                        window._bf_gain_node.gain.value = 1;
                    }
                }
                // Also try clicking the game's own mute button if present
                const muteBtn = document.querySelector(
                    '[class*="sound"] button, [class*="mute"] button, ' +
                    'button[class*="sound"], button[class*="mute"]'
                );
                if (muteBtn) {
                    const isMuted = muteBtn.className.includes('off') || muteBtn.className.includes('muted');
                    if (muted && !isMuted) muteBtn.click();
                    if (!muted && isMuted) muteBtn.click();
                }
            }""", muted)
            self._muted = muted
        except Exception:
            pass

    # ── DOM probe (debug helper) ─────────────────────────────────────────────

    def _probe_dom(self):
        """Dump relevant DOM info to dom_probe.json for selector debugging."""
        frame = self._get_frame()
        result = frame.evaluate("""() => {
            const info = {};
            const classes = new Set();
            document.querySelectorAll('*').forEach(el => {
                if (el.className && typeof el.className === 'string')
                    el.className.split(' ').forEach(c => { if(c) classes.add(c); });
            });
            info.relevant_classes = [...classes].filter(c =>
                /multi|coef|crash|fly|round|history|result|bet|cashout|win|lose|active|wait|start|end/i.test(c)
            ).slice(0, 80);
            info.buttons = [...document.querySelectorAll('button')]
                .map(b => b.textContent.trim().slice(0,40)).filter(t=>t);
            info.inputs = [...document.querySelectorAll('input')].map(i => ({
                type: i.type, placeholder: i.placeholder,
                value: i.value, class: i.className.slice(0,60)
            }));
            const hist = document.querySelector('[class*="history"]');
            info.history_html = hist ? hist.innerHTML.slice(0, 500) : 'not found';
            return info;
        }""")
        with open("dom_probe.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        self._log("DOM probe saved → dom_probe.json")
        self._log(f"Classes: {result.get('relevant_classes', [])}")
        self._log(f"Buttons: {result.get('buttons', [])}")

    # ── one-time panel setup ─────────────────────────────────────────────────

    def _setup_auto_tab(self):
        """
        One-time setup — runs once before the first bet.
        1. Click Auto tab
        2. Enable Auto Cash Out toggle (.cash-out-switcher .oval)
        3. Set cashout odds to 1.3x via Angular-compatible setter
        """
        self._log("Setting up panel...")
        frame = self._get_frame()

        # 1. Click the Auto tab
        frame.evaluate("""() => {
            const btns = document.querySelectorAll('.bet-control button');
            for (const b of btns) {
                if (b.textContent.trim().toLowerCase() === 'auto') { b.click(); return; }
            }
        }""")
        time.sleep(1.2)

        # 2. Enable Auto Cash Out toggle only if currently OFF
        # DOM probe confirmed: toggle div has class 'input-switch off' when disabled
        frame.evaluate("""() => {
            const toggle_div = document.querySelector('.bet-control .cash-out-switcher');
            if (!toggle_div) return;
            const sw = toggle_div.querySelector('.input-switch');
            // Only click if it has 'off' class (disabled state)
            if (sw && sw.className.includes('off')) {
                const oval = toggle_div.querySelector('.oval');
                if (oval) oval.click();
            }
        }""")
        time.sleep(0.8)

        # 3. Set cashout odds — Angular-compatible value setter
        result = frame.evaluate("""(val) => {
            const inputs = document.querySelectorAll('.bet-control input');
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
        }""", str(self.auto_cashout))
        self._log(f"✅ Panel ready — cashout set to {result}x")

    # ── per-bet stake setter ─────────────────────────────────────────────────

    def _set_stake(self, amount: float):
        """Set stake via JS — Angular-compatible, no scrolling."""
        frame = self._get_frame()
        frame.evaluate("""(val) => {
            const si = document.querySelector('.bet-control input');
            if (!si) return;
            si.focus();
            si.select();
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(si, val);
            si.dispatchEvent(new Event('input',  { bubbles: true }));
            si.dispatchEvent(new Event('change', { bubbles: true }));
            si.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
            si.blur();
        }""", str(int(amount)))
        time.sleep(0.15)
        self._last_stake = amount
        self._log(f"Stake → {int(amount)} KES")

    def _check_balance_threshold(self):
        """Check if balance is above minimum threshold"""
        frame = self._get_frame()
        balance = frame.evaluate("""() => {
            const bal = document.querySelector('[class*="balance"]');
            if (bal) {
                const text = bal.textContent.replace(/[^0-9.]/g, '');
                return parseFloat(text) || 0;
            }
            return 0;
        }""")
        
        # Need enough for at least one full sequence + buffer
        min_balance = sum(self.steps) * 1.2
        should_continue = balance >= EMERGENCY_STOP_CONDITIONS["min_balance_threshold"]
        
        self._last_balance = balance
        return should_continue, balance

    def _click_bet_button(self, amount: float):
        """Click Bet button via JS — no Playwright locator, no scroll."""
        # Simulation mode - don't actually bet
        if self.simulation_mode:
            self._log(f"[SIMULATION] Would bet {int(amount)} KES — step {self._step_idx+1}/{len(self.steps)}")
            return
        
        frame = self._get_frame()

        # Check for insufficient funds — balance element or error toast
        low_balance = frame.evaluate("""() => {
            // Check for error/toast messages
            const msgs = document.querySelectorAll('[class*="error"], [class*="alert"], [class*="toast"], [class*="notification"]');
            for (const el of msgs) {
                const txt = el.textContent.toLowerCase();
                if (txt.includes('insufficient') || txt.includes('not enough') ||
                    txt.includes('low balance') || txt.includes('funds')) {
                    return el.textContent.trim();
                }
            }
            // Check balance value directly
            const bal = document.querySelector('[class*="balance"] [class*="amount"], [class*="balance-value"]');
            if (bal) {
                const v = parseFloat(bal.textContent.replace(/[^0-9.]/g, ''));
                if (!isNaN(v) && v < 10) return 'Balance too low: ' + bal.textContent.trim();
            }
            return null;
        }""")
        if low_balance:
            raise RuntimeError(f"Insufficient funds — {low_balance}")

        frame.evaluate("""() => {
            const panel = document.querySelector('.bet-control');
            if (!panel) return;
            const btns = panel.querySelectorAll('button');
            for (const b of btns) {
                const txt = b.textContent.trim().toLowerCase();
                if (!b.disabled && txt.includes('bet') && !txt.includes('cancel')) {
                    b.click(); return;
                }
            }
        }""")
        self._log(f"✅ Bet {int(amount)} KES — step {self._step_idx+1}/{len(self.steps)}")

    def _verify_bet_placed(self, expected_amount: float):
        """Verify bet was actually placed and accepted"""
        frame = self._get_frame()
        
        bet_confirmed = frame.evaluate("""(amount) => {
            // Look for active bet indicator
            const indicators = [
                '[class*="active-bet"]',
                '[class*="bet-placed"]',
                '.bet-control [class*="active"]'
            ];
            
            for (const sel of indicators) {
                const el = document.querySelector(sel);
                if (el && el.textContent.includes(amount.toString())) {
                    return true;
                }
            }
            
            // Check if stake input is disabled (bet in progress)
            const stakeInput = document.querySelector('.bet-control input');
            if (stakeInput && stakeInput.disabled) {
                return true;
            }
            
            // Check if button changed to Cancel
            const btn = document.querySelector('.bet-control button');
            if (btn && btn.textContent.toLowerCase().includes('cancel')) {
                return true;
            }
            
            return false;
        }""", int(expected_amount))
        
        return bet_confirmed

    # ── multiplier reader ────────────────────────────────────────────────────

    def _read_multiplier(self):
        """
        Read the crash multiplier from the DOM after a round ends.
        Returns float or None.

        Strategy:
          1. Pull full history via _get_history (up to 200 items) — sync self._history
             with whatever the DOM currently shows. This keeps the analyzer dataset
             always up to date even if a round was missed.
          2. The newest item in history IS the last round's result.
          3. Fallback: scan coef/multiplier/crash class elements directly.
        """
        frame = self._get_frame()

        # ── Primary: sync full history from DOM ──────────────────────────────
        # Retry a few times to give the DOM time to update after round end
        dom_history = []
        for _ in range(8):
            dom_history = _get_history(frame, limit=200)
            if dom_history:
                break
            time.sleep(0.4)

        if dom_history:
            # Merge: keep DOM history as source of truth, preserve any extras
            self._history = dom_history[:200]
            return dom_history[0]  # newest = last round result

        # ── Fallback: direct JS scan for coef/multiplier elements ────────────
        val = frame.evaluate("""() => {
            for (const sel of ['[class*="coef"]','[class*="multiplier"]','[class*="crash"]']) {
                for (const el of document.querySelectorAll(sel)) {
                    if (el.children.length > 0) continue;
                    const v = parseFloat(el.textContent.trim().replace('x','').replace(',','.'));
                    if (!isNaN(v) && v >= 1.0 && v < 10000) return v;
                }
            }
            return null;
        }""")
        if val:
            result = float(val)
            # Prepend to history so analyzer always has data
            if not self._history or self._history[0] != result:
                self._history.insert(0, result)
                self._history = self._history[:200]
            return result

        return None

    def _read_multiplier_robust(self):
        """Enhanced multiplier reading with multiple verification attempts"""
        attempts = []
        frame = self._get_frame()

        # Attempt 1-3: History sync with verification
        for _ in range(3):
            hist = _get_history(frame, limit=10)
            if hist:
                attempts.append(hist[0])
            time.sleep(0.2)

        # Attempt 4: Direct DOM scan
        direct_val = frame.evaluate("""() => {
            const selectors = [
                '.result-history span:first-child',
                '[class*="coef"]',
                '[class*="multiplier"]',
                '[class*="crash"]'
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.children.length === 0) {
                    const val = parseFloat(el.textContent.replace(/[^0-9.]/g, ''));
                    if (val >= 1.0 && val < 10000) return val;
                }
            }
            return null;
        }""")

        if direct_val:
            attempts.append(float(direct_val))

        # Consensus: most common value (handles occasional DOM glitches)
        if attempts:
            from collections import Counter
            most_common = Counter(attempts).most_common(1)[0][0]

            # Update history
            if not self._history or self._history[0] != most_common:
                self._history.insert(0, most_common)
                self._history = self._history[:200]

            return most_common

        return None


    # ── single round ─────────────────────────────────────────────────────────

    def _check_circuit_breaker(self):
        """Check if circuit breaker should activate"""
        # Check consecutive losses
        if self._consecutive_losses >= EMERGENCY_STOP_CONDITIONS["max_consecutive_losses"]:
            self._log(f"🚨 Circuit breaker: {self._consecutive_losses} consecutive losses")
            return True
        
        # Check session loss
        if self._session_profit < -EMERGENCY_STOP_CONDITIONS["max_session_loss"]:
            self._log(f"🚨 Circuit breaker: Session loss {abs(self._session_profit):.0f} KES")
            return True
        
        # Check stop loss threshold
        if self._session_profit <= EMERGENCY_STOP_CONDITIONS["stop_loss_threshold"]:
            self._log(f"🛑 Stop loss hit: {self._session_profit:.0f} KES")
            return True
        
        # Check take profit target
        if self._session_profit >= EMERGENCY_STOP_CONDITIONS["take_profit_target"]:
            self._log(f"🎯 Take profit target reached: {self._session_profit:.0f} KES")
            return True
        
        # Check session duration
        if self._session_start:
            duration = time.time() - self._session_start
            if duration > EMERGENCY_STOP_CONDITIONS["max_session_duration"]:
                self._log(f"🚨 Circuit breaker: Session duration {duration/3600:.1f} hours")
                return True
        
        return False

    def _auto_recover_from_error(self, error: Exception):
        """Attempt automatic recovery from common errors"""
        error_str = str(error).lower()
        self._recovery_attempts += 1
        
        if self._recovery_attempts > 3:
            self._log("❌ Max recovery attempts reached")
            return False
        
        # Network/timeout errors - refresh page
        if any(x in error_str for x in ['timeout', 'network', 'connection']):
            self._log("🔄 Auto-recovery: Refreshing page...")
            try:
                self._page.reload()
                time.sleep(3)
                frame = self._get_frame()
                if frame:
                    self._setup_auto_tab()
                    self._recovery_attempts = 0
                    return True
            except:
                pass
        
        # Element not found - re-setup
        if 'element' in error_str or 'selector' in error_str:
            self._log("🔄 Auto-recovery: Re-initializing game...")
            try:
                self._setup_auto_tab()
                self._recovery_attempts = 0
                return True
            except:
                pass
        
        return False

    def _simulate_round(self):
        """Simulate a complete round for testing without real bets"""
        import random
        
        bet_amount = self.steps[self._step_idx]
        
        # Cap bet amount based on virtual balance
        max_allowed = self._virtual_balance * EMERGENCY_STOP_CONDITIONS["max_stake_percent"]
        if bet_amount > max_allowed:
            self._log(f"[SIMULATION] Stake {bet_amount} exceeds 15% of virtual balance, capping at {max_allowed:.0f}")
            bet_amount = max_allowed
        
        # Check minimum balance
        if self._virtual_balance < EMERGENCY_STOP_CONDITIONS["min_balance_threshold"]:
            raise RuntimeError(f"Virtual balance too low: {self._virtual_balance:.0f} KES")
        
        self._last_bet_amount = bet_amount
        self._last_balance = self._virtual_balance
        
        self._log(f"[SIMULATION] Betting {int(bet_amount)} KES (Virtual balance: {int(self._virtual_balance)} KES)")
        
        # Generate realistic multiplier based on actual Aviator distribution
        # ~60% crash before 2x, ~30% between 2-5x, ~10% above 5x
        rand = random.random()
        if rand < 0.6:
            multiplier = round(random.uniform(1.0, 2.0), 2)
        elif rand < 0.9:
            multiplier = round(random.uniform(2.0, 5.0), 2)
        else:
            multiplier = round(random.uniform(5.0, 20.0), 2)
        
        # Simulate round duration (5-15 seconds)
        self._log(f"[SIMULATION] Round in progress...")
        time.sleep(random.uniform(2, 5))  # Faster for testing
        
        # Update virtual balance
        if multiplier >= self.auto_cashout:
            profit = bet_amount * (self.auto_cashout - 1)
            self._virtual_balance += profit
            self._log(f"[SIMULATION] WIN at {multiplier}x (cashed out at {self.auto_cashout}x) | Profit: +{profit:.0f} KES")
        else:
            self._virtual_balance -= bet_amount
            self._log(f"[SIMULATION] LOSS at {multiplier}x (needed {self.auto_cashout}x) | Loss: -{bet_amount:.0f} KES")
        
        return multiplier

    def _run_round(self):
        """
        One full round: wait → stake → bet → wait start → wait end → read result.
        Returns crash multiplier (float) or None.
        """
        # Simulation mode - generate fake round
        if self.simulation_mode:
            return self._simulate_round()
        
        frame = self._get_frame()

        # 0. Check balance before betting
        should_continue, balance = self._check_balance_threshold()
        if not should_continue:
            raise RuntimeError(f"Balance too low: {balance:.0f} KES (min: {EMERGENCY_STOP_CONDITIONS['min_balance_threshold']} KES)")

        # 1. Wait for betting window to be open
        if not _is_betting_window_open(frame):
            self._log("Waiting for betting window...")
            overlay_status(self._page, "Waiting for round...")
            if not _wait_for_round_end(frame, timeout_s=120):
                self._log("⚠️ Timed out waiting for betting window")
                return None
            time.sleep(0.3)

        # 2. Set stake (with dynamic adjustment based on balance)
        bet_amount = self.steps[self._step_idx]
        max_allowed = balance * EMERGENCY_STOP_CONDITIONS["max_stake_percent"]
        if bet_amount > max_allowed:
            self._log(f"⚠️ Stake {bet_amount} exceeds {EMERGENCY_STOP_CONDITIONS['max_stake_percent']*100}% of balance, capping at {max_allowed:.0f}")
            bet_amount = max_allowed
        
        # Store actual bet amount for tracking
        self._last_bet_amount = bet_amount
        
        overlay_step(self._page, f"Step {self._step_idx+1}/{len(self.steps)} | {int(bet_amount)} KES | Bal: {int(balance)}")
        self._set_stake(bet_amount)

        # 3. Click Bet
        self._click_bet_button(bet_amount)
        overlay_status(self._page, f"Bet {int(bet_amount)} KES — in flight...")

        # 3b. Verify bet was accepted
        time.sleep(0.5)
        if not self._verify_bet_placed(bet_amount):
            self._log("⚠️ Bet confirmation unclear, checking round state...")
        
        frame = self._get_frame()
        bet_accepted = _wait_for_round_start(frame, timeout_s=5)
        if not bet_accepted:
            # Bet didn't register — likely no funds
            no_funds = frame.evaluate("""() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const txt = el.textContent.toLowerCase();
                    if (el.children.length === 0 && (
                        txt.includes('insufficient') || txt.includes('not enough') ||
                        txt.includes('low balance') || txt.includes('no funds')
                    )) return el.textContent.trim();
                }
                return null;
            }""")
            if no_funds:
                raise RuntimeError(f"Insufficient funds — {no_funds}")
            self._log("⚠️ Bet not confirmed — round may have started already, continuing")
        self._log("Round in progress...")
        overlay_status(self._page, "Round in progress...")

        # 5. Wait for round to end (button goes green again)
        _wait_for_round_end(frame, timeout_s=120)
        time.sleep(0.8)  # let DOM update with result

        # 6. Read multiplier with enhanced verification
        return self._read_multiplier_robust()

    # ── stop browser ─────────────────────────────────────────────────────────

    def _stop_browser(self):
        for attr in ("_context", "_browser", "_pw"):
            try:
                obj = getattr(self, attr, None)
                if obj:
                    obj.close() if attr != "_pw" else obj.stop()
            except Exception:
                pass

    # ── main loop ────────────────────────────────────────────────────────────

    def run(self):
        mode_str = "[SIMULATION MODE]" if self.simulation_mode else ""
        self._log(f"Starting Martingale bot {mode_str} | Site: {self.site}")
        self._log(f"Steps: {self.steps}")
        self._log(f"Auto cashout: {self.auto_cashout}x | On exhaustion: {self.on_exhaustion}")
        self._log(f"Safety: Max {EMERGENCY_STOP_CONDITIONS['max_consecutive_losses']} losses, "
                  f"Max loss {EMERGENCY_STOP_CONDITIONS['max_session_loss']} KES, "
                  f"Stop loss {EMERGENCY_STOP_CONDITIONS['stop_loss_threshold']} KES, "
                  f"Take profit {EMERGENCY_STOP_CONDITIONS['take_profit_target']} KES, "
                  f"Min balance {EMERGENCY_STOP_CONDITIONS['min_balance_threshold']} KES")

        # Skip browser launch in simulation mode
        if not self.simulation_mode:
            try:
                self._launch()
            except Exception as e:
                self._log(f"❌ Launch failed: {e}")
                return

            # One-time setup: Auto tab + cashout toggle + cashout odds
            self._setup_auto_tab()
        else:
            self._log(f"[SIMULATION] Starting with virtual balance: {self._virtual_balance:.0f} KES")

        self._running  = True
        self._step_idx = 0
        self._stop_evt.clear()
        self._session_start = time.time()
        self._consecutive_losses = 0
        self._session_profit = 0.0
        if not self.simulation_mode:
            overlay_status(self._page, "Running")
        else:
            self._last_balance = self._virtual_balance

        while not self._stop_evt.is_set():
            # Check circuit breaker
            if self._check_circuit_breaker():
                overlay_status(self._page, "Circuit breaker activated")
                break
            
            # Check overlay stop/csv commands (skip in simulation mode)
            if not self.simulation_mode:
                cmd = poll_overlay_cmd(self._page)
                if cmd == "stop":
                    self._log("Stop requested via overlay")
                    break
                if cmd == "csv":
                    self._log(f"CSV: {self.logger.export_path()}")
                if cmd == "sound":
                    self._muted = not self._muted
                    self._mute_game(self._muted)
                    self._log(f"Sound {'OFF' if self._muted else 'ON'}")

            try:
                multiplier = self._run_round()
            except RuntimeError as e:
                if "insufficient" in str(e).lower() or "balance too low" in str(e).lower():
                    self._log(f"🚫 {e}")
                    overlay_status(self._page, "Stopped — Insufficient funds")
                    break
                self._log(f"Round error: {e}")
                # Attempt auto-recovery
                if self._auto_recover_from_error(e):
                    self._log("✅ Auto-recovery successful, continuing...")
                    time.sleep(2)
                    continue
                else:
                    self._error_count += 1
                    if self._error_count >= 5:
                        self._log("❌ Too many errors, stopping")
                        break
                    time.sleep(2)
                    continue
            except Exception as e:
                self._log(f"Round error: {e}")
                # Attempt auto-recovery
                if self._auto_recover_from_error(e):
                    self._log("✅ Auto-recovery successful, continuing...")
                    time.sleep(2)
                    continue
                else:
                    self._error_count += 1
                    if self._error_count >= 5:
                        self._log("❌ Too many errors, stopping")
                        break
                    time.sleep(2)
                    continue

            if multiplier is None:
                self._log("⚠️ Could not read multiplier — skipping round")
                self._error_count += 1
                continue

            # Use actual bet amount (may have been capped)
            bet_amount = self._last_bet_amount or self.steps[self._step_idx]
            won        = multiplier >= self.auto_cashout
            outcome    = "win" if won else "loss"
            self.logger.log(self._step_idx + 1, bet_amount, multiplier, outcome)

            # Update session tracking
            if won:
                profit = bet_amount * (self.auto_cashout - 1)
                self._session_profit += profit
                self._consecutive_losses = 0
                self._error_count = 0  # Reset error count on success
            else:
                self._session_profit -= bet_amount
                self._consecutive_losses += 1

            # Passive stats — raw data only, no predictions
            stats = analyze(self._history, cashout_target=self.auto_cashout)
            s50   = stats["last_50"]
            self._log(
                f"Result: {multiplier}x → {'✅ WIN' if won else '❌ LOSS'} | "
                f"Step {self._step_idx+1} | Bet {int(bet_amount)} KES | "
                f"Balance: {int(self._last_balance)} KES | "
                f"Session P/L: {self._session_profit:+.0f} KES | "
                f"Streak: {self._consecutive_losses} losses | "
                f"History: {len(self._history)} rounds | "
                f"50-avg: {s50.get('avg_multiplier','?')} | "
                f"<{self.auto_cashout}: {s50.get('pct_below_target','?')}%"
            )

            if won:
                self._log(f"✅ WIN at {multiplier}x — resetting to step 1 (stake {self.steps[0]} KES)")
                self._step_idx  = 0
                self._last_stake = None  # force stake re-type on next bet
            else:
                self._log(f"❌ LOSS at {multiplier}x (needed {self.auto_cashout}x)")
                next_idx = self._step_idx + 1
                if next_idx >= len(self.steps):
                    if self.on_exhaustion == "reset":
                        self._log("Sequence exhausted — resetting to step 1")
                        self._step_idx  = 0
                        self._last_stake = None
                    else:
                        self._log("Sequence exhausted — stopping")
                        overlay_status(self._page, "Sequence exhausted — stopped")
                        break
                else:
                    self._step_idx = next_idx
                    self._log(f"→ Next step {self._step_idx+1}: {self.steps[self._step_idx]} KES")

            # Update overlay with next step info (skip in simulation mode)
            next_stake = self.steps[self._step_idx]
            if not self.simulation_mode:
                overlay_step(self._page, f"Next → step {self._step_idx+1} | {int(next_stake)} KES")

        self._running = False
        
        # Final session summary
        duration = time.time() - self._session_start if self._session_start else 0
        final_balance = self._virtual_balance if self.simulation_mode else self._last_balance
        self._log("=" * 60)
        self._log("SESSION SUMMARY")
        self._log(f"Mode: {'SIMULATION' if self.simulation_mode else 'LIVE'}")
        self._log(f"Duration: {duration/60:.1f} minutes")
        self._log(f"Total rounds: {len(self.logger._rows)}")
        self._log(f"Final P/L: {self._session_profit:+.0f} KES")
        self._log(f"Final balance: {final_balance:.0f} KES")
        self._log(f"Max consecutive losses: {self._consecutive_losses}")
        self._log(f"CSV saved: {self.logger.export_path()}")
        self._log("=" * 60)
        
        if not self.simulation_mode:
            overlay_status(self._page, f"Stopped | P/L: {self._session_profit:+.0f} KES")
            self._stop_browser()

    def stop(self):
        self._stop_evt.set()

    def run_in_thread(self):
        t = threading.Thread(target=self.run, daemon=True)
        t.start()
        return t


# ─── Entry point ─────────────────────────────────────────────────────────────

def run_martingale_bot(phone: str, password: str, progress_cb=None,
                       steps=None, auto_cashout=AUTO_CASHOUT, headless=False,
                       on_exhaustion="stop", site="OdiBets"):
    bot = AviatorMartingaleBot(
        phone=phone, password=password,
        progress_cb=progress_cb,
        steps=steps or MARTINGALE_STEPS,
        auto_cashout=auto_cashout,
        headless=headless,
        on_exhaustion=on_exhaustion,
        site=site,
    )
    bot.run_in_thread()
    return bot


if __name__ == "__main__":
    import sys
    phone    = sys.argv[1] if len(sys.argv) > 1 else input("Phone: ")
    password = sys.argv[2] if len(sys.argv) > 2 else input("Password: ")
    site     = sys.argv[3] if len(sys.argv) > 3 else "OdiBets"
    bot = AviatorMartingaleBot(phone=phone, password=password, site=site)
    bot.run()
