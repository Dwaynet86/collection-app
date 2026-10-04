"""End-to-end tests against a real PostgreSQL database.

Skipped unless TEST_DATABASE_URL is set. Use a scratch database; the schema is
applied and test data is created under unique names (nothing is dropped):

    TEST_DATABASE_URL=postgresql://postgres:postgres@localhost/collection_test pytest tests/test_integration.py
"""
import io
import os
import uuid
from pathlib import Path

import psycopg
import pytest
from PIL import Image

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    from app import create_app
    from app import collection_repository as coll_repo, user_repository as users
    from werkzeug.security import generate_password_hash

    with psycopg.connect(URL) as conn:
        conn.execute((Path(__file__).parent.parent / "schema.sql").read_text())
    app = create_app({"TESTING": True, "SECRET_KEY": "t", "WTF_CSRF_ENABLED": False,
                      "DATABASE_URL": URL, "UPLOAD_DIR": tmp_path_factory.mktemp("uploads")})
    uid = uuid.uuid4().hex[:8]
    with app.app_context():
        user_id = users.create_user(f"user{uid}", generate_password_hash("password1"))
        slug_a = coll_repo.create(f"Coins {uid}", user_id)
        slug_b = coll_repo.create(f"Stamps {uid}", user_id)
    client = app.test_client()
    assert client.post("/login", data={"username": f"user{uid}", "password": "password1"}).status_code == 302
    return client, slug_a, slug_b


def _png() -> io.BytesIO:
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "blue").save(buf, "PNG")
    buf.seek(0)
    return buf


def _trip_id(client, slug, name):
    html = client.get(f"/c/{slug}/trips/").get_data(as_text=True)
    import re
    m = re.search(r'<strong>%s</strong>.*?/trips/(\d+)/edit' % re.escape(name), html, re.S)
    return int(m.group(1))


def test_full_flow(env):
    client, a, b = env
    base = f"/c/{a}"

    # every collection starts with a default "Home" trip
    assert "Default" in client.get(f"{base}/trips/").get_data(as_text=True)

    # add a dated trip
    r = client.post(f"{base}/trips/", data={"name": "Rome", "start_date": "2024-05-01", "end_date": "2024-05-09"})
    assert r.status_code == 302
    dup = client.post(f"{base}/trips/", data={"name": "rome", "start_date": "2024-05-01"})
    assert dup.status_code == 400 and b"already exists" in dup.data
    rome = _trip_id(client, a, "Rome")

    # add items: one with trip + cost + photo + tags, one defaulting to Home
    r = client.post(f"{base}/items/new", data={
        "name": "Bronze coin", "trip_id": str(rome), "date_acquired": "2024-05-02", "cost": "$1,200.50",
        "tags": "Roman, bronze", "image": (_png(), "coin.png")}, content_type="multipart/form-data")
    assert r.status_code == 302
    coin_url = r.headers["Location"]
    assert client.post(f"{base}/items/new", data={"name": "Old mug", "cost": "10"}).status_code == 302

    html = client.get(f"{base}/").get_data(as_text=True)
    assert "EST. VALUE" in html and "$1,210.50" in html
    assert "$1,200.50" not in html.split("</header>")[1]            # no per-item cost in the gallery
    detail = client.get(coin_url).get_data(as_text=True)
    assert "$1,200.50" in detail and "Rome" in detail and "May 1, 2024 – May 9, 2024" in detail

    # filters and search
    assert "1 item" in client.get(f"{base}/?trip={rome}").get_data(as_text=True)
    assert "Bronze coin" in client.get(f"{base}/?q=rome").get_data(as_text=True)
    assert "Bronze coin" in client.get(f"{base}/?tag=roman").get_data(as_text=True)

    # a trip from another collection can't be attached: falls back to Home
    client.post(f"/c/{b}/trips/", data={"name": "Paris", "start_date": "2024-06-01"})
    paris = _trip_id(client, b, "Paris")
    client.post(f"{base}/items/new", data={"name": "Sneaky", "trip_id": str(paris)})
    assert "Paris" not in client.get(f"{base}/?q=sneaky").get_data(as_text=True)

    # export, then restore into the other collection
    zip_bytes = client.get(f"{base}/maintenance/export.zip").data
    assert client.get(f"{base}/maintenance/export.csv").data.startswith(b"\xef\xbb\xbfid,name")
    up = lambda skip: client.post(f"/c/{b}/maintenance/import", content_type="multipart/form-data", follow_redirects=True,
                                  data={"backup": (io.BytesIO(zip_bytes), "backup.zip"), **({"skip_duplicates": "1"} if skip else {})})
    r = up(True)
    assert b"Imported 3 items" in r.data and b"added 1 trip" in r.data
    r = up(True)
    assert b"Imported 0 items" in r.data and b"skipped 3" in r.data
    stamps = client.get(f"/c/{b}/?q=bronze").get_data(as_text=True)
    assert "Bronze coin" in stamps and "/thumbs/" in stamps          # photo restored
    assert "May 1, 2024" in client.get(f"/c/{b}/trips/").get_data(as_text=True)   # trip dates restored
    # images are only served inside the owning collection
    thumb = stamps.split("/thumbs/")[1].split('"')[0]
    assert client.get(f"/c/{b}/thumbs/{thumb}").status_code == 200

    # deleting a trip moves its items to Home
    r = client.post(f"{base}/trips/{rome}/delete", follow_redirects=True)
    assert b"1 item moved to Home" in r.data
    assert "Home" in client.get(coin_url).get_data(as_text=True)
    assert client.post(f"{base}/trips/{_trip_id(client, a, 'Home')}/delete", follow_redirects=True).data.count(b"can&#39;t be deleted") == 1

    # collections page header shows the combined value
    assert "EST. VALUE" in client.get("/collections").get_data(as_text=True)


def test_map_pins_flow(env):
    client, a, b = env
    base = f"/c/{a}"
    pinned = {"name": "Lisbon tile", "latitude": "38.7223", "longitude": "-9.1393", "tags": "azulejo",
              "location_acquired": "Lisbon, Portugal", "cost": "30"}
    assert client.post(f"{base}/items/new", data=pinned).status_code == 302
    assert client.post(f"{base}/items/new", data={"name": "Sydney mug", "latitude": "-33.8688",
                                                  "longitude": "151.2093", "tags": "mug"}).status_code == 302
    assert client.post(f"{base}/items/new", data={"name": "Unpinned thing", "tags": "azulejo"}).status_code == 302

    # half a pin is rejected by the form, and by the database constraint underneath it
    bad = client.post(f"{base}/items/new", data={"name": "Half", "latitude": "10"})
    assert bad.status_code == 400
    with psycopg.connect(URL) as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO items (collection_id, trip_id, name, latitude) "
                     "SELECT c.id, t.id, 'x', 5 FROM collections c JOIN trips t ON t.collection_id = c.id AND t.is_default "
                     "WHERE c.slug = %s", (a,))

    body = client.get(f"{base}/map/pins.json").get_json()
    names = {p["name"] for p in body["pins"]}
    assert {"Lisbon tile", "Sydney mug"} <= names and "Unpinned thing" not in names
    assert body["unpinned"] >= 1 and all("cost" not in p for p in body["pins"])
    sydney = next(p for p in body["pins"] if p["name"] == "Sydney mug")
    assert sydney["lat"] == -33.8688 and sydney["lon"] == 151.2093          # negative values survive

    # filters: tag, search, and both together; counts reflect unpinned matches
    tagged = client.get(f"{base}/map/pins.json?tag=azulejo").get_json()
    assert [p["name"] for p in tagged["pins"]] == ["Lisbon tile"] and tagged["matching"] == 2 and tagged["unpinned"] == 1
    assert [p["name"] for p in client.get(f"{base}/map/pins.json?q=sydney").get_json()["pins"]] == ["Sydney mug"]
    assert client.get(f"{base}/map/pins.json?q=sydney&tag=azulejo").get_json()["pins"] == []

    # pins are per collection
    other = client.get(f"/c/{b}/map/pins.json").get_json()
    assert "Lisbon tile" not in {p["name"] for p in other["pins"]}

    # editing the pin and clearing it
    item_id = next(p["id"] for p in body["pins"] if p["name"] == "Lisbon tile")
    assert client.post(f"{base}/items/{item_id}/edit", data={"name": "Lisbon tile", "latitude": "41.15", "longitude": "-8.61"}).status_code == 302
    moved = next(p for p in client.get(f"{base}/map/pins.json?q=lisbon").get_json()["pins"])
    assert (moved["lat"], moved["lon"]) == (41.15, -8.61)
    assert client.post(f"{base}/items/{item_id}/edit", data={"name": "Lisbon tile"}).status_code == 302
    assert client.get(f"{base}/map/pins.json?q=lisbon").get_json()["pins"] == []

    # backup -> restore into another collection keeps pins; CSV keeps negative numbers
    zip_bytes = client.get(f"{base}/maintenance/export.zip").data
    csv = client.get(f"{base}/maintenance/export.csv").data.decode("utf-8-sig")
    assert ",-33.8688,151.2093," in csv
    r = client.post(f"/c/{b}/maintenance/import", content_type="multipart/form-data", follow_redirects=True,
                    data={"backup": (io.BytesIO(zip_bytes), "backup.zip"), "skip_duplicates": "1"})
    assert b"Imported" in r.data
    restored = {p["name"]: p for p in client.get(f"/c/{b}/map/pins.json").get_json()["pins"]}
    assert restored["Sydney mug"]["lat"] == -33.8688

    # the map page and search endpoint work for the owner
    assert b"map-page" in client.get(f"{base}/map/").data
    assert client.get(f"{base}/map/search?q=lisbon").get_json()[0]["label"] == "Lisbon, Portugal"
