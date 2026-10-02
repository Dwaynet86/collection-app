import json
import zipfile
from datetime import date, datetime, timezone

from app import exporter

ITEM = {
    "id": 1, "name": "=cmd()", "date_acquired": date(2024, 3, 4),
    "location_acquired": None, "trip_name": "Portugal 2024", "tags": ["coins", "bronze"],
    "description": "", "image_filename": "a.webp",
    "created_at": datetime(2024, 3, 5, tzinfo=timezone.utc), "updated_at": None,
}


def test_csv_escapes_formulas_and_joins_tags():
    text = exporter.to_csv([ITEM]).decode("utf-8-sig")
    assert "'=cmd()" in text
    assert "coins; bronze" in text


def test_json_roundtrip():
    data = json.loads(exporter.to_json([ITEM]))
    assert data["items"][0]["date_acquired"] == "2024-03-04"


def test_backup_zip_contains_images(tmp_path):
    (tmp_path / "a.webp").write_bytes(b"img")
    with zipfile.ZipFile(exporter.build_backup_zip([ITEM], tmp_path)) as zf:
        assert set(zf.namelist()) == {"items.json", "images/a.webp"}
