"""Database access for items. All item SQL lives here; tag SQL is in tag_repository.py.

Every function takes `collection_id` and filters on it, so one collection can
never read or change another's data. Functions accept an optional `conn` so
they can join a larger transaction (see importer.py).
"""
from . import tag_repository as tag_repo
from .db import use_conn

# Whitelisted ORDER BY clauses; never interpolate user input into SQL.
SORTS = {
    "added": "i.created_at DESC",
    "oldest": "i.created_at ASC",
    "name": "lower(i.name) ASC",
    "acquired": "i.date_acquired DESC NULLS LAST, i.created_at DESC",
}

_FROM = "FROM items i JOIN trips tr ON tr.id = i.trip_id"

# Items plus trip details and tag names (sorted array in `tags`).
_SELECT_ITEMS = f"""
    SELECT i.*, tr.name AS trip_name, tr.start_date AS trip_start, tr.end_date AS trip_end,
           ARRAY(
               SELECT t.name FROM tags t JOIN item_tags it ON it.tag_id = t.id
               WHERE it.item_id = i.id ORDER BY lower(t.name)
           ) AS tags
    {_FROM}
"""

_HAS_TAG = (
    "EXISTS (SELECT 1 FROM item_tags it JOIN tags t ON t.id = it.tag_id "
    "WHERE it.item_id = i.id AND {cond})"
)

# An item's trip: the requested one if it belongs to this collection, else the default.
_RESOLVE_TRIP = """COALESCE(
    (SELECT id FROM trips WHERE id = %(trip_id)s AND collection_id = %(cid)s),
    (SELECT id FROM trips WHERE collection_id = %(cid)s AND is_default))"""


def _like(term: str) -> str:
    """Build a safe ILIKE pattern, escaping wildcard characters."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filters(collection_id: int, search: str, tag: str, trip_id: int | None) -> tuple[str, dict]:
    """Build a WHERE clause and params; the collection filter is always present."""
    clauses, params = ["i.collection_id = %(cid)s"], {"cid": collection_id}
    if search:
        params["like"] = _like(search)
        clauses.append(
            "(i.name ILIKE %(like)s OR i.location_acquired ILIKE %(like)s "
            "OR tr.name ILIKE %(like)s OR i.description ILIKE %(like)s OR "
            + _HAS_TAG.format(cond="t.name ILIKE %(like)s") + ")"
        )
    if tag:
        params["tag"] = tag
        clauses.append(_HAS_TAG.format(cond="lower(t.name) = lower(%(tag)s)"))
    if trip_id:
        params["trip_id"] = trip_id
        clauses.append("i.trip_id = %(trip_id)s")
    return "WHERE " + " AND ".join(clauses), params


def list_items(collection_id: int, search: str, tag: str, trip_id: int | None, sort: str,
               page: int, per_page: int) -> tuple[list[dict], int]:
    """Return (items for this page, total matching count)."""
    order = SORTS.get(sort, SORTS["added"])
    where, params = _filters(collection_id, search, tag, trip_id)
    with use_conn() as conn:
        total = conn.execute(f"SELECT count(*) AS n {_FROM} {where}", params).fetchone()["n"]
        rows = conn.execute(
            f"{_SELECT_ITEMS} {where} ORDER BY {order} LIMIT %(limit)s OFFSET %(offset)s",
            {**params, "limit": per_page, "offset": (page - 1) * per_page},
        ).fetchall()
    return rows, total


MAX_PINS = 5000


def map_items(collection_id: int, search: str, tag: str, trip_id: int | None) -> tuple[list[dict], int, int]:
    """Items with a map pin that match the filters.

    Returns (pinned rows, total items matching, total pinned matching). Rows are capped at MAX_PINS.
    """
    where, params = _filters(collection_id, search, tag, trip_id)
    with use_conn() as conn:
        counts = conn.execute(
            f"SELECT count(*) AS total, count(i.latitude) AS pinned {_FROM} {where}", params
        ).fetchone()
        rows = conn.execute(
            f"""SELECT i.id, i.name, i.latitude, i.longitude, i.location_acquired, i.image_filename
                {_FROM} {where} AND i.latitude IS NOT NULL
                ORDER BY i.id LIMIT %(limit)s""",
            {**params, "limit": MAX_PINS},
        ).fetchall()
    return rows, counts["total"], counts["pinned"]


def all_items(collection_id: int) -> list[dict]:
    """Every item in the collection with trip and tags, for export."""
    with use_conn() as conn:
        return conn.execute(
            f"{_SELECT_ITEMS} WHERE i.collection_id = %s ORDER BY i.id", (collection_id,)
        ).fetchall()


def get_item(collection_id: int, item_id: int) -> dict | None:
    with use_conn() as conn:
        return conn.execute(
            f"{_SELECT_ITEMS} WHERE i.id = %s AND i.collection_id = %s", (item_id, collection_id)
        ).fetchone()


def image_belongs(collection_id: int, filename: str) -> bool:
    """True if an item in this collection uses the given image file."""
    with use_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM items WHERE collection_id = %s AND image_filename = %s LIMIT 1",
            (collection_id, filename),
        ).fetchone() is not None


def item_exists(collection_id: int, name: str, date_acquired, location, conn=None) -> bool:
    """True if an item with the same name, date and location is already in the collection."""
    with use_conn(conn) as c:
        return c.execute(
            """SELECT 1 FROM items WHERE collection_id = %s AND lower(name) = lower(%s)
                 AND date_acquired IS NOT DISTINCT FROM %s
                 AND lower(coalesce(location_acquired, '')) = lower(coalesce(%s, ''))
               LIMIT 1""",
            (collection_id, name, date_acquired, location),
        ).fetchone() is not None


def create_item(collection_id: int, data: dict, conn=None) -> int:
    """Insert an item (and its tags) and return its new id.

    `data` may include `trip_id` (falls back to the default trip) and
    `created_at` (used when restoring a backup).
    """
    params = {
        **data, "cid": collection_id, "trip_id": data.get("trip_id"),
        "created_at": data.get("created_at"), "cost": data.get("cost"),
        "latitude": data.get("latitude"), "longitude": data.get("longitude"),
    }
    with use_conn(conn) as c:
        item_id = c.execute(
            f"""INSERT INTO items (collection_id, trip_id, name, date_acquired, location_acquired,
                                   latitude, longitude, cost, description, image_filename, created_at)
                VALUES (%(cid)s, {_RESOLVE_TRIP}, %(name)s, %(date_acquired)s,
                        %(location_acquired)s, %(latitude)s, %(longitude)s, %(cost)s, %(description)s,
                        %(image_filename)s, COALESCE(%(created_at)s, now()))
                RETURNING id""",
            params,
        ).fetchone()["id"]
        tag_repo.set_item_tags(c, collection_id, item_id, data["tags"])
    return item_id


def update_item(collection_id: int, item_id: int, data: dict) -> bool:
    """Update an item. Returns False if it isn't in this collection."""
    params = {**data, "id": item_id, "cid": collection_id, "trip_id": data.get("trip_id")}
    with use_conn() as c:
        cur = c.execute(
            f"""UPDATE items SET name = %(name)s, date_acquired = %(date_acquired)s,
                       location_acquired = %(location_acquired)s, cost = %(cost)s,
                       latitude = %(latitude)s, longitude = %(longitude)s,
                       trip_id = {_RESOLVE_TRIP}, description = %(description)s,
                       image_filename = %(image_filename)s, updated_at = now()
                WHERE id = %(id)s AND collection_id = %(cid)s""",
            params,
        )
        if cur.rowcount == 0:
            return False
        tag_repo.set_item_tags(c, collection_id, item_id, data["tags"])
    return True


def delete_item(collection_id: int, item_id: int) -> str | None:
    """Delete an item. Returns its image file name (if any) so the caller can clean up."""
    with use_conn() as c:
        row = c.execute(
            "DELETE FROM items WHERE id = %s AND collection_id = %s RETURNING image_filename",
            (item_id, collection_id),
        ).fetchone()
        tag_repo.prune_unused_tags(c)
    return row["image_filename"] if row else None


def list_tags(collection_id: int) -> list[dict]:
    with use_conn() as c:
        return tag_repo.list_tags(c, collection_id)


def get_stats(collection_id: int) -> dict:
    """Headline numbers for the maintenance page."""
    with use_conn() as c:
        return c.execute(
            """SELECT (SELECT count(*) FROM items WHERE collection_id = %(cid)s) AS item_count,
                      (SELECT count(*) FROM items WHERE collection_id = %(cid)s
                         AND image_filename IS NOT NULL) AS with_images,
                      (SELECT count(*) FROM tags WHERE collection_id = %(cid)s) AS tags,
                      (SELECT count(*) FROM trips WHERE collection_id = %(cid)s
                         AND NOT is_default) AS trips,
                      (SELECT COALESCE(sum(cost), 0) FROM items
                         WHERE collection_id = %(cid)s) AS total_value""",
            {"cid": collection_id},
        ).fetchone()
