# Collection

Small catalog app for a personal collection. Flask + PostgreSQL + Pillow.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set DATABASE_URL and SECRET_KEY
createdb collection             # or create via your existing Postgres tooling
python scripts/init_db.py       # applies schema.sql
python run.py                   # http://127.0.0.1:5000
```
## Windows
```
pip install waitress
waitress-serve --host=0.0.0.0 --port=5000 --call app:create_app
```

## Layout
```
app/
  __init__.py      app factory, filters, error handlers
  config.py        env-driven settings
  db.py            psycopg connection pool
  repository.py    all SQL (list/get/create/update/delete)
  forms.py         input validation
  images.py        upload validation, WebP re-encode, thumbnails
  routes/items.py  view / add / edit / remove + image serving
  templates/       Jinja templates (+ _macros.html)
  static/          css, js
schema.sql         table + indexes
scripts/init_db.py apply schema
tests/             pytest (forms, images)
```

## Notes
- Images are stored on disk under `UPLOAD_DIR`; the DB keeps only the file name.
- Uploads are re-encoded to WebP (max 1600px) with a 600px thumbnail.
- CSRF protection is on for all POST routes.
- No auth yet: run on a trusted network or add login before exposing it.
