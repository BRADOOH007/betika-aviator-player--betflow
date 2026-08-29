#!/usr/bin/env python3
"""
BetFlow Pro - Core Exception Classes and Circuit Breaker Pattern
Provides robust error handling and fault tolerance
"""
import time
from typing import Optional, Callable, Any
from datetime import datetime, timedelta
from utils import log_message


# ============================================================================
# EXCEPTION HIERARCHY
# ============================================================================

class BetFlowException(Exception):
    """Base exception for all BetFlow errors"""
    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now()
        super().__init__(self.message)


class AuthenticationError(BetFlowException):
    """Authentication and authorization failures"""
    pass


class LoginFailure(AuthenticationError):
    """Failed login attempt"""
    pass


class InvalidCredentials(AuthenticationError):
    """Invalid username or password"""
    pass


class TokenExpired(AuthenticationError):
    """Authentication token expired"""
    pass


class AccountLocked(AuthenticationError):
    """Account locked due to security reasons"""
    pass


class NetworkError(BetFlowException):
    """Network-related errors"""
    pass


class ConnectionTimeout(NetworkError):
    """Connection timeout"""
    pass


class RateLimitExceeded(NetworkError):
    """Rate limit exceeded (429 error)"""
    def __init__(self, message: str, retry_after: int = None, details: dict = None):
        super().__init__(message, details)
        self.retry_after = retry_after


class ServerError(NetworkError):
    """Server-side error (5xx)"""
    pass


class ValidationError(BetFlowException):
    """Input validation failures"""
    pass


class InvalidPhoneNumber(ValidationError):
    """Invalid phone number format"""
    pass


class InvalidBookingCode(ValidationError):
    """Invalid booking code"""
    pass


class InvalidStake(ValidationError):
    """Invalid stake amount"""
    pass


class BusinessLogicError(BetFlowException):
    """Business logic violations"""
    pass


class InsufficientBalance(BusinessLogicError):
    """Insufficient account balance"""
    pass


class BetPlacementFailed(BusinessLogicError):
    """Bet placement operation failed"""
    pass


class AccountInactive(BusinessLogicError):
    """Account is inactive or suspended"""
    pass


class DataError(BetFlowException):
    """Data-related errors"""
    pass


class DatabaseError(DataError):
    """Database operation failed"""
    pass


class CacheError(DataError):
    """Cache operation failed"""
    pass


# ============================================================================
# CIRCUIT BREAKER PATTERN
# ============================================================================

class CircuitBreakerState:
    """Circuit breaker states"""
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Failing, reject requests
    HALF_OPEN = "HALF_OPEN"  # Testing if recovered


class CircuitBreaker:
    """
    Circuit Breaker Pattern Implementation
    
    Prevents cascading failures by:
    - Tracking failure rates
    - Opening circuit after threshold
    - Allowing periodic recovery attempts
    - Auto-closing on success
    
    Usage:
        breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        result = breaker.call(risky_function, arg1, arg2)
    """
    
    def __init__(self, 
                 failure_threshold: int = 5,
                 success_threshold: int = 2,
                 timeout: int = 60,
                 name: str = "default"):
        """
        Initialize circuit breaker
        
        Args:
            failure_threshold: Number of failures before opening
            success_threshold: Number of successes to close from half-open
            timeout: Seconds to wait before attempting recovery
            name: Circuit breaker identifier for logging
        """
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.name = name
        
        # State tracking
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
        self.state = CircuitBreakerState.CLOSED
        
        # Metrics
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0
        self.state_changes = []
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker
        
        Args:
            func: Function to execute
            *args, **kwargs: Function arguments
            
        Returns:
            Function result
            
        Raises:
            BetFlowException: If circuit is open
            Original exception: If function fails
        """
        self.total_calls += 1
        
        # Check circuit state
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                raise BetFlowException(
                    f"Circuit breaker '{self.name}' is OPEN",
                    details={
                        'failure_count': self.failure_count,
                        'last_failure': self.last_failure_time,
                        'retry_in_seconds': self._seconds_until_retry()
                    }
                )
        
        # Attempt execution
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            raise
    
    def _on_success(self):
        """Handle successful execution"""
        self.total_successes += 1
        self.success_count += 1
        self.last_success_time = datetime.now()
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            if self.success_count >= self.success_threshold:
                self._transition_to_closed()
        elif self.state == CircuitBreakerState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0
    
    def _on_failure(self, exception: Exception):
        """Handle failed execution"""
        self.total_failures += 1
        self.failure_count += 1
        self.success_count = 0
        self.last_failure_time = datetime.now()
        
        log_message(f"⚠️ Circuit breaker '{self.name}' failure {self.failure_count}/{self.failure_threshold}: {exception}")
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self._transition_to_open()
        elif self.state == CircuitBreakerState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                self._transition_to_open()
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if not self.last_failure_time:
            return True
        
        time_since_failure = (datetime.now() - self.last_failure_time).total_seconds()
        return time_since_failure >= self.timeout
    
    def _seconds_until_retry(self) -> int:
        """Calculate seconds until retry is allowed"""
        if not self.last_failure_time:
            return 0
        
        time_since_failure = (datetime.now() - self.last_failure_time).total_seconds()
        return max(0, int(self.timeout - time_since_failure))
    
    def _transition_to_open(self):
        """Transition to OPEN state"""
        if self.state != CircuitBreakerState.OPEN:
            log_message(f"🔴 Circuit breaker '{self.name}' OPENED (failures: {self.failure_count})")
            self.state = CircuitBreakerState.OPEN
            self.state_changes.append({
                'timestamp': datetime.now(),
                'from': self.state,
                'to': CircuitBreakerState.OPEN,
                'reason': f'{self.failure_count} failures'
            })
    
    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state"""
        if self.state != CircuitBreakerState.HALF_OPEN:
            log_message(f"🟡 Circuit breaker '{self.name}' HALF-OPEN (attempting recovery)")
            self.state = CircuitBreakerState.HALF_OPEN
            self.success_count = 0
            self.state_changes.append({
                'timestamp': datetime.now(),
                'from': self.state,
                'to': CircuitBreakerState.HALF_OPEN,
                'reason': 'timeout elapsed'
            })
    
    def _transition_to_closed(self):
        """Transition to CLOSED state"""
        if self.state != CircuitBreakerState.CLOSED:
            log_message(f"🟢 Circuit breaker '{self.name}' CLOSED (recovered)")
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.state_changes.append({
                'timestamp': datetime.now(),
                'from': self.state,
                'to': CircuitBreakerState.CLOSED,
                'reason': f'{self.success_count} successful recoveries'
            })
    
    def reset(self):
        """Manually reset circuit breaker to CLOSED state"""
        log_message(f"🔄 Circuit breaker '{self.name}' manually reset")
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
    
    def get_stats(self) -> dict:
        """Get circuit breaker statistics"""
        return {
            'name': self.name,
            'state': self.state,
            'total_calls': self.total_calls,
            'total_successes': self.total_successes,
            'total_failures': self.total_failures,
            'success_rate': self.total_successes / self.total_calls if self.total_calls > 0 else 0,
            'current_failure_count': self.failure_count,
            'last_failure_time': self.last_failure_time,
            'last_success_time': self.last_success_time,
            'state_changes': len(self.state_changes)
        }


# ============================================================================
# RETRY DECORATOR WITH EXPONENTIAL BACKOFF
# ============================================================================

def retry_with_backoff(max_retries: int = 3, 
                      base_delay: float = 1.0,
                      max_delay: float = 60.0,
                      exceptions: tuple = (Exception,)):
    """
    Decorator for automatic retry with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exceptions: Tuple of exceptions to catch and retry
    
    Usage:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def unstable_function():
            # function code
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        log_message(f"❌ Max retries ({max_retries}) exceeded for {func.__name__}")
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    
                    log_message(f"🔄 Retry {attempt + 1}/{max_retries} for {func.__name__} in {delay:.1f}s: {e}")
                    time.sleep(delay)
            
        return wrapper
    return decorator


# ============================================================================
# EXCEPTION HANDLER UTILITIES
# ============================================================================

def handle_http_error(status_code: int, message: str = None, details: dict = None):
    """
    Convert HTTP status code to appropriate exception
    
    Args:
        status_code: HTTP status code
        message: Error message
        details: Additional error details
    
    Raises:
        Appropriate BetFlowException subclass
    """
    details = details or {}
    details['status_code'] = status_code
    
    if status_code == 401:
        raise InvalidCredentials(message or "Invalid credentials", details)
    elif status_code == 403:
        raise AccountLocked(message or "Account locked or forbidden", details)
    elif status_code == 404:
        raise BetFlowException(message or "Resource not found", details)
    elif status_code == 422:
        raise AccountInactive(message or "Account inactive", details)
    elif status_code == 429:
        retry_after = details.get('retry_after', 60)
        raise RateLimitExceeded(message or "Rate limit exceeded", retry_after, details)
    elif 500 <= status_code < 600:
        raise ServerError(message or "Server error", details)
    else:
        raise NetworkError(message or f"HTTP error {status_code}", details)


def is_retryable_error(exception: Exception) -> bool:
    """
    Determine if an error should be retried
    
    Args:
        exception: The exception to check
    
    Returns:
        True if error is retryable, False otherwise
    """
    retryable_types = (
        ConnectionTimeout,
        RateLimitExceeded,
        ServerError,
        NetworkError
    )
    
    # Don't retry authentication or validation errors
    non_retryable_types = (
        InvalidCredentials,
        ValidationError,
        AccountLocked,
        AccountInactive
    )
    
    if isinstance(exception, non_retryable_types):
        return False
    
    if isinstance(exception, retryable_types):
        return True
    
    # Generic network errors might be retryable
    return isinstance(exception, (ConnectionError, TimeoutError))
