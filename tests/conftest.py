"""Shared fixtures: an app with the database layer stubbed out."""
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from app import create_app

ITEM = {"id": 1, "name": "Brass compass", "date_acquired": date(2024, 3, 4),
        "location_acquired": "Lisbon", "latitude": None, "longitude": None, "trip_id": 2, "trip_name": "Portugal 2024",
        "trip_start": date(2024, 3, 4), "trip_end": date(2024, 3, 12), "cost": Decimal("45.00"),
        "tags": ["coins"], "description": "Pocket.", "image_filename": None}
TRIPS = [
    {"id": 1, "name": "Home", "start_date": None, "end_date": None, "is_default": True, "item_count": 3},
    {"id": 2, "name": "Portugal 2024", "start_date": date(2024, 3, 4), "end_date": date(2024, 3, 12),
     "is_default": False, "item_count": 2},
]
USER = {"id": 1, "username": "sam", "is_admin": False, "is_active": True,
        "password_hash": generate_password_hash("correct horse")}


def collection(role: str) -> dict:
    return {"id": 10, "name": "Coins", "slug": "coins", "role": role, "item_count": 1,
            "total_value": Decimal("1234.50")}


@pytest.fixture
def app():
    with patch("app.db.ConnectionPool"):
        return create_app({"TESTING": True, "SECRET_KEY": "test", "WTF_CSRF_ENABLED": False})


@pytest.fixture
def stub():
    """Patch repository functions; returns a function to set the user's role."""
    stack = ExitStack()
    state = {"role": "viewer", "user": dict(USER)}

    def role_lookup(slug, user_id):
        return collection(state["role"]) if state["role"] and slug == "coins" else None

    targets = {
        "user_repository.get_by_id": lambda i: state["user"],
        "user_repository.get_by_username": lambda n: state["user"] if n == "sam" else None,
        "collection_repository.get_for_user": role_lookup,
        "collection_repository.list_for_user": lambda uid: [collection(state["role"] or "viewer")],
        "repository.list_items": lambda *a, **k: ([ITEM], 1),
        "repository.get_item": lambda *a: ITEM,
        "repository.list_tags": lambda cid: [{"name": "coins", "n": 1}],
        "trip_repository.list_trips": lambda cid, conn=None: TRIPS,
        "trip_repository.get_trip": lambda cid, tid: next((t for t in TRIPS if t["id"] == tid), None),
        "trip_repository.get_default": lambda cid, conn=None: TRIPS[0],
        "repository.all_items": lambda cid: [ITEM],
        "repository.get_stats": lambda cid: {"item_count": 7, "with_images": 3, "tags": 2, "trips": 1,
                                          "total_value": Decimal("1234.50")},
        "repository.image_belongs": lambda cid, f: False,
        "repository.create_item": lambda cid, d: 5,
    }
    for name, fn in targets.items():
        stack.enter_context(patch(f"app.{name}", side_effect=fn))
    yield state
    stack.close()


@pytest.fixture
def client(app, stub):
    return app.test_client()


@pytest.fixture
def login(client):
    def _login():
        with client.session_transaction() as s:
            s["_user_id"] = "1"
    return _login
