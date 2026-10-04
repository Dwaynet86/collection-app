"""Optional background removal, powered by rembg (runs locally, nothing leaves this machine).

rembg is not required: when it isn't installed, available() is False and the
option is hidden. The first cut-out loads a model (downloaded once, ~170 MB).
"""
import importlib.util
import threading

from flask import current_app
from PIL import Image

MIN_SUBJECT_FRACTION = 0.02   # a cut-out keeping under 2% of the photo is treated as a failure

_session_lock = threading.Lock()
_one_at_a_time = threading.Semaphore(1)   # cut-outs are CPU and RAM heavy
_sessions: dict[str, object] = {}


class BackgroundError(RuntimeError):
    """Background removal wasn't possible for this photo."""


def available() -> bool:
    """True if the feature is enabled and rembg is installed."""
    return bool(current_app.config.get("BACKGROUND_REMOVAL")) and \
        importlib.util.find_spec("rembg") is not None


def _session(model: str):
    with _session_lock:
        if model not in _sessions:
            from rembg import new_session
            _sessions[model] = new_session(model)
        return _sessions[model]


def remove(img: Image.Image) -> Image.Image:
    """Return an RGBA copy of `img` with the background transparent."""
    if not available():
        raise BackgroundError("Background removal isn't installed.")
    try:
        from rembg import remove as rembg_remove
        session = _session(current_app.config["BACKGROUND_MODEL"])
        with _one_at_a_time:
            cut = rembg_remove(img, session=session)
    except (Exception, SystemExit) as exc:   # rembg exits if onnxruntime is missing
        current_app.logger.warning("Background removal failed: %s", exc)
        raise BackgroundError("Background removal failed.") from exc

    cut = cut.convert("RGBA")
    kept = sum(cut.getchannel("A").histogram()[128:]) / (cut.width * cut.height)
    if kept < MIN_SUBJECT_FRACTION:
        raise BackgroundError("No clear subject was found in the photo.")
    return cut
