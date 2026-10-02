"""Form parsing and validation for item create/edit."""
from datetime import date

MAX_NAME = 200
MAX_LOCATION = 200
MAX_TRIP = 200
MAX_TAGS = 20
MAX_TAG_LENGTH = 40
MAX_DESCRIPTION = 5000


def parse_tags(raw: str) -> list[str]:
    """Split a comma-separated string into unique, lowercase, whitespace-normalised tags."""
    seen, tags = set(), []
    for part in raw.split(","):
        tag = " ".join(part.split()).lower()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def parse_item_form(form) -> tuple[dict, dict]:
    """Validate submitted form data.

    Returns (data, errors). `data` holds cleaned values ready for the
    repository; `errors` maps field name -> message (empty if valid).
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

    trip_name = form.get("trip_name", "").strip()
    if len(trip_name) > MAX_TRIP:
        errors["trip_name"] = f"Keep the trip name under {MAX_TRIP} characters."

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
        "trip_name": trip_name or None,
        "tags": tags,
        "description": description or None,
    }
    return data, errors
