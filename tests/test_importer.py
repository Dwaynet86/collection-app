"""Backup import: validation, trip mapping, and rollback of saved images."""
import io
import json
import zipfile
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from werkzeug.datastructures import FileStorage

from app import importer

PAYLOAD = {
    "version": 2,
    "trips": [
        {"name": "Home Base", "start_date": None, "end_date": None, "is_default": True},
        {"name": "Portugal 2024", "start_date": "2024-03-04", "end_date": "2024-03-12", "is_default": False},
    ],
    "items": [
        {"name": "Compass", "date_acquired": "2024-03-05", "location_acquired": "Lisbon",
         "trip_name": "Portugal 2024", "cost": "45.00", "tags": ["brass"], "description": "",
         "image_filename": "a.webp", "created_at": "2024-03-06T10:00:00+00:00"},
        {"name": "Mug", "trip_name": "Home Base", "cost": "", "tags": [], "image_filename": None},
    ],
}


def _upload(payload, name="backup.zip", images=None):
    buf = io.BytesIO()
    if name.endswith(".zip"):
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("items.json", json.dumps(payload))
            for fname, data in (images or {}).items():
                zf.writestr(f"images/{fname}", data)
    else:
        buf.write(json.dumps(payload).encode())
    buf.seek(0)
    return FileStorage(buf, filename=name)


def test_rejects_wrong_file_types():
    with pytest.raises(importer.BackupError):
        importer.load_bundle(FileStorage(io.BytesIO(b"x"), filename="notes.txt"))
    with pytest.raises(importer.BackupError):
        importer.load_bundle(FileStorage(io.BytesIO(b"not a zip"), filename="x.zip"))


def test_zip_without_items_json_is_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("other.txt", "hi")
    buf.seek(0)
    with pytest.raises(importer.BackupError, match="items.json"):
        importer.load_bundle(FileStorage(buf, filename="x.zip"))


def test_invalid_items_are_reported_and_nothing_loads():
    bad = {"items": [{"name": ""}, {"name": "ok", "cost": "abc"}]}
    with pytest.raises(importer.BackupError) as exc:
        importer.load_bundle(_upload(bad, "x.json"))
    assert len(exc.value.problems) == 2


def test_v1_json_without_trips_list_loads():
    bundle = importer.load_bundle(_upload({"items": [{"name": "Old", "trip_name": "Rome"}]}, "x.json"))
    assert bundle.trips == [] and bundle.items[0]["_trip_name"] == "Rome"


def test_image_names_cannot_escape_images_folder():
    bundle = importer.load_bundle(_upload({"items": [{"name": "x", "image_filename": "../../etc/passwd"}]}, "x.json"))
    assert bundle.items[0]["_image"] == "passwd"


class FakeDb:
    """Records what restore() asks the repositories to do."""

    def __init__(self, existing_names=()):
        self.created, self.trips, self.existing = [], [], set(existing_names)

    def install(self, stack):
        @contextmanager
        def conn():
            yield object()

        stack.enter_context(patch("app.importer.get_conn", conn))
        stack.enter_context(patch("app.importer.trip_repo.get_default", lambda cid, c: {"id": 1, "name": "Home"}))
        stack.enter_context(patch("app.importer.trip_repo.list_trips", lambda cid, c: [{"id": 1, "name": "Home"}]))
        stack.enter_context(patch("app.importer.trip_repo.create_trip", self.create_trip))
        stack.enter_context(patch("app.importer.repo.item_exists", lambda cid, n, d, loc, c: n in self.existing))
        stack.enter_context(patch("app.importer.repo.create_item", lambda cid, data, c: self.created.append(data) or 1))

    def create_trip(self, cid, name, start, end, conn):
        self.trips.append((name, start, end))
        return 100 + len(self.trips)


@pytest.fixture
def stack():
    from contextlib import ExitStack
    with ExitStack() as s:
        yield s


def test_restore_maps_trips_and_default(stack):
    db = FakeDb(); db.install(stack)
    stack.enter_context(patch("app.importer.images.save_image", lambda f: "new.webp"))
    result = importer.restore(10, _upload(PAYLOAD, images={"a.webp": b"img"}))
    assert (result.created, result.skipped, result.trips_created) == (2, 0, 1)
    compass, mug = db.created
    assert compass["trip_id"] == 101 and compass["image_filename"] == "new.webp"
    assert mug["trip_id"] == 1                      # exported default trip -> this collection's default
    assert db.trips[0][0] == "Portugal 2024" and str(db.trips[0][1]) == "2024-03-04"


def test_restore_skips_duplicates_and_counts_missing_images(stack):
    db = FakeDb(existing_names={"Mug"}); db.install(stack)
    result = importer.restore(10, _upload(PAYLOAD))   # no images in the ZIP
    assert (result.created, result.skipped, result.images_missing) == (1, 1, 1)


def test_restore_removes_saved_images_if_database_step_fails(stack):
    db = FakeDb(); db.install(stack)
    deleted = []
    stack.enter_context(patch("app.importer.images.save_image", lambda f: "new.webp"))
    stack.enter_context(patch("app.importer.images.delete_image", deleted.append))
    calls = {"n": 0}

    def flaky(cid, data, conn):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("db down")
        return 1

    stack.enter_context(patch("app.importer.repo.create_item", flaky))
    payload = {"items": [{"name": "A", "image_filename": "a.webp"}, {"name": "B"}]}
    with pytest.raises(RuntimeError):
        importer.restore(10, _upload(payload, images={"a.webp": b"x"}))
    assert deleted == ["new.webp"]
