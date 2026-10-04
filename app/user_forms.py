"""Validation for account and collection forms. Each returns an error message or None."""
import re

_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")


def username_error(username: str) -> str | None:
    if not _USERNAME_RE.match(username):
        return "Use 3-32 letters, numbers, dots, dashes, or underscores."
    return None


def password_error(password: str, min_length: int) -> str | None:
    if len(password) < min_length:
        return f"Use at least {min_length} characters."
    if len(password) > 200:
        return "Keep the password under 200 characters."
    return None


def collection_name_error(name: str) -> str | None:
    if not name:
        return "Enter a name for the collection."
    if len(name) > 100:
        return "Keep the name under 100 characters."
    return None
