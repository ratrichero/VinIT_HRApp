-- Ordered immutable BGE route set. Selecting routes never enables semantic
-- retrieval; worker environment gates remain authoritative.
CREATE TABLE IF NOT EXISTS app_private.bge_route_sets (
    route_set_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    route_config_ids jsonb NOT NULL CHECK (jsonb_typeof(route_config_ids) = 'array'
        AND jsonb_array_length(route_config_ids) BETWEEN 1 AND 4),
    status text NOT NULL CHECK (status IN ('ACTIVE', 'DISABLED')),
    created_by uuid NOT NULL REFERENCES app_private.user_profiles(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    disabled_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_bge_route_sets_one_active
    ON app_private.bge_route_sets(status) WHERE status = 'ACTIVE';
REVOKE ALL ON app_private.bge_route_sets FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON app_private.bge_route_sets TO service_role;
GRANT UPDATE (status, disabled_at) ON app_private.bge_route_sets TO service_role;

CREATE OR REPLACE FUNCTION app_private.guard_bge_route_set_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.route_set_id IS DISTINCT FROM OLD.route_set_id
       OR NEW.route_config_ids IS DISTINCT FROM OLD.route_config_ids
       OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR (OLD.status = 'DISABLED' AND NEW.status <> 'DISABLED') THEN
        RAISE EXCEPTION 'BGE route set versions are immutable';
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION app_private.guard_bge_route_set_version() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS guard_bge_route_set_version ON app_private.bge_route_sets;
CREATE TRIGGER guard_bge_route_set_version BEFORE UPDATE ON app_private.bge_route_sets
FOR EACH ROW EXECUTE FUNCTION app_private.guard_bge_route_set_version();
COMMENT ON TABLE app_private.bge_route_sets IS
    'Versioned embedding routes only; does not bypass worker feature or egress gates.';
