"""Routes for viewing, adding, editing, and removing items."""
from math import ceil

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, send_from_directory, url_for)

from .. import images, repository as repo
from ..forms import parse_item_form

bp = Blueprint("items", __name__)


def _get_or_404(item_id: int) -> dict:
    item = repo.get_item(item_id)
    if item is None:
        abort(404)
    return item


def _form_page(item, errors: dict, mode: str, status: int = 200):
    """Render the item form with tag/trip suggestions."""
    html = render_template(
        "items/form.html", item=item, errors=errors, mode=mode,
        known_tags=[t["name"] for t in repo.list_tags()],
        known_trips=[t["trip_name"] for t in repo.list_trips()],
    )
    return html, status


def _store_upload(errors: dict) -> str | None:
    """Save the uploaded image if present; record a message in `errors` on failure."""
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return None
    try:
        return images.save_image(upload)
    except images.ImageError as exc:
        errors["image"] = str(exc)
        return None


# ---- View -----------------------------------------------------------------

@bp.get("/")
def index():
    search = request.args.get("q", "").strip()
    tag = request.args.get("tag", "").strip()
    trip = request.args.get("trip", "").strip()
    sort = request.args.get("sort", "added")
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = current_app.config["ITEMS_PER_PAGE"]

    items, total = repo.list_items(search, tag, trip, sort, page, per_page)
    return render_template(
        "items/list.html", items=items, total=total, search=search, tag=tag,
        trip=trip, sort=sort, page=page, pages=max(ceil(total / per_page), 1),
        tags=repo.list_tags(), trips=repo.list_trips(),
    )


@bp.get("/items/<int:item_id>")
def detail(item_id: int):
    return render_template("items/detail.html", item=_get_or_404(item_id))


# ---- Add ------------------------------------------------------------------

@bp.route("/items/new", methods=["GET", "POST"])
def create():
    if request.method == "GET":
        return _form_page({}, {}, "create")

    data, errors = parse_item_form(request.form)
    data["image_filename"] = _store_upload(errors) if not errors else None
    if not errors:
        try:
            item_id = repo.create_item(data)
        except Exception:
            images.delete_image(data["image_filename"])
            raise
        flash("Item added.", "success")
        return redirect(url_for("items.detail", item_id=item_id))

    return _form_page(request.form, errors, "create", 400)


# ---- Edit -----------------------------------------------------------------

@bp.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
def edit(item_id: int):
    existing = _get_or_404(item_id)
    if request.method == "GET":
        return _form_page(existing, {}, "edit")

    data, errors = parse_item_form(request.form)
    old_image = existing["image_filename"]
    new_image = _store_upload(errors) if not errors else None

    if not errors:
        if new_image:
            data["image_filename"] = new_image
        elif request.form.get("remove_image"):
            data["image_filename"] = None
        else:
            data["image_filename"] = old_image
        try:
            repo.update_item(item_id, data)
        except Exception:
            images.delete_image(new_image)
            raise
        if data["image_filename"] != old_image:
            images.delete_image(old_image)
        flash("Changes saved.", "success")
        return redirect(url_for("items.detail", item_id=item_id))

    merged = {**existing, **request.form.to_dict()}
    return _form_page(merged, errors, "edit", 400)


# ---- Remove ---------------------------------------------------------------

@bp.post("/items/<int:item_id>/delete")
def delete(item_id: int):
    filename = repo.delete_item(item_id)
    images.delete_image(filename)
    flash("Item removed.", "success")
    return redirect(url_for("items.index"))


# ---- Image files ----------------------------------------------------------

@bp.get("/media/<path:filename>")
def media(filename: str):
    return send_from_directory(current_app.config["UPLOAD_DIR"], filename, max_age=86400)


@bp.get("/media/thumbs/<path:filename>")
def thumb(filename: str):
    return send_from_directory(
        current_app.config["UPLOAD_DIR"] / "thumbs", filename, max_age=86400
    )
