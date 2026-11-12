"""Admin-managed BGE routing: pinned public metadata and lazy secret hydration."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import text

from app.services.ai_secrets import AISecretError, decrypt_api_key
from app.services.embedding import BGEHttpEmbeddingProvider, EmbeddingError


def load_bge_route(db, config_id: str, *, include_secret: bool = False) -> dict[str, Any]:
    row = db.execute(text("""
        SELECT config_id, service_type, config, api_key_ciphertext
        FROM app_private.ai_auxiliary_config_drafts WHERE config_id = :id
    """), {"id": config_id}).mappings().first()
    if not row or row["service_type"] != "BGE" or not isinstance(row["config"], dict):
        raise EmbeddingError("BGE configuration not found")
    route = {"config_id": str(row["config_id"]), "config": dict(row["config"]),
             "api_key_configured": bool(row["api_key_ciphertext"])}
    if include_secret and row["api_key_ciphertext"]:
        try:
            route["api_key"] = decrypt_api_key(row["api_key_ciphertext"])
        except AISecretError:
            raise EmbeddingError("BGE credential unavailable") from None
    return route


def load_active_bge_chain(db) -> dict[str, Any]:
    row = db.execute(text("""
        SELECT route_set_id, route_config_ids FROM app_private.bge_route_sets
        WHERE status = 'ACTIVE'
    """)).mappings().first()
    if not row:
        raise EmbeddingError("Managed BGE route set is not configured")
    ids = row["route_config_ids"]
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 4
            or not all(isinstance(item, str) for item in ids) or len(set(ids)) != len(ids)):
        raise EmbeddingError("Invalid BGE route set")
    return {"route_set_id": str(row["route_set_id"]),
            "routes": [load_bge_route(db, item) for item in ids]}


def provider_for_pinned_route(db, route: dict[str, Any]) -> BGEHttpEmbeddingProvider:
    stored = load_bge_route(db, route["config_id"], include_secret=True)
    if stored["config"] != route.get("config") or stored["api_key_configured"] != route.get("api_key_configured"):
        raise EmbeddingError("Pinned BGE route differs from stored version")
    config = stored["config"]
    return BGEHttpEmbeddingProvider(
        api_base=config["api_base"], api_key=stored.get("api_key") or "",
        model=config["model_name"], dimension=int(config["dimension"]),
    )


def route_index_version(route: dict[str, Any]) -> str:
    """Isolate vector spaces even when providers advertise the same model."""
    public = {"config_id": route["config_id"], "config": route["config"]}
    digest = hashlib.sha256(json.dumps(public, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"managed-bge-{digest}"
