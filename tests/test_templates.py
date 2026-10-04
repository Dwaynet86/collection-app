"""Render pages (database stubbed) and check output is sane."""
import pytest


def test_maintenance_shows_numbers_not_python_objects(client, login, stub):
    login(); stub["role"] = "owner"
    html = client.get("/c/coins/maintenance/").get_data(as_text=True)
    assert "built-in method" not in html and ">7<" in html


@pytest.mark.parametrize("url", ["/c/coins/", "/c/coins/items/1", "/collections", "/account"])
def test_pages_render(client, login, url):
    login()
    r = client.get(url)
    assert r.status_code == 200 and "built-in method" not in r.get_data(as_text=True)


def test_camera_button_on_form(client, login, stub):
    login(); stub["role"] = "editor"
    html = client.get("/c/coins/items/new").get_data(as_text=True)
    assert 'capture="environment"' in html and "Take photo" in html
