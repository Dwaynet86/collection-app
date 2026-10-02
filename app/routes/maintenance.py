"""Maintenance page: collection overview and data tools (export, ...).

To add a tool: add a route here and a <section class="panel"> in
templates/maintenance.html.
"""
from datetime import date

from flask import Blueprint, Response, current_app, render_template, send_file

from .. import exporter, images, repository as repo

bp = Blueprint("maintenance", __name__, url_prefix="/maintenance")


def _filename(ext: str) -> str:
    return f"collection-{date.today().isoformat()}.{ext}"


def _download(body: bytes | str, mimetype: str, ext: str) -> Response:
    return Response(
        body, mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{_filename(ext)}"'},
    )


@bp.get("/")
def index():
    return render_template(
        "maintenance.html", stats=repo.get_stats(), disk_bytes=images.disk_usage()
    )


@bp.get("/export.csv")
def export_csv():
    return _download(exporter.to_csv(repo.all_items()), "text/csv; charset=utf-8", "csv")


@bp.get("/export.json")
def export_json():
    return _download(exporter.to_json(repo.all_items()), "application/json", "json")


@bp.get("/export.zip")
def export_zip():
    archive = exporter.build_backup_zip(repo.all_items(), current_app.config["UPLOAD_DIR"])
    return send_file(
        archive, mimetype="application/zip", as_attachment=True,
        download_name=_filename("zip"),
    )
