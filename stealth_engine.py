#!/usr/bin/env python3
"""
BetFlow Pro - Stealth Engine
Advanced human behavior simulation and anti-detection system
"""
import random
import time
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import numpy as np


class StealthEngine:
    """
    Intelligent stealth mode for undetectable automation
    
    Features:
    - Human-like timing patterns
    - Behavioral randomization
    - Anti-fingerprinting
    - Session management
    - Request pattern obfuscation
    """
    
    def __init__(self, aggressiveness: str = "balanced"):
        """
        Initialize stealth engine
        
        Args:
            aggressiveness: "fast", "balanced", "paranoid"
        """
        self.aggressiveness = aggressiveness
        self.session_start = datetime.now()
        self.request_history = []
        self.current_fingerprint = None
        self.human_patterns = self._load_human_patterns()
        
        # Configure timing based on aggressiveness
        self.timing_profiles = {
            "fast": {
                "min_action_delay": 0.1,
                "max_action_delay": 0.5,
                "typing_speed_min": 0.02,
                "typing_speed_max": 0.08,
                "reading_time_multiplier": 0.3,
                "mouse_movement_duration": 0.1,
                "between_accounts_min": 0.5,
                "between_accounts_max": 1.5
            },
            "balanced": {
                "min_action_delay": 0.8,
                "max_action_delay": 2.5,
                "typing_speed_min": 0.08,
                "typing_speed_max": 0.22,
                "reading_time_multiplier": 1.0,
                "mouse_movement_duration": 0.5,
                "between_accounts_min": 3.0,
                "between_accounts_max": 8.0
            },
            "paranoid": {
                "min_action_delay": 1.5,
                "max_action_delay": 4.0,
                "typing_speed_min": 0.12,
                "typing_speed_max": 0.30,
                "reading_time_multiplier": 1.5,
                "mouse_movement_duration": 0.8,
                "between_accounts_min": 5.0,
                "between_accounts_max": 12.0
            }
        }
        
        self.profile = self.timing_profiles[aggressiveness]
        
    def _load_human_patterns(self) -> Dict:
        """Load realistic human behavior patterns"""
        return {
            "common_mistakes": [
                "misclick", "backspace", "pause", "re-read"
            ],
            "browsing_patterns": [
                "scroll_down", "scroll_up", "hover", "click_away", "tab_switch"
            ],
            "mistake_probability": 0.03,  # 3% chance of human-like mistakes
            "distraction_probability": 0.02,  # 2% chance of getting "distracted"
        }
    
    def human_delay(self, action_type: str = "general") -> float:
        """
        Generate human-like delay based on action type
        
        Args:
            action_type: Type of action (click, type, read, scroll, etc.)
        
        Returns:
            Delay in seconds
        """
        base_delays = {
            "click": (self.profile["min_action_delay"], self.profile["max_action_delay"]),
            "type": (self.profile["typing_speed_min"], self.profile["typing_speed_max"]),
            "read": (1.0, 3.0),
            "scroll": (0.5, 1.5),
            "load": (0.8, 2.0),
            "think": (1.5, 4.0),
            "general": (self.profile["min_action_delay"], self.profile["max_action_delay"])
        }
        
        min_delay, max_delay = base_delays.get(action_type, base_delays["general"])
        
        # Use beta distribution for more realistic human timing (skewed towards faster)
        delay = np.random.beta(2, 5) * (max_delay - min_delay) + min_delay
        
        # Add occasional longer pauses (human distraction)
        if random.random() < self.human_patterns["distraction_probability"]:
            delay += random.uniform(2.0, 5.0)
        
        return delay
    
    def execute_with_human_timing(self, action_func, action_type: str = "general"):
        """
        Execute action with human-like delay
        
        Args:
            action_func: Function to execute
            action_type: Type of action for timing
        
        Returns:
            Result of action_func
        """
        # Pre-action delay (thinking time)
        time.sleep(self.human_delay(action_type))
        
        # Execute action
        result = action_func()
        
        # Post-action micro-delay
        time.sleep(random.uniform(0.05, 0.15))
        
        return result
    
    def simulate_typing(self, text: str, field_name: str = "input") -> List[Tuple[str, float]]:
        """
        Generate realistic typing pattern with mistakes and corrections
        
        Args:
            text: Text to type
            field_name: Name of field being typed into
        
        Returns:
            List of (character, delay) tuples
        """
        typing_pattern = []
        text_chars = list(text)
        
        i = 0
        while i < len(text_chars):
            char = text_chars[i]
            
            # Calculate typing delay with variance
            base_delay = random.uniform(
                self.profile["typing_speed_min"],
                self.profile["typing_speed_max"]
            )
            
            # Slower for complex characters
            if char.isupper() or char in "!@#$%^&*()_+{}|:\"<>?":
                base_delay *= 1.5
            
            # Occasional mistakes
            if random.random() < self.human_patterns["mistake_probability"]:
                # Type wrong character
                wrong_char = random.choice("qwertyuiopasdfghjklzxcvbnm")
                typing_pattern.append((wrong_char, base_delay))
                
                # Realize mistake (pause)
                typing_pattern.append(("", random.uniform(0.2, 0.5)))
                
                # Backspace
                typing_pattern.append(("\b", random.uniform(0.1, 0.2)))
                
                # Retype correctly
                typing_pattern.append((char, base_delay))
            else:
                typing_pattern.append((char, base_delay))
            
            i += 1
        
        return typing_pattern
    
    def generate_mouse_curve(self, start: Tuple[int, int], end: Tuple[int, int], 
                            num_points: int = 20) -> List[Tuple[int, int]]:
        """
        Generate realistic mouse movement curve (Bezier-like)
        
        Args:
            start: Starting coordinates (x, y)
            end: Ending coordinates (x, y)
            num_points: Number of points in curve
        
        Returns:
            List of (x, y) coordinates
        """
        # Add control points for natural curve
        control1_x = start[0] + random.uniform(-50, 50) + (end[0] - start[0]) * 0.3
        control1_y = start[1] + random.uniform(-50, 50) + (end[1] - start[1]) * 0.3
        
        control2_x = start[0] + random.uniform(-50, 50) + (end[0] - start[0]) * 0.7
        control2_y = start[1] + random.uniform(-50, 50) + (end[1] - start[1]) * 0.7
        
        points = []
        for i in range(num_points):
            t = i / (num_points - 1)
            
            # Cubic Bezier curve
            x = (1-t)**3 * start[0] + \
                3 * (1-t)**2 * t * control1_x + \
                3 * (1-t) * t**2 * control2_x + \
                t**3 * end[0]
            
            y = (1-t)**3 * start[1] + \
                3 * (1-t)**2 * t * control1_y + \
                3 * (1-t) * t**2 * control2_y + \
                t**3 * end[1]
            
            # Add micro-jitter for realism
            x += random.uniform(-2, 2)
            y += random.uniform(-2, 2)
            
            points.append((int(x), int(y)))
        
        return points
    
    def random_fingerprint(self) -> Dict:
        """
        Generate randomized browser fingerprint
        
        Returns:
            Fingerprint dictionary
        """
        screen_resolutions = [
            (1920, 1080), (1366, 768), (1440, 900), (1536, 864),
            (1280, 720), (1600, 900), (2560, 1440), (1920, 1200)
        ]
        
        platforms = [
            "Win32", "MacIntel", "Linux x86_64"
        ]
        
        user_agents = [
            # Chrome on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            # Firefox on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
            # Edge on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            # Chrome on Mac
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        
        languages = [
            "en-US,en;q=0.9",
            "en-GB,en;q=0.9",
            "en-US,en;q=0.9,es;q=0.8",
        ]
        
        timezones = [
            "Africa/Nairobi",  # Kenya
            "Africa/Lagos",    # Nigeria
            "Africa/Johannesburg",  # South Africa
            "Europe/London",
        ]
        
        screen = random.choice(screen_resolutions)
        
        fingerprint = {
            "user_agent": random.choice(user_agents),
            "platform": random.choice(platforms),
            "screen_width": screen[0],
            "screen_height": screen[1],
            "color_depth": 24,
            "language": random.choice(languages),
            "timezone": random.choice(timezones),
            "hardware_concurrency": random.choice([2, 4, 6, 8]),
            "device_memory": random.choice([4, 8, 16]),
            "webgl_vendor": "Google Inc. (Intel)",
            "webgl_renderer": random.choice([
                "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0)",
                "ANGLE (Intel, Intel(R) HD Graphics Direct3D11 vs_5_0 ps_5_0)"
            ]),
            "canvas_hash": hashlib.md5(str(random.random()).encode()).hexdigest()[:8]
        }
        
        self.current_fingerprint = fingerprint
        return fingerprint
    
    def get_request_headers(self, referer: str = None) -> Dict:
        """
        Generate realistic request headers
        
        Args:
            referer: Referer URL
        
        Returns:
            Headers dictionary
        """
        if not self.current_fingerprint:
            self.random_fingerprint()
        
        headers = {
            "User-Agent": self.current_fingerprint["user_agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": self.current_fingerprint["language"],
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": str(random.choice([0, 1])),
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin" if referer else "none",
            "Cache-Control": "max-age=0",
        }
        
        if referer:
            headers["Referer"] = referer
        
        return headers
    
    def intelligent_rate_limit(self, endpoint: str) -> float:
        """
        Calculate intelligent delay based on request history
        
        Args:
            endpoint: API endpoint being accessed
        
        Returns:
            Delay in seconds
        """
        now = datetime.now()
        
        # Track request
        self.request_history.append({
            "endpoint": endpoint,
            "timestamp": now
        })
        
        # Keep only last 100 requests
        if len(self.request_history) > 100:
            self.request_history = self.request_history[-100:]
        
        # Count recent requests to same endpoint
        recent_window = now - timedelta(seconds=60)
        recent_same_endpoint = [
            r for r in self.request_history
            if r["endpoint"] == endpoint and r["timestamp"] > recent_window
        ]
        
        # Base delay
        base_delay = random.uniform(
            self.profile["between_accounts_min"],
            self.profile["between_accounts_max"]
        )
        
        # Increase delay if too many recent requests (only for balanced/paranoid)
        if self.aggressiveness != "fast" and len(recent_same_endpoint) > 5:
            multiplier = 1 + (len(recent_same_endpoint) - 5) * 0.3
            base_delay *= multiplier
        
        # Add randomness to avoid patterns
        if self.aggressiveness == "fast":
            jitter = random.uniform(-0.2, 0.2)  # Minimal jitter for fast mode
        else:
            jitter = random.uniform(-0.5, 1.0)
        
        # For fast mode, don't enforce minimum delay
        if self.aggressiveness == "fast":
            return max(0.1, base_delay + jitter)
        else:
            return max(1.0, base_delay + jitter)
    
    def simulate_browsing_session(self) -> List[Dict]:
        """
        Generate realistic browsing session actions
        
        Returns:
            List of browsing actions
        """
        actions = []
        
        # Simulate user browsing before taking action
        browsing_actions = random.randint(2, 5)
        
        for _ in range(browsing_actions):
            action_type = random.choice(self.human_patterns["browsing_patterns"])
            
            if action_type == "scroll_down":
                actions.append({
                    "type": "scroll",
                    "direction": "down",
                    "amount": random.randint(100, 500),
                    "delay": self.human_delay("scroll")
                })
            elif action_type == "scroll_up":
                actions.append({
                    "type": "scroll",
                    "direction": "up",
                    "amount": random.randint(50, 200),
                    "delay": self.human_delay("scroll")
                })
            elif action_type == "hover":
                actions.append({
                    "type": "hover",
                    "duration": random.uniform(0.5, 2.0),
                    "delay": self.human_delay("general")
                })
            elif action_type == "click_away":
                actions.append({
                    "type": "click",
                    "target": "random",
                    "delay": self.human_delay("click")
                })
        
        return actions
    
    def get_session_duration(self) -> float:
        """Get current session duration in seconds"""
        return (datetime.now() - self.session_start).total_seconds()
    
    def should_take_break(self) -> bool:
        """
        Determine if a break should be taken (human behavior)
        
        Returns:
            True if break recommended
        """
        session_duration = self.get_session_duration()
        
        # Take breaks every 15-30 minutes in paranoid mode
        if self.aggressiveness == "paranoid":
            if session_duration > random.uniform(900, 1800):
                return True
        
        # Balanced mode: breaks every 30-60 minutes
        elif self.aggressiveness == "balanced":
            if session_duration > random.uniform(1800, 3600):
                return True
        
        return False
    
    def calculate_break_duration(self) -> float:
        """
        Calculate realistic break duration
        
        Returns:
            Break duration in seconds
        """
        if self.aggressiveness == "paranoid":
            return random.uniform(60, 180)  # 1-3 minutes
        elif self.aggressiveness == "balanced":
            return random.uniform(30, 90)   # 30-90 seconds
        else:
            return random.uniform(10, 30)   # 10-30 seconds
    
    def reset_session(self):
        """Reset session tracking"""
        self.session_start = datetime.now()
        self.request_history = []
        self.random_fingerprint()
    
    def get_stealth_stats(self) -> Dict:
        """
        Get stealth mode statistics
        
        Returns:
            Statistics dictionary
        """
        return {
            "aggressiveness": self.aggressiveness,
            "session_duration": self.get_session_duration(),
            "total_requests": len(self.request_history),
            "current_fingerprint": self.current_fingerprint,
            "timing_profile": self.profile,
            "break_recommended": self.should_take_break()
        }


class StealthSessionManager:
    """
    Manages multiple stealth sessions with intelligent switching
    """
    
    def __init__(self, num_profiles: int = 3):
        """
        Initialize session manager
        
        Args:
            num_profiles: Number of profiles to rotate
        """
        self.profiles = [StealthEngine() for _ in range(num_profiles)]
        self.current_profile_idx = 0
        self.profile_usage = {i: 0 for i in range(num_profiles)}
    
    def get_current_profile(self) -> StealthEngine:
        """Get current active stealth profile"""
        return self.profiles[self.current_profile_idx]
    
    def rotate_profile(self):
        """Rotate to next profile for variety"""
        self.profile_usage[self.current_profile_idx] += 1
        
        # Switch to least used profile
        self.current_profile_idx = min(
            self.profile_usage.keys(),
            key=lambda k: self.profile_usage[k]
        )
        
        # Reset the new profile
        self.profiles[self.current_profile_idx].reset_session()
    
    def should_rotate(self) -> bool:
        """Determine if profile should be rotated"""
        current_profile = self.get_current_profile()
        
        # Rotate after certain duration or request count
        if current_profile.get_session_duration() > 1800:  # 30 minutes
            return True
        
        if len(current_profile.request_history) > 50:
            return True
        
        return False


# Example usage
if __name__ == "__main__":
    # Test stealth engine
    stealth = StealthEngine(aggressiveness="balanced")
    
    print("🥷 Stealth Engine Test")
    print("=" * 50)
    
    # Test human delays
    print("\n⏱️ Human Delay Simulation:")
    for action in ["click", "type", "read", "scroll"]:
        delay = stealth.human_delay(action)
        print(f"  {action}: {delay:.3f}s")
    
    # Test typing simulation
    print("\n⌨️ Typing Simulation for 'test@example.com':")
    pattern = stealth.simulate_typing("test@example.com")
    total_time = sum(delay for _, delay in pattern)
    print(f"  Total typing time: {total_time:.2f}s")
    print(f"  Average per character: {total_time/len('test@example.com'):.3f}s")
    
    # Test fingerprint
    print("\n🖐️ Random Fingerprint:")
    fp = stealth.random_fingerprint()
    print(f"  User Agent: {fp['user_agent'][:50]}...")
    print(f"  Screen: {fp['screen_width']}x{fp['screen_height']}")
    print(f"  Language: {fp['language']}")
    
    # Test rate limiting
    print("\n⏳ Intelligent Rate Limiting:")
    for i in range(5):
        delay = stealth.intelligent_rate_limit("/api/login")
        print(f"  Request {i+1}: {delay:.2f}s delay")
    
    # Test mouse curve
    print("\n🖱️ Mouse Movement Curve:")
    curve = stealth.generate_mouse_curve((100, 100), (500, 300), num_points=10)
    print(f"  Generated {len(curve)} points")
    print(f"  Start: {curve[0]}, End: {curve[-1]}")
    
    print("\n✅ Stealth Engine Test Complete!")
