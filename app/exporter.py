"""Build downloadable exports of a collection: CSV, JSON, and a full ZIP backup.

The JSON/ZIP format is what importer.py reads back (format "version": 2).
"""
import csv
import io
import json
import tempfile
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ITEM_FIELDS = [
    "id", "name", "date_acquired", "location_acquired", "latitude", "longitude", "trip_name",
    "cost", "tags",
    "description", "image_filename", "created_at", "updated_at",
]
TRIP_FIELDS = ["name", "start_date", "end_date", "is_default"]


def _cell(value) -> str:
    """Format a value for CSV. Neutralises spreadsheet formula injection."""
    if value is None:
        return ""
    if isinstance(value, (int, float, Decimal)):   # numbers (e.g. -9.14) are not formulas
        return str(value)
    if isinstance(value, (list, tuple)):
        value = "; ".join(value)
    text = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return "'" + text if text and text[0] in "=+-@\t\r" else text


def to_csv(items: list[dict]) -> bytes:
    """One row per item. UTF-8 with BOM so Excel reads accents correctly."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(ITEM_FIELDS)
    for item in items:
        writer.writerow([_cell(item.get(f)) for f in ITEM_FIELDS])
    return buf.getvalue().encode("utf-8-sig")


def _json_default(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)  # dates, Decimal


def to_json(items: list[dict], trips: list[dict] | None = None) -> str:
    payload = {
        "version": 2,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "trips": [{f: t.get(f) for f in TRIP_FIELDS} for t in (trips or [])],
        "items": [{f: item.get(f) for f in ITEM_FIELDS} for item in items],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default)


def build_backup_zip(items: list[dict], trips: list[dict], upload_dir: Path):
    """ZIP containing items.json and every referenced image under images/.

    Returns a seekable file object positioned at the start.
    """
    tmp = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("items.json", to_json(items, trips))
        for item in items:
            name = item.get("image_filename")
            path = upload_dir / name if name else None
            if path and path.is_file():
                # WebP is already compressed; store without recompressing.
                zf.write(path, f"images/{name}", compress_type=zipfile.ZIP_STORED)
    tmp.seek(0)
    return tmp
