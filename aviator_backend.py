try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    sync_playwright = None
    class PlaywrightTimeoutError(Exception):
        pass
    PLAYWRIGHT_AVAILABLE = False
try:
    from stealth_engine import StealthEngine
    STEALTH_AVAILABLE = True
except Exception:
    STEALTH_AVAILABLE = False
import os
import time
import re

class AviatorBackend:
    def __init__(self, headless=False, storage_path="recordings/storage.json", mute_audio=True, use_stealth=True, mobile_view=True, engine="firefox", progress_cb=None, visual_ai=True):
            self.headless = headless
            self.storage_path = storage_path
            self.mute_audio = mute_audio
            self.use_stealth = use_stealth and STEALTH_AVAILABLE
            self.mobile_view = mobile_view
            self.engine = engine
            self.playwright = None
            self.browser = None
            self.context = None
            self.page = None
            self.started = False
            self._stealth = StealthEngine(aggressiveness="balanced") if self.use_stealth else None
            self._engine_fallback_done = False
            self.progress_cb = progress_cb
            self._visual_ai = visual_ai or str(os.getenv("AVIATOR_VISUAL_AI", "1")).strip() in ("1", "true", "True")
            self._templates_loaded = False
            self._ui_templates = []
            self._snap_enabled = False

    def _emit(self, msg):
        try:
            if self.progress_cb:
                self.progress_cb(msg)
            else:
                print(msg)
        except Exception:
            try:
                print(msg)
            except Exception:
                pass

    def _snap(self, name):
        try:
            if not self._snap_enabled:
                return
            os.makedirs("debug_screenshots", exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            self.page.screenshot(path=f"debug_screenshots/snap_{name}_{ts}.png")
        except Exception:
            pass
    def _retry(self, fn, times=3, delay_ms=250):
        d = max(50, delay_ms)
        for i in range(max(1, times)):
            try:
                r = fn()
                if r is not False and r is not None:
                    return r
            except Exception:
                pass
            try:
                self.page.wait_for_timeout(d)
            except Exception:
                try:
                    time.sleep(d / 1000.0)
                except Exception:
                    pass
            d = min(int(d * 1.6), 1500)
        return False

    def start(self):
        if self.started:
            return
        if not PLAYWRIGHT_AVAILABLE:
            self._emit("❌ Playwright is not available. Install dependencies first:")
            self._emit("   pip install playwright")
            self._emit("   python -m playwright install firefox chromium")
            raise RuntimeError("playwright_missing")
        self.playwright = sync_playwright().start()
        launch_args = []
        if self.mute_audio:
            launch_args.append('--mute-audio')
        launch_args.extend([
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-site-isolation-trials',
        ])
        if (self.engine or "chromium") == "chromium":
            try:
                self.browser = self.playwright.chromium.launch(headless=self.headless, channel="chrome", args=launch_args)
            except Exception:
                self.browser = self.playwright.chromium.launch(headless=self.headless, args=launch_args)
        elif self.engine == "firefox":
            try:
                self.browser = self.playwright.firefox.launch(headless=self.headless)
            except Exception:
                # Fallback to Chromium if Firefox browser binaries are not installed
                try:
                    self.browser = self.playwright.chromium.launch(headless=self.headless, args=launch_args)
                    self.engine = "chromium"
                    self._emit("ℹ️ Firefox not available; switched to Chromium engine")
                except Exception as e:
                    raise
        else:
            self.browser = self.playwright.chromium.launch(headless=self.headless, args=launch_args)
        context_kwargs = {}
        if self._stealth:
            fp = self._stealth.random_fingerprint()
            ua_mobile_chrome = "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
            ua_mobile_firefox = "Mozilla/5.0 (Android 11; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0"
            if self.mobile_view:
                if self.engine == "firefox":
                    context_kwargs.update({
                        "user_agent": ua_mobile_firefox,
                        "locale": "en-US",
                        "viewport": {"width": 414, "height": 896},
                        "timezone_id": fp.get("timezone", "Africa/Nairobi"),
                        "extra_http_headers": self._stealth.get_request_headers(referer="https://odibets.com/aviator"),
                    })
                else:
                    context_kwargs.update({
                        "user_agent": ua_mobile_chrome,
                        "locale": "en-US",
                        "viewport": {"width": 414, "height": 896},
                        "device_scale_factor": 2,
                        "is_mobile": True,
                        "has_touch": True,
                        "timezone_id": fp.get("timezone", "Africa/Nairobi"),
                        "extra_http_headers": self._stealth.get_request_headers(referer="https://odibets.com/aviator"),
                    })
            else:
                context_kwargs.update({
                    "user_agent": fp.get("user_agent"),
                    "locale": fp.get("language", "en-US").split(",")[0],
                    "viewport": {"width": fp.get("screen_width", 1366), "height": fp.get("screen_height", 768)},
                    "device_scale_factor": 1,
                    "timezone_id": fp.get("timezone", "Africa/Nairobi"),
                    "extra_http_headers": self._stealth.get_request_headers(referer="https://odibets.com/aviator"),
                })
        # Strengthen anti-detection and unblock policies
        context_kwargs.update({
            "bypass_csp": True,
        })
        # Use device descriptor if available for mobile
        try:
            if self.mobile_view and self.engine != "firefox":
                from playwright.sync_api import devices
                pixel = devices.get("Pixel 5")
                if pixel:
                    context_kwargs.update({
                        "viewport": pixel["viewport"],
                        "device_scale_factor": pixel.get("deviceScaleFactor", 2),
                        "is_mobile": pixel.get("isMobile", True),
                        "has_touch": pixel.get("hasTouch", True),
                    })
        except Exception:
            pass
        self.context = self.browser.new_context(**context_kwargs)
        try:
            # Anti-automation init script
            self.context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = window.chrome || { runtime: {} };
                Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                """
            )
        except Exception:
            pass
        self.page = self.context.new_page()
        try:
            tm = int(str(os.getenv("AVIATOR_TIMEOUT_MS", "12000")).strip())
        except Exception:
            tm = 12000
        try:
            ntm = int(str(os.getenv("AVIATOR_NAV_TIMEOUT_MS", "20000")).strip())
        except Exception:
            ntm = 20000
        try:
            self.page.set_default_timeout(tm)
        except Exception:
            pass
        try:
            self.page.set_default_navigation_timeout(ntm)
        except Exception:
            pass
        self.started = True
    def _wait_iframe(self, timeout=10000):
        try:
            el = self.page.locator("#app iframe").first
            el.wait_for(state="visible", timeout=timeout)
            return el.content_frame
        except Exception:
            return None

    def _switch_engine(self, engine):
        try:
            self.stop()
        except Exception:
            pass
        self.engine = engine
        self.start()
        self._engine_fallback_done = True

    def stop(self):
        try:
            if self.context:
                try:
                    if self.storage_path:
                        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
                        self.context.storage_state(path=self.storage_path)
                except Exception:
                    pass
                self.context.close()
        finally:
            try:
                if self.browser:
                    self.browser.close()
            finally:
                try:
                    if self.playwright:
                        self.playwright.stop()
                finally:
                    self.playwright = None
                    self.browser = None
                    self.context = None
                    self.page = None
                    self.started = False

    def _mute_frame_audio(self, frame):
        try:
            frame.evaluate("""() => {
                try { (document.querySelectorAll('audio,video')||[]).forEach(el => { el.muted = true; el.pause && el.pause(); }); } catch(e) {}
                try { const AC = window.AudioContext || window.webkitAudioContext; if (AC && AC.prototype) { AC.prototype.resume = function(){ return Promise.resolve(); }; } } catch(e) {}
                try { const AP = window.HTMLAudioElement && window.HTMLAudioElement.prototype; if (AP && AP.play) { AP.play = function(){ return Promise.resolve(); }; } } catch(e) {}
                try { const VP = window.HTMLVideoElement && window.HTMLVideoElement.prototype; if (VP && VP.play) { VP.play = function(){ return Promise.resolve(); }; } } catch(e) {}
                return true;
            }""")
        except Exception:
            pass

    def _load_ui_templates(self, category="UI_ELEMENTS"):
            """Load UI element templates for visual detection"""
            if self._templates_loaded:
                return
            try:
                base = os.path.join(os.getcwd(), "VISUAL_TRAINING_DATA", category)
                if os.path.isdir(base):
                    import cv2
                    import numpy as np
                    for root, _, files in os.walk(base):
                        for fn in files:
                            if fn.lower().endswith((".png", ".jpg", ".jpeg")):
                                p = os.path.join(root, fn)
                                try:
                                    img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                                    if img is not None and img.size > 0:
                                        self._ui_templates.append(img)
                                except Exception:
                                    pass
                self._templates_loaded = True
            except Exception:
                self._templates_loaded = True

    def _frame_screenshot_gray(self, frame):
            """Enhanced preprocessing with histogram equalization for better contrast"""
            try:
                import cv2
                import numpy as np
                buf = frame.screenshot(type="png")
                arr = np.frombuffer(buf, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)

                # Apply histogram equalization for better contrast
                if img is not None:
                    img = cv2.equalizeHist(img)
                    # Apply slight Gaussian blur to reduce noise
                    img = cv2.GaussianBlur(img, (3, 3), 0)

                return img
            except Exception:
                return None

    def _visual_detect_element(self, frame, category="UI_ELEMENTS") -> bool:
                """Enhanced multi-scale template matching with ensemble voting for UI element detection"""
                if not self._visual_ai:
                    return False
                try:
                    self._load_ui_templates(category)
                    img = self._frame_screenshot_gray(frame)
                    if img is None:
                        return False

                    import cv2
                    import numpy as np

                    # Track matches across all templates and scales
                    match_scores = []

                    for tpl in self._ui_templates:
                        try:
                            # Multi-scale matching (90%, 100%, 110% of original size)
                            scales = [0.9, 1.0, 1.1]
                            best_match = 0.0

                            for scale in scales:
                                # Resize template
                                if scale != 1.0:
                                    w = int(tpl.shape[1] * scale)
                                    h = int(tpl.shape[0] * scale)
                                    if w < 10 or h < 10:  # Skip if too small
                                        continue
                                    scaled_tpl = cv2.resize(tpl, (w, h), interpolation=cv2.INTER_AREA)
                                else:
                                    scaled_tpl = tpl

                                # Skip if template is larger than image
                                if scaled_tpl.shape[0] > img.shape[0] or scaled_tpl.shape[1] > img.shape[1]:
                                    continue

                                # Try multiple matching methods and take the best
                                methods = [
                                    cv2.TM_CCOEFF_NORMED,
                                    cv2.TM_CCORR_NORMED,
                                    cv2.TM_SQDIFF_NORMED
                                ]

                                for method in methods:
                                    try:
                                        res = cv2.matchTemplate(img, scaled_tpl, method)
                                        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

                                        # For TM_SQDIFF_NORMED, lower is better, so invert
                                        if method == cv2.TM_SQDIFF_NORMED:
                                            score = 1.0 - min_val
                                        else:
                                            score = max_val

                                        best_match = max(best_match, score)
                                    except Exception:
                                        pass

                            match_scores.append(best_match)

                        except Exception:
                            pass

                    if not match_scores:
                        return False

                    # Ensemble voting: if any template has high confidence OR multiple have medium confidence
                    max_score = max(match_scores)
                    high_confidence_count = sum(1 for s in match_scores if s >= 0.70)
                    medium_confidence_count = sum(1 for s in match_scores if s >= 0.60)

                    # Decision logic:
                    # 1. Any single template with 75%+ confidence = YES
                    # 2. 2+ templates with 70%+ confidence = YES  
                    # 3. 3+ templates with 60%+ confidence = YES
                    if max_score >= 0.75:
                        return True
                    if high_confidence_count >= 2:
                        return True
                    if medium_confidence_count >= 3:
                        return True

                    return False

                except Exception:
                    return False
    def _click_template(self, frame, parts_list, threshold=0.78) -> bool:
            """Enhanced multi-scale template matching for button clicks"""
            try:
                import cv2
                import numpy as np
                img = self._frame_screenshot_gray(frame)
                if img is None:
                    return False
                bb = self.page.locator("#app iframe").bounding_box()
                if not bb:
                    return False

                best = None
                best_tpl = None
                best_scale = 1.0

                for parts in parts_list or []:
                    try:
                        p = os.path.join(os.getcwd(), "VISUAL_TRAINING_DATA", *parts)
                        tpl = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                        if tpl is None or tpl.size == 0:
                            continue

                        # Apply same preprocessing as screenshot
                        tpl = cv2.equalizeHist(tpl)
                        tpl = cv2.GaussianBlur(tpl, (3, 3), 0)

                        # Multi-scale matching
                        scales = [0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15]

                        for scale in scales:
                            # Resize template
                            if scale != 1.0:
                                w = int(tpl.shape[1] * scale)
                                h = int(tpl.shape[0] * scale)
                                if w < 10 or h < 10:
                                    continue
                                scaled_tpl = cv2.resize(tpl, (w, h), interpolation=cv2.INTER_AREA)
                            else:
                                scaled_tpl = tpl

                            # Skip if template is larger than image
                            if scaled_tpl.shape[0] > img.shape[0] or scaled_tpl.shape[1] > img.shape[1]:
                                continue

                            # Try multiple matching methods
                            methods = [
                                cv2.TM_CCOEFF_NORMED,
                                cv2.TM_CCORR_NORMED,
                                cv2.TM_SQDIFF_NORMED
                            ]

                            for method in methods:
                                try:
                                    res = cv2.matchTemplate(img, scaled_tpl, method)
                                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

                                    # For TM_SQDIFF_NORMED, lower is better
                                    if method == cv2.TM_SQDIFF_NORMED:
                                        score = 1.0 - min_val
                                        loc = min_loc
                                    else:
                                        score = max_val
                                        loc = max_loc

                                    if best is None or score > best:
                                        best = score
                                        best_tpl = (scaled_tpl, loc)
                                        best_scale = scale
                                except Exception:
                                    pass

                    except Exception:
                        pass

                # Lower threshold slightly since we're using ensemble methods
                if best is None or best < (threshold - 0.08) or best_tpl is None:
                    return False

                tpl, loc = best_tpl
                sx = bb["width"] / float(img.shape[1])
                sy = bb["height"] / float(img.shape[0])
                cx = bb["x"] + (loc[0] + tpl.shape[1] / 2.0) * sx
                cy = bb["y"] + (loc[1] + tpl.shape[0] / 2.0) * sy

                try:
                    self.page.mouse.click(cx, cy)
                    return True
                except Exception:
                    return False
            except Exception:
                return False
    def _smart_click(self, frame, dom_fn, templates, threshold=0.76):
        ok = self._retry(dom_fn, times=2, delay_ms=200)
        if ok:
            return True
        if templates:
            if self._click_template(frame, templates, threshold=threshold):
                return True
        return False

    def _open_menu_immediate(self, frame):
            """Open the menu in the Aviator game"""
            def menu_opened():
                try:
                    return (
                        frame.locator(".dropdown-item.list-menu-item").count() > 0 or
                        frame.locator(".menu-content").count() > 0 or
                        frame.get_by_text("Sound", exact=False).count() > 0 or
                        frame.get_by_text("Home", exact=False).count() > 0
                    )
                except Exception:
                    return False

            try:
                b = frame.locator(".burger-i")
                try:
                    b.click(timeout=500, force=True)
                except Exception:
                    b.wait_for(state="visible", timeout=1200)
                    b.click(force=True)
                frame.wait_for_selector(".dropdown-item.list-menu-item, .menu-content, text=Sound, text=Home", timeout=2000)
                if menu_opened():
                    return True
            except Exception:
                pass

            try:
                alt = frame.locator("button.profile-menu-opener")
                try:
                    alt.click(timeout=800, force=True)
                except Exception:
                    alt.wait_for(state="visible", timeout=1200)
                    if alt.is_enabled():
                        alt.click()
                    else:
                        try:
                            frame.evaluate("document.querySelector('button.profile-menu-opener')?.click()")
                        except Exception:
                            pass
                frame.wait_for_selector(".dropdown-item.list-menu-item, .menu-content, text=Sound, text=Home", timeout=2000)
                if menu_opened():
                    return True
            except Exception:
                pass

            # Strategy 2: button after balance/KES
            try:
                frame.locator("xpath=//*[contains(text(),'KES') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'balance')]/following::button[1]").first.click()
                frame.wait_for_selector(".dropdown-item.list-menu-item, .menu-content, text=Sound, text=Home", timeout=2000)
                if menu_opened():
                    return True
            except Exception:
                pass

            # Strategy 3: coordinate click near top-right of iframe
            try:
                iframe_bb = self.page.locator("#app iframe").bounding_box()
                if iframe_bb:
                    x = iframe_bb['x'] + iframe_bb['width'] - 28
                    y = iframe_bb['y'] + 28
                    self.page.mouse.click(x, y)
                    frame.wait_for_selector(".dropdown-item.list-menu-item, .menu-content, text=Sound, text=Home", timeout=2000)
                    if menu_opened():
                        return True
            except Exception:
                pass

            try:
                for _ in range(3):
                    for sel in [
                        "i.burger",
                        ".burger",
                        "button[aria-label*='Menu']",
                        "[class*='burger']",
                        "[class*='menu']"
                    ]:
                        try:
                            frame.locator(sel).first.click(force=True, timeout=400)
                            frame.wait_for_selector(".dropdown-item.list-menu-item, .menu-content, text=Sound, text=Home", timeout=1200)
                            if menu_opened():
                                return True
                        except Exception:
                            pass
                    self.page.wait_for_timeout(250)
            except Exception:
                pass

            try:
                if self._smart_click(
                    frame,
                    lambda: frame.locator(".burger-i").first.click(force=True),
                    [["BETTING BUTTONS", "menu_button.png"], ["UI_ELEMENTS", "menu_button.png"]],
                    threshold=0.75
                ):
                    frame.wait_for_selector(".dropdown-item.list-menu-item, .menu-content, text=Sound, text=Home", timeout=2000)
                    if menu_opened():
                        return True
            except Exception:
                pass

            return False

    def _normalize_phone(self, phone: str) -> str:
        return (phone or "").strip()

    def _human_type(self, locator, text: str, delay_ms: int = 120, post_delay_ms: int = 0):
        locator.click()
        locator.clear()
        locator.type(text, delay=delay_ms)
        if post_delay_ms > 0:
            self.page.wait_for_timeout(post_delay_ms)

    def _looks_logged_in(self) -> bool:
        try:
            if self.page.locator("#app iframe").count() > 0:
                el = self.page.locator("#app iframe").first
                el.wait_for(state="visible", timeout=3000)
                frame = el.content_frame
                if frame:
                    try:
                        if frame.locator("canvas").count() > 0:
                            return True
                    except Exception:
                        pass
                    try:
                        if frame.get_by_text("Balance", exact=False).count() > 0:
                            return True
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            if self.page.get_by_role("button", name="Login to play").count() == 0:
                return True
        except Exception:
            pass
        return False

    def navigate_to_aviator(self):
        self.page.goto("https://odibets.com/aviator")
        try:
            self.page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass
        try:
            self.page.wait_for_selector("text=Login to play", timeout=8000)
        except PlaywrightTimeoutError:
            pass
        self._emit("Navigated to Aviator")
        self._snap("aviator_navigated")
        return True

    def login_and_open_menu(self, phone: str, password: str):
        try:
            self.navigate_to_aviator()
            try:
                self.page.get_by_role("button", name="Login to play").click()
                self._emit("Login dialog opened")
                self._snap("login_dialog_opened")
            except Exception:
                try:
                    self.page.click("//button[contains(., 'Login to play')]")
                    self._emit("Login dialog opened")
                except Exception:
                    # Extra fallbacks: UI text varies occasionally
                    clicked = False
                    for sel in [
                        "button:has-text('Login')",
                        "button:has-text('Log in')",
                        "text=Login",
                        "role=button[name='Login']",
                        "role=button[name='Log in']",
                    ]:
                        try:
                            self.page.locator(sel).first.click()
                            self._emit("Login dialog opened (fallback selector)")
                            clicked = True
                            break
                        except Exception:
                            pass
                    if not clicked:
                        try:
                            self.page.click("//button[contains(., 'Login')]")
                            self._emit("Login dialog opened (xpath fallback)")
                        except Exception:
                            pass

            if not phone or not password:
                return {"success": False, "reason": "missing_credentials"}

            phone = self._normalize_phone(phone)
            try:
                phone_input = self.page.get_by_role("textbox", name="07xxxxxxxx")
                self._human_type(phone_input, phone, delay_ms=180, post_delay_ms=300)
                self._emit("Phone input typed")
                self._snap("phone_typed")
            except Exception:
                try:
                    phone_input = self.page.locator("//input[contains(@placeholder,'07') or contains(@aria-label,'07')]")
                    self._human_type(phone_input, phone, delay_ms=180, post_delay_ms=300)
                    self._emit("Phone input typed")
                except Exception:
                    try:
                        phone_input = self.page.locator("input[type='tel'], input[placeholder*='07'], input[aria-label*='07']").first
                        self._human_type(phone_input, phone, delay_ms=180, post_delay_ms=300)
                        self._emit("Phone input typed")
                    except Exception:
                        return {"success": False, "reason": "phone_input_not_found"}

            try:
                pwd_input = self.page.get_by_role("textbox", name="• • • • • • • •")
                self._human_type(pwd_input, password, delay_ms=220, post_delay_ms=400)
                self._emit("Password typed")
                self._snap("password_typed")
            except Exception:
                try:
                    pwd_input = self.page.locator("input[type='password']")
                    self._human_type(pwd_input, password, delay_ms=220, post_delay_ms=400)
                    self._emit("Password typed")
                except Exception:
                    return {"success": False, "reason": "password_input_not_found"}

            # Click Login to Odibets button
            self._emit("Clicking login button...")
            login_clicked = False
            try:
                self.page.locator("button:has-text('Login to Odibets')").first.click(timeout=5000)
                login_clicked = True
                self._emit("✅ Login button clicked")
            except Exception as e1:
                self._emit(f"Primary click failed: {str(e1)[:80]}")
                try:
                    # JavaScript fallback
                    self.page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const loginBtn = buttons.find(b => b.textContent.trim() === 'Login to Odibets');
                        if (loginBtn) loginBtn.click();
                    }""")
                    login_clicked = True
                    self._emit("✅ Login button clicked (JavaScript)")
                except Exception as e2:
                    self._emit(f"JavaScript click failed: {str(e2)[:80]}")
            
            if not login_clicked:
                return {"success": False, "reason": "login_button_click_failed"}
            
            # MANDATORY: Wait for login dialog to close
            self._emit("Waiting for login dialog to close...")
            dialog_closed = False
            for attempt in range(15):
                try:
                    phone_count = self.page.locator("input[type='tel'], input[placeholder*='07']").count()
                    if phone_count == 0:
                        dialog_closed = True
                        self._emit("✅ Login dialog closed")
                        break
                    else:
                        self._emit(f"Attempt {attempt+1}/15: Dialog still open")
                except Exception:
                    pass
                self.page.wait_for_timeout(1000)
            
            if not dialog_closed:
                self._emit("❌ Login dialog did not close!")
                self._snap("login_failed_dialog_open")
                return {"success": False, "reason": "login_dialog_did_not_close"}
            
            # Wait for page to settle
            try:
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                self.page.wait_for_timeout(3000)

            frame = self._wait_iframe(timeout=10000)
            if frame is None:
                if not self._looks_logged_in():
                    if not self._engine_fallback_done:
                        try:
                            alt = "chromium" if self.engine == "firefox" else "firefox"
                            self._switch_engine(alt)
                            return self.login_and_open_menu(phone, password)
                        except Exception:
                            pass
                    return {"success": False, "reason": "frame_not_found"}
            else:
                self._emit("Login successful")
                self._snap("login_success")

            # If content appears blank after login, refresh once
            refreshed = False
            try:
                frame.wait_for_selector(".burger-i, .dropdown-item.list-menu-item, canvas", timeout=5000)
            except PlaywrightTimeoutError:
                self.page.reload()
                refreshed = True
                self._emit("Page reloaded once after blank content")
                self._snap("page_reloaded")
                frame = self._wait_iframe(timeout=10000)
                if frame is None:
                    if not self._engine_fallback_done:
                        try:
                            alt = "chromium" if self.engine == "firefox" else "firefox"
                            self._switch_engine(alt)
                            return self.login_and_open_menu(phone, password)
                        except Exception:
                            pass
                    return {"success": False, "reason": "frame_not_ready_after_refresh"}

            self._mute_frame_audio(frame)

            if not self._open_menu_immediate(frame):
                return {"success": False, "reason": "header_menu_not_found"}
            
            self._emit("Menu opened successfully")
            self._snap("menu_opened")
            
            # Clear site data and logout
            try:
                self._clear_site_data()
            except Exception:
                pass
            
            try:
                if self._open_menu_immediate(frame):
                    try:
                        frame.locator(".menu-content >> a:has-text('Logout')").first.click()
                        self._emit("Logout")
                        self._snap("logout")
                        return {"success": True, "post": "logout_via_menu_content"}
                    except Exception:
                        try:
                            frame.locator("a:has-text('Logout')").first.click()
                            self._emit("Logout")
                            self._snap("logout")
                            return {"success": True, "post": "logout_via_link"}
                        except Exception:
                            pass
            except Exception:
                pass
            
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "reason": str(e)}

    def _clear_site_data(self):
        try:
            self.page.evaluate("""() => {
                try { localStorage.clear(); } catch(e) {}
                try { sessionStorage.clear(); } catch(e) {}
                try {
                    if (window.caches && caches.keys) {
                        caches.keys().then(names => Promise.all(names.map(n => caches.delete(n))));
                    }
                } catch(e) {}
                try {
                    if (window.indexedDB && indexedDB.databases) {
                        indexedDB.databases().then(dbs => Promise.all(dbs.map(db => indexedDB.deleteDatabase(db.name))));
                    }
                } catch(e) {}
                return true;
            }""")
        except Exception:
            pass

    def dump_page_html(self, path):
        try:
            enabled = str(os.getenv("AVIATOR_WRITE_DUMPS", "0")).strip() in ("1", "true", "True")
        except Exception:
            enabled = False
        if not enabled:
            return False
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:
            pass
        try:
            content = self.page.content()
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception:
            return False
