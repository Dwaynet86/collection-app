from datetime import date

from app.trip_forms import parse_trip_form


def test_range_trip():
    data, errors = parse_trip_form({"name": " Rome ", "start_date": "2024-05-01", "end_date": "2024-05-09"})
    assert not errors and data == {"name": "Rome", "start_date": date(2024, 5, 1), "end_date": date(2024, 5, 9)}


def test_single_day_trip_drops_equal_end_date():
    data, errors = parse_trip_form({"name": "Day out", "start_date": "2024-05-01", "end_date": "2024-05-01"})
    assert not errors and data["end_date"] is None


def test_start_required_except_for_default_trip():
    assert "start_date" in parse_trip_form({"name": "x"})[1]
    assert not parse_trip_form({"name": "Home"}, require_start=False)[1]


def test_end_before_start_rejected():
    assert "end_date" in parse_trip_form({"name": "x", "start_date": "2024-05-09", "end_date": "2024-05-01"})[1]


def test_end_without_start_rejected():
    assert "end_date" in parse_trip_form({"name": "Home", "end_date": "2024-05-01"}, require_start=False)[1]
