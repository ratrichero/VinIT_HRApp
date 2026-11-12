-- Immutable, audited deployment intent. This is not a runtime feature flag:
-- workers also require ALLOW_MANAGED_LTR_ROUTING and LTR_MODE=SHADOW.
-- ACTIVE is deliberately not supported by this workflow.
CREATE TABLE IF NOT EXISTS app_private.ltr_managed_selections (
    selection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_config_id uuid REFERENCES app_private.ai_auxiliary_config_drafts(config_id),
    mode text NOT NULL CHECK (mode IN ('OFF', 'SHADOW')),
    model_version text REFERENCES app_private.ltr_model_versions(model_version),
    artifact_sha256 text,
    reason text NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 1000),
    current boolean NOT NULL DEFAULT true,
    created_by uuid NOT NULL REFERENCES app_private.user_profiles(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    CHECK ((mode = 'OFF' AND model_version IS NULL AND artifact_sha256 IS NULL)
        OR (mode = 'SHADOW' AND draft_config_id IS NOT NULL AND model_version IS NOT NULL
            AND artifact_sha256 ~ '^[0-9a-f]{64}$'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ltr_managed_selection_current
    ON app_private.ltr_managed_selections(current) WHERE current;
REVOKE ALL ON app_private.ltr_managed_selections FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON app_private.ltr_managed_selections TO service_role;
GRANT UPDATE (current, retired_at) ON app_private.ltr_managed_selections TO service_role;

CREATE OR REPLACE FUNCTION app_private.guard_ltr_managed_selection() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.selection_id IS DISTINCT FROM OLD.selection_id
       OR NEW.draft_config_id IS DISTINCT FROM OLD.draft_config_id
       OR NEW.mode IS DISTINCT FROM OLD.mode
       OR NEW.model_version IS DISTINCT FROM OLD.model_version
       OR NEW.artifact_sha256 IS DISTINCT FROM OLD.artifact_sha256
       OR NEW.reason IS DISTINCT FROM OLD.reason
       OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR (NOT OLD.current AND NEW.current) THEN
        RAISE EXCEPTION 'LTR managed selections are immutable';
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION app_private.guard_ltr_managed_selection() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS guard_ltr_managed_selection ON app_private.ltr_managed_selections;
CREATE TRIGGER guard_ltr_managed_selection BEFORE UPDATE ON app_private.ltr_managed_selections
FOR EACH ROW EXECUTE FUNCTION app_private.guard_ltr_managed_selection();
ALTER TABLE app_private.ranking_runs ADD COLUMN IF NOT EXISTS ltr_selection_id uuid
    REFERENCES app_private.ltr_managed_selections(selection_id);
COMMENT ON TABLE app_private.ltr_managed_selections IS
    'Audited shadow-only deployment intents, subject to independent worker feature gates.';
