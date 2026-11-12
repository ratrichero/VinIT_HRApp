-- Explicit Cloudflare reranker selection. No reranking is enabled on upgrade.
-- A selection points to an immutable BGE draft solely to reuse that account's
-- encrypted credential; embedding and reranking remain separate capabilities.
CREATE TABLE app_private.reranker_selections (
    selection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bge_config_id uuid NOT NULL REFERENCES app_private.ai_auxiliary_config_drafts(config_id),
    model_name text NOT NULL CHECK (model_name = '@cf/baai/bge-reranker-base'),
    current boolean NOT NULL DEFAULT true,
    created_by uuid NOT NULL REFERENCES app_private.user_profiles(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz
);
CREATE UNIQUE INDEX idx_reranker_one_current ON app_private.reranker_selections(current) WHERE current;
REVOKE ALL ON app_private.reranker_selections FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON app_private.reranker_selections TO service_role;
GRANT UPDATE (current, retired_at) ON app_private.reranker_selections TO service_role;

CREATE FUNCTION app_private.guard_reranker_selection() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.selection_id IS DISTINCT FROM OLD.selection_id
       OR NEW.bge_config_id IS DISTINCT FROM OLD.bge_config_id
       OR NEW.model_name IS DISTINCT FROM OLD.model_name
       OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR (NOT OLD.current AND NEW.current) THEN
        RAISE EXCEPTION 'Reranker selections are immutable';
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION app_private.guard_reranker_selection() FROM PUBLIC, anon, authenticated;
CREATE TRIGGER guard_reranker_selection BEFORE UPDATE ON app_private.reranker_selections
FOR EACH ROW EXECUTE FUNCTION app_private.guard_reranker_selection();
COMMENT ON TABLE app_private.reranker_selections IS
    'Admin-authorized Cloudflare evidence reranking. No current selection means OFF.';
