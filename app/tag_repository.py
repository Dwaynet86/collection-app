"""Database access for tags. Functions take an open connection so they can
run inside the caller's transaction (see repository.py)."""


def set_item_tags(conn, item_id: int, names: list[str]) -> None:
    """Replace an item's tags with `names`, creating new tags as needed."""
    conn.execute("DELETE FROM item_tags WHERE item_id = %s", (item_id,))
    for name in names:
        tag_id = conn.execute(
            """INSERT INTO tags (name) VALUES (%s)
               ON CONFLICT (lower(name)) DO UPDATE SET name = tags.name
               RETURNING id""",
            (name,),
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO item_tags (item_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (item_id, tag_id),
        )
    prune_unused_tags(conn)


def prune_unused_tags(conn) -> None:
    """Delete tags no longer attached to any item."""
    conn.execute(
        "DELETE FROM tags WHERE NOT EXISTS (SELECT 1 FROM item_tags WHERE tag_id = tags.id)"
    )


def list_tags(conn) -> list[dict]:
    """All tags with usage counts, alphabetical: [{'name', 'n'}, ...]."""
    return conn.execute(
        """SELECT t.name, count(*) AS n FROM tags t
           JOIN item_tags it ON it.tag_id = t.id
           GROUP BY t.id ORDER BY lower(t.name)"""
    ).fetchall()
