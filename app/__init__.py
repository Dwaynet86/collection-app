"""Application factory."""
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect

from . import db
from .config import Config

csrf = CSRFProtect()


def _pretty_date(value) -> str:
    """Format a date like 'Mar 4, 2024' (portable across platforms)."""
    return f"{value:%b} {value.day}, {value.year}" if value else ""


def _filesize(num: int) -> str:
    """Format a byte count like '4.2 MB'."""
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def create_app(config: type | dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if isinstance(config, dict):
        app.config.update(config)
    elif config:
        app.config.from_object(config)

    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)

    db.init_pool(app)
    csrf.init_app(app)

    from .routes.items import bp as items_bp
    from .routes.maintenance import bp as maintenance_bp
    app.register_blueprint(items_bp)
    app.register_blueprint(maintenance_bp)

    app.add_template_filter(_pretty_date, "pretty_date")
    app.add_template_filter(_filesize, "filesize")

    @app.errorhandler(404)
    def not_found(_):
        return render_template("404.html"), 404

    @app.errorhandler(413)
    def too_large(_):
        return render_template("404.html", message="That upload is too large (10 MB max)."), 413

    return app
