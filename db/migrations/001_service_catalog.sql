CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS services (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL CHECK (btrim(name) <> ''),
    provider TEXT NOT NULL CHECK (btrim(provider) <> ''),
    service_type TEXT NOT NULL CHECK (service_type IN ('oa', 'website', 'mini_app')),
    category TEXT NOT NULL CHECK (btrim(category) <> ''),
    description TEXT NOT NULL CHECK (btrim(description) <> ''),
    launch_url TEXT NOT NULL CHECK (btrim(launch_url) <> ''),
    owner TEXT NOT NULL CHECK (btrim(owner) <> ''),
    active BOOLEAN NOT NULL DEFAULT FALSE,
    review_status TEXT NOT NULL DEFAULT 'candidate',
    service_priority INTEGER NOT NULL DEFAULT 0,
    region TEXT,
    target_user TEXT,
    organization TEXT,
    last_verified_at TIMESTAMPTZ,
    search_text TEXT NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', search_text)
    ) STORED,
    embedding vector(768),
    source_type TEXT NOT NULL DEFAULT 'registry',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (NOT active OR review_status IN ('approved', 'published')),
    CHECK (NOT active OR last_verified_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS service_aliases (
    service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    alias TEXT NOT NULL CHECK (btrim(alias) <> ''),
    PRIMARY KEY (service_id, alias)
);

CREATE TABLE IF NOT EXISTS service_intents (
    service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    intent TEXT NOT NULL CHECK (btrim(intent) <> ''),
    example_query TEXT NOT NULL CHECK (btrim(example_query) <> ''),
    PRIMARY KEY (service_id, intent, example_query)
);

CREATE TABLE IF NOT EXISTS service_evidence (
    id BIGSERIAL PRIMARY KEY,
    service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    source_url TEXT NOT NULL CHECK (btrim(source_url) <> ''),
    publisher TEXT,
    checked_at TIMESTAMPTZ,
    verification_status TEXT NOT NULL DEFAULT 'candidate',
    UNIQUE (service_id, source_url)
);

CREATE INDEX IF NOT EXISTS services_active_status_idx
    ON services (active, review_status, category);
CREATE INDEX IF NOT EXISTS services_search_vector_idx
    ON services USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS services_name_trgm_idx
    ON services USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS services_search_text_trgm_idx
    ON services USING GIN (search_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS service_aliases_alias_trgm_idx
    ON service_aliases USING GIN (alias gin_trgm_ops);
CREATE INDEX IF NOT EXISTS services_embedding_hnsw_idx
    ON services USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;
