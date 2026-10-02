"""Image handling: validate, normalise, store, and delete uploaded images.

Every upload is re-encoded to WebP (strips metadata, defends against
malformed files) and saved twice: a full-size copy and a grid thumbnail.
The database stores only the generated file name.
"""
from pathlib import Path
from uuid import uuid4

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError


class ImageError(ValueError):
    """Raised with a user-facing message when an upload is unusable."""


def _dirs() -> tuple[Path, Path]:
    root: Path = current_app.config["UPLOAD_DIR"]
    thumbs = root / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    return root, thumbs


def save_image(file_storage) -> str:
    """Validate and store an uploaded image. Returns the stored file name."""
    ext = Path(file_storage.filename or "").suffix.lower()
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        allowed = ", ".join(sorted(current_app.config["ALLOWED_IMAGE_EXTENSIONS"]))
        raise ImageError(f"Unsupported file type. Use one of: {allowed}.")

    try:
        img = Image.open(file_storage.stream)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImageError("That file couldn't be read as an image.") from None

    img = ImageOps.exif_transpose(img)  # respect phone-camera rotation
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    root, thumbs = _dirs()
    name = f"{uuid4().hex}.webp"

    full = img.copy()
    full.thumbnail((current_app.config["IMAGE_MAX_SIZE"],) * 2)
    full.save(root / name, "WEBP", quality=85)

    thumb = img.copy()
    thumb.thumbnail((current_app.config["THUMB_MAX_SIZE"],) * 2)
    thumb.save(thumbs / name, "WEBP", quality=80)

    return name


def delete_image(filename: str | None) -> None:
    """Remove an image and its thumbnail. Missing files are ignored."""
    if not filename:
        return
    root, thumbs = _dirs()
    for path in (root / filename, thumbs / filename):
        path.unlink(missing_ok=True)


def disk_usage() -> int:
    """Total bytes used by stored images and thumbnails."""
    root, _ = _dirs()
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and p.name != ".gitkeep")
