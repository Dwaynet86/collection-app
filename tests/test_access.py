"""Authentication and role enforcement."""
import pytest


def test_anonymous_is_redirected_to_login(client):
    for url in ["/", "/collections", "/c/coins/", "/c/coins/media/x.webp", "/admin/users"]:
        r = client.get(url)
        assert r.status_code == 302 and "/login" in r.headers["Location"], url


def test_login_flow(client):
    bad = client.post("/login", data={"username": "sam", "password": "nope"})
    assert bad.status_code == 401
    ok = client.post("/login?next=/c/coins/", data={"username": "sam", "password": "correct horse"})
    assert ok.status_code == 302 and ok.headers["Location"] == "/c/coins/"


def test_login_ignores_offsite_next(client):
    r = client.post("/login?next=//evil.example", data={"username": "sam", "password": "correct horse"})
    assert "evil" not in r.headers["Location"]


def test_login_is_throttled(client):
    for _ in range(5):
        client.post("/login", data={"username": "sam", "password": "wrong"})
    r = client.post("/login", data={"username": "sam", "password": "correct horse"})
    assert r.status_code == 401 and b"Too many attempts" in r.data


def test_inactive_user_is_locked_out(client, login, stub):
    login(); stub["user"]["is_active"] = False
    assert client.get("/c/coins/").status_code == 302


def test_non_member_gets_404(client, login, stub):
    login(); stub["role"] = None
    assert client.get("/c/coins/").status_code == 404


@pytest.mark.parametrize("role,expected", [("viewer", 403), ("editor", 200), ("owner", 200)])
def test_add_form_requires_editor(client, login, stub, role, expected):
    login(); stub["role"] = role
    assert client.get("/c/coins/items/new").status_code == expected


@pytest.mark.parametrize("role,expected", [("viewer", 403), ("editor", 403), ("owner", 200)])
def test_owner_only_pages(client, login, stub, role, expected):
    login(); stub["role"] = role
    for url in ["/c/coins/members/", "/c/coins/maintenance/", "/c/coins/maintenance/export.csv"]:
        assert client.get(url).status_code == expected, url


def test_viewer_cannot_post_changes(client, login, stub):
    login(); stub["role"] = "viewer"
    assert client.post("/c/coins/items/new", data={"name": "x"}).status_code == 403
    assert client.post("/c/coins/items/1/delete").status_code == 403


def test_viewer_sees_no_edit_controls(client, login, stub):
    login(); stub["role"] = "viewer"
    html = client.get("/c/coins/items/1").get_data(as_text=True)
    assert "Remove" not in html and "/edit" not in html


def test_admin_pages_need_admin(client, login, stub):
    login()
    assert client.get("/admin/users").status_code == 403
    stub["user"]["is_admin"] = True
    with patch_users():
        assert client.get("/admin/users").status_code == 200


def patch_users():
    from unittest.mock import patch
    return patch("app.user_repository.list_users", return_value=[])


# ---- trips, import, cost visibility, header value -------------------------

def test_trips_page_visible_to_viewers_but_edit_requires_editor(client, login, stub):
    login(); stub["role"] = "viewer"
    assert client.get("/c/coins/trips/").status_code == 200
    assert client.get("/c/coins/trips/2/edit").status_code == 403
    assert client.post("/c/coins/trips/", data={"name": "x"}).status_code == 403
    stub["role"] = "editor"
    assert client.get("/c/coins/trips/2/edit").status_code == 200


def test_default_trip_cannot_be_deleted(client, login, stub):
    from unittest.mock import patch
    login(); stub["role"] = "editor"
    with patch("app.trip_repository.delete_trip", return_value=None):
        r = client.post("/c/coins/trips/1/delete", follow_redirects=True)
    assert b"can&#39;t be deleted" in r.data or b"can't be deleted" in r.data


def test_deleting_a_trip_reports_items_moved_to_default(client, login, stub):
    from unittest.mock import patch
    login(); stub["role"] = "editor"
    with patch("app.trip_repository.delete_trip", return_value=2):
        r = client.post("/c/coins/trips/2/delete", follow_redirects=True)
    assert b"2 items moved to Home" in r.data


def test_import_is_owner_only(client, login, stub):
    login(); stub["role"] = "editor"
    assert client.post("/c/coins/maintenance/import").status_code == 403


def test_header_shows_estimated_value(client, login):
    login()
    html = client.get("/c/coins/").get_data(as_text=True)
    assert "EST. VALUE" in html and "$1,234.50" in html
    assert "EST. VALUE" in client.get("/collections").get_data(as_text=True)


def test_cost_only_on_detail_page_not_gallery_tiles(client, login):
    login()
    assert "$45.00" not in client.get("/c/coins/").get_data(as_text=True)
    assert "$45.00" in client.get("/c/coins/items/1").get_data(as_text=True)


def test_gallery_has_size_slider_and_details_toggle(client, login):
    login()
    html = client.get("/c/coins/").get_data(as_text=True)
    assert 'id="tile-size"' in html and 'id="show-details"' in html


def test_form_has_trip_dates_for_prefill_and_cost(client, login, stub):
    login(); stub["role"] = "editor"
    html = client.get("/c/coins/items/new").get_data(as_text=True)
    assert 'data-start="2024-03-04"' in html and 'name="cost"' in html
