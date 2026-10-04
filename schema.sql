-- Collection app schema. Ordered and idempotent: safe on fresh AND existing databases.
-- Older installs are upgraded in place (columns added, data backfilled).

-- ---- Accounts, collections, membership -------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    username      TEXT        NOT NULL CHECK (length(btrim(username)) > 0),
    password_hash TEXT        NOT NULL,
    is_admin      BOOLEAN     NOT NULL DEFAULT false,   -- manages user accounts
    is_active     BOOLEAN     NOT NULL DEFAULT true,    -- false = cannot sign in
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS users_username_key ON users (lower(username));

CREATE TABLE IF NOT EXISTS collections (
    id         BIGSERIAL PRIMARY KEY,
    name       TEXT        NOT NULL CHECK (length(btrim(name)) > 0),
    slug       TEXT        NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS collection_members (
    collection_id BIGINT NOT NULL REFERENCES collections (id) ON DELETE CASCADE,
    user_id       BIGINT NOT NULL REFERENCES users (id)       ON DELETE CASCADE,
    role          TEXT   NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    PRIMARY KEY (collection_id, user_id)
);
CREATE INDEX IF NOT EXISTS collection_members_user_idx ON collection_members (user_id);

-- ---- Items -----------------------------------------------------------------
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
ALTER TABLE items ADD COLUMN IF NOT EXISTS collection_id BIGINT
    REFERENCES collections (id) ON DELETE CASCADE;

-- ---- Trips (per collection; every collection has one default trip) --------
CREATE TABLE IF NOT EXISTS trips (
    id            BIGSERIAL PRIMARY KEY,
    collection_id BIGINT      NOT NULL REFERENCES collections (id) ON DELETE CASCADE,
    name          TEXT        NOT NULL CHECK (length(btrim(name)) > 0),
    start_date    DATE,                       -- NULL = no date (e.g. the default trip)
    end_date      DATE,                       -- NULL = single-day trip
    is_default    BOOLEAN     NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (end_date IS NULL OR (start_date IS NOT NULL AND end_date >= start_date))
);
CREATE UNIQUE INDEX IF NOT EXISTS trips_collection_name_key ON trips (collection_id, lower(name));
CREATE UNIQUE INDEX IF NOT EXISTS trips_one_default_key     ON trips (collection_id) WHERE is_default;

-- Items point at a trip; deleting a trip moves its items to the default trip (done in code).
ALTER TABLE items ADD COLUMN IF NOT EXISTS trip_id BIGINT REFERENCES trips (id);
ALTER TABLE items ADD COLUMN IF NOT EXISTS cost NUMERIC(12, 2) CHECK (cost >= 0);

-- Optional map pin: both coordinates or neither. location_acquired stays free text.
ALTER TABLE items ADD COLUMN IF NOT EXISTS latitude  DOUBLE PRECISION CHECK (latitude  BETWEEN  -90 AND  90);
ALTER TABLE items ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION CHECK (longitude BETWEEN -180 AND 180);
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'items_pin_pair') THEN
        ALTER TABLE items ADD CONSTRAINT items_pin_pair CHECK ((latitude IS NULL) = (longitude IS NULL));
    END IF;
END $$;

-- ---- Tags (scoped per collection) -------------------------------------------
CREATE TABLE IF NOT EXISTS tags (
    id   BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(btrim(name)) > 0)
);
ALTER TABLE tags ADD COLUMN IF NOT EXISTS collection_id BIGINT
    REFERENCES collections (id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS item_tags (
    item_id BIGINT NOT NULL REFERENCES items (id) ON DELETE CASCADE,
    tag_id  BIGINT NOT NULL REFERENCES tags (id)  ON DELETE CASCADE,
    PRIMARY KEY (item_id, tag_id)
);

-- ---- Upgrade: move pre-existing rows into a default collection --------------
-- The default collection has no members until an admin is created with
-- scripts/create_user.py --admin, which adopts it.
DO $$
DECLARE default_id BIGINT;
BEGIN
    IF EXISTS (SELECT 1 FROM items WHERE collection_id IS NULL) THEN
        INSERT INTO collections (name, slug) VALUES ('My Collection', 'my-collection')
            ON CONFLICT (slug) DO NOTHING;
        SELECT id INTO default_id FROM collections WHERE slug = 'my-collection';
        UPDATE items SET collection_id = default_id WHERE collection_id IS NULL;
    END IF;

    UPDATE tags t SET collection_id = (
        SELECT i.collection_id FROM item_tags it JOIN items i ON i.id = it.item_id
        WHERE it.tag_id = t.id LIMIT 1)
    WHERE t.collection_id IS NULL;
    DELETE FROM tags WHERE collection_id IS NULL;   -- unused tags
END $$;

-- ---- Upgrade: free-text trip_name -> trips table ---------------------------
DO $$
BEGIN
    -- Every collection gets a default trip.
    INSERT INTO trips (collection_id, name, is_default)
    SELECT c.id, 'Home', true FROM collections c
    WHERE NOT EXISTS (SELECT 1 FROM trips t WHERE t.collection_id = c.id AND t.is_default)
    ON CONFLICT DO NOTHING;

    -- Older databases: turn each distinct trip_name into a trip, then drop the column.
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'items'
                 AND column_name = 'trip_name') THEN
        INSERT INTO trips (collection_id, name)
        SELECT DISTINCT ON (collection_id, lower(btrim(trip_name))) collection_id, btrim(trip_name)
        FROM items WHERE trip_name IS NOT NULL AND btrim(trip_name) <> ''
        ORDER BY collection_id, lower(btrim(trip_name)), created_at
        ON CONFLICT DO NOTHING;

        UPDATE items i SET trip_id = t.id FROM trips t
        WHERE i.trip_id IS NULL AND t.collection_id = i.collection_id
          AND lower(t.name) = lower(btrim(i.trip_name));

        DROP INDEX IF EXISTS items_trip_name_idx;
        ALTER TABLE items DROP COLUMN trip_name;
    END IF;

    -- Items with no trip go to their collection's default trip.
    UPDATE items i SET trip_id = (
        SELECT t.id FROM trips t WHERE t.collection_id = i.collection_id AND t.is_default)
    WHERE i.trip_id IS NULL;
END $$;

ALTER TABLE items ALTER COLUMN trip_id SET NOT NULL;
ALTER TABLE items ALTER COLUMN collection_id SET NOT NULL;
ALTER TABLE tags  ALTER COLUMN collection_id SET NOT NULL;

-- ---- Upgrade: free-text items.trip_name -> trips ----------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = 'items' AND column_name = 'trip_name') THEN
        INSERT INTO trips (collection_id, name)
        SELECT collection_id, min(btrim(trip_name)) FROM items
        WHERE trip_name IS NOT NULL AND btrim(trip_name) <> ''
        GROUP BY collection_id, lower(btrim(trip_name))
        ON CONFLICT DO NOTHING;
    END IF;

    -- Every collection gets a default trip: reuse one already named "Home", else create it.
    UPDATE trips t SET is_default = true
    WHERE lower(t.name) = 'home'
      AND NOT EXISTS (SELECT 1 FROM trips d WHERE d.collection_id = t.collection_id AND d.is_default);
    INSERT INTO trips (collection_id, name, is_default)
    SELECT c.id, 'Home', true FROM collections c
    WHERE NOT EXISTS (SELECT 1 FROM trips d WHERE d.collection_id = c.id AND d.is_default);

    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = 'items' AND column_name = 'trip_name') THEN
        UPDATE items i SET trip_id = t.id FROM trips t
        WHERE i.trip_id IS NULL AND t.collection_id = i.collection_id
          AND lower(t.name) = lower(btrim(i.trip_name));
    END IF;
    UPDATE items i SET trip_id = (
        SELECT d.id FROM trips d WHERE d.collection_id = i.collection_id AND d.is_default)
    WHERE i.trip_id IS NULL;
END $$;

ALTER TABLE items ALTER COLUMN trip_id SET NOT NULL;
ALTER TABLE items DROP COLUMN IF EXISTS trip_name;   -- also drops its old index

-- ---- Indexes ---------------------------------------------------------------
DROP INDEX IF EXISTS tags_name_key;   -- replaced by the per-collection index below
CREATE UNIQUE INDEX IF NOT EXISTS tags_collection_name_key ON tags (collection_id, lower(name));
CREATE INDEX IF NOT EXISTS item_tags_tag_idx        ON item_tags (tag_id);
CREATE INDEX IF NOT EXISTS items_collection_idx     ON items (collection_id);
CREATE INDEX IF NOT EXISTS items_name_idx           ON items (lower(name));
CREATE INDEX IF NOT EXISTS items_date_acquired_idx  ON items (date_acquired);
CREATE INDEX IF NOT EXISTS items_created_at_idx     ON items (created_at DESC);
CREATE INDEX IF NOT EXISTS items_trip_idx           ON items (trip_id);
CREATE INDEX IF NOT EXISTS items_pinned_idx         ON items (collection_id) WHERE latitude IS NOT NULL;
