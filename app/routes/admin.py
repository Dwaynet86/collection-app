"""User account management (instance admins only)."""
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from werkzeug.security import generate_password_hash

from .. import user_repository as users
from ..permissions import admin_required
from ..user_forms import password_error, username_error

bp = Blueprint("admin", __name__)


@bp.before_request
@admin_required
def _admin_only():
    """Applies to every route in this blueprint."""


def _back():
    return redirect(url_for("admin.user_list"))


@bp.get("/users")
def user_list():
    return render_template("admin/users.html", users=users.list_users())


@bp.post("/users")
def create():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    min_len = current_app.config["MIN_PASSWORD_LENGTH"]
    error = username_error(username) or password_error(password, min_len)
    if error:
        flash(error, "error")
    elif users.create_user(username, generate_password_hash(password), bool(request.form.get("is_admin"))) is None:
        flash("That username is already taken.", "error")
    else:
        flash(f"Created user {username}.", "success")
    return _back()


@bp.post("/users/<int:user_id>/password")
def reset_password(user_id: int):
    password = request.form.get("password", "")
    error = password_error(password, current_app.config["MIN_PASSWORD_LENGTH"])
    if error:
        flash(error, "error")
    else:
        users.set_password(user_id, generate_password_hash(password))
        flash("Password updated.", "success")
    return _back()


@bp.post("/users/<int:user_id>/active")
def toggle_active(user_id: int):
    if user_id == current_user.id:
        flash("You can't deactivate your own account.", "error")
    else:
        users.set_active(user_id, request.form.get("active") == "1")
        flash("Account updated.", "success")
    return _back()


@bp.post("/users/<int:user_id>/admin")
def toggle_admin(user_id: int):
    if user_id == current_user.id:
        flash("You can't change your own admin status.", "error")
    else:
        users.set_admin(user_id, request.form.get("admin") == "1")
        flash("Account updated.", "success")
    return _back()
