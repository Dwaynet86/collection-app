"""Database access for user accounts."""
from .db import get_conn


def get_by_id(user_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


def get_by_username(username: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE lower(username) = lower(%s)", (username,)
        ).fetchone()


def list_users() -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """SELECT id, username, is_admin, is_active, created_at
               FROM users ORDER BY lower(username)"""
        ).fetchall()


def create_user(username: str, password_hash: str, is_admin: bool = False) -> int | None:
    """Create a user. Returns the new id, or None if the username is taken."""
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO users (username, password_hash, is_admin)
               VALUES (%s, %s, %s) ON CONFLICT (lower(username)) DO NOTHING RETURNING id""",
            (username, password_hash, is_admin),
        ).fetchone()
    return row["id"] if row else None


def set_password(user_id: int, password_hash: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))


def set_active(user_id: int, active: bool) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_active = %s WHERE id = %s", (active, user_id))


def set_admin(user_id: int, admin: bool) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_admin = %s WHERE id = %s", (admin, user_id))
