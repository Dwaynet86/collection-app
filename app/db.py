"""PostgreSQL connection pool.

Usage:
    with get_conn() as conn:
        rows = conn.execute("SELECT ...", params).fetchall()

The connection commits on clean exit and rolls back on exception.
Rows are returned as dicts.
"""
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
