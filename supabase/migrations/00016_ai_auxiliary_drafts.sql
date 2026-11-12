-- Draft-only configuration for BGE embedding and LTR ranking.
-- Saving a draft does not activate semantic retrieval, change worker settings,
-- approve a model, or enable LTR. Provider credentials are Fernet ciphertext.
CREATE TABLE IF NOT EXISTS app_private.ai_auxiliary_config_drafts (
    config_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    service_type text NOT NULL CHECK (service_type IN ('BGE', 'LTR')),
    config jsonb NOT NULL CHECK (jsonb_typeof(config) = 'object'),
    api_key_ciphertext text CHECK (api_key_ciphertext IS NULL OR char_length(api_key_ciphertext) BETWEEN 1 AND 4096),
    api_key_hint text CHECK (api_key_hint IS NULL OR char_length(api_key_hint) BETWEEN 1 AND 16),
    created_by uuid NOT NULL REFERENCES app_private.user_profiles(user_id),
    created_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON app_private.ai_auxiliary_config_drafts FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON app_private.ai_auxiliary_config_drafts TO service_role;
COMMENT ON TABLE app_private.ai_auxiliary_config_drafts IS
    'Admin-managed draft metadata only; not connected to runtime activation.';
