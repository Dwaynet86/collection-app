"""Landing page and the list of collections you belong to."""
from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user

from .. import collection_repository as coll_repo
from ..user_forms import collection_name_error

bp = Blueprint("collections", __name__)


@bp.get("/")
def home():
    """Go straight to your collection if you only have one."""
    mine = coll_repo.list_for_user(current_user.id)
    if len(mine) == 1:
        return redirect(url_for("items.index", slug=mine[0]["slug"]))
    return redirect(url_for("collections.index"))


@bp.route("/collections", methods=["GET", "POST"])
def index():
    error, name = None, ""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        error = collection_name_error(name)
        if not error:
            slug = coll_repo.create(name, current_user.id)
            return redirect(url_for("items.index", slug=slug))
    return render_template(
        "collections/list.html", mine=coll_repo.list_for_user(current_user.id),
        error=error, name=name,
    ), (400 if error else 200)
