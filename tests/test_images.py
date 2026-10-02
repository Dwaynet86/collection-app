import io

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from app import images
from flask import Flask


@pytest.fixture
def app(tmp_path):
    app = Flask(__name__)
    app.config.update(
        UPLOAD_DIR=tmp_path, ALLOWED_IMAGE_EXTENSIONS={".png", ".jpg"},
        IMAGE_MAX_SIZE=100, THUMB_MAX_SIZE=40,
    )
    return app


def _png(size=(300, 200)):
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, "PNG")
    buf.seek(0)
    return FileStorage(buf, filename="a.png")


def test_save_and_delete(app, tmp_path):
    with app.app_context():
        name = images.save_image(_png())
        assert (tmp_path / name).exists() and (tmp_path / "thumbs" / name).exists()
        assert max(Image.open(tmp_path / name).size) <= 100
        images.delete_image(name)
        assert not (tmp_path / name).exists()


def test_rejects_bad_files(app):
    with app.app_context():
        with pytest.raises(images.ImageError):
            images.save_image(FileStorage(io.BytesIO(b"nope"), filename="a.png"))
        with pytest.raises(images.ImageError):
            images.save_image(FileStorage(io.BytesIO(b"x"), filename="a.exe"))
