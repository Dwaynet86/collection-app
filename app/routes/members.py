"""Membership management for a collection (owners only)."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask_login import current_user

from .. import collection_repository as coll_repo, user_repository as users
from ..permissions import collection_access

bp = Blueprint("members", __name__)


def _back():
    return redirect(url_for("members.index"))


def _is_last_owner(user_id: int) -> bool:
    cid = g.collection["id"]
    return coll_repo.get_member_role(cid, user_id) == "owner" and coll_repo.count_owners(cid) <= 1


@bp.get("/")
@collection_access("owner")
def index():
    return render_template(
        "members.html", members=coll_repo.list_members(g.collection["id"]), roles=coll_repo.ROLES
    )


@bp.post("/add")
@collection_access("owner")
def add():
    username, role = request.form.get("username", "").strip(), request.form.get("role", "")
    user = users.get_by_username(username)
    if role not in coll_repo.ROLES:
        flash("Choose a role.", "error")
    elif not user or not user["is_active"]:
        flash(f"No active user named “{username}”. Ask an admin to create the account first.", "error")
    elif not coll_repo.add_member(g.collection["id"], user["id"], role):
        flash(f"{user['username']} is already a member.", "error")
    else:
        flash(f"Added {user['username']} as {role}.", "success")
    return _back()


@bp.post("/<int:user_id>/role")
@collection_access("owner")
def change_role(user_id: int):
    role = request.form.get("role", "")
    if role not in coll_repo.ROLES:
        flash("Choose a role.", "error")
    elif role != "owner" and _is_last_owner(user_id):
        flash("A collection needs at least one owner. Make someone else an owner first.", "error")
    else:
        coll_repo.set_role(g.collection["id"], user_id, role)
        flash("Role updated.", "success")
    # Demoting yourself removes access to this page.
    if user_id == current_user.id and role != "owner":
        return redirect(url_for("collections.index"))
    return _back()


@bp.post("/<int:user_id>/remove")
@collection_access("owner")
def remove(user_id: int):
    if _is_last_owner(user_id):
        flash("A collection needs at least one owner. Make someone else an owner first.", "error")
        return _back()
    coll_repo.remove_member(g.collection["id"], user_id)
    flash("Member removed.", "success")
    if user_id == current_user.id:
        return redirect(url_for("collections.index"))
    return _back()
