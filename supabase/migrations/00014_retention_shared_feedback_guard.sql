-- Preserve a non-identifying fence after an item is purged. Existing shared
-- text is never deleted here, and historical purges cannot be reconstructed.
ALTER TABLE app_private.shortlist_shares
    ADD COLUMN IF NOT EXISTS share_level_feedback_blocked BOOLEAN NOT NULL DEFAULT FALSE;
