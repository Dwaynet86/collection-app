"""Database access for items. All item SQL lives here; tag SQL is in tag_repository.py."""
from . import tag_repository as tag_repo
from .db import get_conn

# Whitelisted ORDER BY clauses; never interpolate user input into SQL.
SORTS = {
    "added": "created_at DESC",
    "oldest": "created_at ASC",
    "name": "lower(name) ASC",
    "acquired": "date_acquired DESC NULLS LAST, created_at DESC",
}

# Items plus their tag names as a sorted array in the `tags` column.
_SELECT_ITEMS = """
    SELECT i.*, ARRAY(
        SELECT t.name FROM tags t JOIN item_tags it ON it.tag_id = t.id
        WHERE it.item_id = i.id ORDER BY lower(t.name)
    ) AS tags
    FROM items i
"""

_HAS_TAG = (
    "EXISTS (SELECT 1 FROM item_tags it JOIN tags t ON t.id = it.tag_id "
    "WHERE it.item_id = i.id AND {cond})"
)


def _like(term: str) -> str:
    """Build a safe ILIKE pattern, escaping wildcard characters."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filters(search: str, tag: str, trip: str) -> tuple[str, dict]:
    """Build a WHERE clause and params from the active filters."""
    clauses, params = [], {}
    if search:
        params["like"] = _like(search)
        clauses.append(
            "(i.name ILIKE %(like)s OR i.location_acquired ILIKE %(like)s "
            "OR i.trip_name ILIKE %(like)s OR i.description ILIKE %(like)s OR "
            + _HAS_TAG.format(cond="t.name ILIKE %(like)s") + ")"
        )
    if tag:
        params["tag"] = tag
        clauses.append(_HAS_TAG.format(cond="lower(t.name) = lower(%(tag)s)"))
    if trip:
        params["trip"] = trip
        clauses.append("lower(i.trip_name) = lower(%(trip)s)")
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def list_items(search: str, tag: str, trip: str, sort: str,
               page: int, per_page: int) -> tuple[list[dict], int]:
    """Return (items for this page, total matching count)."""
    order = SORTS.get(sort, SORTS["added"])
    where, params = _filters(search, tag, trip)
    with get_conn() as conn:
        total = conn.execute(f"SELECT count(*) AS n FROM items i {where}", params).fetchone()["n"]
        rows = conn.execute(
            f"{_SELECT_ITEMS} {where} ORDER BY {order} LIMIT %(limit)s OFFSET %(offset)s",
            {**params, "limit": per_page, "offset": (page - 1) * per_page},
        ).fetchall()
    return rows, total


def all_items() -> list[dict]:
    """Every item with tags, for export."""
    with get_conn() as conn:
        return conn.execute(f"{_SELECT_ITEMS} ORDER BY i.id").fetchall()


def get_item(item_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(f"{_SELECT_ITEMS} WHERE i.id = %s", (item_id,)).fetchone()


def create_item(data: dict) -> int:
    """Insert an item (and its tags) and return its new id."""
    with get_conn() as conn:
        item_id = conn.execute(
            """INSERT INTO items (name, date_acquired, location_acquired, trip_name,
                                  description, image_filename)
               VALUES (%(name)s, %(date_acquired)s, %(location_acquired)s, %(trip_name)s,
                       %(description)s, %(image_filename)s)
               RETURNING id""",
            data,
        ).fetchone()["id"]
        tag_repo.set_item_tags(conn, item_id, data["tags"])
    return item_id


def update_item(item_id: int, data: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE items SET name = %(name)s, date_acquired = %(date_acquired)s,
                      location_acquired = %(location_acquired)s, trip_name = %(trip_name)s,
                      description = %(description)s, image_filename = %(image_filename)s,
                      updated_at = now()
               WHERE id = %(id)s""",
            {**data, "id": item_id},
        )
        tag_repo.set_item_tags(conn, item_id, data["tags"])


def delete_item(item_id: int) -> str | None:
    """Delete an item. Returns its image file name (if any) so the caller can clean up."""
    with get_conn() as conn:
        row = conn.execute(
            "DELETE FROM items WHERE id = %s RETURNING image_filename", (item_id,)
        ).fetchone()
        tag_repo.prune_unused_tags(conn)
    return row["image_filename"] if row else None


def list_tags() -> list[dict]:
    with get_conn() as conn:
        return tag_repo.list_tags(conn)


def list_trips() -> list[dict]:
    """Distinct trip names with item counts: [{'trip_name', 'n'}, ...]."""
    with get_conn() as conn:
        return conn.execute(
            """SELECT min(trip_name) AS trip_name, count(*) AS n FROM items
               WHERE trip_name IS NOT NULL GROUP BY lower(trip_name)
               ORDER BY lower(min(trip_name))"""
        ).fetchall()


def get_stats() -> dict:
    """Headline counts for the maintenance page."""
    with get_conn() as conn:
        return conn.execute(
            """SELECT (SELECT count(*) FROM items) AS items,
                      (SELECT count(*) FROM items WHERE image_filename IS NOT NULL) AS with_images,
                      (SELECT count(*) FROM tags) AS tags,
                      (SELECT count(DISTINCT lower(trip_name)) FROM items) AS trips"""
        ).fetchone()
