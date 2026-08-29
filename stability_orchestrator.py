#!/usr/bin/env python3
"""
BetFlow Pro - Stability Orchestrator
Coordinates all stability systems for 1000+ account processing
"""

import os
import time
import threading
import psutil
import gc
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
import logging

from account_queue_manager import AccountQueueManager, process_accounts_stable
from adaptive_rate_limiter import AdaptiveRateLimiter, create_stable_operation_wrapper

class StabilityOrchestrator:
    """
    Master coordinator for all stability systems
    Ensures 1000+ accounts can be processed without crashes or lags
    """

    def __init__(self):
        # Core components
        self.account_manager = AccountQueueManager(max_concurrent_accounts=5, max_memory_percent=75.0)
        self.rate_limiter = AdaptiveRateLimiter(base_delay=5.0, max_delay=300.0)
        self.performance_monitor = PerformanceMonitor()

        # System state
        self.is_initialized = False
        self.system_healthy = True
        self.emergency_mode = False

        # Stability settings
        self.stability_config = {
            'max_concurrent_accounts': 5,
            'batch_size': 25,
            'memory_threshold': 75.0,
            'cpu_threshold': 80.0,
            'disk_threshold': 90.0,
            'max_processing_time': 600,  # 10 minutes per account
            'health_check_interval': 30,
            'auto_recovery_attempts': 3,
            'emergency_cooldown': 300  # 5 minutes
        }

        # Monitoring
        self.monitoring_thread = None
        self.health_history = []
        self.performance_history = []

        # Callbacks
        self.health_callback: Optional[Callable] = None
        self.performance_callback: Optional[Callable] = None

    def initialize_system(self) -> bool:
        """Initialize all stability systems"""
        try:
            print("[INIT] Initializing Stability Orchestrator...")

            # Start system monitoring
            self._start_system_monitoring()

            # Start rate limiter monitoring
            self.rate_limiter.start_monitoring()

            # Pre-allocate resources and test system
            if not self._perform_system_health_check():
                print("[ERROR] System health check failed during initialization")
                return False

            # Configure garbage collection for stability
            gc.set_threshold(1000, 10, 10)  # Aggressive garbage collection
            gc.enable()

            self.is_initialized = True
            print("[OK] Stability Orchestrator initialized successfully")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to initialize stability orchestrator: {e}")
            return False

    def _start_system_monitoring(self):
        """Start comprehensive system monitoring"""
        self.monitoring_thread = threading.Thread(target=self._system_monitoring_loop, daemon=True)
        self.monitoring_thread.start()

    def _system_monitoring_loop(self):
        """Continuous system monitoring and health assessment"""
        while True:
            try:
                health_status = self._assess_system_health()

                # Store health history
                self.health_history.append({
                    'timestamp': datetime.now(),
                    'healthy': health_status['overall_healthy'],
                    'metrics': health_status
                })

                # Keep only last 100 health checks
                if len(self.health_history) > 100:
                    self.health_history = self.health_history[-100:]

                # Update system health status
                was_healthy = self.system_healthy
                self.system_healthy = health_status['overall_healthy']

                # Handle health changes
                if not self.system_healthy and was_healthy:
                    self._handle_health_degradation(health_status)
                elif self.system_healthy and not was_healthy:
                    self._handle_health_recovery()

                # Performance monitoring
                perf_metrics = self.performance_monitor.get_metrics()
                self.performance_history.append({
                    'timestamp': datetime.now(),
                    'metrics': perf_metrics
                })

                # Callbacks
                if self.health_callback:
                    self.health_callback(health_status)

                if self.performance_callback:
                    self.performance_callback(perf_metrics)

            except Exception as e:
                print(f"Monitoring error: {e}")

            time.sleep(self.stability_config['health_check_interval'])

    def _assess_system_health(self) -> Dict:
        """Comprehensive system health assessment"""
        try:
            # Memory health
            memory = psutil.virtual_memory()
            memory_healthy = memory.percent < self.stability_config['memory_threshold']

            # CPU health
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_healthy = cpu_percent < self.stability_config['cpu_threshold']

            # Disk health
            disk = psutil.disk_usage('/')
            disk_healthy = disk.percent < self.stability_config['disk_threshold']

            # Network health (basic connectivity check)
            network_healthy = self._check_network_health()

            # Process health
            process = psutil.Process()
            process_healthy = process.memory_percent() < self.stability_config['memory_threshold']

            # Rate limiter health - more lenient during initialization
            rate_limiter_stats = self.rate_limiter.get_stats()
            total_ops = rate_limiter_stats.get('total_operations', 0)
            if total_ops == 0:
                rate_limiter_healthy = True  # No operations yet, consider healthy
            else:
                rate_limiter_healthy = rate_limiter_stats['success_rate'] > 0.5

            # Overall assessment
            overall_healthy = all([
                memory_healthy, cpu_healthy, disk_healthy,
                network_healthy, process_healthy, rate_limiter_healthy
            ])

            return {
                'overall_healthy': overall_healthy,
                'memory': {'usage': memory.percent, 'healthy': memory_healthy},
                'cpu': {'usage': cpu_percent, 'healthy': cpu_healthy},
                'disk': {'usage': disk.percent, 'healthy': disk_healthy},
                'network': {'healthy': network_healthy},
                'process': {'memory_usage': process.memory_percent(), 'healthy': process_healthy},
                'rate_limiter': {'stats': rate_limiter_stats, 'healthy': rate_limiter_healthy}
            }

        except Exception as e:
            print(f"Health assessment error: {e}")
            return {'overall_healthy': False, 'error': str(e)}

    def _check_network_health(self) -> bool:
        """Basic network connectivity check"""
        try:
            # Try to connect to a reliable host
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            return True
        except:
            return False

    def _handle_health_degradation(self, health_status: Dict):
        """Handle system health degradation"""
        print("[WARN] System health degraded - initiating stability measures")

        # Reduce concurrency
        self.account_manager.max_concurrent_accounts = max(1, self.account_manager.max_concurrent_accounts // 2)

        # Increase delays
        self.rate_limiter.base_delay *= 1.5

        # Force garbage collection
        gc.collect()

        # Log degradation details
        unhealthy_components = [k for k, v in health_status.items()
                              if isinstance(v, dict) and not v.get('healthy', True)]
        print(f"Unhealthy components: {unhealthy_components}")

    def _handle_health_recovery(self):
        """Handle system health recovery"""
        print("[RECOVER] System health recovered - optimizing performance")

        # Gradually increase concurrency
        self.account_manager.max_concurrent_accounts = min(
            self.stability_config['max_concurrent_accounts'],
            self.account_manager.max_concurrent_accounts + 1
        )

        # Gradually reduce delays
        self.rate_limiter.base_delay = max(
            3.0,  # Minimum delay
            self.rate_limiter.base_delay * 0.9
        )

    def _perform_system_health_check(self) -> bool:
        """Perform initial system health check"""
        print("[HEALTH] Performing initial system health check...")

        health = self._assess_system_health()

        if not health['overall_healthy']:
            print("[ERROR] Initial health check failed:")
            for component, status in health.items():
                if isinstance(status, dict) and not status.get('healthy', True):
                    print(f"  - {component}: {status}")
            return False

        print("[SAFE] Initial health check passed")
        return True

    def process_accounts_stable(self,
                               account_processor: Callable,
                               account_file: str = "test_accounts.txt") -> Dict:
        """
        Process accounts with maximum stability

        Args:
            account_processor: Function to process individual accounts
            account_file: Path to account file

        Returns:
            Processing results and statistics
        """

        if not self.is_initialized:
            if not self.initialize_system():
                return {"error": "Failed to initialize stability systems"}

        # Wrap account processor with stability enhancements
        stable_processor = self._create_stable_account_processor(account_processor)

        # Configure account manager with stability settings
        self.account_manager.max_concurrent_accounts = self.stability_config['max_concurrent_accounts']

        # Progress callback with stability monitoring
        def progress_callback(phone, success, progress, stats):
            print(".1f"
                  f"Success: {stats['successful_accounts']}, "
                  f"Failed: {stats['failed_accounts']}, "
                  f"Health: {'OK' if self.system_healthy else 'DEGRADED'}")

        self.account_manager.progress_callback = progress_callback

        # Start processing
        print("[SAFE] Starting ultra-stable account processing...")
        print(f"Configuration: {self.stability_config['max_concurrent_accounts']} concurrent, "
              f"batches of {self.stability_config['batch_size']}")

        try:
            self.account_manager.start_processing(
                stable_processor,
                batch_size=self.stability_config['batch_size']
            )

            results = self.account_manager.get_stats()
            results['stability_metrics'] = self._get_stability_report()
            return results

        except Exception as e:
            print(f"Processing error: {e}")
            return {"error": str(e), "stability_metrics": self._get_stability_report()}

    def _create_stable_account_processor(self, original_processor: Callable) -> Callable:
        """Create a stability-enhanced account processor"""
        stable_wrapper = create_stable_operation_wrapper(original_processor, self.rate_limiter)

        def stable_account_processor(phone: str) -> bool:
            """Process account with comprehensive stability measures"""
            try:
                # Pre-processing health check
                if not self.system_healthy:
                    print(f"[SAFE] System unhealthy - delaying processing of {phone}")
                    time.sleep(10)
                    return False

                # Memory check
                if psutil.virtual_memory().percent > self.stability_config['memory_threshold']:
                    print(f"[SAFE] High memory usage - forcing garbage collection before {phone}")
                    gc.collect()

                # Process with timeout
                result = stable_wrapper(phone)

                # Post-processing cleanup
                gc.collect()

                return result.get('success', False)

            except Exception as e:
                print(f"Account processor error for {phone}: {e}")
                return False

        return stable_account_processor

    def _get_stability_report(self) -> Dict:
        """Generate comprehensive stability report"""
        return {
            'system_health': self.system_healthy,
            'emergency_mode': self.emergency_mode,
            'rate_limiter_stats': self.rate_limiter.get_stats(),
            'performance_metrics': self.performance_monitor.get_metrics(),
            'health_history_summary': self._summarize_health_history(),
            'stability_config': self.stability_config.copy()
        }

    def _summarize_health_history(self) -> Dict:
        """Summarize health history"""
        if not self.health_history:
            return {'total_checks': 0}

        total_checks = len(self.health_history)
        healthy_checks = sum(1 for h in self.health_history if h['healthy'])

        return {
            'total_checks': total_checks,
            'healthy_checks': healthy_checks,
            'health_rate': healthy_checks / total_checks if total_checks > 0 else 0,
            'last_health_status': self.health_history[-1] if self.health_history else None
        }

    def emergency_pause(self, reason: str = "Manual emergency pause"):
        """Emergency pause all operations"""
        print(f"[SAFE] EMERGENCY PAUSE: {reason}")
        self.emergency_mode = True
        self.account_manager.pause()

        # Aggressive system cleanup
        gc.collect()
        self.rate_limiter.base_delay *= 2

    def emergency_resume(self):
        """Resume from emergency pause"""
        print("[SAFE] Resuming from emergency pause")
        self.emergency_mode = False
        self.account_manager.resume()

        # Gradually restore normal operation
        self.rate_limiter.base_delay = max(3.0, self.rate_limiter.base_delay * 0.8)

    def adjust_stability_settings(self, new_settings: Dict):
        """Dynamically adjust stability settings"""
        for key, value in new_settings.items():
            if key in self.stability_config:
                old_value = self.stability_config[key]
                self.stability_config[key] = value
                print(f"Adjusted {key}: {old_value} -> {value}")

    def shutdown(self):
        """Graceful shutdown of all stability systems"""
        print("[SAFE] Shutting down stability orchestrator...")

        self.account_manager.shutdown()
        self.rate_limiter.stop_monitoring()

        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=10)

        print("[SAFE] Stability orchestrator shutdown complete")


class PerformanceMonitor:
    """Monitor system performance metrics"""

    def __init__(self):
        self.metrics_history = []
        self.start_time = datetime.now()

    def get_metrics(self) -> Dict:
        """Get current performance metrics"""
        process = psutil.Process()

        return {
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': process.memory_percent(),
            'memory_mb': process.memory_info().rss / 1024 / 1024,
            'threads': process.num_threads(),
            'open_files': len(process.open_files()),
            'connections': len(process.connections())
        }


# Global instance
stability_orchestrator = StabilityOrchestrator()


def process_accounts_ultra_stable(account_processor: Callable,
                                 account_file: str = "test_accounts.txt") -> Dict:
    """
    Process accounts with ultra-high stability for 1000+ accounts

    Args:
        account_processor: Function to process individual accounts
        account_file: Path to account file

    Returns:
        Processing results with stability metrics
    """
    return stability_orchestrator.process_accounts_stable(account_processor, account_file)
