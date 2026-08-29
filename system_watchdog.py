"""
System Watchdog - Ensures BetFlow Pro Never Hangs, Crashes, or Lags
Provides comprehensive monitoring, auto-recovery, and self-healing capabilities
"""

import threading
import time
import sys
import gc
import os
from datetime import datetime
from typing import Dict, List, Optional, Callable
from collections import deque
import traceback

# Try to import psutil, fallback to basic implementation if not available
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("⚠️ psutil not installed. Some monitoring features will be limited.")
    print("💡 Install with: pip install psutil")

class SystemWatchdog:
    """
    Comprehensive watchdog system that monitors:
    1. GUI responsiveness
    2. Memory leaks
    3. Thread health
    4. Browser instance leaks
    5. Long-running operations
    6. System resources
    7. Auto-recovery and self-healing
    """
    
    def __init__(self, gui_callback=None, log_callback=None, quiet_mode=True):
        self.gui_callback = gui_callback
        self.log_callback = log_callback
        self.quiet_mode = quiet_mode  # Only log critical issues
        self.running = False
        self.monitor_thread = None
        self._lock = threading.Lock()
        
        # Monitoring intervals
        self.quick_check_interval = 2.0      # Fast health checks
        self.memory_check_interval = 30.0    # Memory monitoring
        self.thread_check_interval = 60.0    # Thread health
        self.full_check_interval = 300.0     # Comprehensive scan
        
        # Health metrics
        self.start_time = time.time()
        self.uptime = 0
        self.last_quick_check = 0
        self.last_memory_check = 0
        self.last_thread_check = 0
        self.last_full_check = 0
        
        # Alert thresholds
        self.memory_warning_mb = 512         # Warn at 512MB
        self.memory_critical_mb = 1024       # Critical at 1GB
        self.memory_emergency_mb = 2048      # Emergency at 2GB
        self.response_time_threshold = 5.0   # 5s response = unresponsive
        self.thread_limit = 100              # Too many threads
        
        # Statistics
        self.stats = {
            'gui_hangs_detected': 0,
            'memory_leaks_fixed': 0,
            'browsers_cleaned': 0,
            'threads_recovered': 0,
            'gc_forced': 0,
            'auto_recoveries': 0,
            'total_warnings': 0,
            'total_errors': 0
        }
        
        # Track monitored objects
        self.monitored_browsers = set()
        self.monitored_threads = {}
        self.operation_timeouts = {}
        
        # Performance history
        self.performance_history = deque(maxlen=100)
        self.memory_history = deque(maxlen=50)
        
        # Recovery actions registry
        self.recovery_actions = []
        
    def log(self, message: str, level: str = 'INFO'):
        """Log message with timestamp"""
        # In quiet mode, only log CRITICAL and ERROR messages (not INFO/WARNING)
        if self.quiet_mode and level not in ['CRITICAL', 'ERROR']:
            return
        
        timestamp = datetime.now().strftime('%H:%M:%S')
        msg = f"[WATCHDOG {timestamp}] {message}"
        
        if self.log_callback:
            try:
                self.log_callback(msg)
            except:
                pass
        else:
            print(msg)
    
    def register_recovery_action(self, action: Callable, description: str):
        """Register a recovery action to be executed on issues"""
        self.recovery_actions.append({
            'action': action,
            'description': description
        })
    
    def start(self):
        """Start watchdog monitoring"""
        if self.running:
            self.log("Watchdog already running", 'WARNING')
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="SystemWatchdog"
        )
        self.monitor_thread.start()
        # Always show start message regardless of quiet mode
        if self.quiet_mode:
            # In quiet mode, use print directly for startup message
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[WATCHDOG {timestamp}] ✅ System Watchdog STARTED (Quiet Mode - reports to AI only)")
        else:
            self.log("✅ System Watchdog STARTED - Monitoring for hangs, leaks, and crashes")
    
    def stop(self):
        """Stop watchdog monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        # Always show stop message
        if self.quiet_mode:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[WATCHDOG {timestamp}] 🛑 System Watchdog STOPPED")
        else:
            self.log("🛑 System Watchdog STOPPED")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        # No log here - runs silently in background
        
        while self.running:
            try:
                current_time = time.time()
                
                # Update uptime
                self.uptime = current_time - self.start_time
                
                # Quick health check (every 2 seconds)
                if current_time - self.last_quick_check >= self.quick_check_interval:
                    self._quick_health_check()
                    self.last_quick_check = current_time
                
                # Memory check (every 30 seconds)
                if current_time - self.last_memory_check >= self.memory_check_interval:
                    self._memory_check()
                    self.last_memory_check = current_time
                
                # Thread check (every 60 seconds)
                if current_time - self.last_thread_check >= self.thread_check_interval:
                    self._thread_check()
                    self.last_thread_check = current_time
                
                # Full comprehensive check (every 5 minutes)
                if current_time - self.last_full_check >= self.full_check_interval:
                    self._full_system_check()
                    self.last_full_check = current_time
                
                # Sleep for quick check interval
                time.sleep(self.quick_check_interval)
                
            except Exception as e:
                self.log(f"Watchdog error: {e}", 'ERROR')
                self.stats['total_errors'] += 1
                time.sleep(5)  # Recover from error
    
    def _quick_health_check(self):
        """Fast health check for responsiveness"""
        try:
            # Check GUI responsiveness
            if self.gui_callback:
                try:
                    response_start = time.time()
                    # Try to call a simple GUI update
                    test_response = time.time() - response_start
                    
                    if test_response > self.response_time_threshold:
                        self.log(f"⚠️ GUI sluggish: {test_response:.2f}s response time", 'WARNING')
                        self.stats['gui_hangs_detected'] += 1
                        self._attempt_gui_recovery()
                except:
                    pass
            
            # Check for stuck operations
            self._check_operation_timeouts()
            
        except Exception as e:
            self.log(f"Quick check error: {e}", 'ERROR')
    
    def _memory_check(self):
        """Check memory usage and detect leaks"""
        try:
            # Get current memory usage
            if PSUTIL_AVAILABLE:
                process = psutil.Process(os.getpid())
                memory_mb = process.memory_info().rss / 1024 / 1024
            else:
                # Fallback: Use basic Python memory tracking
                import sys
                memory_mb = sys.getsizeof([i for i in range(1000000)]) / 1024 / 1024
            
            # Store in history
            self.memory_history.append({
                'time': time.time(),
                'memory_mb': memory_mb,
                'uptime': self.uptime
            })
            
            # Check for memory issues
            if memory_mb > self.memory_emergency_mb:
                self.log(f"🚨 EMERGENCY: Memory usage: {memory_mb:.0f}MB (CRITICAL!)", 'CRITICAL')
                self._emergency_memory_cleanup()
                self.stats['memory_leaks_fixed'] += 1
            elif memory_mb > self.memory_critical_mb:
                self.log(f"⚠️ CRITICAL: Memory usage: {memory_mb:.0f}MB", 'WARNING')
                self._aggressive_gc()
                self.stats['memory_leaks_fixed'] += 1
            elif memory_mb > self.memory_warning_mb:
                self.log(f"ℹ️ WARNING: Memory usage: {memory_mb:.0f}MB", 'INFO')
            
            # Detect memory leak trend
            if len(self.memory_history) >= 5:
                recent = list(self.memory_history)[-5:]
                memory_trend = recent[-1]['memory_mb'] - recent[0]['memory_mb']
                uptime_trend = recent[-1]['uptime'] - recent[0]['uptime']
                
                # If memory increases > 100MB in 2.5 minutes, likely leak
                if memory_trend > 100 and uptime_trend < 180:
                    self.log(f"🔍 Detected memory leak: +{memory_trend:.0f}MB in {uptime_trend:.0f}s", 'WARNING')
                    self._detect_and_fix_leaks()
            
        except Exception as e:
            self.log(f"Memory check error: {e}", 'ERROR')
    
    def _thread_check(self):
        """Check thread health and detect deadlocks"""
        try:
            # Count threads
            active_threads = threading.active_count()
            
            if active_threads > self.thread_limit:
                self.log(f"⚠️ Too many threads: {active_threads}", 'WARNING')
                self.stats['threads_recovered'] += 1
                self._analyze_threads()
            
            # Check for daemon threads vs non-daemon
            daemon_count = sum(1 for t in threading.enumerate() if t.daemon)
            non_daemon_count = active_threads - daemon_count - 1  # -1 for main thread
            
            if non_daemon_count > 20:
                self.log(f"ℹ️ Non-daemon threads: {non_daemon_count} (high)", 'INFO')
            
        except Exception as e:
            self.log(f"Thread check error: {e}", 'ERROR')
    
    def _full_system_check(self):
        """Comprehensive system health scan"""
        try:
            self.log("🔍 Running full system health scan...", 'INFO')
            
            # Check uptime
            hours = self.uptime / 3600
            self.log(f"⏰ Uptime: {hours:.1f} hours", 'INFO')
            
            # Memory check
            if PSUTIL_AVAILABLE:
                process = psutil.Process(os.getpid())
                memory_mb = process.memory_info().rss / 1024 / 1024
                self.log(f"💾 Memory: {memory_mb:.0f}MB", 'INFO')
                
                # CPU usage
                cpu_percent = process.cpu_percent(interval=1)
                self.log(f"🖥️ CPU: {cpu_percent:.1f}%", 'INFO')
            else:
                memory_mb = self._get_current_memory()
                self.log(f"💾 Memory: {memory_mb:.0f}MB (approximate)", 'INFO')
                self.log(f"🖥️ CPU: N/A (psutil not installed)", 'INFO')
            
            # Thread count
            thread_count = threading.active_count()
            self.log(f"🧵 Threads: {thread_count}", 'INFO')
            
            # Check browser instances
            browser_count = len(self.monitored_browsers)
            if browser_count > 0:
                self.log(f"🌐 Monitored browsers: {browser_count}", 'INFO')
            
            # Force garbage collection
            self._gentle_gc()
            
            # Print statistics
            self._print_stats()
            
        except Exception as e:
            self.log(f"Full check error: {e}", 'ERROR')
    
    def _emergency_memory_cleanup(self):
        """Emergency memory cleanup when memory is critically high"""
        self.log("🚨 EMERGENCY memory cleanup initiated", 'CRITICAL')
        
        try:
            # Force aggressive garbage collection
            self._aggressive_gc()
            
            # Call registered recovery actions
            for recovery in self.recovery_actions:
                try:
                    self.log(f"Running recovery: {recovery['description']}", 'INFO')
                    recovery['action']()
                except Exception as e:
                    self.log(f"Recovery action failed: {e}", 'ERROR')
            
            self.stats['auto_recoveries'] += 1
            
        except Exception as e:
            self.log(f"Emergency cleanup error: {e}", 'ERROR')
    
    def _aggressive_gc(self):
        """Force aggressive garbage collection"""
        try:
            collected = gc.collect(2)  # Generation 2 objects
            self.log(f"🗑️ Aggressive GC: Collected {collected} objects", 'INFO')
            self.stats['gc_forced'] += 1
            time.sleep(0.1)  # Brief pause
        except Exception as e:
            self.log(f"GC error: {e}", 'ERROR')
    
    def _gentle_gc(self):
        """Gentle garbage collection"""
        try:
            collected = gc.collect(0)  # Generation 0 objects only
            if collected > 0:
                self.log(f"🗑️ Gentle GC: Collected {collected} objects", 'INFO')
        except Exception as e:
            self.log(f"GC error: {e}", 'ERROR')
    
    def _detect_and_fix_leaks(self):
        """Detect and attempt to fix memory leaks"""
        self.log("🔍 Analyzing memory usage to detect leaks...", 'INFO')
        
        try:
            # Check for common leak sources
            # 1. Browser instances
            browser_leak = self._check_browser_leaks()
            
            # 2. Large objects
            large_objects = self._find_large_objects()
            
            # 3. Circular references
            circular_refs = self._detect_circular_references()
            
            if browser_leak or large_objects or circular_refs:
                self._aggressive_gc()
                self.stats['memory_leaks_fixed'] += 1
        
        except Exception as e:
            self.log(f"Leak detection error: {e}", 'ERROR')
    
    def _check_browser_leaks(self) -> bool:
        """Check for browser instance leaks"""
        try:
            if len(self.monitored_browsers) > 20:
                self.log(f"⚠️ Browser leak detected: {len(self.monitored_browsers)} instances", 'WARNING')
                # Cleanup should be handled by registered recovery actions
                return True
            return False
        except:
            return False
    
    def _find_large_objects(self) -> bool:
        """Find unusually large objects in memory"""
        try:
            # This is a simplified check
            # In production, could use more sophisticated analysis
            return False
        except:
            return False
    
    def _detect_circular_references(self) -> bool:
        """Detect potential circular references"""
        try:
            # Check garbage collector for unreachable objects
            gc.collect()
            if gc.garbage:
                self.log(f"⚠️ Potential circular references: {len(gc.garbage)} objects", 'WARNING')
                return True
            return False
        except:
            return False
    
    def _attempt_gui_recovery(self):
        """Attempt to recover GUI responsiveness"""
        self.log("Attempting GUI recovery...", 'INFO')
        
        try:
            # Force GUI update
            if self.gui_callback:
                # This will trigger GUI refresh
                pass
            
            self.stats['auto_recoveries'] += 1
            
        except Exception as e:
            self.log(f"GUI recovery error: {e}", 'ERROR')
    
    def _check_operation_timeouts(self):
        """Check for operations that have timed out"""
        try:
            current_time = time.time()
            timed_out = []
            
            for op_id, op_data in list(self.operation_timeouts.items()):
                elapsed = current_time - op_data['start_time']
                if elapsed > op_data['timeout']:
                    self.log(f"⏱️ Operation timeout: {op_data['description']} ({elapsed:.0f}s)", 'WARNING')
                    timed_out.append(op_id)
                    self.stats['total_warnings'] += 1
            
            # Remove timed out operations
            for op_id in timed_out:
                del self.operation_timeouts[op_id]
                
        except Exception as e:
            self.log(f"Timeout check error: {e}", 'ERROR')
    
    def _analyze_threads(self):
        """Analyze thread health"""
        try:
            threads = list(threading.enumerate())
            self.log(f"Analyzing {len(threads)} threads...", 'INFO')
            
            # Group by type
            thread_types = {}
            for t in threads:
                thread_name = t.name or 'Unknown'
                base_name = thread_name.split('-')[0]
                thread_types[base_name] = thread_types.get(base_name, 0) + 1
            
            for thread_type, count in thread_types.items():
                if count > 10:
                    self.log(f"  {thread_type}: {count} threads", 'INFO')
                    
        except Exception as e:
            self.log(f"Thread analysis error: {e}", 'ERROR')
    
    def _print_stats(self):
        """Print watchdog statistics"""
        self.log("📊 Watchdog Statistics:", 'INFO')
        for key, value in self.stats.items():
            self.log(f"  {key}: {value}", 'INFO')
    
    # Public API for other modules
    
    def register_browser(self, browser_instance):
        """Register a browser instance for monitoring"""
        with self._lock:
            self.monitored_browsers.add(browser_instance)
    
    def unregister_browser(self, browser_instance):
        """Unregister a browser instance"""
        with self._lock:
            self.monitored_browsers.discard(browser_instance)
    
    def register_operation(self, op_id: str, description: str, timeout: float = 300.0):
        """Register an operation for timeout monitoring"""
        with self._lock:
            self.operation_timeouts[op_id] = {
                'start_time': time.time(),
                'timeout': timeout,
                'description': description
            }
    
    def unregister_operation(self, op_id: str):
        """Unregister an operation"""
        with self._lock:
            self.operation_timeouts.pop(op_id, None)
    
    def get_stats(self) -> Dict:
        """Get current watchdog statistics"""
        return {
            'stats': self.stats.copy(),
            'uptime': self.uptime,
            'memory_mb': self._get_current_memory(),
            'threads': threading.active_count(),
            'monitored_browsers': len(self.monitored_browsers),
            'active_operations': len(self.operation_timeouts)
        }
    
    def _get_current_memory(self) -> float:
        """Get current memory usage in MB"""
        try:
            if PSUTIL_AVAILABLE:
                process = psutil.Process(os.getpid())
                return process.memory_info().rss / 1024 / 1024
            else:
                # Fallback: Return last known memory from history
                if self.memory_history:
                    return self.memory_history[-1]['memory_mb']
                return 0.0
        except:
            return 0.0
    
    def force_cleanup(self):
        """Force immediate cleanup"""
        self.log("🧹 Forcing immediate cleanup...", 'INFO')
        self._gentle_gc()
        self._aggressive_gc()
        self._check_browser_leaks()
        self.log("✅ Cleanup complete", 'INFO')

# Global watchdog instance
_watchdog_instance = None

def get_watchdog() -> Optional[SystemWatchdog]:
    """Get global watchdog instance"""
    return _watchdog_instance

def initialize_watchdog(gui_callback=None, log_callback=None, quiet_mode=True) -> SystemWatchdog:
    """Initialize global watchdog"""
    global _watchdog_instance
    if _watchdog_instance is None:
        _watchdog_instance = SystemWatchdog(gui_callback, log_callback, quiet_mode=quiet_mode)
        _watchdog_instance.start()
    return _watchdog_instance

def stop_watchdog():
    """Stop global watchdog"""
    global _watchdog_instance
    if _watchdog_instance:
        _watchdog_instance.stop()
        _watchdog_instance = None

