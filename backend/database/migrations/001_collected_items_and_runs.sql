-- 001: storage for collected items and collection runs.
-- Applied by `python -m database.migrate` (never at API runtime).

-- Every item the collectors have ever returned, de-duplicated by item_id.
CREATE TABLE collected_items (
    item_id            TEXT        PRIMARY KEY,                     -- SHA-256 of source_name + external_id
    source_type        TEXT        NOT NULL CHECK (source_type IN ('web', 'social', 'advisory')),
    source_name        TEXT        NOT NULL,
    external_id        TEXT        NOT NULL,
    title              TEXT        NOT NULL,
    url                TEXT,
    content            TEXT,
    tags               TEXT[]      NOT NULL DEFAULT '{}',
    published_at       TIMESTAMPTZ,
    details            JSONB       NOT NULL DEFAULT '{}'::jsonb,    -- type-specific fields (score, severity, affected...)
    raw_payload        JSONB       NOT NULL,                        -- original source record, for later re-processing
    first_collected_at TIMESTAMPTZ NOT NULL,
    last_collected_at  TIMESTAMPTZ NOT NULL,
    -- Date used for ordering and daily counts: when published, or when we first saw it if the source has no date
    sort_at            TIMESTAMPTZ GENERATED ALWAYS AS (COALESCE(published_at, first_collected_at)) STORED
);

-- Newest-first listing (optionally filtered by type or source) with keyset pagination on (sort_at, item_id)
CREATE INDEX collected_items_sort_idx        ON collected_items (sort_at DESC, item_id DESC);
CREATE INDEX collected_items_type_sort_idx   ON collected_items (source_type, sort_at DESC, item_id DESC);
CREATE INDEX collected_items_source_sort_idx ON collected_items (source_name, sort_at DESC, item_id DESC);


-- One row per collection run, so the dashboard can show progress and the result of each run.
CREATE TABLE collection_runs (
    run_id        UUID        PRIMARY KEY,                          -- also the correlation ID in logs
    status        TEXT        NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    requested_at  TIMESTAMPTZ NOT NULL,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    items_collected INTEGER   NOT NULL DEFAULT 0,
    items_new     INTEGER     NOT NULL DEFAULT 0,
    sources       JSONB       NOT NULL DEFAULT '[]'::jsonb,         -- per-source outcome
    error_message TEXT                                              -- set when the whole run failed
);

CREATE INDEX collection_runs_requested_idx ON collection_runs (requested_at DESC);

-- At most one run can be queued or running at a time. Enforced by the database so two
-- simultaneous requests can't both start a run.
CREATE UNIQUE INDEX collection_runs_one_active_idx ON collection_runs ((TRUE)) WHERE status IN ('queued', 'running');
