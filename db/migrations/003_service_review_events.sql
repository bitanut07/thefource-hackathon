-- Audit trail for reviewer-driven catalog changes.
--
-- Approval decides what end users are shown, so every transition needs to stay
-- attributable after the fact.  ``actor`` is a free-text column rather than a
-- foreign key: the current admin surface authenticates one shared operator
-- account, and recording per-person actors later must not require a migration.
CREATE TABLE IF NOT EXISTS service_review_events (
    id BIGSERIAL PRIMARY KEY,
    service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (
        action IN ('create', 'update', 'approve', 'reject', 'deactivate')
    ),
    actor TEXT NOT NULL CHECK (btrim(actor) <> ''),
    note TEXT,
    changed_fields TEXT[] NOT NULL DEFAULT ARRAY[]::text[],
    previous_review_status TEXT,
    new_review_status TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS service_review_events_service_idx
    ON service_review_events (service_id, created_at DESC);
CREATE INDEX IF NOT EXISTS service_review_events_created_idx
    ON service_review_events (created_at DESC);
