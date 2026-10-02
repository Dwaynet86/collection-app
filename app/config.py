"""Application configuration, read from environment variables (.env supported)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/collection"
    )

    # Image uploads
    UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # reject request bodies over 10 MB
    ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    IMAGE_MAX_SIZE = 1600   # px, longest edge of stored image
    THUMB_MAX_SIZE = 600    # px, longest edge of grid thumbnail

    # Listing
    ITEMS_PER_PAGE = 24
