-- Optional, privacy-minimized per-HTTP-attempt diagnostics. Existing rows are
-- not backfilled: historical actual model, latency, and status remain unknown.
SET LOCAL lock_timeout = '5s';
ALTER TABLE app_private.llm_usage_attempts
    ADD COLUMN returned_model text CHECK (returned_model IS NULL OR char_length(returned_model) BETWEEN 1 AND 200),
    ADD COLUMN duration_ms integer CHECK (duration_ms IS NULL OR duration_ms BETWEEN 0 AND 86400000),
    ADD COLUMN http_status integer CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
    ADD COLUMN failure_category text CHECK (failure_category IS NULL OR failure_category IN ('HTTP_ERROR', 'NETWORK_ERROR', 'INVALID_JSON', 'OTHER_ERROR'));
CREATE INDEX idx_llm_usage_attempts_time_id ON app_private.llm_usage_attempts (created_at DESC, attempt_id DESC);
COMMENT ON COLUMN app_private.llm_usage_attempts.returned_model IS 'Provider-returned model only when it matches or has an identifier suffix of the requested model; otherwise NULL.';
COMMENT ON COLUMN app_private.llm_usage_attempts.duration_ms IS 'Elapsed HTTP post until response or exception, milliseconds; excludes response parsing.';
COMMENT ON COLUMN app_private.llm_usage_attempts.http_success IS 'New records: HTTP status success only; older records may also reflect JSON parse failures. Not business success.';
