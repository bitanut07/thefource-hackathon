-- Record *why* a source backs a service, not just that it exists.
--
-- ``data/research/oa-candidates.json`` carries a ``supports`` claim per evidence
-- entry, and that sentence is the actual basis a reviewer approves on: it explains
-- how the source ties the provider to the OA deeplink.  Without a column for it the
-- review console can only show bare URLs.
ALTER TABLE service_evidence
    ADD COLUMN IF NOT EXISTS supports TEXT;
