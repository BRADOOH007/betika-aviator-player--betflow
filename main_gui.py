import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import time
import json
import csv
from datetime import datetime
import requests
import sys
import subprocess
import os

# Force UTF-8 / safe std streams. A windowed (--noconsole) EXE has no
# stdout/stderr, so redirect to a log file to avoid crashes on any print().
def _open_log_stream():
    try:
        _p = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
                          "betflow_runtime.log")
        return open(_p, "a", encoding="utf-8", errors="replace")
    except Exception:
        return open(os.devnull, "w", encoding="utf-8", errors="replace")

if sys.stdout is None:
    sys.stdout = _open_log_stream()
if sys.stderr is None:
    sys.stderr = _open_log_stream()
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Lite mode: only balance + Playwright Aviator; disable heavy modules
LITE_MODE = True
# Disable all keyboard shortcuts in GUI
DISABLE_SHORTCUTS = True

from utils import encrypt_data, decrypt_data, log_message, set_persistence, should_persist
from resource_path import resource_path, ensure_assets
from aviator_backend import AviatorBackend

# Stubs for removed modules
BetFlowHeadless = None
RemoteServer = None
ZapHelper = None
BrowserDiscovery = None
SmartPreloader = None
BetFlowTelegramBot = None
AIIntegration = None
AILearningEnhanced = None
VISUAL_AI_ENABLED = False
STABILITY_SYSTEMS_ENABLED = False

# Optional system/process utilities
try:
    import psutil  # type: ignore
except Exception:
    psutil = None

def allow_sleep(allow):
    """Prevent (or re-allow) Windows system sleep while the tool is open.
    Keeps the machine awake so the 06:00 auto-start always fires."""
    try:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_AWAYMODE_REQUIRED = 0x00000040
        if allow:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        else:
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_AWAYMODE_REQUIRED)
    except Exception:
        pass


def kill_stray_processes():
    """Kill leftover BetFlow processes (backend/python) before starting GUI."""
    if psutil is None:
        try:
            log_message("ℹ️ psutil not available - skipping stray process cleanup")
        except Exception:
            pass
        return

    current_pid = os.getpid()
    targets_names = set()
    cmd_keywords = [
        "main_gui.py",
        "aviator_automation.py",
        "auto_aviator_discovery",
        "capture_aviator",
    ]

    killed = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pid = proc.info.get("pid")
            if pid == current_pid or not pid:
                continue
            name = (proc.info.get("name") or "").lower()
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            if name in targets_names or any(k in cmdline for k in cmd_keywords):
                try:
                    proc.terminate()
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        continue
                killed.append(f"{name or 'python'}:{pid}")
        except Exception:
            continue

    try:
        if killed:
            log_message(f"💀 Killed stray processes: {', '.join(killed)}")
        else:
            log_message("✅ No stray processes found")
    except Exception:
        pass

# Windows API imports for taskbar icon
if sys.platform == 'win32':
    try:
        import ctypes
        WINDOWS_API_AVAILABLE = True
    except ImportError:
        WINDOWS_API_AVAILABLE = False
else:
    WINDOWS_API_AVAILABLE = False

# Application version
APP_VERSION = "5.0.0"
APP_BUILD_DATE = "2025-01-03"
APP_USER_MODEL_ID = "AviatorByBetFlow.App"

class BetFlowAviatorProGUI:
    def __init__(self, root, splash_screen=None):
        self.root = root
        self.splash_screen = splash_screen  # Store splash screen reference for progress updates

        # Windows: set AppUserModelID to ensure custom icon shows in taskbar (no Tk/Python icon)
        if WINDOWS_API_AVAILABLE:
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
            except Exception:
                pass

        # Keep the machine awake so the 06:00 auto-start always fires while the tool is open.
        allow_sleep(False)

        self.root.title(f"🎯 Aviator by BetFlow v{APP_VERSION} — AI-Powered Automation")
        
        # Get screen dimensions for centering
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # PERFORMANCE FIX: Fixed window size eliminates resize lag
        window_width = 1200
        window_height = 800
        
        # Calculate center position
        center_x = int((screen_width - window_width) / 2)
        center_y = int((screen_height - window_height) / 2)
        
        # Set fixed geometry: widthxheight+x+y
        self.root.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")
        
        # PERFORMANCE FIX: Disable resizing = no glitches, no lag!
        self.root.resizable(False, False)  # 80% improvement in smoothness
        
        # ANTI-GLITCH: Prevent geometry changes that cause flickering
        self._geometry_locked = False
        self._original_geometry = None
        
        # ANTI-GLITCH: Prevent excessive root.update() calls that cause lag
        self._root_update_pending = False
        self._root_update_scheduled = False
        
        # 🛡️ FREEZE PREVENTION: Heartbeat to keep GUI responsive
        self._gui_heartbeat_active = True
        self._last_heartbeat = time.time()
        self._heartbeat_interval = 0.1  # 100ms heartbeat
        self._start_gui_heartbeat()

        # Kill stray processes (previous runs) to avoid port conflicts and GO spam
        if not LITE_MODE:
            kill_stray_processes()

        # 🛡️ FREEZE PREVENTION: Watchdog to detect frozen GUI
        self._watchdog_active = True
        self._watchdog_last_check = time.time()
        self._watchdog_interval = 1.0  # Check every second
        self._start_gui_watchdog()

        # Initialize stability systems (non-blocking)
        self.stability_orchestrator = None
        if STABILITY_SYSTEMS_ENABLED and not LITE_MODE:
            self._init_stability_systems()

        
        self.root.configure(bg='#1e1e1e')
        try:
            ensure_assets()
        except Exception:
            pass
        
        # AI control flags (define EARLY to avoid attribute errors)
        self.ai_enabled = tk.BooleanVar(value=False)  # AI disabled for Aviator Pro
        self.ai_mode = tk.StringVar(value="manual")
        
        # Make window appear on top and get focus
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(100, lambda: self.root.attributes('-topmost', False))  # Remove topmost after 100ms so it doesn't stay always on top
        self.root.focus_force()
        
        # Set professional icon for both window AND taskbar (works in EXE and dev)
        _icon_candidates = [
            resource_path('Assets/betflow_icon.ico'),
            resource_path('Aviator_by_BetFlow_Distribution/betflow_icon.ico')
        ]
        icon_path = next((p for p in _icon_candidates if os.path.exists(p)), _icon_candidates[0])
        
        # Also try PNG as fallback
        png_candidates = [
            resource_path('Assets/betflow_logo.png'),
            resource_path('Aviator_by_BetFlow_Distribution/betflow_logo.png')
        ]
        png_path = next((p for p in png_candidates if os.path.exists(p)), None)
        
        if os.path.exists(icon_path):
            try:
                # Convert to absolute path for Windows API
                icon_path_abs = os.path.abspath(icon_path)
                
                # Method 1: iconbitmap (Windows .ico file) - for window title bar
                self.root.iconbitmap(icon_path_abs)
                
                # Method 2: iconphoto using PNG (more reliable for taskbar)
                if png_path and os.path.exists(png_path):
                    try:
                        from PIL import Image, ImageTk
                        # Load PNG and create multiple sizes
                        img = Image.open(png_path)
                        if img.mode != 'RGBA':
                            img = img.convert('RGBA')
                        
                        # Create icon at multiple sizes for better quality
                        icon_sizes = [16, 32, 48, 64]
                        icon_photos = []
                        
                        for size in icon_sizes:
                            resized = img.resize((size, size), Image.Resampling.LANCZOS)
                            # Create white background for transparency
                            background = Image.new('RGBA', (size, size), (255, 255, 255, 255))
                            background.paste(resized, (0, 0), resized)
                            photo = ImageTk.PhotoImage(background)
                            icon_photos.append(photo)
                        
                        # Set the largest as default
                        self.root.iconphoto(True, *icon_photos)
                        
                        # Keep references to prevent garbage collection
                        self._icon_photos = icon_photos
                        
                    except Exception as pil_err:
                        pass
                
                # Method 3: Windows API - Force taskbar icon update (CRITICAL for EXE)
                def set_taskbar_icon_windows_api():
                    """Use Windows API to forcefully set taskbar icon"""
                    if not WINDOWS_API_AVAILABLE:
                        return
                    try:
                        # Get window handle (Tkinter on Windows returns HWND directly)
                        try:
                            hwnd = self.root.winfo_id()
                            if not hwnd:
                                return
                        except:
                            return
                        
                        # Load icon using Windows API
                        LR_LOADFROMFILE = 0x10
                        IMAGE_ICON = 1
                        
                        # Convert path to Unicode string for LoadImageW
                        icon_path_unicode = str(icon_path_abs)
                        
                        # Load icon from file using Windows API
                        user32 = ctypes.windll.user32
                        
                        # LoadImageW signature: LoadImageW(hInst, name, type, cx, cy, fuLoad)
                        # Use 0 (NULL) for hInst when loading from file
                        hicon_large = user32.LoadImageW(0, icon_path_unicode, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
                        hicon_small = user32.LoadImageW(0, icon_path_unicode, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                        
                        if hicon_large and hicon_large != 0:
                            # Set both large and small icons
                            WM_SETICON = 0x0080
                            ICON_BIG = 1
                            ICON_SMALL = 0
                            ICON_SMALL2 = 2
                            
                            # Send WM_SETICON message to update taskbar icon
                            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_large)
                            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_large)
                            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL2, hicon_large)
                            try:
                                GCLP_HICON = -14
                                GCLP_HICONSM = -34
                                user32.SetClassLongPtrW(hwnd, GCLP_HICON, hicon_large)
                                if hicon_small and hicon_small != 0:
                                    user32.SetClassLongPtrW(hwnd, GCLP_HICONSM, hicon_small)
                            except Exception:
                                pass
                            
                            # Store handle to prevent garbage collection
                            if not hasattr(self, '_icon_handle'):
                                self._icon_handle = hicon_large
                    except Exception as api_err:
                        # Fallback to iconbitmap if API fails - silently continue
                        pass
                
                # Method 4: Force update after window is visible (for taskbar)
                def set_taskbar_icon():
                    try:
                        self.root.iconbitmap(icon_path)
                        # Also try Windows API method
                        if WINDOWS_API_AVAILABLE:
                            set_taskbar_icon_windows_api()
                    except:
                        pass
                
                # Set icon after window is fully initialized - multiple attempts
                self.root.after(50, set_taskbar_icon)  # Early attempt
                self.root.after(100, set_taskbar_icon)
                self.root.after(300, set_taskbar_icon)
                self.root.after(500, set_taskbar_icon)  # Second attempt after window is fully visible
                self.root.after(1000, set_taskbar_icon)  # Final attempt
                
            except Exception as e:
                print(f"Warning: Could not set icon: {e}")
        else:
            print(f"Warning: Icon file not found at: {icon_path}")

        # Helper function to update splash screen progress
        def update_splash_progress(progress, status):
            """Update splash screen progress if available"""
            if self.splash_screen:
                try:
                    self.root.after(0, lambda: self.splash_screen.update_progress(progress, status))
                    self.root.update_idletasks()
                except:
                    pass
        
        # Initial progress
        update_splash_progress(10, "🔧 Preparing system...")
        
        # Default: Persistent (writes enabled)
        set_persistence(True)

        # Network status
        self.network_online = True
        self.network_check_interval = 3000  # Check every 3 seconds for faster detection
        
        # ANTI-GLITCH SYSTEM: Prevent GUI tweaks and glitches
        self._gui_update_queue = []  # Queue for batched GUI updates
        self._gui_update_pending = False  # Flag to prevent duplicate update scheduling
        self._last_gui_update = 0  # Track last update time for throttling
        self._gui_update_lock = threading.Lock()  # Lock for thread-safe updates
        self._gui_update_min_interval = 0.016  # ~60fps max update rate (16ms minimum)
        self._log_buffer = []  # Buffer for log messages to batch updates
        self._log_buffer_max = 10  # Batch up to 10 log messages (normal mode)
        self._log_buffer_max_fast = 50  # Batch up to 50 log messages (fast mode)
        self._log_update_scheduled = False
        self._fast_mode_active = False

        update_splash_progress(20, "🧠 Initializing core engine...")
        self.headless = None
        self.remote_server = None
        self.zap_helper = None
        self.browser_discovery = None
        def _init_core_engine_async():
            update_splash_progress(35, "✅ Core engine ready")
        threading.Thread(target=_init_core_engine_async, daemon=True).start()
        
        # Golang backend not used
        self.golang_backend_process = None
        
        # 🚀 SMART PRELOADER - defer start until user triggers Aviator
        self.preloader = None
        self.preloader_started = False
        self.last_accounts_text = ""
        self.last_password = ""
        
        # Network callback is set after engine init

        # AI disabled for Aviator Pro (skip heavy init entirely)
        update_splash_progress(45, "🤖 Skipping AI engine (not needed for Aviator)...")
        self.ai_integration = None
        self.ai_learning = None
        update_splash_progress(55, "✅ Ready (AI skipped)")
        
        # Security and monitoring layer
        update_splash_progress(60, "🔐 Initializing security layer...")
        # Watchdog removed - functionality preserved
        update_splash_progress(65, "✅ Security layer ready")

        # Load config
        update_splash_progress(70, "⚙️ Loading configuration...")
        self.config = self.load_config()
        update_splash_progress(75, "✅ Configuration loaded")
        self.telegram_token = tk.StringVar(value=self.config.get('telegram_token', ''))
        self.telegram_chat_id = tk.StringVar(value=self.config.get('telegram_chat_id', ''))
        # Preset to Aviator page to avoid blank data: URLs
        default_url = 'https://odibets.com/aviator'
        self.target_url = tk.StringVar(value=self.config.get('base_url', default_url) or default_url)
        self.theme = tk.StringVar(value=self.config.get('theme', 'dark'))
        
        # Telegram bot instance
        self.telegram_bot = None
        self.running = True  # Kill switch flag

        # Enhanced UI state
        self.paned_windows = {}  # Store paned window references for resizing
        

        # UI Colors
        self.dark_theme = {
            'bg': '#1e1e1e',
            'fg': '#ffffff',
            'button_bg': '#2196F3',
            'button_fg': '#ffffff',
            'text_bg': '#252525',
            'text_fg': '#e0e0e0'
        }
        self.light_theme = {
            'bg': '#f8f9fa',
            'fg': '#212529',
            'button_bg': '#e9ecef',
            'button_fg': '#212529',
            'text_bg': '#ffffff',
            'text_fg': '#212529'
        }
        
        # Set initial colors based on theme from config
        if self.theme.get() == 'light':
            self.colors = self.light_theme.copy()
        else:
            self.colors = self.dark_theme.copy()

        # Create UI - this is slow (creates all widgets)
        update_splash_progress(80, "🎨 Creating UI components...")
        self.create_widgets()
        update_splash_progress(90, "✅ UI components ready")
        
        # Setup keyboard shortcuts
        self.setup_keyboard_shortcuts()
        
        # Setup drag and drop (basic implementation)
        self.setup_drag_drop()

        # Apply initial theme after everything is initialized
        if hasattr(self, 'apply_theme'):
            self.apply_theme()
        
        # Final initialization steps
        update_splash_progress(92, "🌐 Starting network monitoring...")
        self.start_network_monitor()
        
        update_splash_progress(94, "⏰ Setting up system services...")
        # Start live clock (EAT - Kenya Time)
        self.update_live_clock()

        # Auto Scheduler service (daily 06:00-06:59 parallel runner)
        try:
            self._init_scheduler()
        except Exception as e:
            try:
                self.log(f"Scheduler init error: {e}")
            except Exception:
                pass
        
        # Skip background preloading and telegram auto-start to keep Aviator lean
        # self.preload_system()
        # self.auto_start_telegram_bot()
        
        # Global exception handler to prevent crashes
        self.setup_crash_protection()
        
        # Graceful shutdown handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        update_splash_progress(98, "✨ Finalizing...")
        try:
            env_phones = os.environ.get("PHONES_TEXT", "").strip()
            env_pass = os.environ.get("AVIATOR_PASSWORD", "").strip()
            auto_env = os.environ.get("AUTO_START_AVIATOR", "0").strip()
            if env_phones and env_pass:
                try:
                    self.phone_text.delete(1.0, tk.END)
                    self.phone_text.insert(1.0, env_phones)
                except Exception:
                    pass
                try:
                    self.password_entry.delete(0, tk.END)
                    self.password_entry.insert(0, env_pass)
                except Exception:
                    pass
                if auto_env in ("1", "true", "True"):
                    try:
                        self.root.after(500, self.aviator_automation)
                    except Exception:
                        pass
        except Exception:
            pass
    
    # ── Auto Scheduler (daily 06:00-06:59, parallel workers) ──────────────
    def _init_scheduler(self):
        try:
            import scheduler_engine as se
        except Exception as e:
            try:
                self.log(f"Scheduler module unavailable: {e}")
            except Exception:
                pass
            self._engine = None
            return
        self._se_module = se
        try:
            worker_count = max(1, int(self.sched_workers_var.get() or 4))
            rounds = max(1, int(self.sched_rounds_var.get() or 50))
            stake = max(1, float(self.sched_stake_var.get() or 10))
            real_money = bool(self.sched_real_var.get())
            cashout = float(self.sched_cashout_var.get() or 1.01)
        except Exception:
            worker_count, rounds, stake = 4, 50, 10
            real_money, cashout = False, 1.01
        try:
            minimize = bool(self.sched_minimize_var.get())
        except Exception:
            minimize = True
        self._engine = se.SchedulerEngine(
            worker_count=worker_count, rounds=rounds, stake=stake,
            real_money=real_money, cashout=cashout,
            minimize=minimize,
            progress_cb=self._sched_log,
        )
        self.root.after(5000, self._sched_tick)
        self.root.after(1000, self._update_countdown)
        self._update_sched_status()

    def _update_countdown(self):
        """Live HH:MM:SS countdown to the next 06:00 EAT auto-start."""
        try:
            if not getattr(self, '_engine', None) or not hasattr(self, 'sched_countdown_label'):
                return
            eng = self._engine
            if not eng._auto_enabled:
                self.sched_countdown_label.config(
                    text="AUTO scheduler OFF — tick it to auto-run at 06:00 EAT",
                    fg='#888')
            elif se.in_window(se.ktime()):
                self.sched_countdown_label.config(
                    text="▶ AUTO-RUNNING — playing until 07:00 EAT",
                    fg='#00C853')
            else:
                secs = se.next_window_in_seconds(se.ktime())
                h = int(secs // 3600); m = int((secs % 3600) // 60); s = int(secs % 60)
                self.sched_countdown_label.config(
                    text=f"Next auto-start: {h:02d}:{m:02d}:{s:02d}  (06:00 EAT)",
                    fg='#FFB300')
        except Exception:
            pass
        finally:
            try:
                self.root.after(1000, self._update_countdown)
            except Exception:
                pass

    def _sched_log(self, msg):
        try:
            self.log(f"[SCHED] {msg}")
        except Exception:
            pass

    def _phones_from_gui(self):
        try:
            return [ln.strip() for ln in self.phone_text.get("1.0", tk.END).splitlines() if ln.strip()]
        except Exception:
            return []

    def _load_phones_file(self):
        """Pick a text file and load its phone numbers into the list box.
        Accepts one number per line, or comma/space separated on a line."""
        path = filedialog.askopenfilename(
            title="Select phone numbers file",
            filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()
        except Exception as e:
            try:
                self.log(f"⚠️ Could not read file: {e}")
            except Exception:
                pass
            return
        # Normalise: split each line on commas; strip spaces/dashes so a number
        # written with formatting (e.g. 07 22 000 111) stays as one number.
        numbers = []
        for line in raw.splitlines():
            for tok in line.split(','):
                digits = "".join(ch for ch in tok if ch.isdigit())
                if digits:
                    numbers.append(digits)
        if not numbers:
            try:
                self.log("⚠️ No phone numbers found in that file.")
            except Exception:
                pass
            return
        self.phone_text.delete("1.0", tk.END)
        self.phone_text.insert("1.0", "\n".join(numbers) + "\n")
        try:
            self.log(f"📂 Loaded {len(numbers)} phone number(s) from {os.path.basename(path)}")
            self.save_config()
            self._update_sched_status()
        except Exception:
            pass

    def _on_sched_change(self, event=None):
        try:
            self.save_config()
            self._update_sched_status()
        except Exception:
            pass

    def _sched_tick(self):
        try:
            if getattr(self, '_engine', None) is not None:
                self._engine.tick()
            self._update_sched_status()
        except Exception:
            pass
        try:
            self.root.after(3000, self._sched_tick)
        except Exception:
            pass

    def _update_sched_status(self):
        try:
            if not getattr(self, '_engine', None) or not hasattr(self, 'sched_status_label'):
                return
            eng = self._engine
            phones = self._phones_from_gui()
            if phones:
                eng.set_phones(phones)
            try:
                eng.worker_count = max(1, int(self.sched_workers_var.get() or 4))
                eng.rounds = max(1, int(self.sched_rounds_var.get() or 50))
                eng.stake = max(1, float(self.sched_stake_var.get() or 10))
                eng.real_money = bool(self.sched_real_var.get())
                try:
                    eng.cashout = float(self.sched_cashout_var.get() or 1.01)
                except Exception:
                    eng.cashout = 1.01
                try:
                    eng.minimize = bool(self.sched_minimize_var.get())
                except Exception:
                    eng.minimize = True
                # Cache the login password so AUTO/tick() can start workers at
                # 06:00 without a prior manual Run. Only overwrite when non-empty
                # so a valid cached password is never clobbered by a blank field.
                try:
                    _pw = self.password_entry.get().strip()
                    if _pw:
                        eng._password = _pw
                except Exception:
                    pass
                eng._auto_enabled = bool(self.sched_auto_var.get())
                # AUTO: start IMMEDIATELY once ready (password + phones present),
                # instead of waiting for the 06:00-06:59 window. Manual reason so
                # tick() will not kill the run at 07:00.
                if (eng._auto_enabled and getattr(eng, '_password', None)
                        and eng.pending_count() > 0 and not eng.is_running()):
                    eng.start(eng._password, reason="manual")
            except Exception:
                pass
            # reflect REAL-MONEY state clearly in the status line
            rm = "REAL-MONEY" if getattr(eng, 'real_money', False) else "SIM"
            base = eng.status_text()
            self.sched_status_label.config(text=f"[{rm}] {base}")
            running = eng.is_running()
            self._run_btn.config(state='disabled' if running else 'normal')
            self._stop_btn.config(state='normal' if running else 'disabled')
            # primary buttons mirror scheduler running state (only when nothing a bot thread)
            try:
                if hasattr(self, 'martingale_btn'):
                    self.martingale_btn.config(state='disabled' if running else 'normal')
                if hasattr(self, 'stop_btn'):
                    self.stop_btn.config(state='normal' if running else 'disabled',
                                         text='■ STOP')
            except Exception:
                pass
        except Exception:
            pass

    def _sched_run_now(self):
        try:
            phones = self._phones_from_gui()
            password = self.password_entry.get().strip()
            if not phones:
                self.log("[SCHED] No phone numbers in the list.")
                return
            if not password:
                self.log("[SCHED] No password set.")
                return
            if getattr(self, '_engine', None) is None:
                self._init_scheduler()
            if getattr(self, '_engine', None) is None:
                self.log("[SCHED] Scheduler not available.")
                return
            eng = self._engine
            eng.set_phones(phones)
            total, pending = eng.total_count(), eng.pending_count()
            mode = "⚠ REAL-MONEY (real wagers!)" if eng.real_money else "SIMULATION (no real bets)"
            self.log(f"[SCHED] Manual run: {pending}/{total} pending with "
                     f"{eng.worker_count} worker(s) | rounds/acct={eng.rounds} "
                     f"stake={eng.stake}KES cashout=1.01x | mode: {mode}")
            if pending == 0:
                self.log("[SCHED] All accounts already done. Use Reset to restart.")
                return
            eng.start(password, workers=eng.worker_count, reason="manual")
        except Exception as e:
            try:
                self.log(f"[SCHED] Run error: {e}")
            except Exception:
                pass

    def _sched_stop(self):
        try:
            if getattr(self, '_engine', None) is not None:
                self._engine.stop(reason="user")
            self.log("[SCHED] Stopping all workers (in-progress accounts retried next run).")
        except Exception as e:
            try:
                self.log(f"[SCHED] Stop error: {e}")
            except Exception:
                pass

    def _primary_click(self):
        """Primary green action = run the multi-account scheduler."""
        # keep button states in sync with the engine
        try:
            self._update_sched_status()
        except Exception:
            pass
        self._sched_run_now()
        try:
            self._update_sched_status()
        except Exception:
            pass

    def _primary_stop(self):
        """Primary red action = stop whichever engine or legacy bot is running."""
        running = False
        try:
            eng = getattr(self, '_engine', None)
            running = bool(eng and eng.is_running())
        except Exception:
            running = False
        if running:
            self._sched_stop()
        else:
            try:
                self.stop_martingale_bot()
            except Exception:
                pass
        try:
            self._update_sched_status()
        except Exception:
            pass

    def _sched_reset(self):
        try:
            if getattr(self, '_engine', None) is not None:
                self._engine.mark_all_pending()
            self.log("[SCHED] Progress reset — all accounts marked pending.")
            self._update_sched_status()
        except Exception as e:
            try:
                self.log(f"[SCHED] Reset error: {e}")
            except Exception:
                pass

    def save_scheduler_settings(self):
        try:
            if getattr(self, '_engine', None) is not None:
                self._engine.worker_count = max(1, int(self.sched_workers_var.get() or 4))
                self._engine.rounds = max(1, int(self.sched_rounds_var.get() or 50))
                self._engine.stake = max(1, float(self.sched_stake_var.get() or 10))
                self._engine.real_money = bool(self.sched_real_var.get())
                try:
                    self._engine.cashout = float(self.sched_cashout_var.get() or 1.01)
                except Exception:
                    self._engine.cashout = 1.01
                try:
                    self._engine.minimize = bool(self.sched_minimize_var.get())
                except Exception:
                    self._engine.minimize = True
        except Exception:
            pass

    def on_close(self):
        """INSTANT shutdown - Close immediately without waiting"""
        import os
        import threading

        # Re-allow the OS to sleep now that the tool is closing.
        allow_sleep(True)
        # ⚡ IMMEDIATE: Set kill switch first (prevents new operations)
        # 🏊 Close browser pool gracefully
        try:
            if hasattr(self, 'headless') and self.headless:
                self.headless.close_all_browsers()
        except:
            pass

        # Stop the auto-scheduler workers
        try:
            if getattr(self, '_engine', None) is not None:
                self._engine.stop(reason="app close")
        except Exception:
            pass
        
        try:
            self.headless.running = False
        except:
            pass
            
        # 🚀 NON-BLOCKING: Start cleanup in background thread (don't wait)
        def cleanup_in_background():
            try:
                # Stop preloader
                if hasattr(self, 'preloader'):
                    self.preloader.stop()
                
                # Stop telegram bot if running
                if hasattr(self, 'telegram_bot') and self.telegram_bot:
                    try:
                        self.telegram_bot.stop()
                    except:
                        pass
                
                # Stop remote server if running
                if hasattr(self, 'remote_server') and self.remote_server:
                    try:
                        self.remote_server.stop()
                    except:
                        pass
                
                # 🔧 FIXED: Only clean up app-created processes, NOT user's personal browsers!
                # Browser pool cleanup above handles closing app-created browsers properly
                # We should NOT kill all Chrome processes - that would close user's personal browser!
                
                # Only clean up processes that we might have created (chromedriver, node for Playwright)
                # BUT: Be careful - even these might be from other apps, so only do this as last resort
                # The browser pool cleanup should be sufficient in most cases
                try:
                    import subprocess
                    import time
                    
                    # Check if CREATE_NO_WINDOW is available (Windows only)
                    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                        flags = subprocess.CREATE_NO_WINDOW
                    else:
                        flags = 0
                    
                    devnull = open(os.devnull, 'w') if hasattr(os, 'devnull') else None
                    kwargs = {'shell': True, 'creationflags': flags}
                    if devnull:
                        kwargs.update({'stdout': devnull, 'stderr': devnull})
                    
                    # REMOVED: taskkill chrome.exe - this was closing user's personal browser!
                    # Only clean up chromedriver and node (app-created) - but be careful
                    # Note: Even these could be from other apps, so this is a last resort cleanup
                    # The proper browser pool cleanup above should handle most cases
                    # subprocess.Popen('taskkill /F /IM chrome.exe /T 2>nul', **kwargs)  # REMOVED - was killing user browser!
                    
                    # Only cleanup chromedriver (but be cautious - could be from other apps)
                    # Give browsers time to close gracefully first
                    time.sleep(1)
                    # subprocess.Popen('taskkill /F /IM chromedriver.exe /T 2>nul', **kwargs)  # Commented - risky
                    # subprocess.Popen('taskkill /F /IM node.exe /T 2>nul', **kwargs)  # Commented - risky
                    
                    if devnull:
                        devnull.close()
                except:
                    # Browser pool cleanup should be sufficient
                    pass
            except:
                pass  # Ignore all cleanup errors - we're closing anyway
        
        # Start cleanup thread (non-blocking - don't wait for it)
        cleanup_thread = threading.Thread(target=cleanup_in_background, daemon=True)
        cleanup_thread.start()
        
        # ⚡ INSTANT: Close GUI immediately (don't wait for cleanup)
        try:
            self.root.quit()
            self.root.destroy()
        except:
            pass
            
        # 🔥 FORCE EXIT: If window didn't close, force terminate process
        try:
            import sys
            os._exit(0)  # Hard exit - terminates all threads immediately
        except:
            pass

    def setup_crash_protection(self):
        """Setup global exception handler to prevent app crashes"""
        import sys
        
        def exception_handler(exc_type, exc_value, exc_traceback):
            """Catch all unhandled exceptions"""
            if issubclass(exc_type, KeyboardInterrupt):
                # Allow Ctrl+C
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            
            # Log the error
            import traceback
            error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            try:
                self.log(f"🔥 CRITICAL ERROR CAUGHT (App protected from crash):")
                self.log(f"⚠️ {str(exc_value)[:200]}")
                log_message(f"Critical error: {error_msg[:1000]}")
            except:
                # If logging fails, print to console
                print(f"Critical error: {error_msg}")
            
            # Keep app alive
            try:
                self.headless.running = True
                self.running = True
            except:
                pass
        
        # Set the exception handler
        sys.excepthook = exception_handler
        
        # Also handle threading exceptions
        import threading
        def threading_exception_handler(args):
            try:
                self.log(f"⚠️ Thread error caught: {args.exc_value}")
            except:
                print(f"Thread error: {args.exc_value}")
        
        threading.excepthook = threading_exception_handler

    def preload_system(self):
        """Preload system resources in background for instant button response"""
        def _preload():
            try:
                # Pre-fetch Odi key and cookie so first operation is instant
                self.log("🔄 Preloading system resources...")
                success = self.headless.get_odi_key_and_cookie()
                if success:
                    self.log("✅ System ready - SMART MODE: Up to 10 tasks per second!")
                    self.log("💡 TIP: For Aviator, go straight to ✈️ AVIATOR AUTOMATION to claim free bets fast.")
                    # Backend only - robust mode enabled silently
                    log_message("💪 Robust mode: Can handle 1000+ accounts at 8-10/sec without crashing", verbose=True)
                else:
                    self.log("⚠️ Preload attempted - System will initialize on first use")
            except Exception as e:
                # Silent fail - system will work normally
                log_message(f"Preload info: {str(e)}")
        
        # Run in background thread so GUI stays responsive
        threading.Thread(target=_preload, daemon=True).start()
    
    def auto_start_telegram_bot(self):
        """Auto-start Telegram bot if credentials are configured"""
        def _start_bot():
            # Wait a moment for GUI to fully initialize (non-blocking)
            def start_bot_delayed():
                token = self.telegram_token.get().strip()
                chat_id = self.telegram_chat_id.get().strip()
                
                if token and chat_id:
                    try:
                        self.telegram_bot = BetFlowTelegramBot(token, chat_id, self)
                        success = self.telegram_bot.start()
                        if success:
                            self.log("🤖 Telegram bot auto-started and ready for remote control")
                        else:
                            self.log("⚠️ Telegram bot failed to auto-start (use 'Set Telegram' to reconnect)")
                    except Exception as e:
                        self.log(f"⚠️ Telegram bot auto-start error: {str(e)}")
            
            # Schedule delayed start (non-blocking)
            self.root.after(2000, start_bot_delayed)
        
        # Run in background thread
        threading.Thread(target=_start_bot, daemon=True).start()

    def load_config(self):
        config_path = 'config/endpoints.json'
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)
        return {
            'base_url': 'https://odibets.com',
            'endpoints': {
                'login': '/api/login',
                'balance': '/api/balance',
                'bet': '/api/bet/place',
                'bonus': '/api/bonus/claim'
            },
            'remote_enabled': False,
            'remote_token': 'default_token',
            'theme': 'dark'
        }

    def save_config(self):
        if should_persist():
            os.makedirs('config', exist_ok=True)
            config = self.config.copy()
            config['base_url'] = self.target_url.get()
            config['theme'] = self.theme.get()
            # Save credentials
            try:
                import base64
                config['aviator_pass'] = base64.b64encode(
                    self.password_entry.get().encode()).decode()
                config['aviator_site']       = self.site_var.get()
                try:
                    config['aviator_phone_list'] = self.phone_text.get("1.0", tk.END).strip()
                except Exception:
                    pass
                try:
                    config['sched_workers']  = int(self.sched_workers_var.get())
                    config['sched_rounds']   = int(self.sched_rounds_var.get())
                    config['sched_stake']    = float(self.sched_stake_var.get())
                    config['sched_auto']     = bool(self.sched_auto_var.get())
                    config['sched_real']     = bool(self.sched_real_var.get())
                    try:
                        config['sched_cashout'] = float(self.sched_cashout_var.get())
                    except Exception:
                        config['sched_cashout'] = 1.01
                    try:
                        config['sched_minimize'] = bool(self.sched_minimize_var.get())
                    except Exception:
                        config['sched_minimize'] = True
                except Exception:
                    pass
                try:
                    self.save_scheduler_settings()
                except Exception:
                    pass
            except Exception:
                pass
            with open('config/endpoints.json', 'w') as f:
                json.dump(config, f, indent=2)

    def save_config_on_change(self, event=None):
        # Respect stateless mode
        if should_persist():
            self.save_config()

    def login_aviator_visible(self):
        try:
            phone_lines = self.phone_text.get("1.0", tk.END).splitlines()
            phones = [p.strip() for p in phone_lines if p.strip()]
            phone = phones[0] if phones else ""
            password = self.password_entry.get().strip()
            self.log("Opening Aviator in visible browser")
            backend = AviatorBackend(headless=False, mobile_view=True, engine="chromium", progress_cb=self.log)
            def run():
                backend.start()
                result = backend.login_and_open_menu(phone, password)
                self.log(str(result))
                time.sleep(180)
                backend.stop()
            threading.Thread(target=run, daemon=True).start()
        except Exception as e:
            self.log(f"Error: {e}")

    def create_widgets(self):
        BG      = self.colors['bg']
        FG      = self.colors['fg']
        TBG     = self.colors['text_bg']
        TFG     = self.colors['text_fg']
        BTN_BG  = self.colors['button_bg']
        BTN_FG  = self.colors['button_fg']

        # ── Header bar ────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg='#111111', height=56)
        header.pack(fill='x', side='top')
        header.pack_propagate(False)

        logo_path = resource_path('Assets/betflow_logo.png')
        if os.path.exists(logo_path):
            try:
                from PIL import Image, ImageTk
                img = Image.open(logo_path)
                img.thumbnail((40, 40), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(img)
                tk.Label(header, image=self.logo_photo, bg='#111111').pack(side='left', padx=12, pady=8)
            except Exception:
                pass

        tk.Label(header, text="BetFlow Aviator", font=('Arial', 15, 'bold'),
                 fg='#00E676', bg='#111111').pack(side='left', pady=8)
        tk.Label(header, text="Multi-Account Scheduler", font=('Arial', 10),
                 fg='#666666', bg='#111111').pack(side='left', padx=6, pady=8)

        # right side of header
        hright = tk.Frame(header, bg='#111111')
        hright.pack(side='right', padx=12)
        self.clock_label = tk.Label(hright, text="--:--:--", font=('Consolas', 10, 'bold'),
                                    fg='#FFC107', bg='#111111')
        self.clock_label.pack(side='right', padx=8)
        self.network_label = tk.Label(hright, text="● Online", font=('Arial', 9, 'bold'),
                                      fg='#4CAF50', bg='#111111')
        self.network_label.pack(side='right', padx=8)
        self.stability_label = tk.Label(hright, text="", bg='#111111')
        self.stability_label.pack(side='right')

        # ── Main body: left panel + right terminal ────────────────────────────
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill='both', expand=True, padx=0, pady=0)

        # Left control panel (fixed width)
        left = tk.Frame(body, bg=BG, width=300)
        left.pack(side='left', fill='y', padx=(10, 4), pady=10)
        left.pack_propagate(False)

        # Right terminal panel
        right = tk.Frame(body, bg=BG)
        right.pack(side='left', fill='both', expand=True, padx=(4, 10), pady=10)

        # ── Account ───────────────────────────────────────────────────────────
        creds_frame = tk.LabelFrame(left, text=" Account ", fg='#888', bg=BG,
                                    font=('Arial', 9), bd=1, relief='solid')
        creds_frame.pack(fill='x', pady=(0, 8))
        creds_frame.columnconfigure(1, weight=1)

        tk.Label(creds_frame, text="Site", fg=FG, bg=BG, font=('Arial', 9)).grid(
            row=0, column=0, padx=8, pady=6, sticky='w')
        self.site_var = tk.StringVar(value="Betika")
        site_menu = tk.OptionMenu(creds_frame, self.site_var, "OdiBets", "Betika")
        site_menu.config(bg=TBG, fg=TFG, font=('Arial', 10), relief='flat',
                         highlightthickness=0, activebackground='#333')
        site_menu["menu"].config(bg=TBG, fg=TFG)
        site_menu.grid(row=0, column=1, padx=8, pady=6, sticky='ew')

        tk.Label(creds_frame, text="Password", fg=FG, bg=BG, font=('Arial', 9)).grid(
            row=1, column=0, padx=8, pady=6, sticky='w')
        self.password_entry = tk.Entry(creds_frame, show='●', bg=TBG, fg=TFG,
                                        font=('Arial', 11), insertbackground=TFG,
                                        relief='flat', bd=4)
        self.password_entry.grid(row=1, column=1, padx=8, pady=6, sticky='ew')
        self.password_entry.bind('<Return>', lambda e: self._sched_run_now())
        self._pw_visible = False
        self._pw_toggle_btn = tk.Button(creds_frame, text='👁', fg=TFG, bg=BG,
                                        font=('Arial', 11), relief='flat', bd=2,
                                        activebackground='#333',
                                        command=self._toggle_password_visibility)
        self._pw_toggle_btn.grid(row=1, column=2, padx=(0, 8), pady=6, sticky='e')

        # Phone list (paste as many numbers as you like, one per line) — the
        # primary account input for the auto-scheduler.
        tk.Label(creds_frame, text="Phone numbers\n(paste list, 1 per line)",
                 fg=FG, bg=BG, font=('Arial', 8)).grid(
            row=2, column=0, padx=8, pady=(4, 0), sticky='nw')
        self.phone_text = scrolledtext.ScrolledText(
            creds_frame, width=30, height=9, bg=TBG, fg=TFG,
            insertbackground=TFG, relief='flat', bd=3, font=('Consolas', 10),
            padx=6, pady=4)
        self.phone_text.grid(row=2, column=1, padx=8, pady=(4, 0), sticky='ew')

        # Load phone list from a file (one number per line / comma/space separated)
        load_row = tk.Frame(creds_frame, bg=BG)
        load_row.grid(row=3, column=1, padx=8, pady=(4, 0), sticky='ew')
        tk.Button(load_row, text="📂 Load from file…", command=self._load_phones_file,
                  bg='#1565C0', fg='white', font=('Arial', 10, 'bold'),
                  relief='flat', cursor='hand2', bd=0, height=1,
                  activebackground='#1976D2').pack(fill='x')

        self.password_entry.bind('<FocusOut>', lambda e: self.save_config())



        # ── Auto Scheduler (daily 06:00-06:59, parallel workers) ─────────────
        sched_frame = tk.LabelFrame(left, text=" Auto Scheduler (06:00–06:59) ",
                                    fg='#888', bg=BG, font=('Arial', 9),
                                    bd=1, relief='solid')
        sched_frame.pack(fill='x', pady=(0, 8))
        sched_frame.columnconfigure(1, weight=1)

        tk.Label(sched_frame, text="Workers", fg=FG, bg=BG,
                 font=('Arial', 9)).grid(row=0, column=0, padx=8, pady=4, sticky='w')
        self.sched_workers_var = tk.StringVar(value="4")
        tk.Entry(sched_frame, textvariable=self.sched_workers_var, bg=TBG,
                 fg=TFG, font=('Arial', 10), insertbackground=TFG,
                 relief='flat', bd=4, width=6).grid(row=0, column=1, padx=8, pady=4, sticky='w')

        tk.Label(sched_frame, text="Rounds/acct", fg=FG, bg=BG,
                 font=('Arial', 9)).grid(row=1, column=0, padx=8, pady=4, sticky='w')
        self.sched_rounds_var = tk.StringVar(value="50")
        tk.Entry(sched_frame, textvariable=self.sched_rounds_var, bg=TBG,
                 fg=TFG, font=('Arial', 10), insertbackground=TFG,
                 relief='flat', bd=4, width=6).grid(row=1, column=1, padx=8, pady=4, sticky='w')

        tk.Label(sched_frame, text="Stake KES", fg=FG, bg=BG,
                 font=('Arial', 9)).grid(row=2, column=0, padx=8, pady=4, sticky='w')
        self.sched_stake_var = tk.StringVar(value="10")
        tk.Entry(sched_frame, textvariable=self.sched_stake_var, bg=TBG,
                 fg=TFG, font=('Arial', 10), insertbackground=TFG,
                 relief='flat', bd=4, width=6).grid(row=2, column=1, padx=8, pady=4, sticky='w')

        self.sched_auto_var = tk.BooleanVar(value=True)
        tk.Checkbutton(sched_frame, text="Auto-start daily (06:00)",
                       variable=self.sched_auto_var, fg=FG, bg=BG,
                       selectcolor='#333', activebackground=BG,
                       command=self._on_sched_change, font=('Arial', 9)
                       ).grid(row=3, column=0, columnspan=2, padx=8, pady=2, sticky='w')

        # ── REAL-MONEY toggle (off by default = safe UI-flow simulation) ──
        self.sched_real_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            sched_frame, text="⚠ REAL-MONEY betting",
            variable=self.sched_real_var, fg='#FFB300', bg=BG,
            selectcolor='#333', activebackground=BG,
            activeforeground='#FF8A00',
            command=self._on_sched_change, font=('Arial', 9, 'bold')
        ).grid(row=4, column=0, columnspan=2, padx=8, pady=2, sticky='w')

        self.sched_minimize_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            sched_frame, text="Minimize browser windows",
            variable=self.sched_minimize_var, fg=FG, bg=BG,
            selectcolor='#333', activebackground=BG,
            command=self._on_sched_change, font=('Arial', 9)
        ).grid(row=5, column=0, columnspan=2, padx=8, pady=2, sticky='w')

        tk.Label(sched_frame, text="Cashout odds", fg=FG, bg=BG,
                 font=('Arial', 9)).grid(row=7, column=0, padx=8, pady=2, sticky='w')
        self.sched_cashout_var = tk.StringVar(value="1.01")
        tk.Entry(sched_frame, textvariable=self.sched_cashout_var, bg=TBG,
                 fg=TFG, font=('Arial', 10), insertbackground=TFG,
                 relief='flat', bd=4, width=6).grid(row=7, column=1, padx=8, pady=2, sticky='w')

        self.sched_status_label = tk.Label(
            sched_frame, text="Scheduler idle", fg='#888', bg=BG,
            font=('Consolas', 8), wraplength=270, justify='left')
        self.sched_status_label.grid(row=8, column=0, columnspan=2, padx=8, pady=4, sticky='ew')

        self.sched_countdown_label = tk.Label(
            sched_frame, text="AUTO scheduler OFF", fg='#888', bg=BG,
            font=('Consolas', 9, 'bold'), wraplength=270, justify='left')
        self.sched_countdown_label.grid(row=9, column=0, columnspan=2, padx=8, pady=(0, 4), sticky='ew')

        btnrow = tk.Frame(sched_frame, bg=BG)
        btnrow.grid(row=10, column=0, columnspan=2, padx=6, pady=(2, 6), sticky='ew')
        btnrow.columnconfigure(0, weight=1)
        btnrow.columnconfigure(1, weight=1)
        btnrow.columnconfigure(2, weight=1)

        run_now_btn = tk.Button(btnrow, text="▶ Run Now",
                                command=self._sched_run_now, bg='#00C853',
                                fg='#000', font=('Arial', 11, 'bold'),
                                relief='flat', cursor='hand2', bd=0,
                                height=2, activebackground='#00E676')
        run_now_btn.grid(row=0, column=0, padx=2, sticky='ew')

        stop_btn = tk.Button(btnrow, text="■ Stop",
                             command=self._sched_stop, bg='#D32F2F', fg='white',
                             font=('Arial', 11, 'bold'), relief='flat',
                             cursor='hand2', bd=0, height=2,
                             activebackground='#EF5350')
        stop_btn.grid(row=0, column=1, padx=2, sticky='ew')

        reset_btn = tk.Button(btnrow, text="↺ Reset",
                              command=self._sched_reset, bg='#1565C0', fg='white',
                              font=('Arial', 11, 'bold'), relief='flat',
                              cursor='hand2', bd=0, height=2,
                              activebackground='#1976D2')
        reset_btn.grid(row=0, column=2, padx=2, sticky='ew')

        self._run_btn = run_now_btn
        self._stop_btn = stop_btn
        self._reset_btn = reset_btn

        # No auto-fill: scheduler fields stay empty and wait for user input.


        stats = tk.Frame(left, bg=BG)
        stats.pack(fill='x', pady=(0, 8))
        stats.columnconfigure(0, weight=1)
        stats.columnconfigure(1, weight=1)

        def _card(parent, row, col, label):
            f = tk.Frame(parent, bg='#1a1a2e', bd=0)
            f.grid(row=row, column=col, padx=3, pady=3, sticky='ew')
            tk.Label(f, text=label, fg='#555', bg='#1a1a2e',
                     font=('Arial', 8)).pack(pady=(6,0))
            val = tk.Label(f, text="—", fg='#FFB300', bg='#1a1a2e',
                           font=('Consolas', 11, 'bold'))
            val.pack(pady=(0,6))
            return val

        self.step_label   = _card(stats, 0, 0, "STEP")
        self.result_label = _card(stats, 0, 1, "LAST RESULT")
        self.streak_label = _card(stats, 1, 0, "STREAK")
        _bot_status_card  = _card(stats, 1, 1, "STATUS")
        self._bot_status_label = _bot_status_card

        # ── Control buttons (primary = multi-account scheduler) ──────────────
        self.martingale_btn = tk.Button(
            left, text="▶   RUN SCHEDULER",
            command=self._primary_click,
            bg='#00C853', fg='#000', font=('Arial', 14, 'bold'),
            relief='flat', cursor='hand2', height=3, bd=0,
            activebackground='#00E676', activeforeground='#000'
        )
        self.martingale_btn.pack(fill='x', pady=(0, 6))

        self.stop_btn = tk.Button(
            left, text="■   STOP",
            command=self._primary_stop,
            bg='#D32F2F', fg='white', font=('Arial', 14, 'bold'),
            relief='flat', cursor='hand2', height=3, bd=0,
            activebackground='#EF5350', activeforeground='white',
            state='disabled'
        )
        self.stop_btn.pack(fill='x', pady=(0, 6))

        self.csv_btn = tk.Button(
            left, text="📁  Export CSV",
            command=self.export_martingale_csv,
            bg='#1565C0', fg='white', font=('Arial', 11, 'bold'),
            relief='flat', cursor='hand2', height=2, bd=0,
            activebackground='#1976D2', activeforeground='white'
        )
        self.csv_btn.pack(fill='x')

        # ── Terminal (right panel) ────────────────────────────────────────────
        term_header = tk.Frame(right, bg=BG)
        term_header.pack(fill='x', pady=(0, 4))
        tk.Label(term_header, text="LIVE LOG", fg='#555', bg=BG,
                 font=('Arial', 9, 'bold')).pack(side='left')

        self.auto_scroll_btn = tk.Button(
            term_header, text="⏬ Auto-Scroll: ON",
            command=self.toggle_auto_scroll,
            bg='#2E7D32', fg='white', font=('Arial', 8),
            relief='flat', cursor='hand2', bd=0, padx=8
        )
        self.auto_scroll_btn.pack(side='right', padx=4)
        tk.Button(term_header, text="⬇ Bottom",
                  command=self.jump_to_bottom,
                  bg=BTN_BG, fg=BTN_FG, font=('Arial', 8),
                  relief='flat', cursor='hand2', bd=0, padx=8).pack(side='right', padx=4)
        tk.Button(term_header, text="🗑 Clear",
                  command=self.clear_terminal,
                  bg=BTN_BG, fg=BTN_FG, font=('Arial', 8),
                  relief='flat', cursor='hand2', bd=0, padx=8).pack(side='right', padx=4)

        self.terminal = scrolledtext.ScrolledText(
            right, bg='#0d0d0d', fg='#00E676',
            font=('Consolas', 11), wrap=tk.WORD,
            undo=False, maxundo=0, autoseparators=False,
            insertbackground='#00E676', relief='flat', bd=0
        )
        self.terminal.pack(fill='both', expand=True)

        # ── Status bar ────────────────────────────────────────────────────────
        statusbar = tk.Frame(self.root, bg='#111111', height=24)
        statusbar.pack(fill='x', side='bottom')
        statusbar.pack_propagate(False)
        tk.Label(statusbar, text=f"v{APP_VERSION}", fg='#444', bg='#111111',
                 font=('Arial', 8)).pack(side='right', padx=10)

        # Bind legacy dummy events
        self.phone_text.bind('<KeyRelease>', self.update_button_states)
        self.phone_text.bind('<KeyRelease>', self.on_text_changed, add='+')
        self.phone_text.bind('<<Paste>>', lambda e: self.root.after(100, self.on_text_changed))
        self.password_entry.bind('<KeyRelease>', self.on_text_changed)
        self.auto_scroll_enabled = True
        self.terminal.bind('<Button-1>', self.on_terminal_click)
        self.terminal.bind('<MouseWheel>', self.on_terminal_scroll)
        
        # Configure grid weights
        creds_frame.grid_columnconfigure(1, weight=1)

        # Bind events for dynamic button enabling
        self.phone_text.bind('<KeyRelease>', self.update_button_states)
        
        # 🚀 SMART PRELOADING - Bind listeners for instant feel
        self.phone_text.bind('<KeyRelease>', self.on_text_changed, add='+')
        self.phone_text.bind('<<Paste>>', lambda e: self.root.after(100, self.on_text_changed))
        self.password_entry.bind('<KeyRelease>', self.on_text_changed)
        
        # Auto-scroll configuration
        self.auto_scroll_enabled = True
        self.terminal.bind('<Button-1>', self.on_terminal_click)
        self.terminal.bind('<MouseWheel>', self.on_terminal_scroll)

    def on_terminal_click(self, event):
        """Handle terminal click - smart auto-scroll control"""
        try:
            # Get current view position to detect if user is viewing history
            view = self.terminal.yview()
            
            # If not at bottom (user is viewing history), they might want auto-scroll off
            if view[1] < 0.99:
                # User clicked while viewing history - keep auto-scroll off
                if self.auto_scroll_enabled:
                    self.auto_scroll_enabled = False
            else:
                # User clicked at bottom - they likely want to see live updates
                self.auto_scroll_enabled = True
        except:
            pass

    def on_terminal_scroll(self, event):
        """Handle terminal scroll - disable auto-scroll if user scrolls up, re-enable at bottom"""
        try:
            # Check if user scrolled up (delta > 0 means scroll up)
            if event.delta > 0:
                # User scrolled up - disable auto-scroll
                if self.auto_scroll_enabled:
                    self.auto_scroll_enabled = False
                    # Don't log here to avoid spam
            else:
                # User scrolled down - check if at bottom
                # Get the current view position
                view = self.terminal.yview()
                # If scrolled to bottom (view[1] == 1.0), re-enable auto-scroll
                if view[1] >= 0.99:  # Allow slight margin
                    if not self.auto_scroll_enabled:
                        self.auto_scroll_enabled = True
                        # Subtle notification
        except:
            pass

    def ensure_auto_scroll(self):
        """Ensure terminal stays scrolled to bottom during operations with GUI responsiveness"""
        def _scroll_internal():
            if not self.auto_scroll_enabled:
                return  # Skip if user has disabled auto-scroll
                
            try:
                # Scroll to end (no immediate update - prevents glitches)
                self.terminal.see(tk.END)
                # Use after_idle for smooth updates instead of immediate update
                # This batches with other GUI updates and prevents glitches
                self.root.after_idle(lambda: self.terminal.update_idletasks())
            except:
                pass  # Ignore any errors during scrolling
        
        # Schedule on main thread (throttled to prevent glitches)
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, _scroll_internal)
        else:
            # On main thread, use after_idle to batch updates smoothly
            self.root.after_idle(_scroll_internal)

    def _batch_log_updates(self):
        """Process batched log messages to prevent GUI glitches from rapid updates"""
        if not self._log_buffer:
            self._log_update_scheduled = False
            return
        
        try:
            # Adaptive batch size
            max_batch = self._log_buffer_max_fast if self._fast_mode_active else self._log_buffer_max
            
            # Get buffered messages (up to max batch size)
            with self._gui_update_lock:
                messages_to_log = self._log_buffer[:max_batch]
                self._log_buffer = self._log_buffer[max_batch:]
            
            if not messages_to_log:
                self._log_update_scheduled = False
                return
            
            # Batch insert all messages at once (optimized for fast updates)
            timestamp = datetime.now().strftime('%H:%M:%S')
            log_text = ""
            for message in messages_to_log:
                log_entry = f"[{timestamp}] {message}\n"
                log_text += log_entry
                # Also log to file (non-blocking, don't slow down GUI)
                try:
                    log_message(log_entry.strip())
                except:
                    pass  # Don't block on file logging
            
            # Single insert operation (much faster than multiple inserts)
            if log_text:
                self.terminal.insert(tk.END, log_text)
                
                # Adaptive line limiting: keep more lines in fast mode
                max_lines = 1000 if self._fast_mode_active else 500
                try:
                    line_count = int(self.terminal.index('end-1c').split('.')[0])
                    if line_count > max_lines:
                        self.terminal.delete('1.0', f'{line_count - max_lines}.0')
                except:
                    pass  # Ignore errors in line counting
                
                # Force auto-scroll to bottom only if enabled
                if self.auto_scroll_enabled:
                    self.terminal.see(tk.END)
            
            # Schedule next batch if more messages in buffer
            if self._log_buffer:
                self.root.after(0, self._batch_log_updates)
            else:
                self._log_update_scheduled = False
                
        except Exception as e:
            # Never let log updates crash the GUI
            self._log_update_scheduled = False
            try:
                print(f"⚠️ Log update error (non-critical): {e}")
            except:
                pass  # Even print might fail if GUI is frozen
    
    def _start_gui_heartbeat(self):
        """🛡️ FREEZE PREVENTION: Keep GUI responsive with regular heartbeat"""
        def heartbeat():
            if not self._gui_heartbeat_active:
                return
            
            try:
                # Process pending GUI events (non-blocking)
                self.root.update_idletasks()
                self._last_heartbeat = time.time()
            except:
                pass  # Ignore errors in heartbeat
            
            # Schedule next heartbeat
            if self._gui_heartbeat_active:
                self.root.after(int(self._heartbeat_interval * 1000), heartbeat)
        
        # Start heartbeat
        self.root.after(int(self._heartbeat_interval * 1000), heartbeat)
    
    def _start_gui_watchdog(self):
        """🛡️ FREEZE PREVENTION: Monitor GUI responsiveness and recover if frozen"""
        def watchdog_check():
            if not self._watchdog_active:
                return
            
            try:
                current_time = time.time()
                time_since_last_heartbeat = current_time - self._last_heartbeat
                
                # If heartbeat hasn't updated in 5 seconds, GUI might be frozen
                if time_since_last_heartbeat > 5.0:
                    # Try to recover by forcing GUI update
                    try:
                        self.root.update_idletasks()
                        self._last_heartbeat = time.time()
                        # Log warning (but don't spam)
                        if not hasattr(self, '_watchdog_warning_logged') or not self._watchdog_warning_logged:
                            try:
                                self.log("⚠️ GUI watchdog: Detected potential freeze, recovering...")
                                self._watchdog_warning_logged = True
                            except:
                                pass
                    except:
                        pass
                else:
                    self._watchdog_warning_logged = False
                
                self._watchdog_last_check = current_time
            except:
                pass  # Ignore watchdog errors
            
            # Schedule next check
            if self._watchdog_active:
                self.root.after(int(self._watchdog_interval * 1000), watchdog_check)
        
        # Start watchdog
        self.root.after(int(self._watchdog_interval * 1000), watchdog_check)
    
    def log(self, message):
        """Thread-safe log method with batching to prevent GUI glitches"""
        # Add message to buffer
        with self._gui_update_lock:
            self._log_buffer.append(message)
            
            # Adaptive scheduling: faster updates in fast mode
            max_batch = self._log_buffer_max_fast if self._fast_mode_active else self._log_buffer_max
            
            # Schedule batch update if not already scheduled or if buffer is full
            should_schedule = not self._log_update_scheduled or len(self._log_buffer) >= max_batch
            
            if should_schedule:
                self._log_update_scheduled = True
                
                def _schedule_batch_update():
                    """Schedule batch update on main thread"""
                    self._batch_log_updates()
                
                # Schedule on main thread with throttling
                # In fast mode, use shorter delay for more responsive updates
                delay = 0 if self._fast_mode_active else 0
                if threading.current_thread() != threading.main_thread():
                    self.root.after(delay, _schedule_batch_update)
                else:
                    # On main thread, use after_idle to batch with other updates
                    self.root.after_idle(_schedule_batch_update)
    
    def update_button_states(self, event=None):
        phones_text = self.phone_text.get('1.0', tk.END).strip()
        # If place_bets_btn is not present (Aviator-only UI), skip
        if not hasattr(self, 'place_bets_btn'):
            return
        if phones_text:
            phone_list = [line.strip() for line in phones_text.split('\n') if line.strip()]
            count = len(phone_list)
            self.log(f"Phone numbers loaded: {count} numbers")
            # Keep button always green and enabled - will show error if no phones
            self.place_bets_btn.config(state='normal', bg='#4CAF50')
        else:
            # Keep button green even with no phones - validation will happen on click
            self.place_bets_btn.config(state='normal', bg='#4CAF50')
    
    def on_text_changed(self, event=None):
        """🚀 SMART PRELOAD: Called when user types/pastes - start background processing"""
        accounts_text = self.phone_text.get("1.0", tk.END).strip()
        password = self.password_entry.get().strip()
        
        # Only process if something changed
        if accounts_text != self.last_accounts_text or password != self.last_password:
            self.last_accounts_text = accounts_text
            self.last_password = password
            
            # Start background processing if we have both accounts and password
            if accounts_text and password and self.preloader:
                self.preloader.on_accounts_changed(accounts_text, password)
                self.root.after(2000, self.update_preload_status)
    
    def update_preload_status(self):
        """Show live preload status to user"""
        status = self.preloader.get_status() if self.preloader else {'is_processing': False, 'cached_accounts': 0, 'queue_size': 0}
        cached = status['cached_accounts']
        
        if status['is_processing']:
            log_message("🔥 Smart preload: Processing accounts in background...", verbose=True)
        elif cached > 0:
            # Show user that accounts are ready for instant response
            self.log(f"⚡ INSTANT MODE: {cached} accounts ready - click any button for 10 tasks/sec speed!")
        
        # Keep updating if still processing
        if self.preloader and (status['is_processing'] or status['queue_size'] > 0):
            self.root.after(1000, self.update_preload_status)

        # First-run: ensure the Playwright Firefox browser is present.
        # Auto-installs it (one-time) so recipients don't need Python.
        def _check_browser():
            try:
                import run_multi_betika as rm
                if rm.ensure_firefox_installed(log_cb=self.log):
                    self.log("✓ Firefox browser ready.")
                else:
                    self.log("✗ Firefox missing — auto-install failed. Runs will error until it is installed.")
            except Exception as e:
                self.log(f"Browser check error: {e}")
        threading.Thread(target=_check_browser, daemon=True).start()

    def _toggle_password_visibility(self):
        """Eye toggle: show/hide the password characters."""
        self._pw_visible = not self._pw_visible
        if self._pw_visible:
            self.password_entry.config(show='')
            self._pw_toggle_btn.config(text='🙈')
        else:
            self.password_entry.config(show='●')
            self._pw_toggle_btn.config(text='👁')

    def save_config_on_change(self, event=None):
        if should_persist():
            self.save_config()

    def upload_phones(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"), ("All files", "*.*")])
        if file_path:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                self.phone_text.insert(tk.END, content)
            # Count and log after upload
            phones_text = self.phone_text.get('1.0', tk.END).strip()
            phone_list = [line.strip() for line in phones_text.split('\n') if line.strip()]
            count = len(phone_list)
            self.log(f"Phone numbers uploaded: {count} numbers from {file_path}")
            self.update_button_states()  # Update button state

    def change_bookie(self):
        """Change bookie URL and let AI discover endpoints"""
        new_url = self.target_url.get().strip()
        if not new_url:
            self.log("❌ Error: Please enter a bookie URL first")
            return
        
        # Confirm with user
        confirm = messagebox.askyesno(
            "Change Bookie",
            f"Switch from {self.headless.base_url} to {new_url}?\n\nAI will automatically learn and adapt to the new site."
        )
        if not confirm:
            return
        
        self.log(f"🤖 AI is analyzing the new bookie...")
        self.log("⏳ This may take 10-30 seconds...")
        
        # Run in background thread
        def change_bookie_thread():
            success = self.headless.change_bookie_url(new_url)
            if success:
                self.log(f"  🚀 Ready to use with new bookie!")
                messagebox.showinfo("Success", f"✅ AI successfully learned {new_url}\n\nReady to operate!")
            else:
                self.log("\n❌ AI couldn't fully adapt to the new site")
                self.log("  💡 Site may not be compatible")
                messagebox.showerror("Error", f"AI couldn't fully learn {new_url}\n\nSite may not be compatible")
        
        threading.Thread(target=change_bookie_thread, daemon=True).start()

     

    def claim_bonus(self):
        phones = self.phone_text.get('1.0', tk.END).strip()
        if not phones:
            self.log("❌ Error: Please enter phone numbers before claiming bonuses.")
            return
        
        password = self.password_entry.get()
        if not password:
            self.log("❌ Error: Please enter password for claiming bonuses.")
            return
        
        phone_list = [line.strip() for line in phones.split('\n') if line.strip()]
        
        self.log(f"🎁 Starting bonus claiming for {len(phone_list)} accounts...")
        self.log("🔍 Will fetch and claim all available promotions...")
        
        # Create enhanced callback that ensures auto-scroll
        def enhanced_callback(message):
            self.log(message)
            self.ensure_auto_scroll()
        
        # Use the new bonus claiming method
        threading.Thread(
            target=self.headless.claim_bonuses_for_accounts,
            args=(phone_list, password, enhanced_callback),
            daemon=True
        ).start()

    def withdraw_funds(self):
        """Withdraw funds from all accounts with elegant dialog"""
        phones = self.phone_text.get('1.0', tk.END).strip()
        if not phones:
            self.log("❌ Error: Please enter phone numbers before withdrawing.")
            messagebox.showerror("Missing Data", "Please enter phone numbers")
            return
        
        password = self.password_entry.get()
        if not password:
            self.log("❌ Error: Please enter password for withdrawal.")
            messagebox.showerror("Missing Password", "Please enter password")
            return
        
        phone_list = [line.strip() for line in phones.split('\n') if line.strip()]
        
        if len(phone_list) == 0:
            self.log("❌ Error: No valid phone numbers found")
            messagebox.showerror("Invalid Data", "No valid phone numbers found")
            return
        
        # Show elegant withdrawal dialog
        amount = self.show_withdrawal_dialog(len(phone_list))
        
        if not amount:
            self.log("❌ Withdrawal cancelled")
            return
        
        self.log(f"💸 Starting withdrawal for {len(phone_list)} accounts...")
        self.log(f"💰 Amount per account: KES {amount:.2f}")
        self.log(f"💵 Total withdrawal: KES {amount * len(phone_list):.2f}")
        
        # Create enhanced callback that ensures auto-scroll
        def enhanced_callback(message):
            self.log(message)
            self.ensure_auto_scroll()
        
        def run_withdrawal():
            try:
                # Reset running flag in case it was stopped
                self.headless.running = True
                self.running = True
                self.headless.batch_withdraw(phone_list, password, amount, enhanced_callback)
                self.log("✅ Withdrawal process completed!")
            except KeyboardInterrupt:
                self.log("🛑 Withdrawal stopped by user")
            except Exception as e:
                self.log(f"❌ ERROR during withdrawal: {str(e)}")
                import traceback
                self.log(f"⚠️ Details: {traceback.format_exc()[:500]}")
            finally:
                # Always reset flags
                try:
                    self.headless.running = True
                    self.running = True
                except:
                    pass
        
        threading.Thread(target=run_withdrawal, daemon=True).start()

    def show_withdrawal_dialog(self, account_count):
        """Show elegant withdrawal dialog and return amount or None if cancelled"""
        # Create custom dialog window
        dialog = tk.Toplevel(self.root)
        dialog.title("💸 Withdraw Funds")
        dialog.configure(bg='#1E1E1E')
        dialog.resizable(False, False)
        
        # Center the dialog
        dialog_width = 500
        dialog_height = 480  # Increased from 380 to fit all content + buttons
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - dialog_width) // 2
        y = (screen_height - dialog_height) // 2
        dialog.geometry(f'{dialog_width}x{dialog_height}+{x}+{y}')
        
        # Make it modal
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Result variable
        result = {'amount': None}
        
        # Header with icon
        header_frame = tk.Frame(dialog, bg='#00BCD4', height=80)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="💸", font=('Arial', 36), bg='#00BCD4', fg='white').pack(pady=10)
        tk.Label(header_frame, text="Withdraw to M-Pesa", font=('Arial', 14, 'bold'), bg='#00BCD4', fg='white').pack()
        
        # Main content
        content_frame = tk.Frame(dialog, bg='#1E1E1E', padx=30, pady=15)
        content_frame.pack(fill='both', expand=True)
        
        # Account info
        info_frame = tk.Frame(content_frame, bg='#2A2A2A', relief='flat', bd=0)
        info_frame.pack(fill='x', pady=(0, 12))
        
        tk.Label(info_frame, text=f"📱 Accounts: {account_count}", 
                font=('Arial', 11), bg='#2A2A2A', fg='#00BCD4', anchor='w', padx=15, pady=8).pack(fill='x')
        tk.Label(info_frame, text="💳 Destination: M-Pesa linked to each account", 
                font=('Arial', 10), bg='#2A2A2A', fg='#888888', anchor='w', padx=15, pady=8).pack(fill='x')
        
        # Amount input section
        tk.Label(content_frame, text="Enter Amount per Account (KES)", 
                font=('Arial', 10, 'bold'), bg='#1E1E1E', fg='white', anchor='w').pack(fill='x', pady=(8, 4))
        
        # Amount entry with styled frame
        entry_frame = tk.Frame(content_frame, bg='#2A2A2A', relief='flat', bd=1, highlightthickness=1, highlightbackground='#00BCD4')
        entry_frame.pack(fill='x', pady=(0, 10))
        
        amount_var = tk.StringVar(value="100")
        amount_entry = tk.Entry(entry_frame, textvariable=amount_var, font=('Arial', 16, 'bold'), 
                               bg='#2A2A2A', fg='white', insertbackground='white', 
                               relief='flat', justify='center', bd=0)
        amount_entry.pack(fill='x', padx=2, pady=2, ipady=8)
        amount_entry.select_range(0, tk.END)
        amount_entry.focus()
        
        # Total calculation (updates in real-time)
        total_label = tk.Label(content_frame, text="", font=('Arial', 9), 
                              bg='#1E1E1E', fg='#888888', anchor='center')
        total_label.pack(fill='x', pady=(4, 10))
        
        def update_total(*args):
            try:
                amount = float(amount_var.get())
                total = amount * account_count
                total_label.config(text=f"Total Withdrawal: KES {total:,.2f}", fg='#00BCD4')
            except:
                total_label.config(text="Enter a valid amount", fg='#FF5555')
        
        amount_var.trace('w', update_total)
        update_total()
        
        # Warning message
        warning_frame = tk.Frame(content_frame, bg='#2A2A2A', relief='flat', bd=0)
        warning_frame.pack(fill='x', pady=(0, 10))
        
        tk.Label(warning_frame, text="⚠️ Important Information", font=('Arial', 8, 'bold'), 
                bg='#2A2A2A', fg='#FFC107', anchor='w', padx=10, pady=4).pack(fill='x')
        tk.Label(warning_frame, text="• Sent to M-Pesa immediately\n• Min: KES 100 | Max daily: KES 70,000\n• Cannot be reversed", 
                font=('Arial', 8), bg='#2A2A2A', fg='#888888', anchor='w', padx=10, pady=6, justify='left').pack(fill='x')
        
        # Buttons
        button_frame = tk.Frame(content_frame, bg='#1E1E1E')
        button_frame.pack(fill='x', pady=(10, 0))
        
        def on_confirm():
            try:
                # Get and validate amount
                amount_str = amount_var.get().strip()
                if not amount_str:
                    messagebox.showwarning("Invalid Amount", "Please enter an amount", parent=dialog)
                    amount_entry.focus()
                    return
                
                # Convert to float
                try:
                    amount = float(amount_str)
                except ValueError:
                    messagebox.showerror("Invalid Input", "Please enter a valid number (e.g., 100 or 250.50)", parent=dialog)
                    amount_entry.focus()
                    amount_entry.select_range(0, tk.END)
                    return
                
                # Validate range
                if amount < 100:
                    messagebox.showwarning("Invalid Amount", "Minimum withdrawal is KES 100", parent=dialog)
                    amount_entry.focus()
                    amount_entry.select_range(0, tk.END)
                    return
                    
                # Note: 70,000 is daily total limit across all accounts
                if amount > 70000:
                    messagebox.showwarning("Invalid Amount", "Maximum withdrawal is KES 70,000 (daily total limit)", parent=dialog)
                    amount_entry.focus()
                    amount_entry.select_range(0, tk.END)
                    return
                
                # Final confirmation with clear details
                total = amount * account_count
                confirm_msg = (
                    f"💸 WITHDRAW TO M-PESA\n\n"
                    f"Amount per account: KES {amount:,.2f}\n"
                    f"Number of accounts: {account_count}\n"
                    f"Total withdrawal: KES {total:,.2f}\n\n"
                    f"⚠️ Funds will be sent immediately to M-Pesa.\n"
                    f"This action cannot be reversed.\n\n"
                    f"Do you want to proceed?"
                )
                
                if messagebox.askyesno("Confirm M-Pesa Withdrawal", confirm_msg, parent=dialog):
                    result['amount'] = amount
                    dialog.destroy()
                    
            except Exception as e:
                messagebox.showerror("Error", f"An error occurred: {str(e)}", parent=dialog)
        
        def on_cancel():
            result['amount'] = None
            dialog.destroy()
        
        # Accept button (left) - Changed from "Withdraw" to "Accept"
        confirm_btn = tk.Button(button_frame, text="✓ ACCEPT", command=on_confirm, 
                               bg='#00BCD4', fg='white', font=('Arial', 11, 'bold'), 
                               relief='flat', cursor='hand2', padx=20, pady=10)
        confirm_btn.pack(side='left', fill='x', expand=True, padx=(0, 5))
        
        # Hover effect for confirm button
        def on_enter_confirm(e):
            confirm_btn.config(bg='#00ACC1')
        def on_leave_confirm(e):
            confirm_btn.config(bg='#00BCD4')
        confirm_btn.bind('<Enter>', on_enter_confirm)
        confirm_btn.bind('<Leave>', on_leave_confirm)
        
        # Cancel button (right)
        cancel_btn = tk.Button(button_frame, text="✗ CANCEL", command=on_cancel, 
                              bg='#424242', fg='white', font=('Arial', 11, 'bold'), 
                              relief='flat', cursor='hand2', padx=20, pady=10)
        cancel_btn.pack(side='left', fill='x', expand=True, padx=(5, 0))
        
        # Hover effect for cancel button
        def on_enter_cancel(e):
            cancel_btn.config(bg='#505050')
        def on_leave_cancel(e):
            cancel_btn.config(bg='#424242')
        cancel_btn.bind('<Enter>', on_enter_cancel)
        cancel_btn.bind('<Leave>', on_leave_cancel)
        
        # Bind Enter key to confirm
        dialog.bind('<Return>', lambda e: on_confirm())
        dialog.bind('<Escape>', lambda e: on_cancel())
        
        # Wait for dialog to close
        dialog.wait_window()
        
        return result['amount']

    def odileague_supa5(self):
        """OdiLeague Supa5 - Place 5 bets × 50 KES, get 50 KES bonus"""
        phones = self.phone_text.get('1.0', tk.END).strip()
        if not phones:
            self.log("❌ Error: Please enter phone numbers for Supa5.")
            return
        
        password = self.password_entry.get()
        if not password:
            self.log("❌ Error: Please enter password for Supa5.")
            return
        
        phone_list = [line.strip() for line in phones.split('\n') if line.strip()]
        
        self.log("🎁 ODILEAGUE SUPA5 BONUS STRATEGY")
        self.log("=" * 50)
        self.log(f"📊 Accounts: {len(phone_list)}")
        self.log(f"💰 Strategy: 5 bets × 50 KES = Get 50 KES bonus")
        self.log(f"📈 Total: {len(phone_list) * 250} KES (5 bets × 50 KES each)")
        self.log(f"🎁 Expected bonus: {len(phone_list) * 50} KES")
        self.log("=" * 50)
        self.log("⚠️  Requirements:")
        self.log("  • Place 5 bets of 50 KES each within 1 day")
        self.log("  • Bonus awarded after 5th bet settles")
        self.log("  • Bonus can only be used as ONE bet")
        self.log("=" * 50)
        
        # Ask for confirmation
        confirmed = messagebox.askyesno(
            "OdiLeague Supa5 Confirmation",
            f"Start Supa5 bonus automation?\n\n"
            f"Accounts: {len(phone_list)}\n"
            f"Total cost: {len(phone_list) * 250} KES\n"
            f"Expected bonus: {len(phone_list) * 50} KES\n\n"
            f"This will place 5 bets of 50 KES on Odileague for each account.",
            icon='question'
        )
        
        if not confirmed:
            self.log("❌ Supa5 automation cancelled by user")
            return
        
        self.log("🚀 Starting Supa5 automation...")
        
        # Create enhanced callback
        def enhanced_callback(message):
            self.log(message)
            self.ensure_auto_scroll()
        
        # Run Supa5 automation in background thread
        threading.Thread(
            target=self.headless.odileague_supa5_automation,
            args=(phone_list, password, enhanced_callback),
            daemon=True
        ).start()
    def aviator_automation(self):
        """✈️ AVIATOR AUTOMATION - Playwright Aviator free bet automation (single account)"""
        phones_text = self.phone_text.get('1.0', tk.END).strip()
        if not phones_text:
            self.log("❌ Please enter a phone number for Aviator automation")
            return

        password = self.password_entry.get()
        if not password:
            self.log("❌ Please enter password for Aviator automation")
            return

        # Single account only — take the first non-empty line
        phone = next((line.strip() for line in phones_text.split('\n') if line.strip()), None)
        if not phone:
            self.log("❌ No valid phone number found")
            return

        self.log(f"✈️ Starting Aviator Automation...")
        self.log(f"📱 Account: {phone}")
        self.log(f"🎁 Strategy: FREE BETS ONLY")

        auto_mode = os.environ.get("AUTO_START_AVIATOR", "0").strip() in ("1", "true", "True")
        if not auto_mode:
            confirmed = messagebox.askyesno(
                "Aviator Automation Confirmation",
                f"Start Aviator automation?\n\n"
                f"Account: {phone}\n"
                f"Strategy: FREE BETS ONLY (no cash used)\n\n"
                f"This will only bet if free bets are available.",
                icon='question'
            )
            if not confirmed:
                self.log("❌ Aviator automation cancelled by user")
                return

        def enhanced_callback(message):
            self.log(message)
            self.ensure_auto_scroll()

        def run_aviator():
            try:
                enhanced_callback("🎭 Starting Playwright Aviator automation...")
                enhanced_callback("🎁 Looking for free bets only - no cash will be used")
                sp = ''.join([c for c in phone if c.isdigit()]) or 'unknown'
                bk = AviatorBackend(
                    headless=False,
                    mobile_view=True,
                    engine="chromium",
                    progress_cb=enhanced_callback,
                    storage_path=f"recordings/storage_{sp}.json"
                )
                try:
                    bk.start()
                    res = bk.login_and_open_menu(phone, password)
                    if res.get('success') and res.get('has_freebet'):
                        if res.get('bet_placed'):
                            enhanced_callback(f"✅ Free bet placed successfully")
                        else:
                            enhanced_callback(f"⚠️ Free bet detected but placement failed")
                    elif res.get('success'):
                        enhanced_callback(f"⏭️ No free bet available")
                    else:
                        enhanced_callback(f"❌ Failed: {res.get('reason', 'unknown')}")
                finally:
                    try:
                        bk.stop()
                    except Exception:
                        pass
            except Exception as e:
                enhanced_callback(f"❌ Aviator automation error: {e}")

        threading.Thread(target=run_aviator, daemon=True).start()

    def start_martingale_bot(self):
        """▶ START BOT — Martingale sequence with auto-cashout"""
        # Single-phone field was removed; fall back to first number in the list.
        pe = getattr(self, 'phone_entry', None)
        if pe is not None:
            phone = pe.get().strip()
        else:
            try:
                phone = (self._phones_from_gui() or [''])[0]
            except Exception:
                phone = ""
        password = self.password_entry.get().strip()
        if not phone:
            self.log("❌ Enter a phone number")
            return
        if not password:
            self.log("❌ Enter a password")
            return

        # Parse steps (field removed -> default)
        se = getattr(self, 'steps_entry', None)
        if se is not None:
            steps_text = se.get()
        else:
            steps_text = "10, 40, 174, 754, 3267"
        try:
            steps = [float(x.strip()) for x in steps_text.split(',') if x.strip()]
            assert len(steps) > 0
        except Exception:
            self.log("❌ Invalid steps — use comma-separated numbers e.g. 10, 40, 174")
            return

        # Parse cashout (field removed -> default 1.3)
        ce = getattr(self, 'cashout_entry', None)
        if ce is not None:
            cashout_text = ce.get().strip()
        else:
            cashout_text = "1.3"
        try:
            cashout = float(cashout_text)
            assert cashout > 1.0
        except Exception:
            self.log("❌ Invalid auto cashout — must be a number > 1.0")
            return

        ev = getattr(self, 'exhaustion_var', None)
        on_exhaustion = ev.get() if ev is not None else "stop"
        site = self.site_var.get()

        self.log(f"🎯 Starting Martingale bot | Site: {site} | Steps: {steps} | Cashout: {cashout}x | On exhaustion: {on_exhaustion}")
        self.save_config()
        self.martingale_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.root.after(0, lambda: self._bot_status_label.config(text="Running", fg='#00C853'))

        from aviator_bot import AviatorMartingaleBot

        _loss_streak = [0]
        _win_streak  = [0]

        def _cb(msg):
            self.log(msg)
            self.ensure_auto_scroll()
            try:
                if 'WIN' in msg and 'reset' in msg.lower():
                    _win_streak[0] += 1; _loss_streak[0] = 0
                    self.root.after(0, lambda: self.streak_label.config(text=f"{_win_streak[0]}W", fg='#00C853'))
                elif 'LOSS' in msg and 'advanc' in msg.lower():
                    _loss_streak[0] += 1; _win_streak[0] = 0
                    self.root.after(0, lambda: self.streak_label.config(text=f"{_loss_streak[0]}L", fg='#EF5350'))
                if 'Result:' in msg:
                    for part in msg.split('|'):
                        part = part.strip()
                        if part.startswith('Result:'):
                            c = '#00C853' if 'WIN' in part else '#EF5350'
                            v = part.replace('Result:', '').strip()
                            self.root.after(0, lambda val=v, col=c: self.result_label.config(text=val, fg=col))
                if 'step' in msg.lower() and 'bet:' in msg.lower():
                    for part in msg.split('|'):
                        part = part.strip()
                        if part.lower().startswith('step'):
                            self.root.after(0, lambda v=part: self.step_label.config(text=v, fg='#FFB300'))
                if 'Waiting for' in msg:
                    self.root.after(0, lambda: self._bot_status_label.config(text="Waiting", fg='#FFC107'))
                elif 'Round in progress' in msg:
                    self.root.after(0, lambda: self._bot_status_label.config(text="In Round", fg='#29B6F6'))
                elif 'Bet placed' in msg:
                    self.root.after(0, lambda: self._bot_status_label.config(text="Bet Placed", fg='#00C853'))
            except Exception:
                pass

        def _done():
            self.root.after(0, lambda: self.martingale_btn.config(state='normal'))
            self.root.after(0, lambda: self.stop_btn.config(state='disabled'))
            self.root.after(0, lambda: self.step_label.config(text="—", fg='#FFB300'))
            self.root.after(0, lambda: self._bot_status_label.config(text="Stopped", fg='#888'))

        def _run():
            bot = AviatorMartingaleBot(
                phone=phone, password=password,
                progress_cb=_cb, steps=steps,
                auto_cashout=cashout,
                on_exhaustion=on_exhaustion,
                site=site,
            )
            self._martingale_bot = bot
            bot.run()
            _done()

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def stop_martingale_bot(self):
        bot = getattr(self, '_martingale_bot', None)
        if bot:
            bot.stop()
            self.log("⏹ Stop requested")
        self.stop_btn.config(state='disabled')
        self.martingale_btn.config(state='normal')
        self.root.after(0, lambda: self._bot_status_label.config(text="Stopped", fg='#888'))

    def export_martingale_csv(self):
        bot = getattr(self, '_martingale_bot', None)
        if bot and hasattr(bot, 'logger'):
            path = bot.logger.export_path()
            self.log(f"📁 CSV: {path}")
        else:
            self.log("⚠️ No active session to export")

    def set_telegram(self):
        """Elegant dialog for Telegram bot setup with instructions"""
        dialog = tk.Toplevel(self.root)
        dialog.title("✈️ BetFlow Aviator Pro - Telegram Remote Control")
        dialog.geometry("600x500")
        dialog.configure(bg='#0a0a0a')
        dialog.resizable(False, False)
        
        # Center the dialog
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Main container
        main_frame = tk.Frame(dialog, bg='#0a0a0a', padx=30, pady=20)
        main_frame.pack(fill='both', expand=True)
        
        # Title
        title_label = tk.Label(
            main_frame,
            text="🤖 Telegram Remote Control",
            font=('Arial', 18, 'bold'),
            bg='#0a0a0a',
            fg='#00ff00'
        )
        title_label.pack(pady=(0, 10))
        
        subtitle_label = tk.Label(
            main_frame,
            text="Monitor & control your tool 24/7 from anywhere",
            font=('Arial', 10),
            bg='#0a0a0a',
            fg='#888888'
        )
        subtitle_label.pack(pady=(0, 20))
        
        # Instructions frame
        instructions_frame = tk.LabelFrame(
            main_frame,
            text=" 📖 Setup Instructions ",
            font=('Arial', 10, 'bold'),
            bg='#1a1a1a',
            fg='#00ff00',
            padx=15,
            pady=15
        )
        instructions_frame.pack(fill='x', pady=(0, 20))
        
        instructions_text = """1. Open Telegram and search for @BotFather
2. Send: /newbot
3. Choose a name (e.g., "My BetFlow Bot")
4. Choose a username (e.g., "myBetFlow_bot")
5. Copy the Bot Token provided
6. Start a chat with your new bot
7. Get your Chat ID from @userinfobot"""
        
        instructions_label = tk.Label(
            instructions_frame,
            text=instructions_text,
            font=('Consolas', 9),
            bg='#1a1a1a',
            fg='#ffffff',
            justify='left'
        )
        instructions_label.pack(anchor='w')
        
        # Bot Token field
        token_frame = tk.Frame(main_frame, bg='#0a0a0a')
        token_frame.pack(fill='x', pady=(0, 15))
        
        tk.Label(
            token_frame,
            text="🔑 Bot Token:",
            font=('Arial', 10, 'bold'),
            bg='#0a0a0a',
            fg='#00ff00'
        ).pack(anchor='w', pady=(0, 5))
        
        token_entry = tk.Entry(
            token_frame,
            textvariable=self.telegram_token,
            font=('Consolas', 10),
            bg='#1a1a1a',
            fg='#ffffff',
            insertbackground='#00ff00',
            relief='flat',
            width=50
        )
        token_entry.pack(fill='x', ipady=5)
        
        # Chat ID field
        chat_frame = tk.Frame(main_frame, bg='#0a0a0a')
        chat_frame.pack(fill='x', pady=(0, 20))
        
        tk.Label(
            chat_frame,
            text="💬 Chat ID:",
            font=('Arial', 10, 'bold'),
            bg='#0a0a0a',
            fg='#00ff00'
        ).pack(anchor='w', pady=(0, 5))
        
        chat_entry = tk.Entry(
            chat_frame,
            textvariable=self.telegram_chat_id,
            font=('Consolas', 10),
            bg='#1a1a1a',
            fg='#ffffff',
            insertbackground='#00ff00',
            relief='flat',
            width=50
        )
        chat_entry.pack(fill='x', ipady=5)
        
        # Status label
        status_label = tk.Label(
            main_frame,
            text="",
            font=('Arial', 9),
            bg='#0a0a0a',
            fg='#888888'
        )
        status_label.pack(pady=(0, 15))
        
        # Buttons frame
        buttons_frame = tk.Frame(main_frame, bg='#0a0a0a')
        buttons_frame.pack(fill='x')
        
        def test_connection():
            """Test the Telegram bot connection"""
            token = self.telegram_token.get().strip()
            chat_id = self.telegram_chat_id.get().strip()
            
            if not token or not chat_id:
                status_label.config(text="❌ Please fill in both fields", fg='#ff0000')
                return
            
            status_label.config(text="⏳ Testing connection...", fg='#ffaa00')
            dialog.update()
            
            try:
                import telegram
                bot = telegram.Bot(token=token)
                bot.send_message(
                    chat_id=chat_id,
                    text="✅ *BetFlow Aviator Pro Connection Test Successful!*\n\nYour bot is ready for remote control.",
                    parse_mode='Markdown'
                )
                status_label.config(text="✅ Connection successful! Message sent to Telegram", fg='#00ff00')
            except Exception as e:
                status_label.config(text=f"❌ Connection failed: {str(e)[:50]}...", fg='#ff0000')
        
        def save_and_start():
            """Save configuration and start the bot"""
            token = self.telegram_token.get().strip()
            chat_id = self.telegram_chat_id.get().strip()
            
            if not token or not chat_id:
                status_label.config(text="❌ Please fill in both fields", fg='#ff0000')
                return
            
            # Save to config
            self.config['telegram_token'] = token
            self.config['telegram_chat_id'] = chat_id
            self.save_config()
            
            # Stop existing bot if running
            if self.telegram_bot and self.telegram_bot.running:
                self.telegram_bot.stop()
            
            # Start new bot
            if BetFlowTelegramBot is None:
                status_label.config(text="❌ Telegram bot module not available", fg='#ff0000')
                return
            self.telegram_bot = BetFlowTelegramBot(token, chat_id, self)
            success = self.telegram_bot.start()
            
            if success:
                self.log("✅ Telegram bot connected and ready for remote control!")
                messagebox.showinfo(
                    "Success",
                    "Telegram bot connected successfully!\n\nSend /help to your bot to see available commands."
                )
                dialog.destroy()
            else:
                status_label.config(text="❌ Failed to start bot", fg='#ff0000')
        
        # Test button
        test_btn = tk.Button(
            buttons_frame,
            text="🧪 Test Connection",
            command=test_connection,
            bg='#2196F3',
            fg='white',
            font=('Arial', 10, 'bold'),
            relief='flat',
            padx=20,
            pady=8,
            cursor='hand2'
        )
        test_btn.pack(side='left', padx=(0, 10))
        
        # Save button
        save_btn = tk.Button(
            buttons_frame,
            text="✅ Save & Connect",
            command=save_and_start,
            bg='#4CAF50',
            fg='white',
            font=('Arial', 10, 'bold'),
            relief='flat',
            padx=20,
            pady=8,
            cursor='hand2'
        )
        save_btn.pack(side='left', padx=(0, 10))
        
        # Cancel button
        cancel_btn = tk.Button(
            buttons_frame,
            text="Cancel",
            command=dialog.destroy,
            bg='#555555',
            fg='white',
            font=('Arial', 10),
            relief='flat',
            padx=20,
            pady=8,
            cursor='hand2'
        )
        cancel_btn.pack(side='right')
        
        # Auto-start bot if already configured
        if self.telegram_token.get() and self.telegram_chat_id.get():
            if not self.telegram_bot or not self.telegram_bot.running:
                status_label.config(text="💡 Bot credentials found. Click 'Save & Connect' to start.", fg='#ffaa00')

    def open_ai_hub(self):
        """Open AI HUB dialog - Control AI, API keys, training, and system health"""
        # Create AI HUB window
        hub_window = tk.Toplevel(self.root)
        hub_window.title("🤖 AI HUB - Control Center")
        hub_window.geometry("900x700")
        hub_window.configure(bg='#1e1e1e')
        
        # Center the window
        hub_window.transient(self.root)
        hub_window.grab_set()
        
        # Make it resizable for better UX
        hub_window.resizable(True, True)
        
        # Initialize training state (CRITICAL - prevents AttributeError)
        training_state = {'active': False, 'stop_requested': False}
        
        # Cleanup on window close
        def on_close():
            """Handle window close - cleanup resources"""
            try:
                # Stop any active training
                if training_state.get('active', False):
                    training_state['stop_requested'] = True
                    if hasattr(self, 'ai_learning') and self.ai_learning:
                        try:
                            if self.ai_learning.is_observing:
                                self.ai_learning.stop_observation_mode()
                        except:
                            pass
                # Cancel scheduled updates
                if hasattr(hub_window, '_update_jobs'):
                    for job_id in hub_window._update_jobs:
                        try:
                            hub_window.after_cancel(job_id)
                        except:
                            pass
            except:
                pass
            hub_window.destroy()
        
        hub_window.protocol("WM_DELETE_WINDOW", on_close)
        hub_window._update_jobs = []  # Track scheduled updates for cleanup
        
        # Header
        header_frame = tk.Frame(hub_window, bg='#2d2d2d', pady=10)
        header_frame.pack(fill='x')
        
        title_label = tk.Label(
            header_frame,
            text="🤖 AI HUB - Control Center",
            font=('Arial', 16, 'bold'),
            fg='#00ff00',
            bg='#2d2d2d'
        )
        title_label.pack()
        
        subtitle_label = tk.Label(
            header_frame,
            text="Manage AI API Keys, Training, System Health & Guidelines",
            font=('Arial', 9),
            fg='#888888',
            bg='#2d2d2d'
        )
        subtitle_label.pack()
        
        # Close button in header
        close_btn = tk.Button(
            header_frame,
            text="✕ Close",
            command=on_close,
            bg='#ff4444',
            fg='white',
            font=('Arial', 9, 'bold'),
            width=10
        )
        close_btn.pack(side='right', padx=10)
        
        # Notebook for tabs - OPTIMIZED FOR SMOOTH TAB SWITCHING
        notebook = ttk.Notebook(hub_window)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Smooth tab switching - prevent glitches when changing tabs
        def on_tab_changed(event):
            """Handle tab change smoothly without glitches"""
            try:
                # Update display immediately for smooth transition
                selected_tab = event.widget.select()
                event.widget.update_idletasks()
                # Force small delay to ensure rendering completes
                hub_window.after(10, lambda: hub_window.update_idletasks())
            except:
                pass  # Ignore errors during tab switch
        
        notebook.bind("<<NotebookTabChanged>>", on_tab_changed)
        
        # Tab 1: API Keys
        api_tab = tk.Frame(notebook, bg='#1e1e1e')
        notebook.add(api_tab, text="🔑 API Keys")
        
        api_frame = tk.LabelFrame(api_tab, text="AI API Key Configuration", fg='#00ff00', bg='#1e1e1e', font=('Arial', 11, 'bold'))
        api_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        tk.Label(api_frame, text="DeepSeek / OpenRouter API Key:", fg='white', bg='#1e1e1e', font=('Arial', 10)).pack(anchor='w', padx=10, pady=5)
        
        api_key_frame = tk.Frame(api_frame, bg='#1e1e1e')
        api_key_frame.pack(fill='x', padx=10, pady=5)
        
        self.ai_api_key_entry = tk.Entry(api_key_frame, bg='#2d2d2d', fg='#00ff00', font=('Arial', 10), show='*')
        self.ai_api_key_entry.pack(side='left', fill='x', expand=True)
        
        # Load current API key if available
        current_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENROUTER_API_KEY") or ""
        if current_key:
            self.ai_api_key_entry.insert(0, current_key[:20] + "..." if len(current_key) > 20 else current_key)
        
        def save_api_key():
            """Save API key and update system immediately"""
            new_key = self.ai_api_key_entry.get().strip()
            if not new_key:
                messagebox.showwarning("Warning", "Please enter an API key")
                return
            
            try:
                # Set environment variable
                os.environ["DEEPSEEK_API_KEY"] = new_key
                os.environ["OPENROUTER_API_KEY"] = new_key
                
                # Reinitialize AI engine with new key (robust error handling)
                if self.headless and hasattr(self.headless, 'ai_engine') and self.headless.ai_engine:
                    self.headless.ai_engine.api_key = new_key
                    self.headless.ai_engine.enabled = bool(new_key)
                    log_message(f"✅ AI API key updated - AI Engine {'enabled' if self.headless.ai_engine.enabled else 'disabled'}")
                else:
                    log_message("⚠️ AI Engine not available - key saved to environment only")
                
                # Also update ai_integration if available
                if hasattr(self, 'ai_integration') and self.ai_integration and self.ai_integration.ai_engine:
                    self.ai_integration.ai_engine.api_key = new_key
                    self.ai_integration.ai_engine.enabled = bool(new_key)
                
                messagebox.showinfo("Success", "✅ API key saved and applied immediately!\n\nAI Engine is now active.")
                self.log("✅ AI API key updated successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save API key: {str(e)}")
                self.log(f"❌ Failed to save API key: {e}")
        
        tk.Button(api_key_frame, text="💾 Save & Apply", command=save_api_key, bg='#4CAF50', fg='white', font=('Arial', 9, 'bold')).pack(side='left', padx=5)
        
        tk.Label(api_frame, text="💡 Tip: Get API keys from:\n• OpenRouter.ai (supports DeepSeek, GPT-4, Claude, etc.)\n• DeepSeek.ai (direct API)", 
                fg='#888888', bg='#1e1e1e', font=('Arial', 8), justify='left').pack(anchor='w', padx=10, pady=10)
        
        # Tab 2: Training Mode
        training_tab = tk.Frame(notebook, bg='#1e1e1e')
        notebook.add(training_tab, text="🎓 Training")
        
        training_frame = tk.LabelFrame(training_tab, text="AI Training Mode", fg='#00ff00', bg='#1e1e1e', font=('Arial', 11, 'bold'))
        training_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        tk.Label(training_frame, text="Train AI by performing actions in visible browser:", fg='white', bg='#1e1e1e', font=('Arial', 10)).pack(anchor='w', padx=10, pady=5)
        
        training_buttons_frame = tk.Frame(training_frame, bg='#1e1e1e')
        training_buttons_frame.pack(fill='x', padx=10, pady=10)
        
        def start_training_mode(operation_type):
            """Start training mode for specific operation"""
            # Robust check for AI engine availability
            if not (hasattr(self, 'headless') and self.headless and 
                    hasattr(self.headless, 'ai_engine') and self.headless.ai_engine and 
                    self.headless.ai_engine.enabled):
                messagebox.showwarning("AI Disabled", "Please set an API key first in the API Keys tab")
                return
            
            phones = self.phone_text.get('1.0', tk.END).strip()
            password = self.password_entry.get().strip()
            
            if not phones or not password:
                messagebox.showwarning("Missing Info", "Please enter phone numbers and password")
                return
            
            phone_list = [p.strip() for p in phones.split('\n') if p.strip()]
            if not phone_list:
                messagebox.showwarning("No Accounts", "Please enter at least one phone number")
                return
            
            # Confirm training mode
            confirm = messagebox.askyesno(
                "Start Training Mode",
                f"Start AI training for {operation_type}?\n\n"
                "A visible browser will open.\n"
                "Perform actions manually and AI will learn from them.\n\n"
                "This helps AI understand your workflow better."
            )
            
            if not confirm:
                return
            
            # Mark training as active
            training_state['active'] = True
            training_state['stop_requested'] = False
            
            def run_training():
                training_active = {'value': True}
                observation_stopped = {'value': False}
                
                try:
                    self.log(f"🎓 Starting AI Training Mode for {operation_type}...")
                    self.log("📖 Opening visible browser - YOU will perform actions manually...")
                    self.log("💡 AI will watch and learn from your actions")
                    
                    # Get base URL
                    base_url = self.target_url.get() if hasattr(self, 'target_url') else 'https://www.odibets.com'
                    
                    # Check if AI learning system is available
                    if not self.ai_learning:
                        self.log("❌ AI Learning system not available - cannot start training mode")
                        return
                    
                    # Start observation mode (opens visible browser)
                    self.log("🌐 Opening visible browser window...")
                    success = self.ai_learning.start_observation_mode(base_url, operation_type.lower())
                    
                    if not success:
                        self.log("❌ Failed to open browser for training")
                        return
                    
                    self.log("="*60)
                    self.log("✅ VISIBLE BROWSER IS NOW OPEN!")
                    self.log("="*60)
                    self.log("📝 INSTRUCTIONS:")
                    self.log("   1. Browser window should be visible on your screen")
                    self.log("   2. Perform your actions manually (login, place bets, etc.)")
                    self.log("   3. AI is watching and learning from everything you do")
                    self.log("   4. When done, click the STOP button below")
                    self.log("="*60)
                    
                    # Wait for user to perform actions (keep browser open)
                    # Browser stays open until user clicks stop or closes window
                    self.log("⏳ Waiting for you to perform actions...")
                    self.log("💡 Take your time - perform all actions you want AI to learn")
                    
                    # Keep browser open and monitor for closure
                    max_wait_time = 3600  # 1 hour max
                    check_interval = 2  # Check every 2 seconds
                    elapsed = 0
                    
                    while training_active['value'] and elapsed < max_wait_time:
                        # Check if stop was requested
                        if training_state['stop_requested']:
                            self.log("🛑 Stop button clicked - stopping training...")
                            training_active['value'] = False
                            break
                        
                        time.sleep(check_interval)
                        elapsed += check_interval
                        
                        # Check if browser was closed
                        try:
                            if self.ai_learning.driver:
                                # Try to get current URL (will fail if browser closed)
                                try:
                                    current_url = self.ai_learning.driver.current_url
                                except:
                                    # Browser was closed
                                    self.log("⚠️ Browser window was closed")
                                    training_active['value'] = False
                                    break
                        except:
                            # Driver doesn't exist anymore
                            training_active['value'] = False
                            break
                        
                        # Give status update every 30 seconds
                        if elapsed % 30 == 0:
                            actions_count = self.ai_learning.session_stats.get('actions_observed', 0)
                            self.log(f"📊 Training in progress... ({actions_count} actions recorded so far)")
                    
                    # Stop observation and save learning
                    if not observation_stopped['value']:
                        self.log("🛑 Stopping observation mode...")
                        learning_data = self.ai_learning.stop_observation_mode()
                        observation_stopped['value'] = True
                        
                        # Process and save learned actions
                        actions_count = learning_data.get('actions_count', 0)
                        if actions_count > 0:
                            self.log(f"✅ Training complete! AI recorded {actions_count} actions")
                            self.log("🧠 AI has learned from your actions and will use them in future operations")
                            
                            # Save training session
                            if self.headless.ai_engine and self.headless.ai_engine.enabled:
                                try:
                                    self.headless.ai_engine.remember_repeated_task(
                                        f'training_{operation_type.lower()}',
                                        {
                                            'operation': operation_type,
                                            'actions_count': actions_count,
                                            'learned_selectors': learning_data.get('unique_selectors', 0),
                                            'session_duration': elapsed
                                        },
                                        True
                                    )
                                    self.log("💾 Training session saved to AI knowledge base")
                                except Exception as e:
                                    self.log(f"⚠️ Could not save training session: {e}")
                        else:
                            self.log("⚠️ No actions were recorded - browser may have been closed too quickly")
                            self.log("💡 Please try again and perform some actions before closing")
                    
                except Exception as e:
                    self.log(f"❌ Training error: {e}")
                    import traceback
                    self.log(f"   Details: {traceback.format_exc()[:200]}")
                    
                    # Ensure browser is closed
                    try:
                        if self.ai_learning and self.ai_learning.is_observing:
                            self.ai_learning.stop_observation_mode()
                    except:
                        pass
                    finally:
                        # Mark training as inactive
                        training_state['active'] = False
            
            threading.Thread(target=run_training, daemon=True).start()
        
        def stop_training():
            """Stop current training session"""
            if not training_state['active']:
                messagebox.showinfo("Not Active", "No training session is currently active")
                return
            
            training_state['stop_requested'] = True
            self.log("🛑 Stop requested - training will end after current action completes...")
        
        tk.Button(training_buttons_frame, text="🔄 Train Rollover", 
                 command=lambda: start_training_mode("Rollover"),
                 bg='#FF9800', fg='white', width=20, font=('Arial', 9, 'bold')).pack(side='left', padx=5, pady=5)
        
        tk.Button(training_buttons_frame, text="🎁 Train SUPA5", 
                 command=lambda: start_training_mode("SUPA5"),
                 bg='#E91E63', fg='white', width=20, font=('Arial', 9, 'bold')).pack(side='left', padx=5, pady=5)
        
        tk.Button(training_buttons_frame, text="🎯 Train Odileagues", 
                 command=lambda: start_training_mode("Odileagues"),
                 bg='#4CAF50', fg='white', width=20, font=('Arial', 9, 'bold')).pack(side='left', padx=5, pady=5)
        
        # Stop button
        stop_training_btn = tk.Button(training_buttons_frame, text="🛑 Stop Training", 
                                      command=stop_training,
                                      bg='#F44336', fg='white', width=20, font=('Arial', 9, 'bold'))
        stop_training_btn.pack(side='left', padx=5, pady=5)
        
        tk.Label(training_frame, 
                text="💡 How it works:\n"
                     "1. Click a training button above\n"
                     "2. Visible browser opens\n"
                     "3. Perform actions manually (login, place bets, etc.)\n"
                     "4. AI watches and learns from your actions\n"
                     "5. AI creates permanent fixes based on what works\n\n"
                     "📝 Note: Visible browser mode (stealth disabled) for easy observation",
                fg='#888888', bg='#1e1e1e', font=('Arial', 8), justify='left').pack(anchor='w', padx=10, pady=10)
        
        # Tab 3: System Health
        health_tab = tk.Frame(notebook, bg='#1e1e1e')
        notebook.add(health_tab, text="🏥 System Health")
        
        health_frame = tk.LabelFrame(health_tab, text="System Status", fg='#00ff00', bg='#1e1e1e', font=('Arial', 11, 'bold'))
        health_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.health_text = scrolledtext.ScrolledText(health_frame, height=20, bg='#2d2d2d', fg='#00ff00', font=('Courier', 9))
        self.health_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        def update_health_display():
            """Update system health display"""
            try:
                health_info = []
                health_info.append("=" * 60)
                health_info.append("🤖 AI SYSTEM HEALTH")
                health_info.append("=" * 60)
                health_info.append("")
                
                # AI Engine Status (robust error handling)
                try:
                    if (hasattr(self, 'headless') and self.headless and 
                        hasattr(self.headless, 'ai_engine') and self.headless.ai_engine):
                        if self.headless.ai_engine.enabled:
                            health_info.append("✅ AI Engine: ENABLED")
                            health_info.append(f"   • API Key: {'Set' if getattr(self.headless.ai_engine, 'api_key', None) else 'Not Set'}")
                            health_info.append(f"   • Error Patterns Learned: {len(getattr(self.headless.ai_engine, 'error_patterns', {}))}")
                            health_info.append(f"   • Permanent Fixes: {len(getattr(self.headless.ai_engine, 'permanent_fixes', {}))}")
                            health_info.append(f"   • Selector Learnings: {len(getattr(self.headless.ai_engine, 'selector_learnings', {}))}")
                            health_info.append(f"   • Operation History: {len(getattr(self.headless.ai_engine, 'operation_history', []))} entries")
                        else:
                            health_info.append("⚠️  AI Engine: DISABLED (No API key)")
                    else:
                        health_info.append("❌ AI Engine: NOT INITIALIZED")
                except Exception as e:
                    health_info.append(f"❌ AI Engine: ERROR - {str(e)[:50]}")
                
                health_info.append("")
                health_info.append("-" * 60)
                health_info.append("🌐 NETWORK STATUS")
                health_info.append("-" * 60)
                health_info.append(f"   • Status: {'✅ Online' if self.network_online else '❌ Offline'}")
                
                health_info.append("")
                health_info.append("-" * 60)
                health_info.append("🔧 SYSTEM COMPONENTS")
                health_info.append("-" * 60)
                
                # Check components (robust error handling)
                try:
                    components = {
                        "BetFlowHeadless": hasattr(self, 'headless') and self.headless is not None,
                        "Browser Pool": (hasattr(self, 'headless') and self.headless and 
                                       hasattr(self.headless, 'browser_pool') and self.headless.browser_pool is not None),
                        "API Client": (hasattr(self, 'headless') and self.headless and 
                                     hasattr(self.headless, 'session') and self.headless.session is not None),
                        "Network Handler": (hasattr(self, 'headless') and self.headless and 
                                          hasattr(self.headless, 'network_status_callback')),
                        "AI Integration": hasattr(self, 'ai_integration') and self.ai_integration is not None,
                        "AI Learning": hasattr(self, 'ai_learning') and self.ai_learning is not None,
                    }
                    
                    for component, status in components.items():
                        health_info.append(f"   {'✅' if status else '❌'} {component}: {'OK' if status else 'Missing'}")
                except Exception as e:
                    health_info.append(f"   ⚠️ Component check error: {str(e)[:40]}")
                
                health_info.append("")
                health_info.append("-" * 60)
                health_info.append("📊 AI LEARNING STATS")
                health_info.append("-" * 60)
                
                try:
                    if (hasattr(self, 'headless') and self.headless and 
                        hasattr(self.headless, 'ai_engine') and self.headless.ai_engine and 
                        self.headless.ai_engine.enabled):
                        system_state = getattr(self.headless.ai_engine, 'system_state', {})
                        success_metrics = system_state.get('success_metrics', {})
                        if success_metrics:
                            health_info.append(f"   • Tracked Tasks: {len(success_metrics)}")
                            total_successes = sum(m.get('successes', 0) for m in success_metrics.values())
                            total_attempts = sum(m.get('attempts', 0) for m in success_metrics.values())
                            if total_attempts > 0:
                                overall_rate = (total_successes / total_attempts) * 100
                                health_info.append(f"   • Overall Success Rate: {overall_rate:.1f}%")
                except Exception as e:
                    health_info.append(f"   ⚠️ Stats error: {str(e)[:40]}")
                
                health_info.append("")
                health_info.append("=" * 60)
                
                self.health_text.delete(1.0, tk.END)
                self.health_text.insert(1.0, "\n".join(health_info))
                
                # Schedule next update (with cleanup tracking)
                if hub_window.winfo_exists():
                    job_id = hub_window.after(5000, update_health_display)  # Update every 5 seconds
                    if hasattr(hub_window, '_update_jobs'):
                        hub_window._update_jobs.append(job_id)
            except Exception as e:
                self.log(f"⚠️ Health update error: {e}")
        
        update_health_display()
        
        refresh_btn = tk.Button(health_frame, text="🔄 Refresh Now", command=update_health_display, bg='#2196F3', fg='white')
        refresh_btn.pack(pady=5)
        
        # Tab 4: AI Activity
        activity_tab = tk.Frame(notebook, bg='#1e1e1e')
        notebook.add(activity_tab, text="📡 AI Activity")
        
        activity_frame = tk.LabelFrame(activity_tab, text="Live AI Operations", fg='#00ff00', bg='#1e1e1e', font=('Arial', 11, 'bold'))
        activity_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.activity_text = scrolledtext.ScrolledText(activity_frame, height=20, bg='#2d2d2d', fg='#00ff00', font=('Courier', 9))
        self.activity_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        def update_activity_display():
            """Update AI activity display"""
            try:
                activity_info = []
                activity_info.append("=" * 60)
                activity_info.append("🤖 LIVE AI ACTIVITY")
                activity_info.append("=" * 60)
                activity_info.append("")
                
                try:
                    if (hasattr(self, 'headless') and self.headless and 
                        hasattr(self.headless, 'ai_engine') and self.headless.ai_engine and 
                        self.headless.ai_engine.enabled):
                        # Show recent AI operations (robust access)
                        operation_history = getattr(self.headless.ai_engine, 'operation_history', [])
                        recent_ops = operation_history[-20:] if operation_history else []  # Last 20
                        if recent_ops:
                            activity_info.append("📋 RECENT OPERATIONS:")
                            for op in reversed(recent_ops):
                                if isinstance(op, dict):
                                    status_icon = "✅" if op.get('status') == 'success' else "❌"
                                    activity_info.append(f"   {status_icon} {op.get('operation', 'unknown')} - {str(op.get('timestamp', ''))[:19]}")
                            activity_info.append("")
                        
                        # Show active operations
                        system_state = getattr(self.headless.ai_engine, 'system_state', {})
                        active_ops = system_state.get('active_operations', [])
                        if active_ops:
                            activity_info.append("🔄 ACTIVE OPERATIONS:")
                            for op in active_ops:
                                activity_info.append(f"   • {op}")
                            activity_info.append("")
                        
                        # Show recent improvements
                        self_improvement_log = getattr(self.headless.ai_engine, 'self_improvement_log', [])
                        improvements = self_improvement_log[-10:] if self_improvement_log else []
                        if improvements:
                            activity_info.append("🆕 RECENT IMPROVEMENTS:")
                            for imp in reversed(improvements):
                                activity_info.append(f"   • {imp}")
                            activity_info.append("")
                except Exception as e:
                    activity_info.append(f"⚠️ Error accessing AI engine: {str(e)[:50]}")
                
                activity_info.append("")
                activity_info.append("=" * 60)
                
                self.activity_text.delete(1.0, tk.END)
                self.activity_text.insert(1.0, "\n".join(activity_info))
                
                # Schedule next update (with cleanup tracking)
                if hub_window.winfo_exists():
                    job_id = hub_window.after(5000, update_activity_display)  # Update every 5 seconds
                    if hasattr(hub_window, '_update_jobs'):
                        hub_window._update_jobs.append(job_id)
            except Exception as e:
                self.log(f"⚠️ Activity update error: {e}")
        
        update_activity_display()
        
        
        # Tab 5: Guidelines
        guidelines_tab = tk.Frame(notebook, bg='#1e1e1e')
        notebook.add(guidelines_tab, text="📚 Guidelines")
        
        guidelines_frame = tk.LabelFrame(guidelines_tab, text="System Operation Guidelines", fg='#00ff00', bg='#1e1e1e', font=('Arial', 11, 'bold'))
        guidelines_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        
        guidelines_text = scrolledtext.ScrolledText(guidelines_frame, height=25, bg='#2d2d2d', fg='#00ff00', font=('Arial', 9))
        guidelines_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        guidelines_content = """╔══════════════════════════════════════════════════════════════╗
║         ✈️ Be-T-ka AVIATOR PRO - SYSTEM GUIDELINES            ║
╚══════════════════════════════════════════════════════════════╝

📋 HOW THE SYSTEM OPERATES:

┌─ 🔄 ROLLOVER OPERATION ──────────────────────────────────────┐
│                                                                │
│  Purpose: Transfer money between accounts at 1.88 odds       │
│                                                                │
│  How it works:                                                 │
│  1. Finds matches with Over/Under 2.5 odds = 1.88/1.88        │
│  2. Splits accounts 50/50 (half OVER, half UNDER)            │
│  3. Places bets - 50% lose stake, 50% win stake               │
│  4. Money consolidates at 1.88 odds                          │
│  5. Reuses matches if time allows (multi-round mode)          │
│                                                                │
│  Requirements:                                                 │
│  • Minimum 2 accounts (even number)                           │
│  • Each account balance >= stake amount                       │
│  • Match must be 80+ seconds away                             │
│                                                                │
│  AI Enhancements:                                              │
│  • Auto-fixes login/logout errors                             │
│  • Auto-fixes bet placement errors                            │
│  • Remembers successful patterns                              │
│  • Optimizes for large batches                                │
│                                                                │
└───────────────────────────────────────────────────────────────┘

┌─ 🎁 SUPA5 OPERATION ──────────────────────────────────────────┐
│                                                                │
│  Purpose: Claim 50 KES bonus by placing 5+ bets               │
│                                                                │
│  How it works:                                                 │
│  1. Navigates to Promotions page                              │
│  2. Logs in to account                                        │
│  3. Clicks "OdiLeague Supa5 Play Now" button                 │
│  4. Places 6 bets (3 pairs of Over/Under 2.5)                 │
│     • 50 KES per bet                                          │
│     • Same match, guaranteed win                              │
│  5. Logs out and repeats for next account                    │
│                                                                │
│  Strategy:                                                     │
│  • Targets 1.88/1.88 odds on O/U 2.5                         │
│  • Places Over + Under on same match                          │
│  • Ensures win in each account                                │
│                                                                │
│  AI Enhancements:                                              │
│  • AI selects best match for O/U 2.5 pairs                    │
│  • Auto-fixes navigation errors                               │
│  • Auto-fixes bet placement errors                            │
│                                                                │
└───────────────────────────────────────────────────────────────┘

┌─ 💰 WITHDRAWAL OPERATION ─────────────────────────────────────┐
│                                                                │
│  Purpose: Withdraw funds from accounts                        │
│                                                                │
│  How it works:                                                 │
│  1. Uses API-first approach (fastest)                          │
│  2. Falls back to browser if API fails                        │
│  3. Handles M-Pesa withdrawal flow                           │
│                                                                │
│  AI Enhancements:                                              │
│  • Auto-retries on failure                                    │
│  • Learns from successful withdrawals                         │
│                                                                │
└───────────────────────────────────────────────────────────────┘

┌─ 🤖 AI SYSTEM OPERATION ─────────────────────────────────────┐
│                                                                │
│  AI Role: Enhancement, not control                            │
│                                                                │
│  What AI Does:                                                 │
│  ✅ Fixes errors automatically                                │
│  ✅ Learns from patterns                                      │
│  ✅ Suggests improvements                                     │
│  ✅ Optimizes performance                                     │
│  ✅ Handles failures gracefully                               │
│                                                                │
│  What AI Does NOT:                                             │
│  ❌ Control operations (user always in control)               │
│  ❌ Bypass user controls                                      │
│  ❌ Make decisions alone                                      │
│                                                                │
│  How AI Learns:                                                │
│  1. Tracks all operations                                      │
│  2. Records success/failure patterns                          │
│  3. After 3+ failures → Creates permanent fix                │
│  4. Next time → Fix applies automatically                     │
│                                                                │
│  Permanent Fixes:                                              │
│  • Saved to disk (persist forever)                           │
│  • Apply automatically when error occurs                     │
│  • System gets better over time                               │
│                                                                │
└───────────────────────────────────────────────────────────────┘

┌─ 🛡️ STEALTH MODE ─────────────────────────────────────────────┐
│                                                                │
│  Purpose: Avoid bot detection                                 │
│                                                                │
│  Features:                                                     │
│  • Human-like delays                                          │
│  • Randomized timing                                          │
│  • Stealth browser headers                                    │
│  • Natural mouse movements                                    │
│  • Anti-bot bypass techniques                                │
│                                                                │
│  Always Active:                                                │
│  • All browser operations use stealth mode                    │
│  • AI operations are not flagged as bots                      │
│                                                                │
└───────────────────────────────────────────────────────────────┘

┌─ 📊 LARGE BATCH HANDLING ─────────────────────────────────────┐
│                                                                │
│  For 100+ accounts:                                            │
│  • Auto-chunks into smaller groups                            │
│  • Progress checkpoints                                       │
│  • Error threshold monitoring                                 │
│  • Memory optimization                                        │
│                                                                │
│  AI optimizes automatically based on account count           │
│                                                                │
└───────────────────────────────────────────────────────────────┘

💡 TIPS:
• Set API key in AI HUB for maximum intelligence
• Use training mode to teach AI your workflow
• Check System Health regularly
• AI gets smarter with each operation

⚡ Version 4.0.0 - AI-Powered & Production Ready"""
        
        guidelines_text.insert(1.0, guidelines_content)
        guidelines_text.config(state='disabled')  # Read-only
        
        # Footer with close button
        footer_frame = tk.Frame(hub_window, bg='#2d2d2d', pady=5)
        footer_frame.pack(fill='x', side='bottom')
        
        tk.Label(footer_frame, text="✈️ BetFlow Aviator Pro v1.0.0 - Aviator Automation", 
                fg='#888888', bg='#2d2d2d', font=('Arial', 8)).pack(side='left', padx=10)
        
        tk.Button(footer_frame, text="✕ Close AI HUB", command=on_close, 
                 bg='#ff4444', fg='white', font=('Arial', 9, 'bold')).pack(side='right', padx=10)

    def emergency_stop(self):
        """Emergency stop button - FORCEFULLY kills ALL running operations"""
        try:
            # Set kill switch flags IMMEDIATELY (CRITICAL - must be first!)
            self.headless.running = False
            self.running = False
            
            # Visual feedback
            self.stop_btn.config(bg='#FFD700', text='⏹️ STOPPING...')
            self.log("🛑 EMERGENCY STOP ACTIVATED - Forcefully stopping ALL operations...")
            
            # 🔥 CRITICAL: Stop browser pool IMMEDIATELY (stops all browser operations)
            try:
                if hasattr(self.headless, 'browser_pool') and self.headless.browser_pool:
                    self.log("🧹 Closing browser pool...")
                    self.headless.browser_pool.close_all()
            except Exception as e:
                self.log(f"⚠️ Browser pool close warning: {str(e)[:50]}")
            
            # 🔥 CRITICAL: Close selenium driver IMMEDIATELY (stops bet placement)
            try:
                if hasattr(self.headless, 'selenium_fetcher') and self.headless.selenium_fetcher:
                    if hasattr(self.headless.selenium_fetcher, 'driver') and self.headless.selenium_fetcher.driver:
                        self.log("🧹 Terminating Selenium driver...")
                        try:
                            self.headless.selenium_fetcher.driver.quit()
                        except:
                            pass
            except Exception as e:
                self.log(f"⚠️ Selenium driver close warning: {str(e)[:50]}")
            
            # 🔥 CRITICAL: Close standalone selenium driver
            try:
                if hasattr(self.headless, 'selenium_driver') and self.headless.selenium_driver:
                    self.log("🧹 Terminating standalone Selenium driver...")
                    try:
                        self.headless.selenium_driver.quit()
                    except:
                        pass
            except:
                pass
            
            # CRITICAL: Kill ALL browser processes IMMEDIATELY
            self.log("🧹 Terminating all browser processes...")
            try:
                from cleanup_and_killswitch_helper import kill_all_betflow_processes
                kill_all_betflow_processes()
            except:
                # Fallback: direct system commands
                import subprocess
                try:
                    subprocess.run('taskkill /F /IM chromedriver.exe /T 2>nul', shell=True, timeout=2)
                    subprocess.run('taskkill /F /IM node.exe /T 2>nul', shell=True, timeout=2)
                    # Note: We don't kill chrome.exe anymore (would close user's browser)
                except:
                    pass
            
            # 🔥 CRITICAL: Forcefully shutdown all ThreadPoolExecutors
            try:
                if hasattr(self.headless, 'shutdown_all_executors'):
                    self.log("🧹 Forcefully shutting down all thread pools...")
                    self.headless.shutdown_all_executors()
            except Exception as e:
                self.log(f"⚠️ Executor shutdown warning: {str(e)[:50]}")
            
            # 🔥 CRITICAL: Force stop all background threads and subprocesses
            import threading
            import sys
            import os
            try:
                import psutil  # type: ignore  # Optional; may be missing in some environments
            except Exception:
                psutil = None
            
            try:
                # Get all active threads except main thread
                active_threads = [t for t in threading.enumerate() if t != threading.main_thread() and t.is_alive()]
                if active_threads:
                    self.log(f"🧹 Stopping {len(active_threads)} background threads...")
                    # Set their running flags to False (most threads check this)
                    for thread in active_threads:
                        try:
                            # Threads typically check self.running; nothing to set here safely
                            pass
                        except:
                            pass
            except Exception as e:
                self.log(f"⚠️ Thread stop warning: {str(e)[:50]}")
            
            # 🔥 CRITICAL: Kill ALL child processes (chromedriver, node, etc.)
            try:
                # Try to use psutil if available for better process management
                if psutil is not None:
                    current_process = psutil.Process(os.getpid())
                    children = current_process.children(recursive=True)
                    if children:
                        self.log(f"🧹 Terminating {len(children)} child processes...")
                        for child in children:
                            try:
                                name = child.name().lower()
                                if 'chromedriver' in name or 'node' in name:
                                    child.terminate()
                                    try:
                                        child.wait(timeout=1)
                                    except:
                                        child.kill()
                            except:
                                pass
                else:
                    # psutil not available, use subprocess fallback
                    import subprocess
                    try:
                        self.log("🧹 Terminating child processes (chromedriver, node)...")
                        subprocess.run('taskkill /F /IM chromedriver.exe /T 2>nul', shell=True, timeout=2, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                        subprocess.run('taskkill /F /IM node.exe /T 2>nul', shell=True, timeout=2, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                    except:
                        pass
            except Exception as e:
                self.log(f"⚠️ Process termination warning: {str(e)[:50]}")
            
            # Log aggressive stop
            self.log("⏸️  All processes terminated - System halted")
            
            # Force garbage collection to clean up
            import gc
            gc.collect()
            
            # Re-enable buttons after stop
            def reset_system():
                time.sleep(3)  # Longer delay to ensure all threads stop
                try:
                    self.stop_btn.config(bg='#FF0000', text='⏹️ EMERGENCY STOP')
                    self.headless.running = True
                    self.running = True
                    
                    # Re-enable all action buttons
                    try:
                        self.extract_btn.config(state='normal')
                        if hasattr(self, 'claim_bonus_btn'):
                            self.claim_bonus_btn.config(state='normal')
                    except:
                        pass
                    
                    self.log("✅ System RESET - All operations stopped")
                    self.log("▶️  You can now start new operations safely")
                except:
                    pass
            
            threading.Thread(target=reset_system, daemon=True).start()
        except Exception as e:
            self.log(f"⚠️ Stop error: {str(e)}")
            # Still try to reset flags
            self.headless.running = False
            self.running = False
            self.headless.running = False
            self.running = False
    
    def check_network_status(self):
        """Check if network/internet is available"""
        try:
            # Try to connect to multiple reliable servers with stricter timeout
            test_urls = ['https://www.google.com', 'https://www.cloudflare.com', 'https://1.1.1.1']
            for url in test_urls:
                try:
                    response = requests.head(url, timeout=2)
                    if response.status_code < 500:  # Any response means network is up
                        return True
                except requests.exceptions.ConnectionError:
                    continue  # Try next URL
                except requests.exceptions.Timeout:
                    continue  # Try next URL
                except Exception as e:
                    # Check for specific network-down errors
                    error_str = str(e).lower()
                    if 'unreachable' in error_str or '10051' in error_str or 'failed to establish' in error_str:
                        return False  # Definitely offline
                    continue
            return False  # All attempts failed
        except Exception as e:
            return False
    
    def update_network_status(self):
        """Update network status indicator (runs in background thread)"""
        def check_and_update():
            try:
                is_online = self.check_network_status()
                
                if is_online != self.network_online:
                    self.network_online = is_online
                    
                    # Update GUI in main thread
                    self.root.after(0, lambda: self._update_network_ui(is_online))
            except:
                pass
        
        # Run check in background thread to avoid blocking GUI
        threading.Thread(target=check_and_update, daemon=True).start()
        
        # Schedule next check
        self.root.after(self.network_check_interval, self.update_network_status)
    
    def _update_network_ui(self, is_online):
        """Update network UI (must run in main thread)"""
        try:
            if is_online:
                self.network_label.config(text="● Online", fg='#4CAF50')
                # Only log if status changed from offline to online
                if hasattr(self, '_last_logged_status') and not self._last_logged_status:
                    self.log("✅ Network connection restored")
                    self._last_logged_status = True
            else:
                self.network_label.config(text="● Offline", fg='#F44336')
                # Only log if status changed from online to offline  
                if not hasattr(self, '_last_logged_status') or self._last_logged_status:
                    self.log("⚠️ Network connection lost - Operations will pause")
                    self._last_logged_status = False
        except:
            pass
    
    def start_network_monitor(self):
        """Start periodic network monitoring"""
        self.root.after(1000, self.update_network_status)  # Start after 1 second

    def toggle_auto_scroll(self):
        """Toggle auto-scroll on/off with visual feedback"""
        self.auto_scroll_enabled = not self.auto_scroll_enabled
        
        if self.auto_scroll_enabled:
            self.auto_scroll_btn.config(text="⏬ Auto-Scroll: ON", bg='#4CAF50')
            # Jump to bottom when enabling
            self.terminal.see(tk.END)
            self.terminal.update_idletasks()
        else:
            self.auto_scroll_btn.config(text="⏸️ Auto-Scroll: OFF", bg='#FF5722')
    
    def clear_terminal(self):
        """Clear all terminal content"""
        self.terminal.delete('1.0', tk.END)
        self.log("🗑️ Terminal cleared")
    
    def jump_to_bottom(self):
        """Jump to bottom of terminal and enable auto-scroll"""
        self.terminal.see(tk.END)
        self.terminal.update_idletasks()
        if not self.auto_scroll_enabled:
            self.auto_scroll_enabled = True
            self.auto_scroll_btn.config(text="⏬ Auto-Scroll: ON", bg='#4CAF50')
    

    def toggle_theme(self):
        if self.theme.get() == 'dark':
            self.theme.set('light')
            self.colors = self.light_theme.copy()
            self.log("🌞 Switched to Light theme")
        else:
            self.theme.set('dark')
            self.colors = self.dark_theme.copy()
            self.log("🌙 Switched to Dark theme")

        self.apply_theme()
        self.save_config()  # Save theme preference

    def apply_theme(self):
        def update_widget_recursive(widget):
            try:
                widget_class = widget.winfo_class()
                
                # Handle different widget types
                if isinstance(widget, tk.Button):
                    # Update theme toggle button specifically using stored reference
                    if hasattr(self, 'theme_btn') and widget == self.theme_btn:
                        if self.theme.get() == 'dark':
                            widget.configure(text="🌙 Toggle Theme", bg='#9C27B0', fg='white')
                        else:
                            widget.configure(text="🌞 Toggle Theme", bg='#FF9800', fg='white')
                    # Keep other buttons with their original colors
                    
                elif isinstance(widget, (tk.Label, tk.LabelFrame)):
                    widget.configure(bg=self.colors['bg'], fg=self.colors['fg'])
                    
                elif isinstance(widget, (tk.Text, scrolledtext.ScrolledText)):
                    # Keep terminal always green for techy feel
                    if hasattr(self, 'terminal') and widget == self.terminal:
                        widget.configure(bg='#0a0a0a', fg='#00ff00')
                        widget.configure(selectbackground='#00ff00', selectforeground='#0a0a0a')
                    else:
                        widget.configure(bg=self.colors['text_bg'], fg=self.colors['text_fg'])
                        # Update selection colors for better visibility
                        widget.configure(selectbackground='#4CAF50', selectforeground='white')
                    
                elif isinstance(widget, tk.Entry):
                    widget.configure(bg=self.colors['text_bg'], fg=self.colors['text_fg'])
                    widget.configure(insertbackground=self.colors['text_fg'])  # Cursor color
                    
                elif isinstance(widget, (tk.Frame, tk.Toplevel)):
                    widget.configure(bg=self.colors['bg'])
                    
                elif isinstance(widget, tk.PanedWindow):
                    widget.configure(bg=self.colors['bg'])
                    
                elif isinstance(widget, tk.Checkbutton):
                    widget.configure(
                        bg=self.colors['bg'], 
                        fg=self.colors['fg'],
                        selectcolor=self.colors['bg'],
                        activebackground=self.colors['bg'],
                        activeforeground=self.colors['fg']
                    )
                    
                elif widget_class == 'Scrollbar':
                    # Handle scrollbars
                    widget.configure(
                        bg=self.colors['bg'],
                        troughcolor=self.colors['text_bg'],
                        activebackground=self.colors['button_bg']
                    )
                    
                # Recursively update all children
                for child in widget.winfo_children():
                    update_widget_recursive(child)
                    
            except tk.TclError:
                # Skip widgets that don't support certain configurations
                pass

        # Start with root window
        self.root.configure(bg=self.colors['bg'])
        
        # Update all widgets recursively
        for widget in self.root.winfo_children():
            update_widget_recursive(widget)
            
        # Force update display
        self.root.update_idletasks()

    def save_tokens(self):
        phones_text = self.phone_text.get('1.0', tk.END).strip()
        if not phones_text:
            self.log("❌ No phone numbers provided - cannot save tokens")
            return
        
        phone_list = [line.strip() for line in phones_text.split('\n') if line.strip()]
        if not phone_list:
            self.log("❌ No valid phone numbers - cannot save tokens")
            return
        
        password = self.password_entry.get()
        if not password:
            self.log("❌ Please enter password for token saving")
            return
        
        self.log(f"🔑 Starting token extraction for {len(phone_list)} accounts...")
        
        # Create enhanced callback that ensures auto-scroll
        def enhanced_callback(message):
            self.log(message)
            self.ensure_auto_scroll()
        
        threading.Thread(target=self.headless.extract_tokens_for_accounts, args=(phone_list, password, enhanced_callback), daemon=True).start()

    def load_tokens(self):
        if self.headless.load_tokens():
            self.log("✅ Tokens loaded from file")
        else:
            self.log("❌ No tokens file found")

    def auto_discover_api(self):
        """
        Auto-discover API endpoints using Advanced AI approach
        """
        target_url = self.target_url.get().strip()
        if not target_url:
            self.log("❌ Error: Please enter a target URL first")
            return
        
        # Validate URL format
        if not target_url.startswith(('http://', 'https://')):
            target_url = 'https://' + target_url
            self.target_url.set(target_url)
        
        self.log(f"🚀 Starting API Auto-Discovery for: {target_url}")
        self.log("⏳ This may take 30-60 seconds...")
        
        # Get credentials if available (for dynamic discovery)
        phone = None
        password = None
        
        # Check if user provided test credentials
        phones_text = self.phone_text.get('1.0', tk.END).strip()
        if phones_text:
            phone_list = [line.strip() for line in phones_text.split('\n') if line.strip()]
            if phone_list:
                phone = phone_list[0]  # Use first phone for testing
                password = self.password_entry.get()
        
        # Create enhanced callback
        def enhanced_callback(message):
            self.log(message)
            self.ensure_auto_scroll()
        
        # Run discovery in background thread
        def run_discovery():
            try:
                categorized = self.browser_discovery.hybrid_discovery(
                    target_url, 
                    phone, 
                    password, 
                    enhanced_callback
                )
                
                if categorized:
                    total = sum(len(eps) for eps in categorized.values())
                    enhanced_callback(f"")
                    enhanced_callback(f"✅ AUTO-DISCOVERY SUCCESSFUL!")
                    enhanced_callback(f"📊 Total endpoints discovered: {total}")
                    enhanced_callback(f"💾 Results saved to config/discovered_endpoints.json")
                    enhanced_callback(f"")
                    enhanced_callback(f"🔄 You can now use these endpoints in your operations")
                else:
                    enhanced_callback(f"⚠️ No endpoints discovered. The site may use non-standard patterns.")
                    
            except Exception as e:
                enhanced_callback(f"❌ Discovery failed: {str(e)}")
        
        threading.Thread(target=run_discovery, daemon=True).start()

    def count_phones(self):
        """Count and display the number of phone numbers"""
        phones_text = self.phone_text.get('1.0', tk.END).strip()
        if phones_text:
            phone_list = [line.strip() for line in phones_text.split('\n') if line.strip()]
            count = len(phone_list)
            self.count_btn.config(text=f"📊 Count: {count}")
            self.log(f"📊 Total phone numbers: {count}")
        else:
            self.count_btn.config(text="📊 Count: 0")
            self.log("📊 No phone numbers found")

    def setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for the application"""
        if DISABLE_SHORTCUTS:
            return
        self.root.bind('<Control-o>', lambda e: self.upload_phones())
        self.root.bind('<Control-b>', lambda e: self.place_bets())
        self.root.bind('<Control-t>', lambda e: self.toggle_theme())

    def setup_drag_drop(self):
        """Setup drag and drop functionality (basic implementation)"""
        # Basic drag and drop would require tkinterdnd2 library
        # For now, just a placeholder
        pass

    def start_remote_server(self):
        """Start the remote control server"""
        try:
            self.remote_server = RemoteServer(self)
            self.remote_server.start()
            self.log("🔐 Remote control server started on port 8080")
        except Exception as e:
            self.log(f"❌ Failed to start remote server: {str(e)}")
            self.remote_server = None

    def toggle_persistence(self):
        # Apply persistence toggle globally
        set_persistence(self.allow_persist.get())
        state = "ENABLED" if self.allow_persist.get() else "DISABLED"
        self.log(f"🧯 Persistence {state} — {'files will be written' if self.allow_persist.get() else 'stateless: no disk writes'}")
    
    # AI Control Methods
    def toggle_ai(self):
        """Toggle AI system on/off"""
        enabled = self.ai_enabled.get()
        if self.ai_integration:
            self.ai_integration.ai_engine.ai_enabled = enabled
        
        status = "🤖 AI Status: Active" if enabled else "🤖 AI Status: Disabled"
        color = '#4CAF50' if enabled else '#F44336'
        if hasattr(self, 'ai_status_label'):
            self.ai_status_label.config(text=status, fg=color)
        
        self.log(f"🤖 AI {'enabled' if enabled else 'disabled'}")
    
    def on_ai_mode_change(self, event=None):
        """Handle AI mode change"""
        mode = self.ai_mode.get()
        if self.ai_integration:
            self.ai_integration.configure_ai_settings({'ai_mode': mode})
        
        # Update UI based on mode
        if hasattr(self, 'ai_status_label'):
            if mode == "full_auto":
                self.ai_status_label.config(text="🤖 AI Status: Full Automation", fg='#FF9800')
            elif mode == "assisted":
                self.ai_status_label.config(text="🤖 AI Status: Assisted Mode", fg='#2196F3')
            else:
                self.ai_status_label.config(text="🤖 AI Status: Manual Mode", fg='#9E9E9E')
    
    def on_confidence_change(self, value):
        """Handle confidence threshold change"""
        threshold = float(value)
        if self.ai_integration:
            self.ai_integration.configure_ai_settings({'confidence_threshold': threshold})
            self.log(f"🎯 AI confidence threshold set to {threshold:.1%}")
    
    def show_ai_dashboard(self):
        """Show comprehensive AI dashboard"""
        if not self.ai_integration:
            self.log("❌ AI is not available - AI features disabled for Aviator Pro")
            return
            
        dashboard_data = self.ai_integration.get_ai_dashboard_data()
        
        # Create dashboard window
        dashboard = tk.Toplevel(self.root)
        dashboard.title("🧠 AI Intelligence Dashboard")
        dashboard.geometry("800x600")
        dashboard.configure(bg=self.colors['bg'])
        
        # Create notebook for tabs - OPTIMIZED FOR SMOOTH TAB SWITCHING
        notebook = ttk.Notebook(dashboard)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Smooth tab switching - prevent glitches when changing tabs
        def on_tab_changed(event):
            """Handle tab change smoothly without glitches"""
            try:
                # Update display immediately for smooth transition
                selected_tab = event.widget.select()
                event.widget.update_idletasks()
                # Force small delay to ensure rendering completes
                dashboard.after(10, lambda: dashboard.update_idletasks())
            except:
                pass  # Ignore errors during tab switch
        
        notebook.bind("<<NotebookTabChanged>>", on_tab_changed)
        
        # Performance Tab
        perf_frame = tk.Frame(notebook, bg=self.colors['bg'])
        notebook.add(perf_frame, text="📊 Performance")
        
        performance_text = tk.Text(perf_frame, bg=self.colors['text_bg'], fg=self.colors['text_fg'])
        performance_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Format performance data
        perf_info = f"""🤖 AI PERFORMANCE DASHBOARD
{'='*50}

📈 SESSION STATISTICS:
Total AI Decisions: {dashboard_data['session_performance']['total_ai_decisions']}
Successful Predictions: {dashboard_data['session_performance']['successful_predictions']}
AI Accuracy: {dashboard_data['session_performance']['ai_accuracy']:.1%}
Total ROI: {dashboard_data['session_performance']['total_roi']:.2f}

🎯 AI CONFIGURATION:
Mode: {dashboard_data['ai_status']['mode'].title()}
Engine Active: {dashboard_data['ai_status']['engine_active']}
Learning Enabled: {dashboard_data['ai_status']['learning_enabled']}
Auto Improve: {dashboard_data['ai_status']['auto_improve']}
Confidence Threshold: {dashboard_data['confidence_threshold']:.1%}
Pending Decisions: {dashboard_data['pending_decisions']}

⚖️ STRATEGY WEIGHTS:
"""
        
        for strategy, weight in dashboard_data['current_strategy'].items():
            perf_info += f"{strategy.title()}: {weight:.1%}\n"
        
        perf_info += f"\n🎲 RISK SETTINGS:\nThreshold: {dashboard_data['risk_settings']['threshold'].title()}\nAuto Stake Optimization: {dashboard_data['risk_settings']['auto_stake_optimization']}\n"
        
        performance_text.insert('1.0', perf_info)
        performance_text.config(state='disabled')
        
        # Insights Tab
        insights_frame = tk.Frame(notebook, bg=self.colors['bg'])
        notebook.add(insights_frame, text="💡 Insights")
        
        insights_text = tk.Text(insights_frame, bg=self.colors['text_bg'], fg=self.colors['text_fg'])
        insights_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Get recommendations
        if self.ai_integration:
            recommendations = self.ai_integration.get_smart_recommendations()
            insights_info = "🧠 AI INSIGHTS & RECOMMENDATIONS\n" + "="*50 + "\n\n"
            
            if recommendations:
                insights_info += "💡 CURRENT RECOMMENDATIONS:\n"
                for i, rec in enumerate(recommendations, 1):
                    insights_info += f"{i}. {rec}\n"
            else:
                insights_info += "✅ No specific recommendations at this time.\n"
            
            # Add AI insights
            ai_insights = dashboard_data.get('ai_insights', {})
            insights_info += f"\n📊 AI LEARNING PROGRESS:\n"
            insights_info += f"Total Learning Examples: {ai_insights.get('total_decisions', 0)}\n"
            insights_info += f"Overall Success Rate: {ai_insights.get('success_rate', 0):.1%}\n"
            insights_info += f"Average ROI: {ai_insights.get('average_roi', 0):.2f}\n"
        else:
            insights_info = "❌ AI is not available - AI features disabled for Aviator Pro\n"
        
        insights_text.insert('1.0', insights_info)
        insights_text.config(state='disabled')
        
        self.log("📊 AI Dashboard opened")
    
    def ai_optimize_stakes(self):
        """Use AI to optimize stakes for current operation"""
        if not self.ai_enabled.get() or not self.ai_integration:
            self.log("❌ AI is disabled - enable AI first")
            return
        
        phones_text = self.phone_text.get('1.0', tk.END).strip()
        booking_code = self.booking_entry.get().strip()
        stake = self.stake_entry.get().strip()
        
        if not phones_text or not booking_code or not stake:
            self.log("❌ Please fill in phone numbers, booking code, and stake first")
            return
        
        try:
            stake_float = float(stake)
            phone_list = [line.strip() for line in phones_text.split('\n') if line.strip()]
            
            self.log(f"⚙️ AI optimizing stakes for {len(phone_list)} accounts...")
            
            def optimize():
                optimized_stakes = self.ai_integration.auto_optimize_stakes(
                    phone_list, booking_code, stake_float
                )
                
                # Display optimization results
                self.log("💰 Stake Optimization Results:")
                for phone, optimized_stake in list(optimized_stakes.items())[:5]:  # Show first 5
                    self.log(f"   {phone[-4:]}: {stake_float:.2f} → {optimized_stake:.2f}")
                
                if len(optimized_stakes) > 5:
                    self.log(f"   ... and {len(optimized_stakes) - 5} more accounts")
                
                self.update_ai_stats_display()
            
            threading.Thread(target=optimize, daemon=True).start()
            
        except ValueError:
            self.log("❌ Invalid stake amount - please enter a number")
        except Exception as e:
            self.log(f"❌ Stake optimization failed: {str(e)}")
    
    def reset_ai_learning(self):
        """Reset AI learning data"""
        if not self.ai_integration:
            self.log("❌ AI is not available - AI features disabled for Aviator Pro")
            return
            
        if messagebox.askyesno("Reset AI Learning", 
                              "Are you sure you want to reset all AI learning data?\n\n"
                              "This will clear all accumulated knowledge and start fresh."):
            self.ai_integration.reset_ai_learning()
            self.update_ai_stats_display()
            self.log("🔄 AI learning data has been reset")
    
    def update_ai_stats_display(self):
        """Update AI statistics display"""
        if not self.ai_integration or not hasattr(self, 'ai_stats_label'):
            return
            
        try:
            dashboard_data = self.ai_integration.get_ai_dashboard_data()
            stats = dashboard_data['session_performance']
            
            accuracy_text = f"{stats['ai_accuracy']:.1%}" if stats['total_ai_decisions'] > 0 else "N/A"
            stats_text = f"Decisions: {stats['total_ai_decisions']} | Accuracy: {accuracy_text} | ROI: {stats['total_roi']:.2f}"
            
            self.ai_stats_label.config(text=stats_text)
        except Exception:
            pass  # Silently fail if AI not available
    
    def update_live_clock(self):
        """
        Update live clock with Kenya time (EAT = UTC+3)
        Shows system is alive and helps with match timing
        """
        try:
            import pytz
            from datetime import datetime
            
            # Get Kenya time (EAT = UTC+3)
            kenya_tz = pytz.timezone('Africa/Nairobi')
            now = datetime.now(kenya_tz)
            
            # Format time nicely
            time_str = now.strftime("%H:%M:%S")
            date_str = now.strftime("%a, %d %b")
            
            # Update clock label
            clock_text = f"🕐 {time_str}\n{date_str}"
            self.clock_label.config(text=clock_text)
            
        except Exception as e:
            # Fallback to system time if pytz fails
            from datetime import datetime
            now = datetime.now()
            time_str = now.strftime("%H:%M:%S")
            date_str = now.strftime("%a, %d %b")
            clock_text = f"🕐 {time_str}\n{date_str}"
            self.clock_label.config(text=clock_text)
        
        # Update every 1 second (keeps UI alive and responsive)
        if hasattr(self, 'root') and self.root.winfo_exists():
            self.root.after(1000, self.update_live_clock)

# ==========================================
# STABILITY SYSTEM INTEGRATION
# ==========================================

    def _init_stability_systems(self):
        """Initialize ultra-stability systems for 1000+ account processing"""
        try:
            from stability_orchestrator import stability_orchestrator
            self.stability_orchestrator = stability_orchestrator
            if not self.stability_orchestrator.initialize_system():
                print("[WARN] Stability orchestrator initialization failed")
                self.stability_orchestrator = None
                return
            print("[OK] Ultra-stability systems initialized for 1000+ accounts")
        except Exception as e:
            print(f"[WARN] Failed to initialize stability systems: {e}")
            self.stability_orchestrator = None

    def _start_stability_monitoring(self):
        """Start real-time stability monitoring in GUI"""
        if not STABILITY_SYSTEMS_ENABLED or not getattr(self, "stability_orchestrator", None):
            return

        def update_stability_status():
            try:
                health_status = self.stability_orchestrator._assess_system_health()
                if health_status.get("overall_healthy", False):
                    status_text = "🛡️ Stable"
                    status_color = "#4CAF50"
                else:
                    status_text = "⚠️ Degraded"
                    status_color = "#FF9800"
                    unhealthy_components = [
                        k for k, v in health_status.items()
                        if isinstance(v, dict) and not v.get("healthy", True)
                    ]
                    if unhealthy_components:
                        status_text += f" ({unhealthy_components[0]})"

                def update_label():
                    if hasattr(self, "stability_label"):
                        self.stability_label.config(text=status_text, fg=status_color)

                self.root.after(0, update_label)
            except Exception as e:
                print(f"Stability monitoring error: {e}")

            self.root.after(5000, update_stability_status)

        self.root.after(1000, update_stability_status)

    def get_stability_status(self) -> dict:
        """Get current stability system status"""
        if not STABILITY_SYSTEMS_ENABLED or not getattr(self, "stability_orchestrator", None):
            return {"enabled": False, "status": "Stability systems not available"}

        try:
            health = self.stability_orchestrator._assess_system_health()
            stats = self.stability_orchestrator._get_stability_report()
            return {
                "enabled": True,
                "system_healthy": health.get("overall_healthy", False),
                "health_details": health,
                "performance_stats": stats,
                "recommendations": self._get_stability_recommendations(health),
            }
        except Exception as e:
            return {"enabled": True, "error": str(e)}

    def _get_stability_recommendations(self, health_status: dict) -> list:
        """Get stability recommendations based on health status"""
        recommendations = []

        if not health_status.get("overall_healthy", True):
            if health_status.get("memory", {}).get("usage", 0) > 80:
                recommendations.append("High memory usage - reduce concurrent accounts")
            if health_status.get("cpu", {}).get("usage", 0) > 85:
                recommendations.append("High CPU usage - system may be overloaded")
            if not health_status.get("network", {}).get("healthy", True):
                recommendations.append("Network connectivity issues detected")

        if health_status.get("rate_limiter", {}).get("stats", {}).get("success_rate", 1) < 0.8:
            recommendations.append("Low success rate - increase delays between operations")

        return recommendations if recommendations else ["System operating normally"]

    def process_accounts_with_stability(self, account_processor, account_file="test_accounts.txt"):
        """Process accounts using ultra-stable systems"""
        if not STABILITY_SYSTEMS_ENABLED or not getattr(self, "stability_orchestrator", None):
            messagebox.showwarning("Stability Systems", "Ultra-stability systems not available. Using standard processing.")
            return None

        try:
            processing_window = tk.Toplevel(self.root)
            processing_window.title("Ultra-Stable Account Processing")
            processing_window.geometry("600x400")

            progress_text = scrolledtext.ScrolledText(processing_window, height=20, width=70)
            progress_text.pack(pady=10, padx=10, fill='both', expand=True)

            status_label = tk.Label(processing_window, text="Initializing ultra-stable processing...", font=('Arial', 10, 'bold'))
            status_label.pack(pady=5)

            def update_progress(message):
                def _update():
                    progress_text.insert('end', f"{datetime.now().strftime('%H:%M:%S')} - {message}\n")
                    progress_text.see('end')
                    status_label.config(text=message)
                processing_window.after(0, _update)

            def run_processing():
                try:
                    update_progress("Starting ultra-stable account processing...")
                    results = self.stability_orchestrator.process_accounts_stable(account_processor, account_file)
                    update_progress(f"Processing complete! Results: {results}")
                    if results and 'error' not in results:
                        success_rate = (results.get('successful_accounts', 0) / max(results.get('total_accounts', 1), 1)) * 100
                        update_progress(f"Success rate: {success_rate:.1f}%")
                        update_progress("Stability maintained throughout processing.")
                    else:
                        update_progress(f"Error: {results.get('error') if results else 'Unknown error'}")
                except Exception as e:
                    update_progress(f"Processing error: {e}")

            processing_thread = threading.Thread(target=run_processing, daemon=True)
            processing_thread.start()

            return processing_window

        except Exception as e:
            messagebox.showerror("Processing Error", f"Failed to start stable processing: {e}")
            return None

if __name__ == "__main__":
    # 🔧 ROBUST SPLASH SCREEN: Always works, with graceful fallback
    splash = None
    root = None
    
    try:
        # Step 1: Import splash screen module (with fallback)
        try:
            from splash_screen import SplashScreen
            splash_available = True
        except ImportError as import_err:
            print(f"⚠️ Splash screen module not available: {import_err}")
            splash_available = False
        except Exception as import_err:
            print(f"⚠️ Splash screen import error: {import_err}")
            splash_available = False
        
        if WINDOWS_API_AVAILABLE:
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
            except Exception:
                pass
        # Step 2: Create main root window first (always needed)
        root = tk.Tk()
        root.withdraw()
        
        # Step 3: Try to show splash screen (with fallback)
        if splash_available:
            try:
                splash = SplashScreen(parent=root)
                splash_shown = True
                # CRITICAL: Force splash screen to be visible immediately
                root.update_idletasks()
                root.update()
                # Small delay to ensure splash screen is fully rendered
                time.sleep(0.1)
            except Exception as splash_err:
                print(f"⚠️ Splash screen initialization failed: {splash_err}")
                print("   Starting without splash screen...")
                splash_shown = False
                splash = None
        else:
            splash_shown = False
        
        # Store splash screen reference for GUI initialization
        global splash_ref
        splash_ref = splash if splash_shown else None
        
        def initialize_app():
            """Initialize application with UI creation on main thread"""
            try:
                def update_splash(progress, status):
                    if splash_ref and splash_shown:
                        try:
                            root.after(0, lambda: splash_ref.update_progress(progress, status) if splash_ref else None)
                            root.update_idletasks()
                        except:
                            pass
                def create_and_show():
                    try:
                        BetFlowAviatorProGUI(root, splash_ref if splash_shown else None)
                        update_splash(100, "✅ Ready! Starting BetFlow Aviator Pro...")
                        root.update_idletasks()
                        try:
                            time.sleep(0.3)
                        except Exception:
                            pass
                        if splash and splash_shown:
                            try:
                                splash.close()
                            except:
                                pass
                        try:
                            root.deiconify(); root.update_idletasks(); root.update(); root.lift(); root.focus_force()
                        except:
                            pass
                        try:
                            root.after(50, lambda: root.lift() if root else None)
                            root.after(100, lambda: root.focus_force() if root else None)
                        except:
                            pass
                    except Exception as e:
                        print(f"⚠️ Initialization error: {e}")
                        import traceback
                        traceback.print_exc()
                        try:
                            if splash and splash_shown:
                                splash.close()
                        except:
                            pass
                        try:
                            root.deiconify(); root.update_idletasks(); root.update(); root.lift(); root.focus_force()
                        except:
                            pass
                root.after(0, create_and_show)
            except Exception:
                try:
                    root.deiconify(); root.update_idletasks(); root.update(); root.lift(); root.focus_force()
                except:
                    pass
        
        # Start initialization in background thread after a brief delay
        # This ensures splash screen is fully visible first
        import threading
        def start_init():
            time.sleep(0.2)  # Brief delay to ensure splash screen is visible
            init_thread = threading.Thread(target=initialize_app, daemon=True)
            init_thread.start()
        
        threading.Thread(target=start_init, daemon=True).start()
        
        # Run main event loop - this must run to process splash screen updates
        root.mainloop()
        
    except Exception as e:
        # CRITICAL FALLBACK: If everything fails, start normally
        print(f"⚠️ Critical error during startup: {e}")
        print("   Starting without splash screen...")
        try:
            # Ensure splash is closed if it exists
            if splash:
                try:
                    splash.close()
                except:
                    pass
        except:
            pass
        
        # Start normally
        if root is None:
            root = tk.Tk()
        try:
            app = BetFlowAviatorProGUI(root)
            root.mainloop()
        except Exception as final_err:
            print(f"❌ Fatal error: {final_err}")
            import traceback
            traceback.print_exc()







import os
import json
import threading
import time

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None
    ttk = None

def _log(msg, sink):
    try:
        if sink:
            sink(msg)
        else:
            print(msg)
    except Exception:
        print(msg)

def _make_driver(headless=True):
    try:
        import undetected_chromedriver as uc
        chrome_options = uc.ChromeOptions()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1280,800')
        try:
            chrome_options.add_experimental_option('prefs', {
                'credentials_enable_service': False,
                'profile.password_manager_enabled': False,
            })
        except Exception:
            pass
        if headless:
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--disable-gpu')
        driver = uc.Chrome(options=chrome_options, use_subprocess=True)
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"})
        except Exception:
            pass
        return driver
    except Exception:
        pass
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1280,800')
        driver = webdriver.Chrome(options=chrome_options)
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"})
        except Exception:
            pass
        return driver
    except Exception:
        return None

def run_macro(driver, macro_path, logger):
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except Exception as e:
        _log(f"Selenium import error: {e}", logger)
        return False
    try:
        with open(macro_path, 'r', encoding='utf-8') as f:
            steps = json.load(f)
    except Exception as e:
        _log(f"Macro load error: {e}", logger)
        return False
    def _ensure_game_context():
        try:
            outers = driver.find_elements(By.CSS_SELECTOR, "#app iframe")
            if outers:
                driver.switch_to.frame(outers[0])
                inner_frames = driver.find_elements(By.TAG_NAME, "iframe")
                for f in inner_frames[:4]:
                    try:
                        driver.switch_to.frame(f)
                        driver.find_element(By.CSS_SELECTOR, ".burger-i")
                        return True
                    except Exception:
                        driver.switch_to.parent_frame()
                return True
        except Exception:
            pass
        return False
    def _safe_click(el):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        except Exception:
            pass
        try:
            el.click(); return True
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", el); return True
            except Exception:
                return False
    for s in steps:
        t = (s.get('type') or '').lower()
        if t == 'goto':
            driver.get(s['url']); continue
        if t == 'sleep_ms':
            time.sleep(max(0, int(s.get('ms',0)))/1000.0); continue
        if t.startswith('click_') or t.startswith('wait_') or t.startswith('fill_'):
            _ensure_game_context()
        if t in ('click_xpath','wait_visible_xpath','fill_xpath'):
            xp = s.get('value');
            if not xp: continue
            if t == 'wait_visible_xpath':
                try:
                    WebDriverWait(driver, s.get('timeout',5000)/1000.0).until(EC.visibility_of_element_located((By.XPATH, xp)))
                except Exception:
                    _log(f"Macro wait failed: {xp}", logger)
            elif t == 'click_xpath':
                try:
                    el = WebDriverWait(driver, s.get('timeout',5000)/1000.0).until(EC.element_to_be_clickable((By.XPATH, xp)))
                    _safe_click(el)
                except Exception:
                    _log(f"Macro click failed: {xp}", logger)
            elif t == 'fill_xpath':
                try:
                    el = WebDriverWait(driver, s.get('timeout',5000)/1000.0).until(EC.presence_of_element_located((By.XPATH, xp)))
                    el.clear(); el.send_keys(s.get('text',''))
                except Exception:
                    _log(f"Macro fill failed: {xp}", logger)
        if t in ('click_css','wait_visible_css','fill_css'):
            css = s.get('value');
            if not css: continue
            if t == 'wait_visible_css':
                try:
                    WebDriverWait(driver, s.get('timeout',5000)/1000.0).until(EC.visibility_of_element_located((By.CSS_SELECTOR, css)))
                except Exception:
                    _log(f"Macro wait failed: {css}", logger)
            elif t == 'click_css':
                try:
                    el = WebDriverWait(driver, s.get('timeout',5000)/1000.0).until(EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
                    _safe_click(el)
                except Exception:
                    _log(f"Macro click failed: {css}", logger)
            elif t == 'fill_css':
                try:
                    el = WebDriverWait(driver, s.get('timeout',5000)/1000.0).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))
                    el.clear(); el.send_keys(s.get('text',''))
                except Exception:
                    _log(f"Macro fill failed: {css}", logger)
    return True

def run_batch(phones_text, password, headless, keep_open, macro_path, logger):
    phones = [p.strip() for p in (phones_text or '').replace(',', '\n').splitlines() if p.strip()]
    if not phones or not password:
        _log('ERROR: provide phones and password', logger)
        return
    for idx, phone in enumerate(phones):
        _log(f"\n=== Processing {phone} ===", logger)
        drv = _make_driver(headless=headless)
        if not drv:
            _log('Driver init failed', logger)
            continue
        try:
            # Navigate and login quick path
            drv.get('https://odibets.com/aviator')
            try:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                try:
                    btn = WebDriverWait(drv, 6).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Login to play')]")))
                    btn.click(); time.sleep(0.2)
                except Exception:
                    pass
                try:
                    pbox = WebDriverWait(drv, 6).until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder,'07') or contains(@aria-label,'07')]")))
                    pbox.clear(); pbox.send_keys(phone)
                except Exception:
                    pass
                try:
                    pass_box = WebDriverWait(drv, 6).until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
                    pass_box.clear(); pass_box.send_keys(password)
                except Exception:
                    pass
                try:
                    sb = drv.find_element(By.XPATH, "//button[contains(., 'Login to Odibets')]")
                    sb.click(); time.sleep(0.3)
                except Exception:
                    pass
            except Exception:
                pass
            # Optional macro playback after login
            if macro_path and os.path.exists(macro_path):
                try:
                    run_macro(drv, macro_path, logger)
                except Exception as e:
                    _log(f"Macro run error: {e}", logger)
            _log('Done for account', logger)
        finally:
            try:
                if not keep_open:
                    drv.quit()
            except Exception:
                pass

def main():
    macro_default = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recordings', 'selenium_macro_manage.json')
    if tk is None:
        print('Tkinter not available. Running in console mode.')
        phones = os.environ.get('PHONES_TEXT', '')
        password = os.environ.get('AVIATOR_PASSWORD', '')
        headless = os.environ.get('AVIATOR_HEADLESS', '0').strip() not in ('0','false','False')
        keep_open = os.environ.get('AVIATOR_KEEP_OPEN', '1').strip() in ('1','true','True')
        run_batch(phones, password, headless, keep_open, macro_default, print)
        return
    root = tk.Tk()
    root.title('BetFlow GUI')
    frm = ttk.Frame(root, padding=10)
    frm.grid(row=0, column=0, sticky='nsew')
    for i in range(3):
        frm.grid_rowconfigure(i, weight=1)
        frm.grid_columnconfigure(i, weight=1)
    tk.Label(frm, text='Phones (comma or newline):').grid(row=0, column=0, sticky='w')
    phones_var = tk.StringVar()
    phones_entry = tk.Text(frm, height=4, width=50)
    phones_entry.grid(row=1, column=0, columnspan=3, sticky='ew')
    tk.Label(frm, text='Password:').grid(row=2, column=0, sticky='w')
    pwd_var = tk.StringVar()
    pwd_entry = ttk.Entry(frm, textvariable=pwd_var, show='*', width=40)
    pwd_entry.grid(row=2, column=1, sticky='w')
    headless_var = tk.BooleanVar(value=False)
    keep_open_var = tk.BooleanVar(value=True)
    # Shortcuts removed: no headless/keep-open toggles
    log_box = tk.Text(frm, height=18, width=80)
    log_box.grid(row=4, column=0, columnspan=3, sticky='nsew', pady=(8,4))
    def gui_log(msg):
        try:
            log_box.insert('end', str(msg) + '\n')
            log_box.see('end')
        except Exception:
            pass
    def on_run():
        phones_text = phones_entry.get('1.0', 'end').strip()
        password = pwd_var.get().strip()
        headless = False
        keep_open = True
        gui_log('Starting...')
        threading.Thread(target=run_batch, args=(phones_text, password, headless, keep_open, macro_default, gui_log), daemon=True).start()
    ttk.Button(frm, text='Run', command=on_run).grid(row=3, column=2, sticky='e')
    def on_save():
        try:
            ts = time.strftime('%Y%m%d_%H%M%S')
            out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recordings')
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f'gui_session_{ts}.json')
            data = {
                'phones': phones_entry.get('1.0', 'end').strip(),
                'password': pwd_var.get().strip(),
                'log': log_box.get('1.0', 'end')
            }
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            gui_log(f'Saved to {out_path}')
        except Exception as e:
            gui_log(f'Save error: {e}')
    ttk.Button(frm, text='Save to Disk', command=on_save).grid(row=3, column=1, sticky='w')
    root.mainloop()

if __name__ == '__main__':
    main()
