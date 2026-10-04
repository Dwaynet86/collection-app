"""Map: one pin per item that has coordinates, plus place search for the item form.

Everything is served locally (bundled outlines and city list); no internet is needed.
"""
from flask import Blueprint, g, jsonify, render_template, request, url_for

from .. import places, repository as repo, trip_repository as trip_repo
from ..permissions import collection_access

bp = Blueprint("geo", __name__)


def _cid() -> int:
    return g.collection["id"]


def _filters() -> tuple[str, str, int | None]:
    return (request.args.get("q", "").strip(), request.args.get("tag", "").strip(),
            request.args.get("trip", type=int))


@bp.get("/")
@collection_access("viewer")
def index():
    search, tag, trip = _filters()
    return render_template(
        "map.html", search=search, tag=tag, trip=trip, focus=request.args.get("focus", type=int),
        tags=repo.list_tags(_cid()), trips=trip_repo.list_trips(_cid()),
    )


@bp.get("/pins.json")
@collection_access("viewer")
def pins():
    """Pins for the current filters. Never includes costs."""
    rows, total, pinned = repo.map_items(_cid(), *_filters())
    response = jsonify(
        pins=[{
            "id": r["id"], "name": r["name"], "lat": r["latitude"], "lon": r["longitude"],
            "where": r["location_acquired"] or "",
            "url": url_for("items.detail", item_id=r["id"]),
            "thumb": url_for("items.thumb", filename=r["image_filename"]) if r["image_filename"] else None,
        } for r in rows],
        matching=total, unpinned=total - pinned, truncated=pinned > len(rows),
    )
    response.cache_control.private = True
    response.cache_control.no_store = True
    return response


@bp.get("/search")
@collection_access("editor")
def search():
    """Offline place search for the item form picker."""
    return jsonify(places.search(request.args.get("q", "")))
