"""Application factory."""
from flask import Flask, abort, render_template, request
from flask_wtf.csrf import CSRFProtect

from . import db
from .auth import init_auth
from .config import Config
from .permissions import register_permissions

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


def _trip_dates(start, end) -> str:
    """'Mar 4, 2024' or 'Mar 4, 2024 – Mar 12, 2024'; empty when the trip has no dates."""
    if not start:
        return ""
    return f"{_pretty_date(start)} – {_pretty_date(end)}" if end else _pretty_date(start)


def create_app(config: type | dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if isinstance(config, dict):
        app.config.update(config)
    elif config:
        app.config.from_object(config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is not set. Add it to .env, e.g. generate one with:\n"
            "  python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)

    db.init_pool(app)
    csrf.init_app(app)
    init_auth(app)
    register_permissions(app)

    from .routes.admin import bp as admin_bp
    from .routes.auth import bp as auth_bp
    from .routes.collections import bp as collections_bp
    from .routes.items import bp as items_bp
    from .routes.maintenance import bp as maintenance_bp
    from .routes.members import bp as members_bp
    from .routes.trips import bp as trips_bp
    from .routes.geo import bp as geo_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(collections_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(items_bp, url_prefix="/c/<slug>")
    app.register_blueprint(maintenance_bp, url_prefix="/c/<slug>/maintenance")
    app.register_blueprint(members_bp, url_prefix="/c/<slug>/members")
    app.register_blueprint(trips_bp, url_prefix="/c/<slug>/trips")
    app.register_blueprint(geo_bp, url_prefix="/c/<slug>/map")

    app.add_template_filter(_pretty_date, "pretty_date")
    app.add_template_filter(_filesize, "filesize")
    app.add_template_filter(_trip_dates, "trip_dates")
    from .images import is_cutout
    app.add_template_filter(is_cutout, "is_cutout")

    @app.template_filter("money")
    def money(value) -> str:
        """Format an amount with the configured currency symbol: $1,234.50."""
        return "" if value is None else f"{app.config['CURRENCY_SYMBOL']}{value:,.2f}"

    @app.before_request
    def limit_upload_size():
        """Only the backup import may exceed the ordinary upload limit."""
        if (request.method == "POST" and request.endpoint != "maintenance.import_backup"
                and (request.content_length or 0) > app.config["MAX_UPLOAD_BYTES"]):
            abort(413)

    @app.errorhandler(403)
    def forbidden(_):
        return render_template("404.html", message="You don't have permission to do that."), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("404.html"), 404

    @app.errorhandler(413)
    def too_large(_):
        return render_template("404.html", message="That upload is too large."), 413

    return app
