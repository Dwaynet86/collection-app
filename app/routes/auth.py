"""Sign in, sign out, and change your own password."""
from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from .. import auth, user_repository as users
from ..user_forms import password_error

bp = Blueprint("auth", __name__)


def _safe_next(target: str | None) -> str | None:
    """Only allow same-site relative redirects after login."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    parts = urlparse(target)
    return None if parts.scheme or parts.netloc else target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("collections.home"))

    error, username = None, ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        key = f"{username.lower()}|{request.remote_addr}"
        if auth.is_throttled(key):
            error = "Too many attempts. Wait a few minutes and try again."
        else:
            row = users.get_by_username(username)
            password = request.form.get("password", "")
            if row and row["is_active"] and check_password_hash(row["password_hash"], password):
                auth.clear_failures(key)
                login_user(auth.User(row), remember=bool(request.form.get("remember")))
                return redirect(_safe_next(request.args.get("next")) or url_for("collections.home"))
            auth.record_failure(key)
            error = "Username or password is incorrect."

    status = 401 if error else 200
    return render_template("auth/login.html", error=error, username=username), status


@bp.post("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/account", methods=["GET", "POST"])
def account():
    error = None
    if request.method == "POST":
        row = users.get_by_id(current_user.id)
        new, confirm = request.form.get("new_password", ""), request.form.get("confirm_password", "")
        if not check_password_hash(row["password_hash"], request.form.get("current_password", "")):
            error = "Your current password is incorrect."
        elif err := password_error(new, current_app.config["MIN_PASSWORD_LENGTH"]):
            error = err
        elif new != confirm:
            error = "The new passwords don't match."
        else:
            users.set_password(current_user.id, generate_password_hash(new))
            flash("Password updated.", "success")
            return redirect(url_for("auth.account"))
    return render_template("auth/account.html", error=error), (400 if error else 200)

