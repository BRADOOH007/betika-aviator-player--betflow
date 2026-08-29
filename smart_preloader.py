"""
Smart Predictive Loading System
Makes the app FEEL instant by processing in background
"""

import threading
import time
from queue import Queue
from utils import log_message

class SmartPreloader:
    """
    Predictive background processor
    Starts work as soon as user pastes phone numbers
    """
    
    def __init__(self, engine):
        self.engine = engine
        self.current_accounts = []
        self.current_password = ""
        
        # Background processing
        self.process_queue = Queue()
        self.results_cache = {}  # {phone: {token, balance, timestamp}}
        
        # State
        self.is_processing = False
        self.last_update_time = 0
        self.debounce_delay = 1.0  # Wait 1 second after typing stops
        
        # Background worker thread
        self.worker_thread = None
        self.running = True
        
    def start(self):
        """Start background worker"""
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.running = True
            self.worker_thread = threading.Thread(target=self._background_worker, daemon=True)
            self.worker_thread.start()
            log_message("🔥 Smart preloader started - ready for instant responses")
    
    def stop(self):
        """Stop background worker"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=2)
    
    def on_accounts_changed(self, accounts_text, password):
        """
        Called when user types/pastes in phone number box
        Debounced - waits for user to stop typing
        """
        self.last_update_time = time.time()
        
        # Parse accounts
        accounts = self._parse_accounts(accounts_text)
        
        if accounts and password:
            # Queue for background processing
            self.process_queue.put({
                'accounts': accounts,
                'password': password,
                'timestamp': time.time()
            })
    
    def _parse_accounts(self, text):
        """Parse phone numbers from text"""
        if not text or not text.strip():
            return []
        
        # Split by newlines and clean
        lines = text.strip().split('\n')
        accounts = []
        
        for line in lines:
            line = line.strip()
            if line and line.isdigit() and len(line) >= 9:
                accounts.append(line)
        
        return accounts
    
    def _background_worker(self):
        """Background thread that processes accounts predictively"""
        while self.running:
            try:
                # Check if there's work to do
                if not self.process_queue.empty():
                    work_item = self.process_queue.get(timeout=0.1)
                    
                    # Debounce - wait to see if user is still typing
                    time_since_update = time.time() - work_item['timestamp']
                    if time_since_update < self.debounce_delay:
                        wait_time = self.debounce_delay - time_since_update
                        time.sleep(wait_time)
                        
                        # Check if there's newer work
                        if not self.process_queue.empty():
                            continue  # Skip this, process newer work
                    
                    # Process accounts in background
                    accounts = work_item['accounts']
                    password = work_item['password']
                    
                    self._process_accounts_background(accounts, password)
                
                else:
                    time.sleep(0.1)  # Wait for work
                    
            except Exception as e:
                log_message(f"⚠️ Preloader worker error: {e}", verbose=True)
                time.sleep(1)
    
    def _process_accounts_background(self, accounts, password):
        """
        Process accounts in background
        Extract tokens and cache them for instant access
        """
        if self.is_processing:
            return  # Already processing
        
        self.is_processing = True
        
        try:
            log_message(f"🔥 Smart preload: Processing {len(accounts)} accounts in background...", verbose=True)
            
            # Limit to first 20 accounts for preload (don't overwhelm)
            accounts_to_preload = accounts[:20]
            
            # Extract tokens in background
            for i, phone in enumerate(accounts_to_preload):
                if not self.running:
                    break
                
                # Check if already cached and fresh (< 5 minutes old)
                if phone in self.results_cache:
                    cached = self.results_cache[phone]
                    age = time.time() - cached.get('timestamp', 0)
                    if age < 300:  # 5 minutes
                        continue  # Skip, already have fresh data
                
                try:
                    # Try to get token
                    token = self.engine.load_token_for_phone(phone)
                    
                    if not token:
                        # Login in background
                        result = self.engine.login(phone, password)
                        if result and result.get('token'):
                            token = result['token']
                    
                    # Cache result
                    if token:
                        self.results_cache[phone] = {
                            'phone': phone,
                            'token': token,
                            'timestamp': time.time(),
                            'status': 'ready'
                        }
                        log_message(f"✅ Preloaded: {phone} ({i+1}/{len(accounts_to_preload)})", verbose=True)
                    
                    # Small delay to avoid overwhelming server
                    time.sleep(0.5)
                    
                except Exception as e:
                    log_message(f"⚠️ Preload failed for {phone}: {e}", verbose=True)
            
            log_message(f"✅ Smart preload complete: {len(self.results_cache)} accounts ready", verbose=True)
            
        except Exception as e:
            log_message(f"❌ Background processing error: {e}", verbose=True)
        
        finally:
            self.is_processing = False
    
    def get_cached_result(self, phone):
        """Get cached result for instant response"""
        return self.results_cache.get(phone)
    
    def get_cached_count(self):
        """Get number of cached accounts"""
        return len(self.results_cache)
    
    def clear_cache(self):
        """Clear cached results"""
        self.results_cache.clear()
        log_message("🗑️ Preload cache cleared", verbose=True)
    
    def get_status(self):
        """Get current status"""
        return {
            'is_processing': self.is_processing,
            'cached_accounts': len(self.results_cache),
            'queue_size': self.process_queue.qsize()
        }


# Example usage in GUI:
"""
# In BetFlowProGUI.__init__:
self.preloader = SmartPreloader(self.headless)
self.preloader.start()

# Connect to text box:
def on_phone_text_changed(event=None):
    accounts_text = self.phone_text.get("1.0", tk.END)
    password = self.password_entry.get()
    self.preloader.on_accounts_changed(accounts_text, password)
    
    # Show live status
    cached = self.preloader.get_cached_count()
    if cached > 0:
        self.log(f"🔥 {cached} accounts preloaded - ready for instant results!")

# Add binding:
self.phone_text.bind('<<Modified>>', on_phone_text_changed)
self.phone_text.bind('<KeyRelease>', on_phone_text_changed)

# In button handlers, check cache first:
def check_balance(self):
    # Check cache first
    cached = self.preloader.get_cached_result(phone)
    if cached:
        # Instant response from cache!
        return show_cached_balance(cached)
    else:
        # Fall back to normal processing
        return normal_check_balance()
"""

