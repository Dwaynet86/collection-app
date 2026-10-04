"""Item routes within a collection: view (viewer+), add/edit/remove (editor+)."""
from math import ceil

from flask import (Blueprint, abort, current_app, flash, g, redirect,
                   render_template, request, send_from_directory, url_for)

from .. import background, images, repository as repo, trip_repository as trip_repo
from ..forms import parse_item_form
from ..permissions import collection_access

bp = Blueprint("items", __name__)


def _cid() -> int:
    return g.collection["id"]


def _get_or_404(item_id: int) -> dict:
    item = repo.get_item(_cid(), item_id)
    if item is None:
        abort(404)
    return item


def _form_page(item, errors: dict, mode: str, status: int = 200):
    """Render the item form with tag/trip suggestions."""
    html = render_template(
        "items/form.html", item=item, errors=errors, mode=mode,
        known_tags=[t["name"] for t in repo.list_tags(_cid())],
        trips=trip_repo.list_trips(_cid()),
        bg_removal=background.available(),
        has_original=images.has_original(item.get("image_filename")),
    )
    return html, status


def _warn_if_cutout_failed(stored: images.StoredImage) -> None:
    if stored.cutout_failed:
        flash("The background couldn't be removed, so the photo was saved as it was.", "error")


def _store_upload(errors: dict) -> str | None:
    """Save the uploaded image if present; record a message in `errors` on failure."""
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return None
    try:
        stored = images.store_image(upload, remove_bg=bool(request.form.get("remove_background")))
    except images.ImageError as exc:
        errors["image"] = str(exc)
        return None
    _warn_if_cutout_failed(stored)
    return stored.name


def _reprocess_current(filename: str | None, errors: dict) -> str | None:
    """No new upload: cut out the background of (or restore the original of) the current photo."""
    if not filename:
        return None
    restore = request.form.get("restore_original") and images.has_original(filename)
    cut = request.form.get("remove_background")
    if not (restore or cut):
        return None
    try:
        stored = (images.reprocess(filename, from_original=True) if restore else
                  images.reprocess(filename, remove_bg=True, from_original=images.has_original(filename)))
    except images.ImageError as exc:
        errors["image"] = str(exc)
        return None
    if stored.cutout_failed:           # nothing changed; drop the duplicate copy
        images.delete_image(stored.name)
        _warn_if_cutout_failed(stored)
        return None
    return stored.name


# ---- View -----------------------------------------------------------------

@bp.get("/")
@collection_access("viewer")
def index():
    search = request.args.get("q", "").strip()
    tag = request.args.get("tag", "").strip()
    trip = request.args.get("trip", type=int)
    sort = request.args.get("sort", "added")
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = current_app.config["ITEMS_PER_PAGE"]

    items, total = repo.list_items(_cid(), search, tag, trip, sort, page, per_page)
    return render_template(
        "items/list.html", items=items, total=total, search=search, tag=tag,
        trip=trip, sort=sort, page=page, pages=max(ceil(total / per_page), 1),
        tags=repo.list_tags(_cid()), trips=trip_repo.list_trips(_cid()),
    )


@bp.get("/items/<int:item_id>")
@collection_access("viewer")
def detail(item_id: int):
    return render_template("items/detail.html", item=_get_or_404(item_id))


# ---- Add ------------------------------------------------------------------

@bp.route("/items/new", methods=["GET", "POST"])
@collection_access("editor")
def create():
    if request.method == "GET":
        return _form_page({}, {}, "create")

    data, errors = parse_item_form(request.form)
    data["image_filename"] = _store_upload(errors) if not errors else None
    if not errors:
        try:
            item_id = repo.create_item(_cid(), data)
        except Exception:
            images.delete_image(data["image_filename"])
            raise
        flash("Item added.", "success")
        return redirect(url_for("items.detail", item_id=item_id))

    return _form_page(request.form, errors, "create", 400)


# ---- Edit -----------------------------------------------------------------

@bp.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@collection_access("editor")
def edit(item_id: int):
    existing = _get_or_404(item_id)
    if request.method == "GET":
        return _form_page(existing, {}, "edit")

    data, errors = parse_item_form(request.form)
    old_image = existing["image_filename"]
    new_image = None
    if not errors:
        new_image = _store_upload(errors)
        if not new_image and not errors and not request.form.get("remove_image"):
            new_image = _reprocess_current(old_image, errors)

    if not errors:
        if new_image:
            data["image_filename"] = new_image
        elif request.form.get("remove_image"):
            data["image_filename"] = None
        else:
            data["image_filename"] = old_image
        try:
            repo.update_item(_cid(), item_id, data)
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
@collection_access("editor")
def delete(item_id: int):
    filename = repo.delete_item(_cid(), item_id)
    images.delete_image(filename)
    flash("Item removed.", "success")
    return redirect(url_for("items.index"))


# ---- Image files (only served to members of the owning collection) --------

def _serve_image(directory, filename: str):
    if not repo.image_belongs(_cid(), filename):
        abort(404)
    response = send_from_directory(directory, filename, max_age=86400)
    response.cache_control.public = False
    response.cache_control.private = True
    return response


@bp.get("/media/<filename>")
@collection_access("viewer")
def media(filename: str):
    return _serve_image(current_app.config["UPLOAD_DIR"], filename)


@bp.get("/thumbs/<filename>")
@collection_access("viewer")
def thumb(filename: str):
    return _serve_image(current_app.config["UPLOAD_DIR"] / "thumbs", filename)
