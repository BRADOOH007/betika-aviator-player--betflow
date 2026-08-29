"""
Scheduler Engine — Betika Aviator multi-account auto-runner
===========================================================
Tkinter-independent core that the GUI (main_gui.py) drives via tick().

Responsibilities:
  * Maintain a thread-safe pending queue built from a phone-number list.
  * Run N parallel browser workers; each worker processes one account by
    calling run_multi_betika.process_account() (which opens its own Playwright
    browser/context, logs in, sets up both panels @ 1.01x, presses Bet on both
    panels, and observes the round cycles).
  * Persist per-account completion state to a JSON file so unfinished accounts
    are resumed the next day instead of being restarted.
  * Enforce a daily play window 06:00 (inclusive) - 06:59 (inclusive) Kenya time
    (UTC+3). Outside the window it stays idle and waits for the next window.
    A manual override can start/stop the workers regardless of the window.

This module has NO tkinter imports so it can be tested headlessly.
"""

import os
import json
import time
import queue
import threading
from datetime import datetime, timedelta

# Reuse the per-account worker from the multi-account dry-run tool.
import run_multi_betika as multi

# Defaults
STATE_PATH = os.path.join("config", "scheduler_state.json")
DEFAULT_WORKERS = 4
DEFAULT_ROUNDS = 50      # round-cycles per account (=100 bets across 2 panels)
DEFAULT_STAKE = 10       # KES
DEFAULT_CASHOUT = 1.01

MAX_ATTEMPTS = 3              # per-account retries before giving up (per run/day)
RETRY_BACKOFF_SEC = 5         # base backoff between retries (scaled by attempt #

# Daily play window (Kenya time, UTC+3)
WINDOW_START_STR = "06:00"
WINDOW_END_STR = "06:59"


def ktime():
    """Return current datetime in Kenya time (UTC+3)."""
    return datetime.utcnow() + timedelta(hours=3)


def in_window(now=None):
    """True if now (Kenya time) is within the daily play window."""
    now = now or ktime()
    hs, ms = WINDOW_START_STR.split(":")
    he, me = WINDOW_END_STR.split(":")
    start_sec = int(hs) * 3600 + int(ms) * 60
    end_sec = int(he) * 3600 + int(me) * 60
    sec = now.hour * 3600 + now.minute * 60 + now.second
    return start_sec <= sec <= end_sec


def next_window_in_seconds(now=None):
    """Seconds until the next daily window starts (or 0 if currently in it)."""
    now = now or ktime()
    if in_window(now):
        return 0
    hs, ms = WINDOW_START_STR.split(":")
    start_sec = int(hs) * 3600 + int(ms) * 60
    sec = now.hour * 3600 + now.minute * 60 + now.second
    if sec < start_sec:
        return start_sec - sec
    # tomorrow
    return (24 * 3600 - sec) + start_sec


class SchedulerEngine:
    def __init__(self, state_path=STATE_PATH, worker_count=DEFAULT_WORKERS,
                 rounds=DEFAULT_ROUNDS, stake=DEFAULT_STAKE,
                 cashout=DEFAULT_CASHOUT, progress_cb=None,
                 real_money=False, minimize=True):
        self.state_path = state_path
        self.worker_count = worker_count
        self.rounds = rounds
        self.stake = stake
        self.cashout = cashout
        self.real_money = real_money
        self.minimize = minimize
        self.loop_until_window_end = True
        self.progress_cb = progress_cb or (lambda msg: None)

        self._pending = queue.Queue()
        self._lock = threading.Lock()
        self._running = False
        self._manual_running = False
        self._manual_request = False
        self._auto_session = False
        self._auto_enabled = False
        self._stop_evt = threading.Event()
        self._workers = []
        self._active_workers = 0
        self._session_start = None
        # in-memory per-account retry counters (reset each start())
        self._attempts = {}
        # loop-mode bookkeeping: cap how many in-window restarts happen per day
        self._loops_today = 0
        self._today = None
        self.max_loops = 10

        # state: { phone: {"done": bool, "finished_at": str, "last_error": str, "cycles": int} }
        self.state = self._load_state()

    # ── helpers ───────────────────────────────────────────────────────────

    def _emit(self, msg):
        try:
            self.progress_cb(msg)
        except Exception:
            pass

    def _load_state(self):
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            self._emit(f"state save error: {e}")

    # ── public API ────────────────────────────────────────────────────────

    def set_phones(self, phones):
        """Sync the engine's known account records with a phone list. New phones
        are added as pending; if a run is active, they are also pushed onto the
        live work queue so they're picked up immediately. Rebuilds the queue
        from scratch when not running. Returns (total_known, pending_now)."""
        with self._lock:
            added = False
            for p in phones:
                if p not in self.state:
                    self.state[p] = {"done": False}
                    added = True
            if added:
                self._save_state()
            pending = [p for p in phones if not self.state.get(p, {}).get("done")]
            # Rebuild the WORK queue when not running; otherwise only add
            # brand-new accounts that aren't already queued or in-flight.
            if not self._running:
                self._pending = queue.Queue()
                for p in pending:
                    self._pending.put(p)
            else:
                queued = set()
                try:
                    for item in list(self._pending.queue):
                        queued.add(item)
                except Exception:
                    pass
                for p in pending:
                    if p not in queued and not self.state[p].get("done"):
                        if self._attempts.get(p, 0) < MAX_ATTEMPTS:
                            self._pending.put(p)
            return len(phones), len(pending)

    def mark_account_complete(self, phone, cycles=None, error=None, pnl=None):
        with self._lock:
            rec = self.state.setdefault(phone, {})
            if error:
                rec["last_error"] = error
            else:
                rec["done"] = True
                rec["finished_at"] = datetime.utcnow().isoformat()
                if cycles is not None:
                    rec["cycles"] = cycles
                if pnl is not None:
                    rec["pnl"] = pnl
            self._save_state()

    def mark_all_pending(self):
        """Reset all records to not-done (e.g. user edits the list / wants a
        fresh run)."""
        with self._lock:
            for p in self.state:
                self.state[p]["done"] = False
                self.state[p].pop("finished_at", None)
            self._save_state()

    def reset_state_file(self):
        with self._lock:
            self.state = {}
            self._save_state()

    def pending_count(self):
        with self._lock:
            return sum(1 for p in self.state if not self.state[p].get("done"))

    def done_count(self):
        with self._lock:
            return sum(1 for p in self.state if self.state[p].get("done"))

    def total_count(self):
        with self._lock:
            return len(self.state)

    def is_running(self):
        return self._running

    def is_auto(self):
        return self._auto_enabled

    # ── worker management ─────────────────────────────────────────────────

    def _worker_loop(self):
        """Run by each worker thread: pull the next pending account, process it.
        Each thread owns its own Playwright instance (sync API is thread-affine)
        and reuses it across the accounts that thread handles."""
        pw = None
        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
        except Exception as e:
            self._emit(f"[WORKER] failed to start playwright: {e}")
            return
        try:
            while not self._stop_evt.is_set():
                try:
                    phone = self._pending.get_nowait()
                except queue.Empty:
                    break
                attempts = self._attempts.get(phone, 0) + 1
                self._attempts[phone] = attempts
                self._emit(f"[WORKER] starting account {phone} "
                           f"(attempt {attempts}/{MAX_ATTEMPTS})")

                outcome = "error"
                error_msg = None
                cycles = None
                pnl = None
                # funnel this worker's detailed per-account output to the GUI
                multi.set_log_cb(lambda m, p=phone: self._emit(f"[{p}] {m}"))
                try:
                    res = multi.process_account(pw, phone, self._password,
                                                self.rounds, self.stake,
                                                cashout=self.cashout)
                    if res and res.get("status") == "ok":
                        outcome = "ok"
                        cycles = res.get("cycles")
                        pnl = res.get("pnl")
                    else:
                        outcome = "failed"
                        error_msg = res.get("status") if res else "failed"
                        self._emit(f"[WORKER] FAILED {phone}: {error_msg}")
                except Exception as e:
                    error_msg = str(e)[:120]
                    self._emit(f"[WORKER] ERROR {phone}: {error_msg}")
                finally:
                    multi.set_log_cb(None)

                if outcome == "ok":
                    self._attempts.pop(phone, None)
                    self.mark_account_complete(phone, cycles=cycles, pnl=pnl)
                    pnl_s = f" | pnl={pnl:+.2f} KES" if pnl is not None and self.real_money else ""
                    self._emit(f"[WORKER] DONE {phone} ({cycles} cycles, "
                               f"{cycles*2 if cycles else 0} bets{pnl_s})")
                elif not self._stop_evt.is_set() and attempts < MAX_ATTEMPTS:
                    # transient failure -> requeue for another attempt after backoff
                    backoff = RETRY_BACKOFF_SEC * attempts
                    self._emit(f"[WORKER] requeue {phone} "
                               f"(attempt {attempts}); retry in {backoff}s")
                    deadline = time.time() + backoff
                    while time.time() < deadline and not self._stop_evt.is_set():
                        time.sleep(0.2)
                    if not self._stop_evt.is_set():
                        self._pending.put(phone)
                else:
                    # retries exhausted (or app stopping) -> mark permanently failed
                    self.mark_account_complete(phone, error=error_msg or outcome)
                    self._emit(f"[WORKER] GAVE UP {phone}: {error_msg or outcome}")

                time.sleep(1.0)
        finally:
            try:
                pw.stop()
            except Exception:
                pass
            with self._lock:
                self._active_workers = max(0, self._active_workers - 1)

    def start(self, password, workers=None, reason="manual"):
        """Launch worker pool. workers defaults to self.worker_count.
        reason='manual' -> a user-driven run (not touched by auto logic).
        Any other reason -> an auto/window/loop run managed by tick()."""
        if self._running:
            return False
        # sync real-money / safety config into the worker module before threads run
        multi.REAL_MONEY = bool(self.real_money)
        multi.MINIMIZE_BROWSER = bool(self.minimize)
        self._password = password
        self._running = True
        self._stop_evt = threading.Event()
        self._manual_request = (reason == "manual")
        self._auto_session = (reason != "manual")
        count = workers or self.worker_count
        self._session_start = time.time()
        self._attempts = {}
        self._active_workers = count
        # Rebuild the work queue from the not-done accounts so loops + manual
        # runs and any mid-run additions all get processed.
        with self._lock:
            self._pending = queue.Queue()
            for phone in sorted(self.state.keys()):
                if not self.state[phone].get("done"):
                    self._pending.put(phone)
        self._emit(f"[SCHED] starting {count} worker(s) ({reason}) | "
                   f"REAL_MONEY={self.real_money} | "
                   f"cashout={self.cashout}x | browser={'minimized' if self.minimize else 'visible'}")
        for _ in range(count):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()
            self._workers.append(t)
        return True

    def stop(self, reason="user"):
        self._emit(f"[SCHED] stopping ({reason})")
        self._manual_request = False
        self._auto_session = False
        self._stop_evt.set()
        self._running = False

    def _can_loop(self):
        """True if loop-mode should fire another in-window restart this day."""
        if not self.loop_until_window_end:
            return False
        if self._loops_today >= self.max_loops:
            self._emit(f"[SCHED] loop cap reached ({self.max_loops}) - staying idle")
            return False
        self._loops_today += 1
        return True

    def wait_all(self, timeout=120):
        for t in self._workers:
            try:
                t.join(timeout=timeout)
            except Exception:
                pass
        self._workers = []

    # ── scheduler tick (called periodically by the GUI) ───────────────────

    def tick(self):
        """Called on an interval (e.g. every 5s) from the GUI main thread.
        Auto-start/stop the workers according to the daily window."""
        if not self._auto_enabled:
            return
        now = ktime()
        # reset loop counter on a new day
        today = now.date()
        if self._today != today:
            self._today = today
            self._loops_today = 0
        window_start = in_window(now)
        if window_start and not self._manual_request:
            if not self._running:
                # time to start automatically
                if not hasattr(self, '_password') or not self._password:
                    self._emit("[SCHED] AUTO start blocked: no login password set. "
                               "Enter the account password (or run once manually).")
                    return
                if self.pending_count() > 0:
                    self.start(self._password, reason="window 06:00-06:59")
                elif self._can_loop():
                    # whole list finished but window still open -> run it again
                    self.mark_all_pending()
                    self._emit(f"[SCHED] list finished in-window, restarting (loop "
                               f"{self._loops_today}/{self.max_loops})")
                    self.start(self._password, reason="window loop")
            elif self._auto_session and self._active_workers == 0 \
                    and self.pending_count() == 0 and self.total_count() > 0 \
                    and self._can_loop():
                # auto workers drained the queue while still in-window -> loop
                self._running = False
                self.mark_all_pending()
                self._emit(f"[SCHED] all workers idle, restarting list (loop "
                           f"{self._loops_today}/{self.max_loops})")
                self.start(self._password, reason="window loop")
        elif not window_start and self._running and self._auto_session:
            # window over -> stop the auto session
            self.stop(reason="window closed")

    def status_text(self, now=None):
        now = now or ktime()
        win = in_window(now)
        if self.is_auto():
            state = "AUTO-ON"
        else:
            state = "AUTO-OFF"
        if win:
            phase = "WINDOW OPEN"
        else:
            secs = next_window_in_seconds(now)
            phase = f"window in {int(secs//3600)}h {int((secs%3600)//60)}m {int(secs%60)}s"
        run = "RUNNING" if self._running else "idle"
        return (f"[{state}] {phase} | workers {run} | "
                f"done {self.done_count()}/{self.total_count()} | pending {self.pending_count()}")
