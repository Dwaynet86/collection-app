"""Create a user from the command line.

    python scripts/create_user.py USERNAME --admin    # first account: do this once
    python scripts/create_user.py USERNAME

With --admin the user can manage accounts, and also adopts any collection that
has no members yet (e.g. the 'My Collection' created when upgrading an older
database). If no collection exists at all, one is created.
"""
import argparse
import getpass
import sys
from pathlib import Path

import psycopg
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import Config  # noqa: E402
from app.user_forms import password_error, username_error  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("--admin", action="store_true", help="grant account-management rights")
    args = parser.parse_args()

    if err := username_error(args.username):
        sys.exit(err)
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords don't match.")
    if err := password_error(password, Config.MIN_PASSWORD_LENGTH):
        sys.exit(err)

    with psycopg.connect(Config.DATABASE_URL) as conn:
        row = conn.execute(
            """INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, %s)
               ON CONFLICT (lower(username)) DO NOTHING RETURNING id""",
            (args.username, generate_password_hash(password), args.admin),
        ).fetchone()
        if row is None:
            sys.exit("That username already exists.")
        user_id = row[0]

        if args.admin:
            conn.execute(
                """INSERT INTO collection_members (collection_id, user_id, role)
                   SELECT c.id, %s, 'owner' FROM collections c
                   WHERE NOT EXISTS (SELECT 1 FROM collection_members m WHERE m.collection_id = c.id)""",
                (user_id,),
            )
            if conn.execute("SELECT count(*) FROM collections").fetchone()[0] == 0:
                cid = conn.execute(
                    "INSERT INTO collections (name, slug) VALUES ('My Collection', 'my-collection') RETURNING id"
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO collection_members (collection_id, user_id, role) VALUES (%s, %s, 'owner')",
                    (cid, user_id),
                )
                conn.execute(
                    "INSERT INTO trips (collection_id, name, is_default) VALUES (%s, 'Home', true)", (cid,)
                )
                conn.execute(
                    "INSERT INTO trips (collection_id, name, is_default) VALUES (%s, 'Home', true)",
                    (cid,),
                )
    print(f"Created {'admin ' if args.admin else ''}user '{args.username}'.")


if __name__ == "__main__":
    main()
