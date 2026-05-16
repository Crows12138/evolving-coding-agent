from validator import validate_email, validate_phone, validate_date, validate_password


# --- validate_email tests ---

def test_email_valid_simple():
    assert validate_email("user@example.com") is True


def test_email_valid_with_plus():
    """Email addresses with '+' in local part are valid (e.g., Gmail filters)."""
    assert validate_email("user+tag@example.com") is True


def test_email_invalid_no_at():
    assert validate_email("userexample.com") is False


def test_email_empty():
    assert validate_email("") is False
    assert validate_email(None) is False


# --- validate_phone tests ---

def test_phone_valid_10_digits():
    assert validate_phone("1234567890") is True


def test_phone_valid_with_formatting():
    assert validate_phone("(123) 456-7890") is True


def test_phone_valid_international():
    """International phone numbers with country code should be valid."""
    assert validate_phone("+44-20-1234-5678") is True
    assert validate_phone("+86 138 0000 0000") is True


def test_phone_invalid_too_short():
    assert validate_phone("12345") is False


def test_phone_empty():
    assert validate_phone("") is False
    assert validate_phone(None) is False


# --- validate_date tests ---

def test_date_valid():
    assert validate_date("2023-01-15") is True
    assert validate_date("2023-12-31") is True


def test_date_invalid_feb_30():
    """February 30th should be invalid."""
    assert validate_date("2023-02-30") is False


def test_date_invalid_apr_31():
    """April only has 30 days."""
    assert validate_date("2023-04-31") is False


def test_date_invalid_month():
    assert validate_date("2023-13-01") is False
    assert validate_date("2023-00-15") is False


def test_date_invalid_format():
    assert validate_date("01-15-2023") is False
    assert validate_date("not-a-date") is False


# --- validate_password tests ---

def test_password_valid():
    assert validate_password("Str0ng!Pass") is True


def test_password_missing_special_char():
    """Password without special characters should be rejected."""
    assert validate_password("Str0ngPass") is False


def test_password_too_short():
    assert validate_password("Aa1!") is False


def test_password_no_uppercase():
    assert validate_password("str0ng!pass") is False


def test_password_no_digit():
    assert validate_password("Strong!Pass") is False


def test_password_empty():
    assert validate_password("") is False
    assert validate_password(None) is False
