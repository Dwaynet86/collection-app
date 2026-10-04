# Collection

Multi-user catalog app for collections. Flask + PostgreSQL + Pillow.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # set SECRET_KEY (required) and DATABASE_URL
python scripts/init_db.py         # creates/upgrades tables (safe to re-run)
python scripts/create_user.py YOURNAME --admin    # first account
python run.py
```
Upgrading an older database: `init_db.py` moves existing items into a collection
named "My Collection"; `create_user.py --admin` makes you its owner.

## Roles
| Role   | Can do |
|--------|--------|
| viewer | browse and search items |
| editor | viewer + add, edit, remove items |
| owner  | editor + manage members, maintenance/export |
| admin (account-level) | create users, reset passwords, deactivate accounts |

Any user can create a collection and becomes its owner. Admins manage accounts,
not collection contents. Non-members get a 404 for a collection.

## Layout
```
app/
  __init__.py            app factory, blueprints, error handlers
  config.py              env-driven settings
  auth.py                Flask-Login, default-deny login, login throttle
  permissions.py         @collection_access(role), @admin_required, template context
  db.py                  psycopg connection pool
  repository.py          item SQL (always scoped by collection_id)
  tag_repository.py      tag SQL
  user_repository.py     user SQL
  collection_repository.py  collections + membership SQL
  forms.py / user_forms.py  validation
  images.py              upload validation, WebP, thumbnails
  exporter.py            CSV / JSON / ZIP export
  routes/                auth, collections, items, members, maintenance, admin
schema.sql               idempotent schema + upgrade steps
scripts/                 init_db.py, create_user.py
tests/                   pytest (DB stubbed)
```

## Trips, cost, gallery
- **Trips** (`/c/<slug>/trips/`): a name plus a start date, or a start and end date. Picking a trip on the
  add-item form fills in the date acquired (never overwriting a date you typed). Every collection has a
  default trip ("Home"); deleting a trip moves its items there.
- **Cost** is per item (shown on the item page only). The header shows **EST. VALUE**, the sum of costs.
  Change the currency symbol with `CURRENCY_SYMBOL` in `.env`.
- **Gallery**: thumbnail size slider and a "Show details" checkbox, remembered per browser.
- **Maintenance -> Import** restores a ZIP backup (with photos) or JSON export. Validated first, then
  imported in one transaction; "skip duplicates" matches on name + date + location.

## Background removal (optional)
Adds a **Remove background** checkbox to the item form (new photo, or the current photo when editing).
Runs entirely on your machine using [rembg](https://github.com/danielgatis/rembg).
- Install: `pip install -r requirements-bgremoval.txt`, then restart the app.
- The first cut-out downloads a ~180 MB model to `~/.rembg` (internet needed once; set `U2NET_HOME` to
  change the folder, or copy the folder to an offline machine). Expect ~3-8 s per photo on CPU, one at a time.
- The untouched photo is kept in `uploads/originals/`; editing the item then offers **Restore the original
  background**. Backups (ZIP) contain the displayed photo only, not originals.
- Cut-outs show uncropped on a neutral tile in the gallery. If no clear subject is found the photo is saved as-is.
- `.env`: `BACKGROUND_REMOVAL=0` hides the option; `BACKGROUND_MODEL` picks the model (default `isnet-general-use`;
  `u2netp` is much smaller and faster but rougher).

## Map (works offline)
- **Pin an item:** on the item form, open **Pin on map**. Click the map, drag the pin, search a city or country, or type/paste
  coordinates (`38.72, -9.14`). Choosing a search result also fills **Location acquired** if it is empty; text you typed
  yourself is never overwritten. The pin is optional and the location text stays free-form.
- **View the map:** **Map** in the header shows one pin per item (nearby pins cluster), filtered by search, tag and trip.
  The gallery has a **View on map** link that keeps your filters, and item pages link to their pin.
- **Fully local:** country outlines (Natural Earth) and ~34,000 cities (GeoNames) are bundled, so there is no internet use,
  no API key and no tracking. Detail is country and city level: no streets or roads, and coastlines are coarse when zoomed in.
  Place search finds English names best; other spellings only for some cities.
- "Use my location" only appears when the page is served over HTTPS (or localhost); browsers block it on plain `http://192.168.x.x`.
- Pins are included in the CSV/JSON/ZIP exports and restored by Import (older backups without pins still import).
- Credits and licenses: `app/data/NOTICE.txt`. To refresh the data: `scripts/build_geodata.py`.

## Tests
`pytest` runs without a database. For the end-to-end test, point it at a scratch database:
`TEST_DATABASE_URL=postgresql://user:pass@localhost/collection_test pytest`
Set `RUN_REMBG_TESTS=1` to also run the real-model test.

## Notes
- Routes under `/c/<slug>/`; `url_for` fills in the slug automatically inside a collection.
- Every page requires login except `/login` (default deny).
- Images are served only to members of the collection that owns them.
- "Take photo" uses the phone camera via `capture`; it works over plain HTTP.
- Serve over HTTPS before exposing beyond a private network.
