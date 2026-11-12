"""Authoritative, fail-closed managed AI runtime controls."""
from sqlalchemy import text


def service_enabled(db, service: str, *, lock: bool = False) -> bool:
    row = db.execute(text("""
        SELECT enabled FROM app_private.ai_runtime_controls WHERE service_type=:service
    """ + (" FOR SHARE" if lock else "")), {"service": service}).scalar_one_or_none()
    if row is None:
        raise RuntimeError("AI runtime control missing")
    return row is True


def lock_service_for_update(db, service: str) -> None:
    # A missing row is an error, not permission to fall back to environment.
    db.execute(text("""
        SELECT service_type FROM app_private.ai_runtime_controls
        WHERE service_type=:service FOR UPDATE
    """), {"service": service}).scalar_one()


def set_service_enabled(db, service: str, enabled: bool, user_id: str) -> None:
    result = db.execute(text("""
        UPDATE app_private.ai_runtime_controls
        SET enabled=:enabled, updated_at=NOW(), updated_by=:user
        WHERE service_type=:service
    """), {"service": service, "enabled": enabled, "user": user_id})
    if result.rowcount != 1:
        raise RuntimeError("AI runtime control missing")


def bge_pin_is_current(db, chain: dict) -> bool:
    if not isinstance(chain, dict) or not chain.get("route_set_id"):
        return False
    routes = chain.get("routes")
    if not isinstance(routes, list) or not routes or any(not isinstance(route, dict) for route in routes):
        return False
    ids = [route.get("config_id") for route in routes]
    if not all(isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
        return False
    active_ids = db.execute(text("""
        SELECT s.route_config_ids FROM app_private.ai_runtime_controls c
        JOIN app_private.bge_route_sets s ON s.status='ACTIVE'
        WHERE c.service_type='BGE' AND c.enabled AND s.route_set_id=:id
    """), {"id": chain["route_set_id"]}).scalar_one_or_none()
    return active_ids == ids
