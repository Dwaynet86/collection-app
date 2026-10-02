-- Collection app schema. Idempotent: safe to run more than once.

CREATE TABLE IF NOT EXISTS items (
    id                BIGSERIAL PRIMARY KEY,
    name              TEXT        NOT NULL CHECK (length(btrim(name)) > 0),
    date_acquired     DATE,
    location_acquired TEXT,
    description       TEXT,
    image_filename    TEXT,            -- file name only; files live in UPLOAD_DIR
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS items_name_idx          ON items (lower(name));
CREATE INDEX IF NOT EXISTS items_date_acquired_idx ON items (date_acquired);
CREATE INDEX IF NOT EXISTS items_created_at_idx    ON items (created_at DESC);

-- ---- v2: trip name, tags --------------------------------------------------
ALTER TABLE items ADD COLUMN IF NOT EXISTS trip_name TEXT;
CREATE INDEX IF NOT EXISTS items_trip_name_idx ON items (lower(trip_name));

CREATE TABLE IF NOT EXISTS tags (
    id   BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(btrim(name)) > 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS tags_name_key ON tags (lower(name));

CREATE TABLE IF NOT EXISTS item_tags (
    item_id BIGINT NOT NULL REFERENCES items (id) ON DELETE CASCADE,
    tag_id  BIGINT NOT NULL REFERENCES tags (id)  ON DELETE CASCADE,
    PRIMARY KEY (item_id, tag_id)
);
CREATE INDEX IF NOT EXISTS item_tags_tag_idx ON item_tags (tag_id);
