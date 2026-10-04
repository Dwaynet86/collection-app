"""Trips: named date ranges used to prefill an item's date acquired.

Anyone in the collection can view trips; editors and owners can change them.
Deleting a trip moves its items to the collection's default trip.
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import trip_repository as trip_repo
from ..permissions import collection_access
from ..trip_forms import parse_trip_form

bp = Blueprint("trips", __name__)


def _cid() -> int:
    return g.collection["id"]


def _list_page(form, errors: dict, status: int = 200):
    return render_template(
        "trips/list.html", trips=trip_repo.list_trips(_cid()), form=form, errors=errors
    ), status


@bp.get("/")
@collection_access("viewer")
def index():
    return _list_page({}, {})


@bp.post("/")
@collection_access("editor")
def create():
    data, errors = parse_trip_form(request.form)
    if not errors:
        try:
            trip_repo.create_trip(_cid(), **data)
        except trip_repo.DuplicateTripError:
            errors["name"] = "A trip with that name already exists."
        else:
            flash("Trip added.", "success")
            return redirect(url_for("trips.index"))
    return _list_page(request.form, errors, 400)


@bp.route("/<int:trip_id>/edit", methods=["GET", "POST"])
@collection_access("editor")
def edit(trip_id: int):
    trip = trip_repo.get_trip(_cid(), trip_id)
    if trip is None:
        abort(404)
    default = trip_repo.get_default(_cid())

    def page(form, errors, status=200):
        return render_template("trips/form.html", trip=trip, form=form, errors=errors,
                               default_trip=default), status

    if request.method == "GET":
        return page(trip, {})

    data, errors = parse_trip_form(request.form, require_start=not trip["is_default"])
    if not errors:
        try:
            trip_repo.update_trip(_cid(), trip_id, **data)
        except trip_repo.DuplicateTripError:
            errors["name"] = "A trip with that name already exists."
        else:
            flash("Trip saved.", "success")
            return redirect(url_for("trips.index"))
    return page(request.form, errors, 400)


@bp.post("/<int:trip_id>/delete")
@collection_access("editor")
def delete(trip_id: int):
    moved = trip_repo.delete_trip(_cid(), trip_id)
    if moved is None:
        flash("That trip can't be deleted.", "error")
    else:
        default = trip_repo.get_default(_cid())
        flash(f"Trip deleted. {moved} item{'' if moved == 1 else 's'} moved to {default['name']}.", "success")
    return redirect(url_for("trips.index"))
