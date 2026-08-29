import logging
import os
import time
from cryptography.fernet import Fernet
import json
import threading

# Persistence control (default: persistent/writes enabled)
PERSIST_ENABLED = True

def set_persistence(enabled: bool):
    global PERSIST_ENABLED
    PERSIST_ENABLED = bool(enabled)

def should_persist() -> bool:
    return PERSIST_ENABLED

# Simple global rate limiter (token bucket)
class RateLimiter:
    def __init__(self, rate_per_sec: float = 5.0, burst: float = None):
        self.rate = max(0.1, float(rate_per_sec))
        self.capacity = float(burst) if burst else self.rate
        self.tokens = self.capacity
        self.lock = threading.Lock()
        self.last_refill = time.time()

    def set_rate(self, rate_per_sec: float):
        with self.lock:
            self.rate = max(0.1, float(rate_per_sec))
            self.capacity = max(self.capacity, self.rate)

    def acquire(self):
        while True:
            now = time.time()
            with self.lock:
                elapsed = now - self.last_refill
                self.last_refill = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
            # Not enough tokens; sleep a bit
            time.sleep(0.01)

_RATE_LIMITER = RateLimiter(rate_per_sec=500.0, burst=500.0)  # ULTRA HIGH THROUGHPUT

def set_rate_limit(rps: float):
    _RATE_LIMITER.set_rate(rps)

def get_rate_limiter() -> RateLimiter:
    return _RATE_LIMITER

# Encryption key handling — ephemeral in stateless mode
KEY_FILE = 'config/encryption.key'

def _load_or_generate_key() -> bytes:
    if should_persist():
        try:
            if os.path.exists(KEY_FILE):
                with open(KEY_FILE, 'rb') as f:
                    return f.read()
            os.makedirs('config', exist_ok=True)
            key = Fernet.generate_key()
            with open(KEY_FILE, 'wb') as f:
                f.write(key)
            return key
        except Exception:
            # Fallback to ephemeral if write fails
            return Fernet.generate_key()
    # Stateless: ephemeral key only in memory
    return Fernet.generate_key()

ENCRYPTION_KEY = _load_or_generate_key()
cipher = Fernet(ENCRYPTION_KEY)

def encrypt_data(data):
    return cipher.encrypt(json.dumps(data).encode()).decode()

def decrypt_data(encrypted_data):
    return json.loads(cipher.decrypt(encrypted_data.encode()).decode())

_logger_initialized = False
VERBOSE_MODE = False  # Set to False for clean terminal output

def _ensure_logger():
    global _logger_initialized
    if _logger_initialized:
        return
    os.makedirs('logs', exist_ok=True)
    logging.basicConfig(
        filename='logs/betflow.log', level=logging.INFO,
        format='%(asctime)s - %(message)s'
    )
    _logger_initialized = True

def log_message(message, verbose=False):
    """
    Log a message to console and file.
    If verbose=True, the message is only logged to file (backend only).
    """
    # Print to console only if not verbose or if VERBOSE_MODE is enabled
    if not verbose or VERBOSE_MODE:
        try:
            print(message, flush=True)
        except UnicodeEncodeError:
            # Fallback: print ASCII-safe version
            print(message.encode('ascii', errors='replace').decode('ascii'), flush=True)
    
    # Always write to file if persistence is enabled
    if should_persist():
        try:
            _ensure_logger()
            logging.info(message.encode('utf-8', errors='ignore').decode('utf-8'))
        except Exception:
            pass

def setup_logging():
    if should_persist():
        os.makedirs('logs', exist_ok=True)
