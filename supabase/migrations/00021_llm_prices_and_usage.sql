-- Prices are per million input/output tokens in USD, not provider invoices.
-- Existing configurations and historical requests remain unpriced/unknown.
ALTER TABLE app_private.ai_configuration_versions
    ADD COLUMN input_price_per_million_usd numeric(18,6),
    ADD COLUMN output_price_per_million_usd numeric(18,6),
    ADD CONSTRAINT ai_config_input_price_check CHECK (input_price_per_million_usd BETWEEN 0 AND 1000000),
    ADD CONSTRAINT ai_config_output_price_check CHECK (output_price_per_million_usd BETWEEN 0 AND 1000000);

-- One row per observed HTTP attempt. No prompt, CV, JD, provider response,
-- credential, or applicant identifier is stored. Missing usage or price stays
-- NULL rather than being treated as zero. Operational telemetry is best effort.
CREATE TABLE app_private.llm_usage_attempts (
    attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    config_id uuid REFERENCES app_private.ai_configuration_versions(config_id),
    provider text NOT NULL,
    model_name text NOT NULL,
    task_name text NOT NULL,
    http_success boolean NOT NULL,
    input_tokens bigint CHECK (input_tokens BETWEEN 0 AND 1000000000),
    output_tokens bigint CHECK (output_tokens BETWEEN 0 AND 1000000000),
    input_price_per_million_usd numeric(18,6),
    output_price_per_million_usd numeric(18,6),
    estimated_cost_usd numeric(24,12) CHECK (estimated_cost_usd >= 0)
);
CREATE INDEX idx_llm_usage_attempts_created_at ON app_private.llm_usage_attempts(created_at DESC);
REVOKE ALL ON app_private.llm_usage_attempts FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON app_private.llm_usage_attempts TO service_role;
COMMENT ON TABLE app_private.llm_usage_attempts IS
    'Best-effort observed LLM HTTP attempts; USD estimates are incomplete and are not invoices.';
