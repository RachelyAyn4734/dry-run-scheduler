import re
from html import escape as _escape


def valid_email(email: str) -> bool:
    """Strict email validation using fullmatch."""
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()))


def normalize_email(email: str) -> str:
    return email.lower().strip()


def safe(value) -> str:
    """Escape a value for safe embedding inside unsafe_allow_html HTML blocks."""
    return _escape(str(value))
