"""Maintenance page for a collection: overview and data tools (export, ...).

Owners only. To add a tool: add a route here and a <section class="panel">
in templates/maintenance.html.
"""
from datetime import date

from flask import (Blueprint, Response, current_app, flash, g, redirect,
                   render_template, request, send_file, url_for)

from .. import exporter, images, importer, repository as repo, trip_repository as trip_repo
from ..permissions import collection_access

bp = Blueprint("maintenance", __name__)


def _filename(ext: str) -> str:
    return f"{g.collection['slug']}-{date.today().isoformat()}.{ext}"


def _download(body: bytes | str, mimetype: str, ext: str) -> Response:
    return Response(
        body, mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{_filename(ext)}"'},
    )


@bp.get("/")
@collection_access("owner")
def index():
    return render_template(
        "maintenance.html", stats=repo.get_stats(g.collection["id"]), disk_bytes=images.disk_usage()
    )


@bp.get("/export.csv")
@collection_access("owner")
def export_csv():
    return _download(exporter.to_csv(repo.all_items(g.collection["id"])), "text/csv; charset=utf-8", "csv")


@bp.get("/export.json")
@collection_access("owner")
def export_json():
    cid = g.collection["id"]
    body = exporter.to_json(repo.all_items(cid), trip_repo.list_trips(cid))
    return _download(body, "application/json", "json")


@bp.get("/export.zip")
@collection_access("owner")
def export_zip():
    cid = g.collection["id"]
    archive = exporter.build_backup_zip(
        repo.all_items(cid), trip_repo.list_trips(cid), current_app.config["UPLOAD_DIR"]
    )
    return send_file(
        archive, mimetype="application/zip", as_attachment=True, download_name=_filename("zip")
    )


@bp.post("/import")
@collection_access("owner")
def import_backup():
    upload = request.files.get("backup")
    if not upload or not upload.filename:
        flash("Choose a backup file to import.", "error")
        return redirect(url_for("maintenance.index"))
    try:
        result = importer.restore(
            g.collection["id"], upload, skip_duplicates=bool(request.form.get("skip_duplicates"))
        )
    except importer.BackupError as exc:
        shown = exc.problems[:5]
        more = len(exc.problems) - len(shown)
        flash("Import failed, nothing was changed. " + " ".join(shown)
              + (f" (and {more} more problems)" if more > 0 else ""), "error")
        return redirect(url_for("maintenance.index"))

    parts = [f"Imported {result.created} item{'' if result.created == 1 else 's'}"]
    if result.skipped:
        parts.append(f"skipped {result.skipped} already in the collection")
    if result.trips_created:
        parts.append(f"added {result.trips_created} trip{'' if result.trips_created == 1 else 's'}")
    if result.images_missing:
        parts.append(f"{result.images_missing} photo{'' if result.images_missing == 1 else 's'} couldn't be restored")
    flash(", ".join(parts) + ".", "success")
    return redirect(url_for("maintenance.index"))
