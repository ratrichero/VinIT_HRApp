-- Ordered fallback references are pinned to each immutable LLM configuration.
-- Secrets remain only in the referenced encrypted configuration rows.
-- Existing configs keep an empty chain; nothing is activated by this migration.
ALTER TABLE app_private.ai_configuration_versions
    ADD COLUMN IF NOT EXISTS fallback_config_ids jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE app_private.ai_configuration_versions
    ADD CONSTRAINT ai_configuration_fallback_ids_array_check
    CHECK (jsonb_typeof(fallback_config_ids) = 'array' AND jsonb_array_length(fallback_config_ids) <= 3);

COMMENT ON COLUMN app_private.ai_configuration_versions.fallback_config_ids IS
    'Ordered list of immutable LLM config UUIDs; runtime validates existence, uniqueness and policy.';
