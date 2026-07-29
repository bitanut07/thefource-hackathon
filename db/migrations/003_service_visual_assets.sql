-- Assets may appear in a Zalo Chatbot list only after a reviewer records
-- provenance and approval.  Never seed/copy candidate research logo URLs.
CREATE TABLE IF NOT EXISTS service_visual_assets (
    id BIGSERIAL PRIMARY KEY,
    service_id UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    placement TEXT NOT NULL CHECK (placement IN ('chatbot_list')),
    image_url TEXT NOT NULL CHECK (image_url ~ '^https://[^[:space:]]+$'),
    source_url TEXT NOT NULL CHECK (source_url ~ '^https://[^[:space:]]+$'),
    owner_or_license_evidence_url TEXT NOT NULL
        CHECK (owner_or_license_evidence_url ~ '^https://[^[:space:]]+$'),
    approval_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (approval_status IN ('candidate', 'approved', 'rejected')),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (
        (approval_status = 'approved' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)
        OR approval_status <> 'approved'
    )
);

CREATE INDEX IF NOT EXISTS service_visual_assets_chatbot_lookup_idx
    ON service_visual_assets (service_id, placement, approval_status, is_active, approved_at DESC);
