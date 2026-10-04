"""Image handling: validate, normalise, store, and delete uploaded images.

Every upload is re-encoded to WebP (strips metadata, defends against
malformed files) and saved twice: a full-size copy and a grid thumbnail.
The database stores only the generated file name.

Background removal (see background.py) is optional. When a cut-out is made,
the untouched photo is kept in originals/ under the same file name so the
background can be restored later. Originals are never served to the browser.
A stored image with real transparency gets a "-cut" name suffix, which lets
the gallery show cut-outs uncropped.
"""
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

from . import background


class ImageError(ValueError):
    """Raised with a user-facing message when an upload is unusable."""


@dataclass
class StoredImage:
    name: str
    cutout_failed: bool = False   # removal was requested but didn't work; photo stored as-is


def _dirs() -> tuple[Path, Path, Path]:
    root: Path = current_app.config["UPLOAD_DIR"]
    thumbs, originals = root / "thumbs", root / "originals"
    thumbs.mkdir(parents=True, exist_ok=True)
    originals.mkdir(parents=True, exist_ok=True)
    return root, thumbs, originals


def is_cutout(filename: str | None) -> bool:
    return bool(filename) and Path(filename).stem.endswith("-cut")


def has_original(filename: str | None) -> bool:
    """True if the untouched photo behind a cut-out is still on disk."""
    return bool(filename) and (_dirs()[2] / filename).is_file()


def _normalise(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)  # respect phone-camera rotation
    if img.mode in ("P", "LA", "PA") or "transparency" in img.info:
        return img.convert("RGBA")
    return img if img.mode in ("RGB", "RGBA") else img.convert("RGB")


def _has_transparency(img: Image.Image) -> bool:
    return img.mode == "RGBA" and img.getchannel("A").getextrema()[0] < 255


def _store(img: Image.Image, remove_bg: bool) -> StoredImage:
    root, thumbs, originals = _dirs()
    full = _normalise(img)
    full.thumbnail((current_app.config["IMAGE_MAX_SIZE"],) * 2)

    original, failed = None, False
    if remove_bg:
        try:
            cut = background.remove(full)
            original, full = full, cut
        except background.BackgroundError:
            failed = True

    name = f"{uuid4().hex}{'-cut' if _has_transparency(full) else ''}.webp"
    full.save(root / name, "WEBP", quality=85)
    thumb = full.copy()
    thumb.thumbnail((current_app.config["THUMB_MAX_SIZE"],) * 2)
    thumb.save(thumbs / name, "WEBP", quality=80)
    if original is not None:
        original.save(originals / name, "WEBP", quality=85)
    return StoredImage(name, cutout_failed=failed)


def store_image(file_storage, remove_bg: bool = False) -> StoredImage:
    """Validate and store an uploaded image, optionally removing its background."""
    ext = Path(file_storage.filename or "").suffix.lower()
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        allowed = ", ".join(sorted(current_app.config["ALLOWED_IMAGE_EXTENSIONS"]))
        raise ImageError(f"Unsupported file type. Use one of: {allowed}.")
    try:
        img = Image.open(file_storage.stream)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImageError("That file couldn't be read as an image.") from None
    return _store(img, remove_bg)


def save_image(file_storage) -> str:
    """Store an uploaded image as-is. Returns the stored file name."""
    return store_image(file_storage).name


def reprocess(filename: str, remove_bg: bool = False, from_original: bool = False) -> StoredImage:
    """Re-store an existing image under a new name (cut out, or restored from its original)."""
    root, _, originals = _dirs()
    source = originals / filename if from_original and (originals / filename).is_file() else root / filename
    try:
        img = Image.open(source)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImageError("The current photo couldn't be read.") from None
    return _store(img, remove_bg)


def delete_image(filename: str | None) -> None:
    """Remove an image, its thumbnail and any saved original. Missing files are ignored."""
    if not filename:
        return
    for folder in _dirs():
        (folder / filename).unlink(missing_ok=True)


def disk_usage() -> int:
    """Total bytes used by stored images, thumbnails and originals."""
    root = _dirs()[0]
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and p.name != ".gitkeep")
