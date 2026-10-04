"""Restore items into a collection from an export (ZIP backup or items JSON).

Safety:
  * the whole file is validated before anything is written;
  * database changes happen in one transaction (all or nothing);
  * images are re-encoded through images.save_image, never copied as-is;
  * ZIP entries are only ever read by exact name, never extracted to disk.
"""
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from werkzeug.datastructures import FileStorage

from . import images, repository as repo, trip_repository as trip_repo
from .db import get_conn
from .forms import parse_item_form

MAX_ITEMS = 20_000
MAX_JSON_BYTES = 50 * 1024 * 1024
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_ZIP_ENTRIES = 50_000


class BackupError(ValueError):
    """The file can't be imported. `problems` is a list of user-facing messages."""

    def __init__(self, *problems: str):
        super().__init__(problems[0] if problems else "Import failed.")
        self.problems = list(problems)


@dataclass
class Bundle:
    trips: list[dict]
    items: list[dict]
    zf: zipfile.ZipFile | None = None


@dataclass
class Result:
    created: int = 0
    skipped: int = 0
    trips_created: int = 0
    images_missing: int = 0


# ---- Reading ---------------------------------------------------------------

def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _read_payload(upload) -> tuple[object, zipfile.ZipFile | None]:
    filename = (upload.filename or "").lower()
    zf = None
    try:
        if filename.endswith(".zip"):
            zf = zipfile.ZipFile(upload.stream)
            if len(zf.infolist()) > MAX_ZIP_ENTRIES:
                raise BackupError("This ZIP has too many files to be a Collection backup.")
            try:
                info = zf.getinfo("items.json")
            except KeyError:
                raise BackupError("This ZIP has no items.json, so it isn't a Collection backup.") from None
            if info.file_size > MAX_JSON_BYTES:
                raise BackupError("The data file inside the ZIP is too large.")
            raw = zf.read(info)
        elif filename.endswith(".json"):
            raw = upload.stream.read(MAX_JSON_BYTES + 1)
            if len(raw) > MAX_JSON_BYTES:
                raise BackupError("That JSON file is too large.")
        else:
            raise BackupError("Choose a .zip backup or a .json export.")
        return json.loads(raw), zf
    except zipfile.BadZipFile:
        raise BackupError("That file isn't a valid ZIP.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise BackupError("The data in that file couldn't be read.") from None
    except BackupError:
        if zf:
            zf.close()
        raise


def _parse_date(value, label: str, problems: list[str]) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        problems.append(f"{label}: “{text}” isn't a valid date.")
        return None


def _parse_timestamp(value) -> datetime | None:
    text = _text(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")) if text else None
    except ValueError:
        return None


def _trip_from_raw(raw, index: int, problems: list[str]) -> dict | None:
    if not isinstance(raw, dict) or not _text(raw.get("name")):
        problems.append(f"Trip {index} has no name.")
        return None
    label = f"Trip “{_text(raw['name'])}”"
    start = _parse_date(raw.get("start_date"), label, problems)
    end = _parse_date(raw.get("end_date"), label, problems)
    if end and (not start or end < start):
        end = None
    return {"name": _text(raw["name"])[:200], "start": start, "end": end,
            "is_default": bool(raw.get("is_default"))}


def _item_from_raw(raw, index: int, problems: list[str]) -> dict | None:
    if not isinstance(raw, dict):
        problems.append(f"Item {index} isn't a valid entry.")
        return None
    tags = raw.get("tags") or []
    form = {
        "name": _text(raw.get("name")),
        "date_acquired": _text(raw.get("date_acquired"))[:10],
        "location_acquired": _text(raw.get("location_acquired")),
        "latitude": _text(raw.get("latitude")),
        "longitude": _text(raw.get("longitude")),
        "cost": _text(raw.get("cost")),
        "description": _text(raw.get("description")),
        "tags": ", ".join(map(str, tags)) if isinstance(tags, list) else _text(tags),
    }
    data, errors = parse_item_form(form)
    if errors:
        problems.append(f"Item {index} ({form['name'] or 'no name'}): {' '.join(errors.values())}")
        return None
    data["created_at"] = _parse_timestamp(raw.get("created_at"))
    data["_trip_name"] = _text(raw.get("trip_name"))
    data["_image"] = Path(_text(raw.get("image_filename"))).name or None
    return data


def load_bundle(upload) -> Bundle:
    """Read and fully validate an uploaded backup. Raises BackupError."""
    payload, zf = _read_payload(upload)
    problems: list[str] = []

    if isinstance(payload, list):
        raw_items, raw_trips = payload, []
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        raw_items, raw_trips = payload["items"], payload.get("trips") or []
    else:
        raise BackupError("That file doesn't contain a list of items.")
    if len(raw_items) > MAX_ITEMS:
        raise BackupError(f"Too many items to import at once (limit {MAX_ITEMS:,}).")

    trips = [t for i, raw in enumerate(raw_trips, 1) if (t := _trip_from_raw(raw, i, problems))]
    items = [x for i, raw in enumerate(raw_items, 1) if (x := _item_from_raw(raw, i, problems))]
    if problems:
        if zf:
            zf.close()
        raise BackupError(*problems)
    return Bundle(trips=trips, items=items, zf=zf)


# ---- Writing ---------------------------------------------------------------

def _store_image(zf, name: str | None, saved: list[str], result: Result) -> str | None:
    """Re-encode an image from the ZIP. Missing or unreadable images are skipped."""
    if not name or zf is None:
        return None
    try:
        info = zf.getinfo(f"images/{name}")
        if info.file_size > MAX_IMAGE_BYTES:
            raise KeyError(name)
        stored = images.save_image(FileStorage(io.BytesIO(zf.read(info)), filename=name))
    except (KeyError, images.ImageError):
        result.images_missing += 1
        return None
    saved.append(stored)
    return stored


def restore(collection_id: int, upload, skip_duplicates: bool = True) -> Result:
    """Import a backup into a collection. Raises BackupError if the file is unusable."""
    bundle = load_bundle(upload)
    result, saved = Result(), []
    try:
        with get_conn() as conn:
            default_id = trip_repo.get_default(collection_id, conn)["id"]
            by_name = {t["name"].lower(): t["id"] for t in trip_repo.list_trips(collection_id, conn)}
            trip_ids: dict[str, int] = {}

            def trip_for(name: str, start=None, end=None) -> int:
                key = name.lower()
                if key not in trip_ids:
                    if key not in by_name:
                        by_name[key] = trip_repo.create_trip(collection_id, name, start, end, conn)
                        result.trips_created += 1
                    trip_ids[key] = by_name[key]
                return trip_ids[key]

            for trip in bundle.trips:
                if trip["is_default"]:
                    trip_ids[trip["name"].lower()] = default_id
                else:
                    trip_for(trip["name"], trip["start"], trip["end"])

            for data in bundle.items:
                trip_name, image = data.pop("_trip_name"), data.pop("_image")
                data["trip_id"] = trip_for(trip_name) if trip_name else default_id
                if skip_duplicates and repo.item_exists(
                    collection_id, data["name"], data["date_acquired"],
                    data["location_acquired"], conn,
                ):
                    result.skipped += 1
                    continue
                data["image_filename"] = _store_image(bundle.zf, image, saved, result)
                repo.create_item(collection_id, data, conn)
                result.created += 1
    except Exception:
        for name in saved:           # database rolled back; remove the files we wrote
            images.delete_image(name)
        raise
    finally:
        if bundle.zf:
            bundle.zf.close()
    return result
