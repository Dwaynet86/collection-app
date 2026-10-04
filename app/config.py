"""Application configuration, read from environment variables (.env supported)."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    # Required: signs sessions and CSRF tokens. The app refuses to start without it.
    SECRET_KEY = os.environ.get("SECRET_KEY")
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/collection"
    )

    # Image uploads
    UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", BASE_DIR / "uploads"))
    MAX_UPLOAD_BYTES = 25 * 1024 * 1024    # ordinary uploads (phone photos are large)
    MAX_IMPORT_BYTES = 500 * 1024 * 1024   # backup restore on the Maintenance page
    MAX_CONTENT_LENGTH = MAX_IMPORT_BYTES  # hard cap; MAX_UPLOAD_BYTES is enforced per request
    ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    IMAGE_MAX_SIZE = 1600   # px, longest edge of stored image
    THUMB_MAX_SIZE = 600    # px, longest edge of grid thumbnail

    # Background removal needs the optional rembg package (see requirements-bgremoval.txt)
    BACKGROUND_REMOVAL = os.environ.get("BACKGROUND_REMOVAL", "1") == "1"
    BACKGROUND_MODEL = os.environ.get("BACKGROUND_MODEL", "isnet-general-use")

    # Listing
    ITEMS_PER_PAGE = 48

    # Sessions / auth
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"  # set 1 behind HTTPS
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_SAMESITE = "Lax"
    MIN_PASSWORD_LENGTH = 8

    # Display
    CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "$")
