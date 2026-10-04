"""Background removal: storage rules (rembg faked), form/route behaviour, and a real-model smoke test."""
import io
import os
import sys
import types
from unittest.mock import patch

import pytest
from flask import Flask
from PIL import Image
from werkzeug.datastructures import FileStorage

from app import background, images
from tests.conftest import ITEM


def _photo(mode="RGB", fmt="PNG", name="a.png"):
    buf = io.BytesIO()
    Image.new(mode, (300, 200), "red").save(buf, fmt)
    buf.seek(0)
    return FileStorage(buf, filename=name)


def _fake_cutout(img):
    """Pretend model: keep the centre, make a border transparent."""
    out = img.convert("RGBA")
    out.paste((0, 0, 0, 0), (0, 0, 20, out.height))
    return out


@pytest.fixture
def img_app(tmp_path):
    app = Flask(__name__)
    app.config.update(UPLOAD_DIR=tmp_path, ALLOWED_IMAGE_EXTENSIONS={".png", ".jpg"},
                      IMAGE_MAX_SIZE=100, THUMB_MAX_SIZE=40,
                      BACKGROUND_REMOVAL=True, BACKGROUND_MODEL="u2netp")
    return app


def _files(tmp_path, name):
    return {d: (tmp_path / d / name).is_file() if d else (tmp_path / name).is_file()
            for d in ("", "thumbs", "originals")}


def test_cutout_keeps_original_and_is_marked(img_app, tmp_path):
    with img_app.app_context(), patch("app.background.remove", _fake_cutout):
        stored = images.store_image(_photo(), remove_bg=True)
        assert stored.name.endswith("-cut.webp") and not stored.cutout_failed
        assert images.is_cutout(stored.name) and images.has_original(stored.name)
        assert _files(tmp_path, stored.name) == {"": True, "thumbs": True, "originals": True}
        images.delete_image(stored.name)
        assert not any(_files(tmp_path, stored.name).values())


def test_failed_cutout_stores_plain_photo_and_flags_it(img_app, tmp_path):
    def boom(img):
        raise background.BackgroundError("nope")
    with img_app.app_context(), patch("app.background.remove", boom):
        stored = images.store_image(_photo(), remove_bg=True)
        assert stored.cutout_failed and not images.is_cutout(stored.name)
        assert _files(tmp_path, stored.name) == {"": True, "thumbs": True, "originals": False}


def test_no_removal_requested_never_calls_model(img_app):
    with img_app.app_context(), patch("app.background.remove", side_effect=AssertionError):
        assert not images.store_image(_photo()).cutout_failed


def test_uploaded_png_with_transparency_is_treated_as_cutout(img_app):
    with img_app.app_context():
        buf = io.BytesIO()
        Image.new("RGBA", (50, 50), (255, 0, 0, 0)).save(buf, "PNG")
        buf.seek(0)
        assert images.is_cutout(images.store_image(FileStorage(buf, filename="t.png")).name)


def test_restore_original_gives_plain_image_under_new_name(img_app):
    with img_app.app_context(), patch("app.background.remove", _fake_cutout):
        cut = images.store_image(_photo(), remove_bg=True).name
        restored = images.reprocess(cut, from_original=True)
        assert restored.name != cut and not images.is_cutout(restored.name)


def test_model_result_with_no_subject_is_rejected(img_app):
    fake = types.ModuleType("rembg")
    fake.new_session = lambda model: object()
    fake.remove = lambda img, session=None: Image.new("RGBA", img.size, (0, 0, 0, 0))
    with img_app.app_context(), patch("app.background.available", return_value=True), \
            patch.dict(sys.modules, {"rembg": fake}), patch.dict(background._sessions, clear=True):
        with pytest.raises(background.BackgroundError, match="No clear subject"):
            background.remove(Image.new("RGB", (40, 40), "white"))


def test_unavailable_when_disabled_or_not_installed(img_app):
    with img_app.app_context():
        img_app.config["BACKGROUND_REMOVAL"] = False
        assert not background.available()
        img_app.config["BACKGROUND_REMOVAL"] = True
        with patch("importlib.util.find_spec", return_value=None):
            assert not background.available()


# ---- form and routes -------------------------------------------------------

def test_form_offers_removal_only_when_available(client, login, stub):
    login(); stub["role"] = "editor"
    with patch("app.background.available", return_value=True):
        assert 'name="remove_background"' in client.get("/c/coins/items/new").get_data(as_text=True)
    with patch("app.background.available", return_value=False):
        assert 'name="remove_background"' not in client.get("/c/coins/items/new").get_data(as_text=True)


def test_edit_form_offers_restore_only_when_original_exists(client, login, stub):
    login(); stub["role"] = "editor"
    item = {**ITEM, "image_filename": "abc-cut.webp"}
    with patch("app.repository.get_item", return_value=item), patch("app.background.available", return_value=False):
        with patch("app.images.has_original", return_value=True):
            assert 'name="restore_original"' in client.get("/c/coins/items/1/edit").get_data(as_text=True)
        with patch("app.images.has_original", return_value=False):
            assert 'name="restore_original"' not in client.get("/c/coins/items/1/edit").get_data(as_text=True)


def test_gallery_shows_cutouts_uncropped(client, login):
    login()
    item = {**ITEM, "image_filename": "abc-cut.webp"}
    with patch("app.repository.list_items", return_value=([item], 1)):
        assert 'class="tile-img cutout"' in client.get("/c/coins/").get_data(as_text=True)


def test_edit_can_cut_out_the_current_photo(client, login, stub):
    login(); stub["role"] = "editor"
    item = {**ITEM, "image_filename": "old.webp"}
    with patch("app.repository.get_item", return_value=item), patch("app.repository.update_item", return_value=True) as upd, \
            patch("app.images.has_original", return_value=False), \
            patch("app.images.reprocess", return_value=images.StoredImage("new-cut.webp")) as rep, \
            patch("app.images.delete_image") as dele:
        r = client.post("/c/coins/items/1/edit", data={"name": "Coin", "remove_background": "1"})
    assert r.status_code == 302
    rep.assert_called_once_with("old.webp", remove_bg=True, from_original=False)
    assert upd.call_args.args[2]["image_filename"] == "new-cut.webp"
    dele.assert_called_once_with("old.webp")


def test_edit_restore_original_wins_and_failed_cutout_keeps_photo(client, login, stub):
    login(); stub["role"] = "editor"
    item = {**ITEM, "image_filename": "old-cut.webp"}
    with patch("app.repository.get_item", return_value=item), patch("app.repository.update_item", return_value=True) as upd, \
            patch("app.images.has_original", return_value=True), \
            patch("app.images.reprocess", return_value=images.StoredImage("plain.webp")) as rep, patch("app.images.delete_image"):
        client.post("/c/coins/items/1/edit", data={"name": "Coin", "restore_original": "1", "remove_background": "1"})
    rep.assert_called_once_with("old-cut.webp", from_original=True)
    assert upd.call_args.args[2]["image_filename"] == "plain.webp"

    with patch("app.repository.get_item", return_value={**ITEM, "image_filename": "old.webp"}), \
            patch("app.repository.update_item", return_value=True) as upd, patch("app.images.has_original", return_value=False), \
            patch("app.images.reprocess", return_value=images.StoredImage("dup.webp", cutout_failed=True)), \
            patch("app.images.delete_image") as dele:
        r = client.post("/c/coins/items/1/edit", data={"name": "Coin", "remove_background": "1"}, follow_redirects=True)
    assert upd.call_args.args[2]["image_filename"] == "old.webp"      # unchanged
    dele.assert_called_once_with("dup.webp")                          # duplicate copy dropped
    assert b"background couldn" in r.data


@pytest.mark.skipif(not os.environ.get("RUN_REMBG_TESTS"), reason="set RUN_REMBG_TESTS=1 (needs rembg + model download)")
def test_real_model_removes_background(img_app, tmp_path):
    from PIL import ImageDraw
    img = Image.new("RGB", (400, 300), (210, 190, 160))
    ImageDraw.Draw(img).rounded_rectangle([120, 60, 280, 240], radius=20, fill=(30, 70, 160))
    buf = io.BytesIO(); img.save(buf, "PNG"); buf.seek(0)
    img_app.config["BACKGROUND_MODEL"] = "isnet-general-use"
    with img_app.app_context():
        stored = images.store_image(FileStorage(buf, filename="x.png"), remove_bg=True)
        assert not stored.cutout_failed
        out = Image.open(tmp_path / stored.name).convert("RGBA")
        assert out.getpixel((2, 2))[3] == 0 and out.getpixel((out.width // 2, out.height // 2))[3] > 200
