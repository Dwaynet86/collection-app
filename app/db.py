"""PostgreSQL connection pool.

Usage:
    with get_conn() as conn:
        rows = conn.execute("SELECT ...", params).fetchall()

The connection commits on clean exit and rolls back on exception.
Rows are returned as dicts.
"""
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def init_pool(app) -> None:
    """Create the shared pool. Called once from the app factory."""
    global _pool
    _pool = ConnectionPool(
        app.config["DATABASE_URL"],
        min_size=1,
        max_size=10,
        kwargs={"row_factory": dict_row},
        open=True,
    )


def get_conn():
    """Check a connection out of the pool (use as a context manager)."""
    if _pool is None:
        raise RuntimeError("Database pool not initialised; call init_pool() first.")
    return _pool.connection()


@contextmanager
def use_conn(conn=None):
    """Use `conn` if given (the caller owns the transaction), else check one out.

    Lets repository functions run on their own, or as part of a larger
    transaction such as a backup import.
    """
    if conn is not None:
        yield conn
    else:
        with get_conn() as own:
            yield own
