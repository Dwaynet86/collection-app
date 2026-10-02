"""Create the database schema. Usage: `python scripts/init_db.py`."""
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import Config  # noqa: E402

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schema.sql"


def main() -> None:
    with psycopg.connect(Config.DATABASE_URL) as conn:
        conn.execute(SCHEMA_FILE.read_text())
    print("Schema applied.")


if __name__ == "__main__":
    main()
