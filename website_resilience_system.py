"""
Website Resilience System - Auto-adapts to website structure changes
Ensures BetFlow Pro never fails due to website updates or anomalies
"""

import time
import hashlib
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from utils import log_message
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class WebsiteStructureMonitor:
    """Monitors website structure changes and auto-adapts selectors"""
    
    def __init__(self):
        self.selector_cache = {}
        self.selector_alternatives = {}
        self.last_structure_hash = None
        self.failure_count = {}
        self.success_count = {}
        self.load_time_history = []
        
        # Initialize known selector alternatives
        self._initialize_selector_alternatives()
    
    def _initialize_selector_alternatives(self):
        """Pre-configure multiple selector strategies for critical elements"""
        
        # Login elements - multiple strategies
        self.selector_alternatives['login_button'] = [
            "//button[contains(text(), 'Login')]",
            "//button[contains(text(), 'Sign In')]",
            "//a[contains(text(), 'Login')]",
            "//button[@type='submit']",
            "//*[@id='login-btn']",
            "//button[contains(@class, 'login')]",
            "//*[contains(@class, 'login-button')]"
        ]
        
        self.selector_alternatives['phone_input'] = [
            "input[type='tel']",
            "input[name='phone']",
            "input[placeholder*='phone' or @placeholder*='Phone']",
            "input[id*='phone']",
            "input[class*='phone']",
            "#phone",
            "//input[@type='text' and contains(@placeholder, 'phone')]"
        ]
        
        self.selector_alternatives['password_input'] = [
            "input[type='password']",
            "input[name='password']",
            "input[id*='password']",
            "#password",
            "//input[@type='password']"
        ]
        
        self.selector_alternatives['place_bet_button'] = [
            "//button[contains(text(), 'Place')]",
            "//button[contains(text(), 'Bet')]",
            "//button[contains(text(), 'Place Bet')]",
            "//button[contains(@class, 'place-bet')]",
            "//button[@type='submit' and contains(@class, 'bet')]",
            "//*[contains(text(), 'Place Bet')]",
            "button[data-action='place-bet']"
        ]
        
        self.selector_alternatives['betslip_stake_input'] = [
            "input[type='number']",
            "input[placeholder*='stake']",
            "input[name*='amount']",
            "input[id*='stake']",
            "input[class*='stake']",
            "#stake",
            "//input[@type='number']"
        ]
        
        self.selector_alternatives['close_popup'] = [
            "//button[contains(text(), 'Close')]",
            "//button[contains(text(), 'OK')]",
            "//button[contains(@class, 'close')]",
            "//button[@aria-label='close']",
            "//*[contains(@class, 'close-icon')]",
            "//button[@type='button' and contains(@class, 'close')]"
        ]
        
        self.selector_alternatives['jetx_popup_close'] = [
            "//button[contains(@class, 'close')]",
            "//*[@aria-label='Close']",
            "//button[contains(text(), '×')]",
            "//*[contains(@class, 'modal-close')]",
            "//button[contains(@class, 'popup-close')]",
            "//div[contains(@class, 'popup')]//button[1]",
            "//*[@role='dialog']//button[contains(@class, 'close')]"
        ]
        
        # OdiLeague specific
        self.selector_alternatives['ov_un_filter'] = [
            "//button[contains(text(), 'OV/UN 2.5')]",
            "//button[contains(text(), 'Over/Under')]",
            "//*[contains(text(), 'OV/UN')]",
            "//button[contains(@class, 'ov-un')]",
            "//button[@data-market='TG25']"
        ]
        
        self.selector_alternatives['match_elements'] = [
            ".game.e",
            ".game",
            "[class*='match']",
            "[data-match-id]",
            "//div[contains(@class, 'match')]",
            ".match-card",
            "[class*='fixture']"
        ]
        
        self.selector_alternatives['odds_buttons'] = [
            "button[class*='odd']",
            ".odds button",
            "//button[contains(@class, 'odd')]",
            "[data-odds]",
            "//*[contains(@class, 'odds-pill')]"
        ]
    
    def find_element_with_fallback(self, driver, element_type: str, timeout: int = 5):
        """
        Try multiple selector strategies to find element
        Returns element or None if all strategies fail
        """
        if element_type not in self.selector_alternatives:
            log_message(f"⚠️  Unknown element type: {element_type}")
            return None
        
        selectors = self.selector_alternatives[element_type]
        
        # Try selectors in order of success rate (tracked internally)
        for selector in selectors:
            try:
                # Determine selector type
                if selector.startswith('//') or selector.startswith('/'):
                    # XPath
                    element = WebDriverWait(driver, timeout).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                else:
                    # CSS selector
                    element = WebDriverWait(driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                
                # Success! Track and return
                self._track_success(element_type, selector)
                return element
                
            except Exception:
                # This selector failed, try next
                self._track_failure(element_type, selector)
                continue
        
        # All selectors failed
        log_message(f"❌ All selectors failed for {element_type}")
        return None
    
    def find_elements_with_fallback(self, driver, element_type: str, timeout: int = 5):
        """Try multiple selector strategies to find multiple elements"""
        if element_type not in self.selector_alternatives:
            return []
        
        selectors = self.selector_alternatives[element_type]
        
        for selector in selectors:
            try:
                if selector.startswith('//') or selector.startswith('/'):
                    elements = driver.find_elements(By.XPATH, selector)
                else:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                
                if elements:
                    self._track_success(element_type, selector)
                    return elements
                    
            except Exception:
                self._track_failure(element_type, selector)
                continue
        
        return []
    
    def _track_success(self, element_type: str, selector: str):
        """Track successful selector usage"""
        key = f"{element_type}:{selector}"
        self.success_count[key] = self.success_count.get(key, 0) + 1
        
        # Reorder selectors to prioritize successful ones
        if selector in self.selector_alternatives.get(element_type, []):
            alternatives = self.selector_alternatives[element_type]
            current_index = alternatives.index(selector)
            
            # If this selector is not first and has high success, move it up
            if current_index > 0 and self.success_count.get(key, 0) > 10:
                alternatives.pop(current_index)
                # Insert at position based on success rate
                insert_pos = min(2, len(alternatives))
                alternatives.insert(insert_pos, selector)
    
    def _track_failure(self, element_type: str, selector: str):
        """Track selector failures"""
        key = f"{element_type}:{selector}"
        self.failure_count[key] = self.failure_count.get(key, 0) + 1
        
        # If selector fails too many times, move it down
        if self.failure_count.get(key, 0) > 5 and selector in self.selector_alternatives.get(element_type, []):
            alternatives = self.selector_alternatives[element_type]
            current_index = alternatives.index(selector)
            if current_index < len(alternatives) - 1:
                alternatives.pop(current_index)
                alternatives.append(selector)  # Move to end
    
    def detect_structure_change(self, driver, url: str) -> bool:
        """
        Detect if website structure has changed by checking page hash
        Returns True if structure changed
        """
        try:
            # Get page source hash
            page_source = driver.page_source
            current_hash = hashlib.md5(page_source.encode()).hexdigest()
            
            if self.last_structure_hash and self.last_structure_hash != current_hash:
                log_message(f"⚠️  Website structure change detected for {url}")
                # Clear caches to force re-discovery
                self.selector_cache.clear()
                self.last_structure_hash = current_hash
                return True
            
            self.last_structure_hash = current_hash
            return False
            
        except Exception as e:
            log_message(f"⚠️  Structure change detection error: {str(e)[:50]}")
            return False
    
    def add_custom_selector(self, element_type: str, selector: str, priority: int = 0):
        """Allow runtime addition of new selector strategies"""
        if element_type not in self.selector_alternatives:
            self.selector_alternatives[element_type] = []
        
        alternatives = self.selector_alternatives[element_type]
        if selector not in alternatives:
            # Insert at priority position
            insert_pos = min(priority, len(alternatives))
            alternatives.insert(insert_pos, selector)
            log_message(f"✅ Added custom selector for {element_type}: {selector}")


class AdaptiveRetryHandler:
    """Intelligent retry handler that adapts based on error patterns"""
    
    def __init__(self):
        self.retry_counts = {}
        self.backoff_times = {}
        self.error_patterns = {}
    
    def should_retry(self, operation: str, error: Exception, attempt: int, max_attempts: int = 3) -> bool:
        """Determine if operation should be retried"""
        
        if attempt >= max_attempts:
            return False
        
        error_type = type(error).__name__
        error_key = f"{operation}:{error_type}"
        
        # Track error patterns
        self.error_patterns[error_key] = self.error_patterns.get(error_key, 0) + 1
        
        # Don't retry certain errors
        non_retryable = [
            'InvalidCredentials',
            'AccountLocked',
            'ValidationError',
            'KeyboardInterrupt'
        ]
        
        if error_type in non_retryable:
            return False
        
        # Always retry network/timeout errors
        retryable = [
            'TimeoutError',
            'ConnectionError',
            'WebDriverException',
            'NoSuchElementException',
            'StaleElementReferenceException'
        ]
        
        if error_type in retryable:
            return True
        
        # Default: retry for unknown errors
        return True
    
    def get_backoff_time(self, operation: str, attempt: int) -> float:
        """Get adaptive backoff time based on operation history"""
        base_backoff = 1.0
        
        # Increase backoff if operation has failed before
        if operation in self.backoff_times:
            base_backoff = self.backoff_times[operation]
        
        # Exponential backoff with jitter
        backoff = base_backoff * (2 ** attempt) + (time.time() % 1)
        
        # Cap at 10 seconds
        return min(backoff, 10.0)
    
    def record_success(self, operation: str):
        """Record successful operation to reduce backoff"""
        if operation in self.backoff_times:
            self.backoff_times[operation] = max(0.5, self.backoff_times[operation] * 0.9)


class SpeedOptimizer:
    """Optimize operations for maximum speed"""
    
    @staticmethod
    def optimize_selenium_driver(driver):
        """Apply speed optimizations to Selenium driver"""
        try:
            # Disable images for faster loading
            prefs = {
                "profile.managed_default_content_settings.images": 2,
                "profile.default_content_setting_values.notifications": 2
            }
            
            # Already set during driver creation, but ensure here too
            driver.execute_cdp_cmd('Network.setBypassServiceWorker', {'bypass': True})
            driver.execute_cdp_cmd('Network.setCacheDisabled', {'cacheDisabled': True})
            
            # Set page load strategy to none (don't wait for page load)
            # Note: This should be set during driver creation, not here
            
        except Exception as e:
            log_message(f"⚠️  Speed optimization warning: {str(e)[:50]}")
    
    @staticmethod
    def parallel_execute(func, items: List, max_workers: int = 4):
        """Execute function on multiple items in parallel"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(func, item): item for item in items}
            
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=30)
                    results.append(result)
                except Exception as e:
                    log_message(f"⚠️  Parallel execution error: {str(e)[:50]}")
                    results.append(None)
        
        return results


class WebsiteResilienceSystem:
    """Main resilience coordinator"""
    
    def __init__(self):
        self.monitor = WebsiteStructureMonitor()
        self.retry_handler = AdaptiveRetryHandler()
        self.speed_optimizer = SpeedOptimizer()
        self.health_status = {
            'last_check': None,
            'status': 'healthy',
            'issues': []
        }
    
    def resilient_execute(self, operation: Callable, operation_name: str, 
                        max_retries: int = 3, **kwargs):
        """
        Execute operation with full resilience (retry, fallback, adaptation)
        
        Args:
            operation: Function to execute
            operation_name: Name for logging
            max_retries: Maximum retry attempts
            **kwargs: Arguments to pass to operation
        
        Returns:
            Operation result or None if all retries failed
        """
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                # Execute operation
                result = operation(**kwargs)
                
                # Record success
                self.retry_handler.record_success(operation_name)
                
                return result
                
            except Exception as e:
                last_error = e
                
                # Check if should retry
                if not self.retry_handler.should_retry(operation_name, e, attempt, max_retries):
                    log_message(f"❌ {operation_name} failed (non-retryable): {str(e)[:100]}")
                    break
                
                # Get backoff time
                backoff = self.retry_handler.get_backoff_time(operation_name, attempt)
                
                log_message(f"⚠️  {operation_name} attempt {attempt}/{max_retries} failed: {str(e)[:100]}")
                log_message(f"   Retrying in {backoff:.1f}s...")
                
                time.sleep(backoff)
        
        log_message(f"❌ {operation_name} failed after {max_retries} attempts")
        return None
    
    def find_element_safe(self, driver, element_type: str, timeout: int = 5):
        """Safely find element with fallback strategies"""
        return self.monitor.find_element_with_fallback(driver, element_type, timeout)
    
    def check_health(self, driver) -> Dict:
        """Check overall system health"""
        issues = []
        
        try:
            # Check if driver is alive
            if not driver or not hasattr(driver, 'current_url'):
                issues.append("Driver not initialized")
            
            # Check page load time
            # (Can be implemented if needed)
            
        except Exception as e:
            issues.append(f"Health check error: {str(e)[:50]}")
        
        self.health_status = {
            'last_check': datetime.now(),
            'status': 'healthy' if not issues else 'degraded',
            'issues': issues
        }
        
        return self.health_status


# Global instance
_resilience_system = None

def get_resilience_system() -> WebsiteResilienceSystem:
    """Get global resilience system instance"""
    global _resilience_system
    if _resilience_system is None:
        _resilience_system = WebsiteResilienceSystem()
    return _resilience_system

