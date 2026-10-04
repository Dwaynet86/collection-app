"""Validation for the trip add/edit form."""
from datetime import date

MAX_NAME = 200


def _parse_date(raw: str):
    """Return (date | None, ok). Blank is (None, True)."""
    raw = raw.strip()
    if not raw:
        return None, True
    try:
        return date.fromisoformat(raw), True
    except ValueError:
        return None, False


def parse_trip_form(form, require_start: bool = True) -> tuple[dict, dict]:
    """Return (data, errors). data keys: name, start_date, end_date.

    The default trip passes require_start=False (it has no dates).
    A trip with an end date equal to its start date is stored as a single-day trip.
    """
    errors: dict[str, str] = {}

    name = form.get("name", "").strip()
    if not name:
        errors["name"] = "Enter a name for the trip."
    elif len(name) > MAX_NAME:
        errors["name"] = f"Keep the name under {MAX_NAME} characters."

    start, start_ok = _parse_date(form.get("start_date", ""))
    end, end_ok = _parse_date(form.get("end_date", ""))
    if not start_ok:
        errors["start_date"] = "Enter a valid start date."
    elif start is None and require_start:
        errors["start_date"] = "Enter the trip's start date."

    if not end_ok:
        errors["end_date"] = "Enter a valid end date."
    elif end is not None and start is None and start_ok:
        errors["end_date"] = "Enter a start date before an end date."
    elif end is not None and start is not None and end < start:
        errors["end_date"] = "The end date can't be before the start date."

    if end is not None and end == start:
        end = None
    return {"name": name, "start_date": start, "end_date": end}, errors
