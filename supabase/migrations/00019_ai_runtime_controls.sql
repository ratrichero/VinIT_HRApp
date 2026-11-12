-- Explicit admin-controlled runtime. Existing managed intents do NOT become
-- enabled on upgrade: both services start OFF until an Admin acts.
CREATE TABLE app_private.ai_runtime_controls (
    service_type text PRIMARY KEY CHECK (service_type IN ('BGE', 'LTR')),
    enabled boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid REFERENCES app_private.user_profiles(user_id)
);
INSERT INTO app_private.ai_runtime_controls(service_type) VALUES ('BGE'), ('LTR');
REVOKE ALL ON app_private.ai_runtime_controls FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON app_private.ai_runtime_controls TO service_role;
GRANT UPDATE (enabled, updated_at, updated_by) ON app_private.ai_runtime_controls TO service_role;

ALTER TABLE app_private.ltr_managed_selections DROP CONSTRAINT ltr_managed_selections_mode_check;
ALTER TABLE app_private.ltr_managed_selections DROP CONSTRAINT ltr_managed_selections_check;
ALTER TABLE app_private.ltr_managed_selections ADD CONSTRAINT ltr_managed_selections_mode_check
    CHECK (mode IN ('OFF', 'SHADOW', 'ACTIVE'));
ALTER TABLE app_private.ltr_managed_selections ADD CONSTRAINT ltr_managed_selections_model_check
    CHECK ((mode = 'OFF' AND model_version IS NULL AND artifact_sha256 IS NULL AND draft_config_id IS NULL)
        OR (mode IN ('SHADOW', 'ACTIVE') AND draft_config_id IS NOT NULL AND model_version IS NOT NULL
            AND artifact_sha256 IS NOT NULL AND artifact_sha256 ~ '^[0-9a-f]{64}$'));
COMMENT ON TABLE app_private.ai_runtime_controls IS
    'Authoritative admin controls for new managed BGE/LTR execution; default OFF. Network policy and model validation remain independent.';
COMMENT ON TABLE app_private.ltr_managed_selections IS
    'Audited managed OFF/SHADOW/ACTIVE selections; ACTIVE requires explicit approval and observed SHADOW.';
