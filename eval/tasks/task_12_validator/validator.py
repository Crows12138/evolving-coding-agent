"""Data validation utilities."""

import re


def validate_email(email):
    """Validate an email address. Returns True if valid."""
    if not email or not isinstance(email, str):
        return False
    # Bug: pattern doesn't allow '+' in local part, rejecting valid addresses like user+tag@example.com
    pattern = r'^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_phone(phone):
    """Validate a phone number. Returns True if valid."""
    if not phone or not isinstance(phone, str):
        return False
    # Bug: only matches US-style numbers, rejects international format like +44-20-1234-5678
    cleaned = re.sub(r'[\s\-\(\)]', '', phone)
    pattern = r'^\d{10,11}$'
    return bool(re.match(pattern, cleaned))


def validate_date(date_str):
    """Validate a date string in YYYY-MM-DD format. Returns True if valid."""
    if not date_str or not isinstance(date_str, str):
        return False
    pattern = r'^\d{4}-(\d{2})-(\d{2})$'
    match = re.match(pattern, date_str)
    if not match:
        return False
    month = int(match.group(1))
    day = int(match.group(2))
    # Bug: only checks basic ranges, doesn't validate actual days per month
    # e.g., 2023-02-30 would pass validation
    if month < 1 or month > 12:
        return False
    if day < 1 or day > 31:
        return False
    return True


def validate_password(password):
    """Validate password strength. Requires:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    Returns True if valid.
    """
    if not password or not isinstance(password, str):
        return False
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'[0-9]', password):
        return False
    # Bug: missing check for special characters
    return True
