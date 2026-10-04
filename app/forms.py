"""Form parsing and validation for item create/edit."""
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation

MAX_NAME = 200
MAX_LOCATION = 200
MAX_DESCRIPTION = 5000
MAX_TAGS = 20
MAX_TAG_LENGTH = 40
MAX_COST = Decimal("9999999999.99")

_CURRENCY_PREFIX = re.compile(r"^[\s$€£¥]+")


def parse_tags(raw: str) -> list[str]:
    """Split a comma-separated string into unique, lowercase, whitespace-normalised tags."""
    seen, tags = set(), []
    for part in raw.split(","):
        tag = " ".join(part.split()).lower()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def parse_cost(raw: str) -> tuple[Decimal | None, str | None]:
    """Parse '1,234.5' or '$24' into (Decimal rounded to cents, error). Blank is allowed."""
    text = _CURRENCY_PREFIX.sub("", raw.replace(",", "")).strip()
    if not text:
        return None, None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None, "Enter the cost as a number, like 24.99."
    if not value.is_finite() or value < 0:
        return None, "Enter a cost of zero or more."
    if value > MAX_COST:
        return None, "That cost is too large."
    return value.quantize(Decimal("0.01")), None


def parse_coordinates(raw_lat: str, raw_lon: str) -> tuple[float | None, float | None, str | None]:
    """Parse an optional map pin. Both values or neither. Returns (lat, lon, error)."""
    raw_lat, raw_lon = raw_lat.strip(), raw_lon.strip()
    if not raw_lat and not raw_lon:
        return None, None, None
    if not raw_lat or not raw_lon:
        return None, None, "Enter both latitude and longitude, or clear both."
    try:
        lat, lon = float(raw_lat), float(raw_lon)
    except ValueError:
        return None, None, "Latitude and longitude must be numbers, like 38.7223 and -9.1393."
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None, "Latitude must be between -90 and 90, and longitude between -180 and 180."
    return round(lat, 5), round(lon, 5), None


def parse_item_form(form) -> tuple[dict, dict]:
    """Validate submitted form data.

    Returns (data, errors). `data` holds cleaned values ready for the
    repository; `errors` maps field name -> message (empty if valid).
    `trip_id` is None when absent; the repository then uses the default trip.
    """
    errors: dict[str, str] = {}

    name = form.get("name", "").strip()
    if not name:
        errors["name"] = "Enter a name for this item."
    elif len(name) > MAX_NAME:
        errors["name"] = f"Keep the name under {MAX_NAME} characters."

    date_acquired = None
    raw_date = form.get("date_acquired", "").strip()
    if raw_date:
        try:
            date_acquired = date.fromisoformat(raw_date)
        except ValueError:
            errors["date_acquired"] = "Enter a valid date."
        else:
            if date_acquired > date.today():
                errors["date_acquired"] = "The date can't be in the future."

    location = form.get("location_acquired", "").strip()
    if len(location) > MAX_LOCATION:
        errors["location_acquired"] = f"Keep the location under {MAX_LOCATION} characters."

    latitude, longitude, pin_error = parse_coordinates(
        str(form.get("latitude", "")), str(form.get("longitude", "")))
    if pin_error:
        errors["latitude"] = pin_error

    cost, cost_error = parse_cost(form.get("cost", ""))
    if cost_error:
        errors["cost"] = cost_error

    raw_trip = str(form.get("trip_id", "")).strip()
    trip_id = int(raw_trip) if raw_trip.isdigit() else None

    tags = parse_tags(form.get("tags", ""))
    if len(tags) > MAX_TAGS:
        errors["tags"] = f"Use at most {MAX_TAGS} tags."
    elif any(len(t) > MAX_TAG_LENGTH for t in tags):
        errors["tags"] = f"Keep each tag under {MAX_TAG_LENGTH} characters."

    description = form.get("description", "").strip()
    if len(description) > MAX_DESCRIPTION:
        errors["description"] = f"Keep the description under {MAX_DESCRIPTION} characters."

    data = {
        "name": name,
        "date_acquired": date_acquired,
        "location_acquired": location or None,
        "latitude": latitude,
        "longitude": longitude,
        "trip_id": trip_id,
        "cost": cost,
        "tags": tags,
        "description": description or None,
    }
    return data, errors
