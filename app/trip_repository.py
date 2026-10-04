"""Database access for trips (scoped per collection).

Every collection has one default trip (is_default) that items fall back to.
Functions accept an optional `conn` so they can join a larger transaction.
"""
import psycopg.errors

from .db import use_conn


class DuplicateTripError(Exception):
    """A trip with that name already exists in the collection."""


def list_trips(collection_id: int, conn=None) -> list[dict]:
    """All trips, default first then newest, each with an `item_count`."""
    with use_conn(conn) as c:
        return c.execute(
            """SELECT t.*, (SELECT count(*) FROM items i WHERE i.trip_id = t.id) AS item_count
               FROM trips t WHERE t.collection_id = %s
               ORDER BY t.is_default DESC, t.start_date DESC NULLS LAST, lower(t.name)""",
            (collection_id,),
        ).fetchall()


def get_trip(collection_id: int, trip_id: int) -> dict | None:
    with use_conn() as c:
        return c.execute(
            """SELECT t.*, (SELECT count(*) FROM items i WHERE i.trip_id = t.id) AS item_count
               FROM trips t WHERE t.id = %s AND t.collection_id = %s""",
            (trip_id, collection_id),
        ).fetchone()


def get_default(collection_id: int, conn=None) -> dict:
    with use_conn(conn) as c:
        return c.execute(
            "SELECT * FROM trips WHERE collection_id = %s AND is_default", (collection_id,)
        ).fetchone()


def create_default(conn, collection_id: int, name: str = "Home") -> int:
    """Create a collection's default trip. Called when a collection is created."""
    return conn.execute(
        "INSERT INTO trips (collection_id, name, is_default) VALUES (%s, %s, true) RETURNING id",
        (collection_id, name),
    ).fetchone()["id"]


def create_trip(collection_id: int, name: str, start_date, end_date, conn=None) -> int:
    """Create a trip. Raises DuplicateTripError if the name is taken."""
    try:
        with use_conn(conn) as c:
            return c.execute(
                """INSERT INTO trips (collection_id, name, start_date, end_date)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (collection_id, name, start_date, end_date),
            ).fetchone()["id"]
    except psycopg.errors.UniqueViolation:
        raise DuplicateTripError(name) from None


def update_trip(collection_id: int, trip_id: int, name: str, start_date, end_date) -> bool:
    """Update a trip. Returns False if it doesn't exist; raises DuplicateTripError on name clash."""
    try:
        with use_conn() as c:
            cur = c.execute(
                """UPDATE trips SET name = %s, start_date = %s, end_date = %s
                   WHERE id = %s AND collection_id = %s""",
                (name, start_date, end_date, trip_id, collection_id),
            )
            return cur.rowcount > 0
    except psycopg.errors.UniqueViolation:
        raise DuplicateTripError(name) from None


def delete_trip(collection_id: int, trip_id: int) -> int | None:
    """Delete a non-default trip, moving its items to the default trip.

    Returns how many items moved, or None if the trip is missing or is the default.
    """
    with use_conn() as c:
        trip = c.execute(
            "SELECT is_default FROM trips WHERE id = %s AND collection_id = %s FOR UPDATE",
            (trip_id, collection_id),
        ).fetchone()
        if trip is None or trip["is_default"]:
            return None
        default_id = get_default(collection_id, c)["id"]
        moved = c.execute(
            "UPDATE items SET trip_id = %s WHERE trip_id = %s AND collection_id = %s",
            (default_id, trip_id, collection_id),
        ).rowcount
        c.execute("DELETE FROM trips WHERE id = %s", (trip_id,))
    return moved
