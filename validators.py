#!/usr/bin/env python3
"""
BetFlow Pro - Input Validation and Sanitization
Ensures data integrity and security
"""
import re
from typing import Tuple, List, Optional
from betflow_exceptions import (
    ValidationError, InvalidPhoneNumber, 
    InvalidBookingCode, InvalidStake
)


class InputValidator:
    """Comprehensive input validation for BetFlow operations"""
    
    # Phone number patterns
    KENYA_PHONE_PATTERN = r'^254\d{9}$'
    PHONE_PATTERNS = {
        'kenya': KENYA_PHONE_PATTERN,
        'international': r'^\+?\d{10,15}$'
    }
    
    # Booking code pattern (alphanumeric, 6-20 characters)
    BOOKING_CODE_PATTERN = r'^[A-Za-z0-9]{6,20}$'
    
    # Password requirements
    MIN_PASSWORD_LENGTH = 4
    MAX_PASSWORD_LENGTH = 128
    
    # Stake limits
    MIN_STAKE = 1.0
    MAX_STAKE = 1000000.0  # 1M KES
    
    @classmethod
    def validate_phone(cls, phone: str, normalize: bool = True) -> Tuple[bool, str, Optional[str]]:
        """
        Validate phone number format
        
        Args:
            phone: Phone number to validate
            normalize: Whether to normalize the phone number
        
        Returns:
            Tuple of (is_valid, normalized_phone, error_message)
        """
        if not phone:
            return False, phone, "Phone number cannot be empty"
        
        # Remove whitespace
        phone = phone.strip()
        
        # Normalize Kenyan numbers
        if normalize:
            phone = cls.normalize_kenya_phone(phone)
        
        # Validate format
        if not re.match(cls.PHONE_PATTERNS['kenya'], phone):
            return False, phone, f"Invalid phone format. Expected format: 254XXXXXXXXX"
        
        return True, phone, None
    
    @classmethod
    def normalize_kenya_phone(cls, phone: str) -> str:
        """
        Normalize Kenyan phone number to 254XXXXXXXXX format
        
        Args:
            phone: Phone number to normalize
        
        Returns:
            Normalized phone number
        """
        # Remove all non-digit characters
        phone = re.sub(r'\D', '', phone)
        
        # Handle different formats
        if phone.startswith('254'):
            return phone
        elif phone.startswith('0'):
            return '254' + phone[1:]
        elif phone.startswith('+254'):
            return phone[1:]
        elif phone.startswith('7') or phone.startswith('1'):
            # Assume Kenyan number without country code
            return '254' + phone
        
        return phone
    
    @classmethod
    def validate_phone_list(cls, phones: List[str], normalize: bool = True) -> Tuple[List[str], List[dict]]:
        """
        Validate and normalize a list of phone numbers
        
        Args:
            phones: List of phone numbers
            normalize: Whether to normalize phone numbers
        
        Returns:
            Tuple of (valid_phones, errors)
            errors is a list of dicts with 'phone', 'error' keys
        """
        valid_phones = []
        errors = []
        
        for idx, phone in enumerate(phones):
            is_valid, normalized_phone, error_msg = cls.validate_phone(phone, normalize)
            
            if is_valid:
                # Avoid duplicates
                if normalized_phone not in valid_phones:
                    valid_phones.append(normalized_phone)
                else:
                    errors.append({
                        'line': idx + 1,
                        'phone': phone,
                        'error': 'Duplicate phone number'
                    })
            else:
                errors.append({
                    'line': idx + 1,
                    'phone': phone,
                    'error': error_msg
                })
        
        return valid_phones, errors
    
    @classmethod
    def validate_booking_code(cls, booking_code: str) -> Tuple[bool, str]:
        """
        Validate booking code format
        
        Args:
            booking_code: Booking code to validate
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not booking_code:
            return False, "Booking code cannot be empty"
        
        # Remove whitespace
        booking_code = booking_code.strip()
        
        # Check length
        if len(booking_code) < 6:
            return False, "Booking code must be at least 6 characters"
        
        if len(booking_code) > 20:
            return False, "Booking code cannot exceed 20 characters"
        
        # Check format (alphanumeric only)
        if not re.match(cls.BOOKING_CODE_PATTERN, booking_code):
            return False, "Booking code must contain only letters and numbers"
        
        return True, None
    
    @classmethod
    def validate_password(cls, password: str) -> Tuple[bool, str]:
        """
        Validate password
        
        Args:
            password: Password to validate
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not password:
            return False, "Password cannot be empty"
        
        if len(password) < cls.MIN_PASSWORD_LENGTH:
            return False, f"Password must be at least {cls.MIN_PASSWORD_LENGTH} characters"
        
        if len(password) > cls.MAX_PASSWORD_LENGTH:
            return False, f"Password cannot exceed {cls.MAX_PASSWORD_LENGTH} characters"
        
        return True, None
    
    @classmethod
    def validate_stake(cls, stake: float, balance: float = None, min_stake: float = None, max_stake: float = None) -> Tuple[bool, str]:
        """
        Validate stake amount
        
        Args:
            stake: Stake amount to validate
            balance: Account balance (optional, for balance check)
            min_stake: Minimum allowed stake (optional)
            max_stake: Maximum allowed stake (optional)
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Use defaults if not provided
        min_stake = min_stake or cls.MIN_STAKE
        max_stake = max_stake or cls.MAX_STAKE
        
        # Check if numeric
        try:
            stake = float(stake)
        except (ValueError, TypeError):
            return False, "Stake must be a valid number"
        
        # Check if positive
        if stake <= 0:
            return False, "Stake must be positive"
        
        # Check minimum
        if stake < min_stake:
            return False, f"Stake must be at least {min_stake} KES"
        
        # Check maximum
        if stake > max_stake:
            return False, f"Stake cannot exceed {max_stake} KES"
        
        # Check against balance if provided
        if balance is not None:
            if stake > balance:
                return False, f"Stake ({stake} KES) exceeds balance ({balance} KES)"
            
            # Warn if stake is >50% of balance
            if stake > balance * 0.5:
                return True, f"Warning: Stake is {(stake/balance)*100:.1f}% of balance"
        
        return True, None
    
    @classmethod
    def validate_batch_input(cls, phones: List[str], password: str, 
                            booking_code: str = None, stake: float = None) -> Tuple[bool, List[str]]:
        """
        Validate all inputs for a batch operation
        
        Args:
            phones: List of phone numbers
            password: Shared password
            booking_code: Booking code (optional, for bet placement)
            stake: Stake amount (optional, for bet placement)
        
        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []
        
        # Validate phone numbers
        if not phones or len(phones) == 0:
            errors.append("No phone numbers provided")
        else:
            valid_phones, phone_errors = cls.validate_phone_list(phones)
            if phone_errors:
                errors.append(f"{len(phone_errors)} invalid phone numbers detected")
        
        # Validate password
        password_valid, password_error = cls.validate_password(password)
        if not password_valid:
            errors.append(f"Password error: {password_error}")
        
        # Validate booking code if provided
        if booking_code is not None:
            code_valid, code_error = cls.validate_booking_code(booking_code)
            if not code_valid:
                errors.append(f"Booking code error: {code_error}")
        
        # Validate stake if provided
        if stake is not None:
            stake_valid, stake_error = cls.validate_stake(stake)
            if not stake_valid:
                errors.append(f"Stake error: {stake_error}")
        
        return len(errors) == 0, errors


class InputSanitizer:
    """Sanitize inputs to prevent injection attacks"""
    
    # Dangerous characters to remove/escape
    DANGEROUS_CHARS = r'[<>"\';`$&|]'
    
    @classmethod
    def sanitize_text(cls, text: str, allow_spaces: bool = True) -> str:
        """
        Sanitize text input by removing dangerous characters
        
        Args:
            text: Text to sanitize
            allow_spaces: Whether to allow spaces
        
        Returns:
            Sanitized text
        """
        if not text:
            return text
        
        # Remove dangerous characters
        text = re.sub(cls.DANGEROUS_CHARS, '', text)
        
        # Remove excessive whitespace
        if allow_spaces:
            text = ' '.join(text.split())
        else:
            text = text.replace(' ', '')
        
        return text.strip()
    
    @classmethod
    def sanitize_phone(cls, phone: str) -> str:
        """
        Sanitize phone number (keep only digits and +)
        
        Args:
            phone: Phone number to sanitize
        
        Returns:
            Sanitized phone number
        """
        if not phone:
            return phone
        
        # Keep only digits and +
        return re.sub(r'[^\d+]', '', phone)
    
    @classmethod
    def sanitize_booking_code(cls, code: str) -> str:
        """
        Sanitize booking code (keep only alphanumeric)
        
        Args:
            code: Booking code to sanitize
        
        Returns:
            Sanitized booking code
        """
        if not code:
            return code
        
        # Keep only alphanumeric
        return re.sub(r'[^A-Za-z0-9]', '', code)
    
    @classmethod
    def sanitize_all(cls, **kwargs) -> dict:
        """
        Sanitize multiple inputs at once
        
        Args:
            **kwargs: Key-value pairs to sanitize
        
        Returns:
            Dictionary of sanitized values
        """
        sanitized = {}
        
        for key, value in kwargs.items():
            if value is None:
                sanitized[key] = value
            elif isinstance(value, str):
                if 'phone' in key.lower():
                    sanitized[key] = cls.sanitize_phone(value)
                elif 'code' in key.lower():
                    sanitized[key] = cls.sanitize_booking_code(value)
                else:
                    sanitized[key] = cls.sanitize_text(value)
            else:
                sanitized[key] = value
        
        return sanitized


# Convenience functions for quick validation
def validate_and_raise(validator_func, *args, **kwargs):
    """
    Run validator and raise exception if invalid
    
    Args:
        validator_func: Validation function to call
        *args, **kwargs: Arguments for validator
    
    Raises:
        ValidationError: If validation fails
    """
    result = validator_func(*args, **kwargs)
    
    # Handle different return formats
    if isinstance(result, tuple):
        is_valid = result[0]
        error_msg = result[1] if len(result) > 1 else "Validation failed"
        
        if not is_valid:
            raise ValidationError(error_msg)
    elif not result:
        raise ValidationError("Validation failed")


def validate_phone_or_raise(phone: str, normalize: bool = True) -> str:
    """
    Validate phone and raise exception if invalid
    
    Args:
        phone: Phone number to validate
        normalize: Whether to normalize
    
    Returns:
        Normalized phone number
    
    Raises:
        InvalidPhoneNumber: If phone is invalid
    """
    is_valid, normalized_phone, error_msg = InputValidator.validate_phone(phone, normalize)
    
    if not is_valid:
        raise InvalidPhoneNumber(error_msg, {'phone': phone})
    
    return normalized_phone


def validate_booking_code_or_raise(booking_code: str) -> str:
    """
    Validate booking code and raise exception if invalid
    
    Args:
        booking_code: Booking code to validate
    
    Returns:
        Validated booking code
    
    Raises:
        InvalidBookingCode: If code is invalid
    """
    is_valid, error_msg = InputValidator.validate_booking_code(booking_code)
    
    if not is_valid:
        raise InvalidBookingCode(error_msg, {'booking_code': booking_code})
    
    return booking_code.strip()


def validate_stake_or_raise(stake: float, balance: float = None) -> float:
    """
    Validate stake and raise exception if invalid
    
    Args:
        stake: Stake amount to validate
        balance: Account balance (optional)
    
    Returns:
        Validated stake
    
    Raises:
        InvalidStake: If stake is invalid
    """
    is_valid, error_msg = InputValidator.validate_stake(stake, balance)
    
    if not is_valid:
        raise InvalidStake(error_msg, {'stake': stake, 'balance': balance})
    
    return float(stake)
