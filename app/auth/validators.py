import re

# RFC 5322 compliant email regex pattern
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


def validate_email_format(email: str | None) -> bool:
    """
    Validates email format across sign-up and login.
    Checks:
      - Non-empty after strip
      - Max length <= 254 (RFC 5321)
      - No consecutive dots
      - Standard mailbox@domain.tld syntax
    """
    if not email:
        return False
    email_clean = email.strip()
    if len(email_clean) > 254 or len(email_clean) < 3:
        return False
    if ".." in email_clean:
        return False
    return bool(EMAIL_REGEX.match(email_clean))


def validate_password_strength(password: str | None) -> tuple[bool, str]:
    """
    Validates password requirements:
      - Non-empty
      - Minimum 6 characters
      - Maximum 128 characters
    Returns (is_valid, error_message).
    """
    if not password:
        return False, "Password cannot be empty."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if len(password) > 128:
        return False, "Password cannot exceed 128 characters."
    return True, ""
