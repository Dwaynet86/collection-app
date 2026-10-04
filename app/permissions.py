"""Collection-level authorization and template helpers.

Collection routes are registered under /c/<slug>/ and decorated with
@collection_access(min_role). The decorator:
  * 404s if the collection doesn't exist OR the user isn't a member
    (existence isn't revealed),
  * 403s if the member's role is too low,
  * exposes g.collection (with `id`, `slug`, `name`) and g.role to the view.
"""
from functools import wraps

from flask import abort, g, request
from flask_login import current_user

from . import collection_repository as coll_repo

ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}


def collection_access(min_role: str = "viewer"):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            slug = kwargs.pop("slug")
            row = coll_repo.get_for_user(slug, current_user.id)
            if row is None:
                abort(404)
            if ROLE_RANK[row["role"]] < ROLE_RANK[min_role]:
                abort(403)
            g.collection, g.role = row, row["role"]
            return view(*args, **kwargs)
        return wrapped
    return decorator


def admin_required(view):
    """Restrict a view to instance admins (user management)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def register_permissions(app) -> None:
    @app.url_defaults
    def add_slug(endpoint, values):
        """Inside a collection, url_for() fills in <slug> automatically."""
        collection = g.get("collection")
        if collection and "slug" not in values and app.url_map.is_endpoint_expecting(endpoint, "slug"):
            values["slug"] = collection["slug"]

    @app.context_processor
    def layout_context():
        role = g.get("role")
        mine = coll_repo.list_for_user(current_user.id) if current_user.is_authenticated else []
        return {
            "collection": g.get("collection"),
            "role": role,
            "can_edit": ROLE_RANK.get(role, 0) >= ROLE_RANK["editor"],
            "is_owner": role == "owner",
            "my_collections": mine,
            "est_value": _estimated_value(mine),
        }


def _estimated_value(mine: list[dict]):
    """Header figure: this collection's value, or everything on the Collections page."""
    collection = g.get("collection")
    if collection:
        match = next((c for c in mine if c["id"] == collection["id"]), None)
        return match["total_value"] if match else None
    if request.endpoint == "collections.index" and mine:
        return sum(c["total_value"] for c in mine)
    return None
