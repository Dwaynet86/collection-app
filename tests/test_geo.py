"""Map pins: coordinates parsing, offline place search, map routes, import/export, front-end guards."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app import exporter, importer, places
from app.forms import parse_coordinates, parse_item_form
from tests.conftest import ITEM
from tests.test_importer import _upload

STATIC = Path(__file__).parent.parent / "app" / "static"


# ---- coordinates -------------------------------------------------------------

@pytest.mark.parametrize("lat,lon,expected", [
    ("", "", (None, None)),
    ("38.7223", "-9.1393", (38.7223, -9.1393)),
    (" 38.722312345 ", "-9.1", (38.72231, -9.1)),
    ("-90", "180", (-90.0, 180.0)),
])
def test_valid_coordinates(lat, lon, expected):
    assert parse_coordinates(lat, lon)[:2] == expected and parse_coordinates(lat, lon)[2] is None


@pytest.mark.parametrize("lat,lon", [("38", ""), ("", "9"), ("abc", "1"), ("91", "0"), ("0", "181"), ("nan", "0"), ("inf", "0")])
def test_invalid_coordinates(lat, lon):
    assert parse_coordinates(lat, lon)[2]


def test_item_form_carries_pin_and_reports_errors_on_latitude_field():
    data, errors = parse_item_form({"name": "x", "latitude": "10", "longitude": "20"})
    assert not errors and (data["latitude"], data["longitude"]) == (10.0, 20.0)
    assert "latitude" in parse_item_form({"name": "x", "latitude": "10"})[1]


# ---- export / import -----------------------------------------------------------

def test_csv_keeps_negative_coordinates_numeric():
    item = {**ITEM, "latitude": -33.8688, "longitude": 151.2093}
    text = exporter.to_csv([item]).decode("utf-8-sig")
    assert ",-33.8688,151.2093," in text and "'-33.8688" not in text


def test_text_cells_are_still_formula_safe():
    assert exporter._cell("=cmd()") == "'=cmd()"


def test_json_export_roundtrips_through_importer():
    item = {**ITEM, "latitude": 38.7223, "longitude": -9.1393}
    payload = json.loads(exporter.to_json([item], []))
    bundle = importer.load_bundle(_upload(payload, "x.json"))
    assert (bundle.items[0]["latitude"], bundle.items[0]["longitude"]) == (38.7223, -9.1393)


def test_old_backup_without_pins_still_imports():
    bundle = importer.load_bundle(_upload({"items": [{"name": "Old"}]}, "x.json"))
    assert bundle.items[0]["latitude"] is None


def test_backup_with_half_a_pin_is_rejected():
    with pytest.raises(importer.BackupError):
        importer.load_bundle(_upload({"items": [{"name": "x", "latitude": "10"}]}, "x.json"))


# ---- offline place search ----------------------------------------------------------

def _labels(q, n=5):
    return [r["label"] for r in places.search(q, n)]


def test_search_finds_cities_countries_and_ignores_accents():
    assert _labels("lisbon")[0] == "Lisbon, Portugal"
    assert _labels("sao paulo")[0] == "São Paulo, Brazil"
    assert _labels("portugal")[0] == "Portugal"
    assert _labels("waukegan")[0] == "Waukegan, Illinois, United States"


def test_search_can_narrow_by_region():
    assert _labels("springfield, illinois")[0] == "Springfield, Illinois, United States"
    assert places.search("x") == [] and places.search("") == []


def test_search_results_have_usable_coordinates():
    r = places.search("lisbon")[0]
    assert 38 < r["lat"] < 39 and -10 < r["lon"] < -8 and r["kind"] == "city"


# ---- routes -------------------------------------------------------------------------

def test_map_page_for_viewers(client, login):
    login()
    html = client.get("/c/coins/map/?tag=coins").get_data(as_text=True)
    assert 'id="map-page"' in html and "/map/pins.json" in html and "vendor/leaflet/leaflet.js" in html


def test_pins_json_shape_and_privacy(client, login):
    login()
    rows = [{"id": 1, "name": "<b>Compass</b>", "latitude": 38.7, "longitude": -9.1,
             "location_acquired": "Lisbon", "image_filename": "a.webp"}]
    with patch("app.repository.map_items", return_value=(rows, 3, 1)) as mi:
        r = client.get("/c/coins/map/pins.json?q=comp&tag=brass&trip=2")
    mi.assert_called_once_with(10, "comp", "brass", 2)
    body = r.get_json()
    assert body["matching"] == 3 and body["unpinned"] == 2 and body["truncated"] is False
    pin = body["pins"][0]
    assert pin["name"] == "<b>Compass</b>" and pin["thumb"].endswith("/thumbs/a.webp") and pin["url"].endswith("/items/1")
    assert "cost" not in pin and "no-store" in r.headers["Cache-Control"]


def test_place_search_endpoint_is_editor_only(client, login, stub):
    login(); stub["role"] = "viewer"
    assert client.get("/c/coins/map/search?q=lisbon").status_code == 403
    stub["role"] = "editor"
    assert client.get("/c/coins/map/search?q=lisbon").get_json()[0]["label"] == "Lisbon, Portugal"


def test_map_requires_login(client):
    assert client.get("/c/coins/map/").status_code == 302


def test_item_form_has_picker_and_prefills_existing_pin(client, login, stub):
    login(); stub["role"] = "editor"
    assert 'id="geo-picker"' in client.get("/c/coins/items/new").get_data(as_text=True)
    item = {**ITEM, "latitude": 38.7223, "longitude": -9.1393}
    with patch("app.repository.get_item", return_value=item):
        html = client.get("/c/coins/items/1/edit").get_data(as_text=True)
    assert 'value="38.7223"' in html and 'value="-9.1393"' in html and "<details" in html and " open" in html.split('id="geo-picker"')[1][:260]


def test_saving_an_item_stores_the_pin(client, login, stub):
    login(); stub["role"] = "editor"
    with patch("app.repository.create_item", return_value=5) as create:
        r = client.post("/c/coins/items/new", data={"name": "Coin", "latitude": "38.7", "longitude": "-9.1"})
    assert r.status_code == 302
    saved = create.call_args.args[1]
    assert (saved["latitude"], saved["longitude"]) == (38.7, -9.1)
    r = client.post("/c/coins/items/new", data={"name": "Coin", "latitude": "38.7"})
    assert r.status_code == 400 and b"both latitude and longitude" in r.data


def test_detail_and_gallery_link_to_map(client, login):
    login()
    assert "Show on map" not in client.get("/c/coins/items/1").get_data(as_text=True)   # no pin yet
    with patch("app.repository.get_item", return_value={**ITEM, "latitude": 1.5, "longitude": 2.5}):
        html = client.get("/c/coins/items/1").get_data(as_text=True)
    assert "Show on map" in html and "focus=1" in html
    assert "/c/coins/map/" in client.get("/c/coins/").get_data(as_text=True)


# ---- bundled assets / front-end guards ----------------------------------------------------

def test_bundled_map_assets_exist_and_are_valid():
    for rel in ("vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "vendor/leaflet/LICENSE",
                "vendor/markercluster/leaflet.markercluster.js", "vendor/markercluster/MarkerCluster.css"):
        assert (STATIC / rel).is_file(), rel
    data = json.loads((STATIC / "geo/countries.json").read_text())
    assert data["type"] == "FeatureCollection" and len(data["features"]) > 200


def test_no_external_urls_in_map_code():
    for rel in ("js/geo.js", "js/picker.js", "js/map.js"):
        text = (STATIC / rel).read_text()
        assert "http://" not in text and "https://" not in text, rel


def test_map_scripts_never_build_html_from_item_data():
    for rel in ("js/geo.js", "js/picker.js", "js/map.js"):
        text = (STATIC / rel).read_text()
        assert "innerHTML" not in text and "insertAdjacentHTML" not in text, rel
