from datetime import date, timedelta

from app.forms import parse_item_form


def test_valid_form():
    data, errors = parse_item_form({"name": " Brass compass ", "date_acquired": "2024-03-04"})
    assert not errors
    assert data["name"] == "Brass compass"
    assert data["date_acquired"] == date(2024, 3, 4)


def test_name_required():
    _, errors = parse_item_form({"name": "  "})
    assert "name" in errors


def test_future_date_rejected():
    future = (date.today() + timedelta(days=2)).isoformat()
    _, errors = parse_item_form({"name": "x", "date_acquired": future})
    assert "date_acquired" in errors


def test_tags_are_normalised_and_deduplicated():
    from app.forms import parse_tags
    assert parse_tags(" Coins,coins , Old  Maps,,") == ["coins", "old maps"]


def test_trip_and_tags_in_cleaned_data():
    data, errors = parse_item_form({"name": "x", "trip_id": "7", "tags": "a, b"})
    assert not errors and data["trip_id"] == 7 and data["tags"] == ["a", "b"]


import pytest
from decimal import Decimal
from app.forms import parse_cost


@pytest.mark.parametrize("raw,expected", [("", None), ("$1,234.5", Decimal("1234.50")), ("24", Decimal("24.00")), ("0", Decimal("0.00"))])
def test_cost_parsing(raw, expected):
    assert parse_cost(raw) == (expected, None)


@pytest.mark.parametrize("raw", ["abc", "-5", "NaN", "1e99"])
def test_cost_rejects_bad_values(raw):
    assert parse_cost(raw)[1]


def test_missing_trip_means_default():
    data, _ = parse_item_form({"name": "x"})
    assert data["trip_id"] is None
