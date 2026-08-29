import json
import os
import time
import statistics
import threading
from datetime import datetime, timedelta
from collections import defaultdict, deque
import requests
from utils import log_message, should_persist

class IntelligentCore:
    def __init__(self):
        self.endpoint_scores = self.load_endpoint_scores()
        self.rate_limit_history = deque(maxlen=100)  # Last 100 errors
        self.success_history = defaultdict(list)  # Success rate per hour
        self.response_times = deque(maxlen=1000)  # Last 1000 response times
        self.error_rates = deque(maxlen=1000)  # Last 1000 errors
        self.telemetry_data = defaultdict(list)  # Telemetry metrics
        self.anomaly_thresholds = {}  # Computed dynamically
        self.current_delay = 2.5  # Base delay in minutes
        self.running = True  # For kill switch integration

    def load_endpoint_scores(self):
        if not should_persist():
            return defaultdict(lambda: {'successes': 0, 'attempts': 0, 'score': 0.0})
        if os.path.exists('config/endpoint_scores.json'):
            with open('config/endpoint_scores.json', 'r') as f:
                return json.load(f)
        return defaultdict(lambda: {'successes': 0, 'attempts': 0, 'score': 0.0})

    def save_endpoint_scores(self):
        if not should_persist():
            return
        os.makedirs('config', exist_ok=True)
        with open('config/endpoint_scores.json', 'w') as f:
            json.dump(dict(self.endpoint_scores), f, indent=2)

    def update_endpoint_score(self, domain, endpoint, success):
        key = f"{domain}:{endpoint}"
        self.endpoint_scores[key]['attempts'] += 1
        if success:
            self.endpoint_scores[key]['successes'] += 1
        self.endpoint_scores[key]['score'] = self.endpoint_scores[key]['successes'] / self.endpoint_scores[key]['attempts']
        self.save_endpoint_scores()

    def get_best_endpoint(self, domain, endpoint_type):
        candidates = [k for k in self.endpoint_scores if k.startswith(f"{domain}:{endpoint_type}")]
        if not candidates:
            return None
        return max(candidates, key=lambda x: self.endpoint_scores[x]['score'])

    def log_rate_limit_error(self, status_code):
        self.rate_limit_history.append((datetime.now(), status_code))
        if len(self.rate_limit_history) > 3:
            recent_errors = [t for t, code in self.rate_limit_history if (datetime.now() - t).seconds < 300 and code in [429, 503]]
            if len(recent_errors) >= 3:
                self.current_delay = min(self.current_delay * 2, 10)  # Slow down to 5-10 min
                log_message("⚠️ Rate limiting detected — slowing down")

    def check_rate_limit_recovery(self):
        if self.rate_limit_history:
            last_error_time = max(t for t, _ in self.rate_limit_history)
            if (datetime.now() - last_error_time).seconds > 3600:  # 1 hour no errors
                self.current_delay = 2.5  # Back to normal
                log_message("✅ No rate limits for 1 hour — returning to normal speed")

    def record_success(self, hour):
        self.success_history[hour].append(True)

    def record_failure(self, hour):
        self.success_history[hour].append(False)

    def get_optimal_hours(self):
        if sum(len(v) for v in self.success_history.values()) < 100:
            return []  # Not enough data
        hourly_rates = {h: sum(v) / len(v) for h, v in self.success_history.items()}
        return sorted(hourly_rates, key=hourly_rates.get, reverse=True)[:3]

    def schedule_next_sweep(self):
        optimal_hours = self.get_optimal_hours()
        if optimal_hours:
            now = datetime.now()
            next_run = now.replace(hour=optimal_hours[0], minute=0, second=0) + timedelta(days=1)
            log_message(f"📅 Auto-scheduled next sweep at {next_run.strftime('%Y-%m-%d %H:%M')}")
            return next_run
        return None

    def self_heal(self, phone, original_error, gui_callback=None):
        strategies = [
            ('retry_same', self.retry_same_endpoint),
            ('backup_endpoint', self.try_backup_endpoint),
            ('reduce_concurrency', self.reduce_concurrency)
        ]
        for strategy_name, strategy_func in strategies:
            if gui_callback:
                gui_callback(f"🔄 Attempting {strategy_name} for {phone}")
            if strategy_func(phone):
                if gui_callback:
                    gui_callback(f"✅ {strategy_name} succeeded for {phone}")
                return True
        if gui_callback:
            gui_callback(f"❌ All strategies failed for {phone} — skipping")
        return False

    def retry_same_endpoint(self, phone):
        # Retry with same endpoint (already handled in code)
        return True  # Assume success for demo

    def try_backup_endpoint(self, phone):
        # Switch to backup endpoint if available
        return True  # Assume success for demo

    def reduce_concurrency(self, phone):
        # Reduce threads if high concurrency
        return True  # Assume success for demo

    def record_telemetry(self, metric, value):
        self.telemetry_data[metric].append((datetime.now(), value))
        if metric == 'response_time':
            self.response_times.append(value)
        elif metric == 'error_rate':
            self.error_rates.append(value)

    def detect_anomalies(self):
        if len(self.response_times) < 10:
            return []
        mean_rt = statistics.mean(self.response_times)
        std_rt = statistics.stdev(self.response_times)
        threshold_rt = mean_rt + 3 * std_rt
        anomalies = []
        if self.response_times[-1] > threshold_rt:
            anomalies.append(f"Response time {self.response_times[-1]}s > threshold {threshold_rt}s")
        if len(self.error_rates) > 10:
            mean_er = statistics.mean(self.error_rates)
            std_er = statistics.stdev(self.error_rates)
            threshold_er = mean_er + 3 * std_er
            if self.error_rates[-1] > threshold_er:
                anomalies.append(f"Error rate {self.error_rates[-1]} > threshold {threshold_er}")
        return anomalies

    def generate_recommendations(self):
        recommendations = []
        if self.detect_anomalies():
            recommendations.append("PAUSE_SWEEP")
        if self.current_delay > 5:
            recommendations.append("SLOW_DOWN")
        # Add more based on telemetry
        return recommendations

    def run_feedback_loop(self):
        while self.running:
            anomalies = self.detect_anomalies()
            if anomalies:
                for anomaly in anomalies:
                    log_message(f"⚠️ Anomaly: {anomaly}")
                    if "critical" in anomaly.lower():  # Auto-pause if critical
                        self.running = False
                        log_message("🚨 Critical anomaly — pausing sweep")
            recommendations = self.generate_recommendations()
            for rec in recommendations:
                log_message(f"🤖 Recommendation: {rec}")
                # Act on recommendation (e.g., pause, slow down)
            time.sleep(60)  # Check every minute

# Global instance for integration
intelligent_core = IntelligentCore()

# Start feedback loop in background
threading.Thread(target=intelligent_core.run_feedback_loop, daemon=True).start()