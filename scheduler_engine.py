"""
Scheduler Engine — Betika Aviator multi-account auto-runner
===========================================================
Commercial-grade, self-healing core.

Features
--------
* Staggered worker starts — random delay between each worker launch so
  requests look like organic traffic, not a synchronized burst.
* Pre-run balance sweep — parallel API check of all accounts before any
  browser opens. Prints a summary table and stops if everything is zero.
* Account health tracking — tracks consecutive auth failures, zero-balance
  days, last run date. Warns operator before a run if accounts look dead.
* Rate-limit detection — if Betika returns 429 or repeated auth errors the
  engine enters a configurable cooldown before continuing.
* Session CSV export — every completed run writes a dated CSV to results/.
* Desktop notification — winsound + Windows toast when a run finishes.
* Self-healing watchdog — if all workers die with work remaining, new ones
  are spawned automatically.
* NTP time source — never trusts the PC clock alone.
"""

import os
import csv
import json
import math
import random
import time
import queue
import threading
from datetime import datetime, timedelta

import run_multi_betika as multi
import betika_balance as bal_mod

# ── Time source ───────────────────────────────────────────────────────────────
_NTP_SERVERS = [
    "time.cloudflare.com",
    "pool.ntp.org",
    "time.google.com",
    "time.windows.com",
]
_WORLDTIME_URL = "http://worldtimeapi.org/api/timezone/Africa/Nairobi"
_time_cache_lock = threading.Lock()
_time_cache = None
_TIME_CACHE_TTL = 300


def _fetch_utc_ntp():
    try:
        import ntplib
    except ImportError:
        return None
    c = ntplib.NTPClient()
    for srv in _NTP_SERVERS:
        try:
            resp = c.request(srv, version=3, timeout=3)
            return datetime.utcfromtimestamp(resp.tx_time)
        except Exception:
            continue
    return None


def _fetch_utc_http():
    try:
        import urllib.request, json as _j
        with urllib.request.urlopen(_WORLDTIME_URL, timeout=5) as r:
            data = _j.loads(r.read().decode())
        raw = data["datetime"][:26]
        naive = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")
        offset_str = raw[19:]
        sign = 1 if offset_str[0] == '+' else -1
        oh, om = int(offset_str[1:3]), int(offset_str[4:6])
        return naive - timedelta(hours=sign * oh, minutes=sign * om)
    except Exception:
        return None


def _sync_time_cache(emit=None):
    utc = _fetch_utc_ntp()
    source = "NTP"
    if utc is None:
        utc = _fetch_utc_http()
        source = "worldtimeapi.org"
    if utc is None:
        utc = datetime.utcnow()
        source = "LOCAL CLOCK ⚠"
        if emit:
            emit("⚠ Network time unavailable — using local clock.")
    with _time_cache_lock:
        global _time_cache
        _time_cache = (utc, time.monotonic())
    return utc, source


def true_utc(emit=None):
    global _time_cache
    with _time_cache_lock:
        cache = _time_cache
    if cache is None:
        utc, _ = _sync_time_cache(emit=emit)
        return utc
    ref_utc, ref_mono = cache
    elapsed = time.monotonic() - ref_mono
    if elapsed > _TIME_CACHE_TTL:
        threading.Thread(target=_sync_time_cache, kwargs={"emit": emit},
                         daemon=True).start()
    return ref_utc + timedelta(seconds=elapsed)


def ktime(emit=None):
    return true_utc(emit=emit) + timedelta(hours=3)


# ── Constants ─────────────────────────────────────────────────────────────────
STATE_PATH        = os.path.join("config", "scheduler_state.json")
HEALTH_PATH       = os.path.join("config", "account_health.json")
RESULTS_DIR       = "results"

DEFAULT_WORKERS   = 4
DEFAULT_ROUNDS    = 50
DEFAULT_STAKE     = 10.0
DEFAULT_CASHOUT   = 1.01
MAX_ATTEMPTS      = 3
RETRY_BACKOFF_SEC = 8

# Stagger defaults (seconds between launching consecutive workers)
DEFAULT_STAGGER_MIN = 5
DEFAULT_STAGGER_MAX = 20

# Rate-limit cooldown
RATE_LIMIT_COOLDOWN = 90   # seconds to pause when 429 / mass auth errors detected
RATE_LIMIT_THRESHOLD = 3   # consecutive errors to trigger cooldown

WINDOW_START_STR = "06:00"
WINDOW_END_STR   = "06:59"

STATUS_PENDING   = "pending"
STATUS_DONE      = "done"
STATUS_SKIPPED   = "skipped"
STATUS_AUTH_FAIL = "auth_fail"
STATUS_GAVE_UP   = "gave_up"


def in_window(now=None):
    now = now or ktime()
    hs, ms = WINDOW_START_STR.split(":")
    he, me = WINDOW_END_STR.split(":")
    start_sec = int(hs) * 3600 + int(ms) * 60
    end_sec   = int(he) * 3600 + int(me) * 60
    sec = now.hour * 3600 + now.minute * 60 + now.second
    return start_sec <= sec <= end_sec


def next_window_in_seconds(now=None):
    now = now or ktime()
    if in_window(now):
        return 0
    hs, ms = WINDOW_START_STR.split(":")
    start_sec = int(hs) * 3600 + int(ms) * 60
    sec = now.hour * 3600 + now.minute * 60 + now.second
    if sec < start_sec:
        return start_sec - sec
    return (24 * 3600 - sec) + start_sec


# ── Desktop notification ──────────────────────────────────────────────────────

def _notify(title, message):
    """Fire a Windows toast notification + beep. Silently no-ops on failure."""
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=8,
                                   threaded=True, icon_path=None)
        return
    except Exception:
        pass
    # Fallback: ctypes balloon tooltip
    try:
        import ctypes
        ctypes.windll.user32.MessageBeep(0)
    except Exception:
        pass


# ── Session CSV ───────────────────────────────────────────────────────────────

def _write_session_csv(run_date, results):
    """Write a per-run CSV to results/run_YYYY-MM-DD_HHMMSS.csv.
    results: list of dicts with keys phone, status, balance_before,
             cycles, pnl, duration_s, error."""
    try:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        ts    = run_date.strftime("%Y-%m-%d_%H%M%S")
        path  = os.path.join(RESULTS_DIR, f"run_{ts}.csv")
        fields = ["phone", "status", "balance_before",
                  "cycles", "pnl", "duration_s", "error"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(results)
        return path
    except Exception:
        return None


# ── Account health store ──────────────────────────────────────────────────────

class AccountHealth:
    """Lightweight JSON store tracking per-account health metrics."""

    def __init__(self, path=HEALTH_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            pass

    def record_run(self, phone, status, balance=None):
        with self._lock:
            rec = self._data.setdefault(phone, {
                "consecutive_auth_fails": 0,
                "consecutive_zero_balance_days": 0,
                "last_run_date": None,
                "last_seen_balance": None,
                "total_runs": 0,
                "total_ok": 0,
            })
            today = datetime.utcnow().strftime("%Y-%m-%d")
            rec["last_run_date"] = today
            rec["total_runs"] = rec.get("total_runs", 0) + 1

            if balance is not None:
                rec["last_seen_balance"] = balance

            if status == STATUS_AUTH_FAIL:
                rec["consecutive_auth_fails"] = rec.get("consecutive_auth_fails", 0) + 1
            else:
                rec["consecutive_auth_fails"] = 0

            if status == STATUS_SKIPPED and balance is not None and balance <= 0:
                rec["consecutive_zero_balance_days"] = \
                    rec.get("consecutive_zero_balance_days", 0) + 1
            elif status == STATUS_DONE:
                rec["consecutive_zero_balance_days"] = 0
                rec["total_ok"] = rec.get("total_ok", 0) + 1

            self._save()

    def warnings(self, phones):
        """Return a list of warning strings for accounts that look unhealthy."""
        warns = []
        with self._lock:
            auth_bad = [p for p in phones
                        if self._data.get(p, {}).get("consecutive_auth_fails", 0) >= 2]
            zero_bad = [p for p in phones
                        if self._data.get(p, {}).get("consecutive_zero_balance_days", 0) >= 3]
            # accounts that haven't run successfully in a long time
            stale = []
            for p in phones:
                rec = self._data.get(p, {})
                last = rec.get("last_run_date")
                if last:
                    try:
                        days_ago = (datetime.utcnow().date() -
                                    datetime.strptime(last, "%Y-%m-%d").date()).days
                        if days_ago >= 5 and rec.get("total_ok", 0) == 0:
                            stale.append(p)
                    except Exception:
                        pass
        if auth_bad:
            warns.append(f"⚠ {len(auth_bad)} account(s) have repeated auth failures "
                         f"(wrong password?): {', '.join(_mask(p) for p in auth_bad)}")
        if zero_bad:
            warns.append(f"⚠ {len(zero_bad)} account(s) had zero balance for 3+ days: "
                         f"{', '.join(_mask(p) for p in zero_bad)}")
        if stale:
            warns.append(f"⚠ {len(stale)} account(s) have never completed a run: "
                         f"{', '.join(_mask(p) for p in stale)}")
        return warns


def _mask(phone):
    """Show 07***111 style masked number."""
    p = str(phone)
    if len(p) >= 6:
        return p[:3] + "*" * (len(p) - 6) + p[-3:]
    return p


# ── Engine ────────────────────────────────────────────────────────────────────

class SchedulerEngine:

    def __init__(self, state_path=STATE_PATH, worker_count=DEFAULT_WORKERS,
                 rounds=DEFAULT_ROUNDS, stake=DEFAULT_STAKE,
                 cashout=DEFAULT_CASHOUT, progress_cb=None,
                 real_money=False, minimize=True,
                 stagger_min=DEFAULT_STAGGER_MIN,
                 stagger_max=DEFAULT_STAGGER_MAX):

        self.state_path    = state_path
        self.worker_count  = worker_count
        self.rounds        = rounds
        self.stake         = stake
        self.cashout       = cashout
        self.real_money    = real_money
        self.minimize      = minimize
        self.stagger_min   = stagger_min   # seconds min between worker starts
        self.stagger_max   = stagger_max   # seconds max between worker starts
        self.progress_cb   = progress_cb or (lambda msg: None)

        self._pending          = queue.Queue()
        self._lock             = threading.Lock()
        self._running          = False
        self._manual_request   = False
        self._auto_session     = False
        self._auto_enabled     = False
        self._stop_evt         = threading.Event()
        self._stop_timer_evt   = threading.Event()
        self._workers          = []
        self._active_workers   = 0
        self._session_start    = None
        self._attempts         = {}
        self._loops_today      = 0
        self._today            = None
        self.max_loops         = 10
        self.loop_until_window_end = True

        # Rate-limit tracking
        self._consec_errors    = 0
        self._rate_limit_lock  = threading.Lock()
        self._in_cooldown      = False

        # Watchdog
        self._last_worker_activity = time.monotonic()

        # Per-session result rows (written to CSV on completion)
        self._session_results  = []
        self._session_results_lock = threading.Lock()
        self._run_date         = None

        self.health = AccountHealth()
        self.state  = {}
        self.start_precision_timer()

    # ── emit ─────────────────────────────────────────────────────────────

    _SUPPRESS = ("rebuilding queue", "state save")

    def _emit(self, msg):
        if any(s in msg.lower() for s in self._SUPPRESS):
            return
        try:
            self.progress_cb(msg)
        except Exception:
            pass

    # ── state ─────────────────────────────────────────────────────────────

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception:
            pass

    # ── phone list management ─────────────────────────────────────────────

    def set_phones(self, phones):
        with self._lock:
            current_set = set(phones)
            for p in list(self.state.keys()):
                if p not in current_set:
                    del self.state[p]
            for p in phones:
                if p not in self.state:
                    self.state[p] = {"status": STATUS_PENDING}
            self._save_state()
            pending = [p for p in phones
                       if self.state.get(p, {}).get("status") == STATUS_PENDING]
            if not self._running:
                self._pending = queue.Queue()
                for p in pending:
                    self._pending.put(p)
            return len(phones), len(pending)

    def mark_account(self, phone, status, **kwargs):
        with self._lock:
            rec = self.state.setdefault(phone, {})
            rec["status"] = status
            rec["updated_at"] = datetime.utcnow().isoformat()
            for k, v in kwargs.items():
                rec[k] = v
            self._save_state()

    def mark_all_pending(self):
        with self._lock:
            for p in self.state:
                self.state[p] = {"status": STATUS_PENDING}
            self._save_state()

    def reset_state_file(self):
        with self._lock:
            self.state = {}
            self._save_state()

    # ── counts ────────────────────────────────────────────────────────────

    def pending_count(self):
        with self._lock:
            return sum(1 for r in self.state.values()
                       if r.get("status") == STATUS_PENDING)

    def done_count(self):
        with self._lock:
            return sum(1 for r in self.state.values()
                       if r.get("status") in (STATUS_DONE, STATUS_SKIPPED,
                                               STATUS_GAVE_UP, STATUS_AUTH_FAIL))

    def total_count(self):
        with self._lock:
            return len(self.state)

    def is_running(self):
        return self._running

    # ── rate-limit detection ──────────────────────────────────────────────

    def _record_api_error(self, is_rate_limit=False):
        """Track consecutive API errors; trigger cooldown if threshold hit."""
        with self._rate_limit_lock:
            self._consec_errors += 1
            if is_rate_limit or self._consec_errors >= RATE_LIMIT_THRESHOLD:
                if not self._in_cooldown:
                    self._in_cooldown = True
                    self._emit(f"⚠ Rate limit / repeated errors detected — "
                               f"cooling down {RATE_LIMIT_COOLDOWN}s before continuing")
                    threading.Thread(target=self._cooldown_timer, daemon=True).start()

    def _record_api_success(self):
        with self._rate_limit_lock:
            self._consec_errors = 0

    def _cooldown_timer(self):
        self._interruptible_sleep(RATE_LIMIT_COOLDOWN)
        with self._rate_limit_lock:
            self._in_cooldown = False
            self._consec_errors = 0
        if not self._stop_evt.is_set():
            self._emit("✅ Cooldown complete — resuming")

    def _wait_if_cooling(self):
        """Block the calling thread until any active cooldown finishes."""
        while True:
            with self._rate_limit_lock:
                if not self._in_cooldown:
                    return
            if self._stop_evt.is_set():
                return
            time.sleep(1)

    # ── pre-run sweep ─────────────────────────────────────────────────────

    def pre_run_balance_sweep(self):
        """Fast parallel balance check of all accounts. Prints a table and
        returns (go, results_list). go=False means nothing has funds."""
        phones = list(self.state.keys())
        if not phones:
            return False, []

        self._emit("─" * 52)
        self._emit(f"📋 PRE-RUN CHECK — {len(phones)} accounts")
        self._emit("─" * 52)

        results = [None] * len(phones)
        threads = []

        def _check(i, ph):
            res = bal_mod.check_account(ph, self._password, timeout=15)
            results[i] = (ph, res)

        for i, ph in enumerate(phones):
            t = threading.Thread(target=_check, args=(i, ph), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=20)

        ok_count = skip_count = fail_count = 0
        total_balance = 0.0

        for ph, res in results:
            if res is None:
                self._emit(f"  {_mask(ph):<14}  ⚠  timeout")
                fail_count += 1
                continue
            if not res.get("ok"):
                err = res.get("error", "?")
                is_auth = any(x in str(err).lower() for x in
                              ("invalid", "wrong", "unauthorized", "401"))
                tag = "AUTH FAIL" if is_auth else "LOGIN ERR"
                self._emit(f"  {_mask(ph):<14}  ❌  {tag}")
                fail_count += 1
            else:
                bal  = float(res.get("balance") or 0)
                bonus = float(res.get("bonus") or 0)
                total_balance += bal
                if bal < self.stake:
                    tag = f"SKIP  KES {bal:>8,.2f}  (bonus {bonus:,.2f})"
                    self._emit(f"  {_mask(ph):<14}  💸  {tag}")
                    skip_count += 1
                else:
                    tag = f"OK    KES {bal:>8,.2f}  (bonus {bonus:,.2f})"
                    self._emit(f"  {_mask(ph):<14}  ✅  {tag}")
                    ok_count += 1

        self._emit("─" * 52)
        self._emit(f"  Ready: {ok_count} | Skipped: {skip_count} | "
                   f"Failed: {fail_count} | Total balance: KES {total_balance:,.2f}")
        self._emit("─" * 52)

        if ok_count == 0:
            self._emit("⛔ No accounts have sufficient funds — run aborted.")
            return False, results

        return True, results

    # ── account health warnings ───────────────────────────────────────────

    def emit_health_warnings(self, phones):
        warns = self.health.warnings(phones)
        for w in warns:
            self._emit(w)
        return len(warns)

    # ── worker loop ───────────────────────────────────────────────────────

    def _worker_loop(self):
        pw = None

        def start_pw():
            nonlocal pw
            try:
                from playwright.sync_api import sync_playwright
                pw = sync_playwright().start()
                return True
            except Exception as e:
                self._emit(f"⚠ Playwright start failed: {e}")
                return False

        start_pw()

        try:
            while not self._stop_evt.is_set():
                self._wait_if_cooling()
                if self._stop_evt.is_set():
                    break

                try:
                    phone = self._pending.get(timeout=2)
                except queue.Empty:
                    break

                self._last_worker_activity = time.monotonic()
                acct_start = time.time()
                attempts = self._attempts.get(phone, 0) + 1
                self._attempts[phone] = attempts

                # ── Step 1: balance check ─────────────────────────────────
                ok_bal, balance, bal_reason = self._check_balance(phone)

                if not ok_bal:
                    duration = round(time.time() - acct_start, 1)
                    if bal_reason and "429" in str(bal_reason):
                        self._record_api_error(is_rate_limit=True)
                    elif bal_reason and bal_reason.startswith("AUTH_FAIL"):
                        self._record_api_error()
                    else:
                        self._record_api_error()

                    if bal_reason and bal_reason.startswith("AUTH_FAIL"):
                        self._emit(f"🔐 {_mask(phone)}: {bal_reason} — skipping")
                        self.mark_account(phone, STATUS_AUTH_FAIL, error=bal_reason)
                        self.health.record_run(phone, STATUS_AUTH_FAIL)
                        self._add_result(phone, STATUS_AUTH_FAIL, balance,
                                         None, None, duration, bal_reason)
                    elif bal_reason and ("ZERO BALANCE" in bal_reason or
                                         "Not Enough Balance" in bal_reason):
                        self._emit(f"💸 {_mask(phone)}: {bal_reason} — skipped")
                        self.mark_account(phone, STATUS_SKIPPED,
                                          balance=balance, error=bal_reason)
                        self.health.record_run(phone, STATUS_SKIPPED, balance)
                        self._add_result(phone, STATUS_SKIPPED, balance,
                                         None, None, duration, bal_reason)
                    else:
                        if attempts < MAX_ATTEMPTS and not self._stop_evt.is_set():
                            backoff = RETRY_BACKOFF_SEC * attempts
                            self._emit(f"⚠ {_mask(phone)}: {bal_reason} — "
                                       f"retry in {backoff}s ({attempts}/{MAX_ATTEMPTS})")
                            self._interruptible_sleep(backoff)
                            if not self._stop_evt.is_set():
                                self._pending.put(phone)
                        else:
                            self._emit(f"❌ {_mask(phone)}: gave up — {bal_reason}")
                            self.mark_account(phone, STATUS_GAVE_UP, error=bal_reason)
                            self.health.record_run(phone, STATUS_GAVE_UP)
                            self._add_result(phone, STATUS_GAVE_UP, balance,
                                             None, None, duration, bal_reason)
                    continue

                self._record_api_success()
                self._emit(f"✅ {_mask(phone)}: KES {balance:,.2f} — starting betting")

                # ── Step 2: betting ───────────────────────────────────────
                if pw is None:
                    if not start_pw():
                        self._pending.put(phone)
                        break

                outcome   = "error"
                error_msg = None
                cycles    = None
                pnl       = None

                multi.set_log_cb(lambda m, p=phone: self._emit(f"  {_mask(p)}: {m}"))
                try:
                    res = multi.process_account(
                        pw, phone, self._password,
                        self.rounds, self.stake,
                        cashout=self.cashout,
                        headless=self.minimize,
                    )
                    if res and res.get("status") == "ok":
                        outcome = "ok"
                        cycles  = res.get("cycles")
                        pnl     = res.get("pnl")
                    else:
                        outcome   = "failed"
                        error_msg = res.get("status") if res else "failed"
                except Exception as e:
                    error_msg = str(e)[:120]
                    if any(x in error_msg.lower() for x in
                           ("playwright", "browser", "target closed",
                            "connection", "crashed")):
                        self._emit(f"⚠ {_mask(phone)}: browser crash — rebuilding")
                        try:
                            pw.stop()
                        except Exception:
                            pass
                        pw = None
                finally:
                    multi.set_log_cb(None)

                duration = round(time.time() - acct_start, 1)

                # ── Step 3: outcome ───────────────────────────────────────
                if outcome == "ok":
                    self._attempts.pop(phone, None)
                    pnl_s = f" | P&L: KES {pnl:+,.2f}" if (pnl is not None
                                                             and self.real_money) else ""
                    self._emit(f"✔ {_mask(phone)}: done "
                               f"({cycles} cycles{pnl_s})")
                    self.mark_account(phone, STATUS_DONE, cycles=cycles, pnl=pnl)
                    self.health.record_run(phone, STATUS_DONE, balance)
                    self._add_result(phone, STATUS_DONE, balance,
                                     cycles, pnl, duration, None)
                elif not self._stop_evt.is_set() and attempts < MAX_ATTEMPTS:
                    backoff = RETRY_BACKOFF_SEC * attempts
                    self._emit(f"⚠ {_mask(phone)}: {error_msg} — "
                               f"retry in {backoff}s ({attempts}/{MAX_ATTEMPTS})")
                    self._interruptible_sleep(backoff)
                    if not self._stop_evt.is_set():
                        self._pending.put(phone)
                else:
                    self._emit(f"❌ {_mask(phone)}: gave up — {error_msg}")
                    self.mark_account(phone, STATUS_GAVE_UP, error=error_msg)
                    self.health.record_run(phone, STATUS_GAVE_UP)
                    self._add_result(phone, STATUS_GAVE_UP, balance,
                                     None, None, duration, error_msg)

                self._last_worker_activity = time.monotonic()
                time.sleep(0.5)

        finally:
            try:
                if pw:
                    pw.stop()
            except Exception:
                pass
            with self._lock:
                self._active_workers = max(0, self._active_workers - 1)
            # If this was the last worker, trigger end-of-run
            if self._active_workers == 0 and self._running:
                threading.Thread(target=self._on_run_complete,
                                 daemon=True).start()

    def _add_result(self, phone, status, balance, cycles, pnl, duration, error):
        row = {
            "phone":          _mask(phone),
            "status":         status,
            "balance_before": balance,
            "cycles":         cycles,
            "pnl":            pnl,
            "duration_s":     duration,
            "error":          error or "",
        }
        with self._session_results_lock:
            self._session_results.append(row)

    def _interruptible_sleep(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._stop_evt.is_set():
                return
            time.sleep(min(0.5, deadline - time.monotonic()))

    # ── end-of-run ────────────────────────────────────────────────────────

    def _on_run_complete(self):
        """Called when the last worker finishes. Writes CSV, notifies."""
        if not self._run_date:
            return
        with self._session_results_lock:
            rows = list(self._session_results)

        if not rows:
            return

        # Summary
        ok    = sum(1 for r in rows if r["status"] == STATUS_DONE)
        skip  = sum(1 for r in rows if r["status"] == STATUS_SKIPPED)
        fail  = sum(1 for r in rows if r["status"] in (STATUS_GAVE_UP,
                                                         STATUS_AUTH_FAIL))
        total_pnl = sum((r["pnl"] or 0) for r in rows if r["pnl"] is not None)
        duration  = round(time.time() - self._session_start, 0)
        mins = int(duration // 60)
        secs = int(duration % 60)

        self._emit("═" * 52)
        self._emit(f"✅ RUN COMPLETE — {mins}m {secs}s")
        self._emit(f"   Done: {ok}  |  Skipped: {skip}  |  Failed: {fail}")
        if self.real_money and total_pnl != 0:
            self._emit(f"   Total P&L: KES {total_pnl:+,.2f}")
        self._emit("═" * 52)

        # CSV
        csv_path = _write_session_csv(self._run_date, rows)
        if csv_path:
            self._emit(f"📄 Report saved: {csv_path}")

        # Desktop notification
        msg = (f"Done {ok} | Skipped {skip} | Failed {fail}\n"
               f"Duration {mins}m {secs}s")
        if self.real_money and total_pnl != 0:
            msg += f"\nP&L: KES {total_pnl:+,.2f}"
        _notify("BeTyca Aviator — Run Complete", msg)

        self._running = False

    # ── start / stop ──────────────────────────────────────────────────────

    def start(self, password, workers=None, reason="manual"):
        if self._running:
            return False

        phones = list(self.state.keys())

        # Show health warnings
        self.emit_health_warnings(phones)

        # Pre-run balance sweep
        go, _ = self.pre_run_balance_sweep()
        if not go:
            return False

        multi.REAL_MONEY       = bool(self.real_money)
        multi.MINIMIZE_BROWSER = bool(self.minimize)
        self._password         = password
        self._running          = True
        self._stop_evt         = threading.Event()
        self._manual_request   = (reason == "manual")
        self._auto_session     = (reason != "manual")
        count                  = workers or self.worker_count
        self._session_start    = time.time()
        self._run_date         = datetime.utcnow()
        self._attempts         = {}
        self._active_workers   = count
        self._last_worker_activity = time.monotonic()
        self._workers          = []
        self._consec_errors    = 0

        with self._session_results_lock:
            self._session_results = []

        # Build work queue
        with self._lock:
            self._pending = queue.Queue()
            for phone, rec in self.state.items():
                if rec.get("status") == STATUS_PENDING:
                    self._pending.put(phone)

        n_pending = self._pending.qsize()
        mode = "REAL-MONEY" if self.real_money else "SIM"
        self._emit(f"▶ Starting {count} worker(s) | {n_pending} accounts | "
                   f"{mode} | stake={self.stake} KES | cashout={self.cashout}x | "
                   f"stagger {self.stagger_min}–{self.stagger_max}s")

        # Staggered worker launch
        def _launch_workers():
            for i in range(count):
                if self._stop_evt.is_set():
                    break
                t = threading.Thread(target=self._worker_loop, daemon=True)
                t.start()
                self._workers.append(t)
                if i < count - 1:
                    delay = random.uniform(self.stagger_min, self.stagger_max)
                    self._emit(f"  worker {i+1}/{count} started — "
                               f"next in {delay:.0f}s")
                    self._interruptible_sleep(delay)
                else:
                    self._emit(f"  worker {count}/{count} started")

        threading.Thread(target=_launch_workers, daemon=True,
                         name="worker-launcher").start()
        return True

    def stop(self, reason="user"):
        if reason == "user":
            self._emit("⛔ Stopped by user — all workers halting")
        self._manual_request = False
        self._auto_session   = False
        self._stop_evt.set()
        self._running        = False
        self._active_workers = 0

    # ── balance check helper ──────────────────────────────────────────────

    def _check_balance(self, phone):
        try:
            res = bal_mod.check_account(phone, self._password, timeout=15)
        except Exception as e:
            return False, 0.0, f"balance check error: {e}"

        if not res.get("ok"):
            err = str(res.get("error", "unknown"))
            if "429" in err:
                return False, 0.0, f"429 RATE LIMITED"
            if any(x in err.lower() for x in
                   ("invalid", "wrong", "unauthorized", "401", "password")):
                return False, 0.0, f"AUTH_FAIL: {err}"
            return False, 0.0, f"login error: {err}"

        balance = float(res.get("balance") or 0)
        if balance <= 0:
            return False, balance, "ZERO BALANCE"
        if balance < self.stake:
            return False, balance, (f"Not Enough Balance "
                                    f"(KES {balance:,.2f} < stake KES {self.stake:,.2f})")
        return True, balance, None

    # ── self-healing watchdog ─────────────────────────────────────────────

    def _workers_alive(self):
        return any(t.is_alive() for t in self._workers)

    def _restart_dead_workers(self):
        if not self._running or self._stop_evt.is_set():
            return
        if self._pending.empty():
            return
        if self._workers_alive():
            return
        needed = min(self.worker_count, self._pending.qsize())
        self._emit(f"🔄 Self-heal: restarting {needed} worker(s) "
                   f"({self._pending.qsize()} remain)")
        self._active_workers = needed
        for _ in range(needed):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()
            self._workers.append(t)

    def _can_loop(self):
        if not self.loop_until_window_end:
            return False
        if self._loops_today >= self.max_loops:
            return False
        self._loops_today += 1
        return True

    # ── precision timer ───────────────────────────────────────────────────

    def start_precision_timer(self):
        threading.Thread(target=self._precision_wakeup_loop,
                         daemon=True, name="sched-precision-timer").start()

    def _precision_wakeup_loop(self):
        while True:
            try:
                utc, source = _sync_time_cache(emit=self._emit)
                now_k = utc + timedelta(hours=3)
                secs  = next_window_in_seconds(now_k)

                if secs > 0:
                    h, m, s = int(secs//3600), int((secs%3600)//60), int(secs%60)
                    self._emit(f"⏰ Auto-start in {h:02d}h {m:02d}m {s:02d}s "
                               f"(06:00 EAT | {source})")
                    deadline = time.monotonic() + secs
                    while time.monotonic() < deadline:
                        if self._stop_timer_evt.is_set():
                            return
                        time.sleep(min(30, deadline - time.monotonic()))

                # Drift guard
                utc2, _ = _sync_time_cache(emit=self._emit)
                now_k2  = utc2 + timedelta(hours=3)
                if not in_window(now_k2):
                    gap = next_window_in_seconds(now_k2)
                    if gap > 0:
                        time.sleep(gap + 1)

                today = (utc2 + timedelta(hours=3)).date()
                mark_all = (self._today != today)
                if mark_all:
                    self._today = today
                    self._loops_today = 0

                if not self._auto_enabled:
                    self._emit("⏰ 06:00 EAT — auto-start OFF, skipping")
                    time.sleep(61 * 60)
                    continue

                if not getattr(self, '_password', None):
                    self._emit("⏰ 06:00 EAT — no password set")
                    time.sleep(61 * 60)
                    continue

                if self.is_running():
                    self._emit("⏰ 06:00 EAT — already running")
                    time.sleep(61 * 60)
                    continue

                if mark_all:
                    self.mark_all_pending()
                    self._emit(f"🔄 New day ({today}) — accounts reset to pending")

                if self.total_count() == 0:
                    self._emit("⏰ 06:00 EAT — no accounts in list")
                    time.sleep(61 * 60)
                    continue

                self._emit(f"▶ 06:00 EAT — auto-start ({self.total_count()} accounts)")
                self.start(self._password, reason="window 06:00-06:59")
                time.sleep(61 * 60)

            except Exception as e:
                self._emit(f"⚠ Timer error: {e} — retry in 60s")
                time.sleep(60)

    # ── tick ──────────────────────────────────────────────────────────────

    def tick(self):
        now = ktime(emit=self._emit)
        today = now.date()
        if self._today != today:
            self._today = today
            self._loops_today = 0

        if self._running:
            self._restart_dead_workers()
            if self._auto_session:
                if not in_window(now):
                    self.stop(reason="window closed 07:00")
                elif self._pending.empty() and not self._workers_alive():
                    if self._can_loop():
                        self._running = False
                        self.mark_all_pending()
                        self._emit(f"🔄 Loop {self._loops_today}/{self.max_loops}")
                        self.start(self._password, reason="window loop")

    # ── status text ───────────────────────────────────────────────────────

    def status_text(self, now=None):
        now   = now or ktime(emit=self._emit)
        win   = in_window(now)
        auto  = "AUTO-ON" if self._auto_enabled else "AUTO-OFF"
        phase = "WINDOW OPEN" if win else (
            f"window in {int(next_window_in_seconds(now)//3600)}h "
            f"{int((next_window_in_seconds(now)%3600)//60)}m")
        run   = "RUNNING" if self._running else "idle"
        skip  = sum(1 for r in self.state.values()
                    if r.get("status") == STATUS_SKIPPED)
        skip_s = f" | skipped {skip}" if skip else ""
        return (f"[{auto}] {phase} | {run} | "
                f"done {self.done_count()}/{self.total_count()}"
                f"{skip_s} | pending {self.pending_count()}")

    def wait_all(self, timeout=120):
        for t in self._workers:
            try:
                t.join(timeout=timeout)
            except Exception:
                pass
        self._workers = []
