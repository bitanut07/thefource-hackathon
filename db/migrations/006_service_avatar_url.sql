-- Avatar URLs are discovered from the public Zalo OA profile page.  They are
-- optional because a profile can be unavailable or its avatar can change.
ALTER TABLE services
    ADD COLUMN IF NOT EXISTS avatar_url TEXT;
