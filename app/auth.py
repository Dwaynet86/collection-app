"""Authentication: Flask-Login setup, default-deny access, login throttling."""
import time

from flask import redirect, request, url_for
from flask_login import LoginManager, UserMixin, current_user

from . import user_repository as users

login_manager = LoginManager()

# Endpoints reachable without signing in. Everything else requires login.
PUBLIC_ENDPOINTS = {"auth.login", "static"}


class User(UserMixin):
    """Thin wrapper around a `users` row for Flask-Login."""

    def __init__(self, row: dict):
        self.id = row["id"]
        self.username = row["username"]
        self.is_admin = row["is_admin"]
        self._active = row["is_active"]

    @property
    def is_active(self) -> bool:
        return self._active

    def get_id(self) -> str:
        return str(self.id)


@login_manager.user_loader
def load_user(user_id: str):
    """Reload the user on every request, so deactivation takes effect immediately."""
    try:
        row = users.get_by_id(int(user_id))
    except ValueError:
        return None
    return User(row) if row and row["is_active"] else None


@login_manager.unauthorized_handler
def _unauthorized():
    return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))


def init_auth(app) -> None:
    login_manager.init_app(app)

    @app.before_request
    def require_login():
        if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        return None


# ---- Login throttling (in-memory, per process) ----------------------------
_WINDOW_SECONDS = 300
_MAX_FAILURES = 5
_failures: dict[str, list[float]] = {}


def _recent(key: str) -> list[float]:
    cutoff = time.monotonic() - _WINDOW_SECONDS
    _failures[key] = [t for t in _failures.get(key, []) if t > cutoff]
    return _failures[key]


def is_throttled(key: str) -> bool:
    return len(_recent(key)) >= _MAX_FAILURES


def record_failure(key: str) -> None:
    _recent(key).append(time.monotonic())


def clear_failures(key: str) -> None:
    _failures.pop(key, None)
