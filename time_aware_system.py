"""
Time-Aware System - Makes all processes aware of current time
Integrates with GUI clock for time-based operations
"""

from datetime import datetime, time
import pytz
from typing import Optional, Tuple


class TimeAwareSystem:
    """System for time-aware operations"""
    
    # EAT (East Africa Time) timezone
    EAT = pytz.timezone('Africa/Nairobi')
    
    def __init__(self):
        self.maintenance_hours = None  # Can be set by user
        self.peak_hours = None  # Can be set by user
    
    def get_current_time(self) -> datetime:
        """Get current time in EAT (Kenya Time)"""
        return datetime.now(self.EAT)
    
    def get_current_time_str(self, format_str: str = "%H:%M:%S") -> str:
        """Get current time as formatted string"""
        return self.get_current_time().strftime(format_str)
    
    def get_current_datetime_str(self) -> str:
        """Get current date and time as formatted string"""
        return self.get_current_time().strftime("%Y-%m-%d %H:%M:%S EAT")
    
    def is_business_hours(self, start_hour: int = 8, end_hour: int = 22) -> bool:
        """
        Check if current time is within business hours
        
        Args:
            start_hour: Business start hour (24-hour format, default 8 AM)
            end_hour: Business end hour (24-hour format, default 10 PM)
        
        Returns:
            True if within business hours
        """
        current = self.get_current_time()
        current_hour = current.hour
        
        if start_hour <= end_hour:
            # Normal case: e.g., 8 AM to 10 PM
            return start_hour <= current_hour < end_hour
        else:
            # Overnight case: e.g., 10 PM to 8 AM
            return current_hour >= start_hour or current_hour < end_hour
    
    def is_maintenance_window(self) -> bool:
        """
        Check if current time is during maintenance window
        Default: 2 AM - 4 AM EAT (off-peak hours)
        
        Returns:
            True if during maintenance window
        """
        current = self.get_current_time()
        current_hour = current.hour
        
        # Default maintenance: 2 AM - 4 AM EAT
        if self.maintenance_hours:
            start, end = self.maintenance_hours
            if start <= end:
                return start <= current_hour < end
            else:
                return current_hour >= start or current_hour < end
        
        # Default: 2 AM - 4 AM
        return 2 <= current_hour < 4
    
    def is_peak_hours(self) -> bool:
        """
        Check if current time is during peak betting hours
        Default: 6 PM - 11 PM EAT (evening betting peak)
        
        Returns:
            True if during peak hours
        """
        current = self.get_current_time()
        current_hour = current.hour
        
        if self.peak_hours:
            start, end = self.peak_hours
            if start <= end:
                return start <= current_hour < end
            else:
                return current_hour >= start or current_hour < end
        
        # Default peak: 6 PM - 11 PM EAT
        return 18 <= current_hour < 23
    
    def get_time_of_day(self) -> str:
        """Get time of day category"""
        current = self.get_current_time()
        hour = current.hour
        
        if 5 <= hour < 12:
            return "Morning"
        elif 12 <= hour < 17:
            return "Afternoon"
        elif 17 <= hour < 21:
            return "Evening"
        elif 21 <= hour < 24:
            return "Night"
        else:
            return "Late Night"
    
    def should_proceed_with_operation(self, operation_type: str = "general") -> Tuple[bool, str]:
        """
        Check if operation should proceed based on current time
        
        Args:
            operation_type: Type of operation (bet, withdraw, check_balance, etc.)
        
        Returns:
            Tuple of (should_proceed: bool, reason: str)
        """
        current_time = self.get_current_time()
        current_hour = current_time.hour
        
        # Check maintenance window
        if self.is_maintenance_window():
            return False, f"Maintenance window (current: {current_time.strftime('%H:%M')} EAT)"
        
        # Time-based warnings for certain operations
        if operation_type == "withdraw":
            # Withdrawals might be slower during peak hours
            if self.is_peak_hours():
                return True, f"Peak hours - withdrawals may be slower"
        
        if operation_type == "bet":
            # Betting is fine anytime (except maintenance)
            return True, "OK for betting"
        
        if operation_type == "check_balance":
            # Balance checks are fine anytime
            return True, "OK for balance checks"
        
        # Default: proceed
        return True, "OK"
    
    def format_duration(self, seconds: float) -> str:
        """
        Format duration in human-readable format
        
        Args:
            seconds: Duration in seconds
        
        Returns:
            Formatted string (e.g., "2h 15m 30s" or "45s")
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s" if secs > 0 else f"{minutes}m"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            parts = [f"{hours}h"]
            if minutes > 0:
                parts.append(f"{minutes}m")
            if secs > 0 and hours == 0:  # Only show seconds if less than 1 hour
                parts.append(f"{secs}s")
            return " ".join(parts)
    
    def get_eta(self, start_time: datetime, completed: int, total: int) -> Optional[str]:
        """
        Calculate ETA based on progress
        
        Args:
            start_time: Operation start time
            completed: Number of items completed
            total: Total number of items
        
        Returns:
            ETA string or None if cannot calculate
        """
        if completed == 0 or total == 0:
            return None
        
        elapsed = (datetime.now(self.EAT) - start_time).total_seconds()
        rate = completed / elapsed if elapsed > 0 else 0
        
        if rate > 0:
            remaining = total - completed
            eta_seconds = remaining / rate
            eta_time = datetime.now(self.EAT).timestamp() + eta_seconds
            eta_datetime = datetime.fromtimestamp(eta_time, self.EAT)
            return eta_datetime.strftime("%H:%M:%S EAT")
        
        return None
    
    def log_with_time(self, message: str, include_date: bool = False) -> str:
        """
        Format log message with timestamp
        
        Args:
            message: Log message
            include_date: Include date in timestamp
        
        Returns:
            Formatted log message with timestamp
        """
        if include_date:
            timestamp = self.get_current_datetime_str()
        else:
            timestamp = self.get_current_time_str()
        
        return f"[{timestamp}] {message}"


# Global instance
_time_system = None

def get_time_system() -> TimeAwareSystem:
    """Get global time-aware system instance"""
    global _time_system
    if _time_system is None:
        _time_system = TimeAwareSystem()
    return _time_system

