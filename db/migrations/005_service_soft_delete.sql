-- Soft delete for catalog rows.
--
-- Hard deletion would cascade away the evidence and the review history, which are
-- the record of *why* a service was ever served. Reviewers need that trail to stay
-- readable after a service is removed, so removal marks the row instead.
ALTER TABLE services
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- Makes "removed but still being served" unrepresentable rather than merely
-- avoided in application code.
ALTER TABLE services
    DROP CONSTRAINT IF EXISTS services_deleted_not_active_check;
ALTER TABLE services
    ADD CONSTRAINT services_deleted_not_active_check
    CHECK (NOT active OR deleted_at IS NULL);

-- Default listings and every runtime query read live rows only.
CREATE INDEX IF NOT EXISTS services_live_idx
    ON services (active, review_status)
    WHERE deleted_at IS NULL;

-- Removal, restoration and spreadsheet import are auditable actions too.
ALTER TABLE service_review_events
    DROP CONSTRAINT IF EXISTS service_review_events_action_check;
ALTER TABLE service_review_events
    ADD CONSTRAINT service_review_events_action_check
    CHECK (
        action IN (
            'create', 'update', 'approve', 'reject',
            'deactivate', 'delete', 'restore', 'import'
        )
    );
