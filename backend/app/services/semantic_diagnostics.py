"""Runtime/configuration diagnostics for semantic retrieval.

The worker keeps assessment available when semantic retrieval fails.  These
in-process counters make that fallback visible to operators instead of
mistaking configured intent for proof that BGE is healthy.  Only model/config metadata and error class names are recorded;
never CV text, queries, endpoints with credentials or API keys.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.services.embedding import get_embedding_provider

_LOCK = threading.Lock()
_RUNTIME: dict[str, Any] = {
    "runs": 0,
    "provider_successes": 0,
    "provider_failures": 0,
    "pgvector_successes": 0,
    "pgvector_failures": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "document_chunks_embedded": 0,
    "query_texts_embedded": 0,
    "last_outcome": None,
    "last_pgvector_status": None,
    "last_error_type": None,
    "last_run_at": None,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def semantic_configuration() -> dict[str, Any]:
    """Return the configured state without contacting the provider."""
    enabled = bool(settings.SEMANTIC_RETRIEVAL_ENABLED)
    provider_name = (settings.EMBEDDING_PROVIDER or "disabled").strip().lower()
    issues: list[str] = []
    if enabled:
        if provider_name == "disabled":
            issues.append("EMBEDDING_PROVIDER is disabled")
        elif provider_name == "hash":
            issues.append("hash provider is test-only and is not BGE")
        elif provider_name == "bge_http":
            if not (settings.EMBEDDING_API_BASE or "").strip():
                issues.append("EMBEDDING_API_BASE is not configured")
        elif provider_name:
            issues.append(f"unsupported EMBEDDING_PROVIDER: {provider_name}")
        else:
            issues.append("EMBEDDING_PROVIDER is not configured")
        try:
            if int(settings.EMBEDDING_DIMENSION) <= 0:
                issues.append("EMBEDDING_DIMENSION must be positive")
        except (TypeError, ValueError):
            issues.append("EMBEDDING_DIMENSION is invalid")
        try:
            if int(settings.SEMANTIC_TOP_K) <= 0:
                issues.append("SEMANTIC_TOP_K must be positive")
        except (TypeError, ValueError):
            issues.append("SEMANTIC_TOP_K is invalid")
        try:
            similarity = float(settings.SEMANTIC_MIN_SIMILARITY)
            if similarity < -1 or similarity > 1:
                issues.append("SEMANTIC_MIN_SIMILARITY must be between -1 and 1")
        except (TypeError, ValueError):
            issues.append("SEMANTIC_MIN_SIMILARITY is invalid")

    if not enabled:
        configured_state = "DISABLED"
    elif issues:
        configured_state = "MISCONFIGURED"
    else:
        configured_state = "READY_UNVERIFIED"

    provider = get_embedding_provider()
    return {
        "enabled": enabled,
        "configured_state": configured_state,
        "issues": issues,
        "provider": provider.name,
        "configured_provider": provider_name,
        "model": provider.model,
        "dimension": int(provider.dimension),
        "index_version": settings.EMBEDDING_INDEX_VERSION,
        "top_k": int(settings.SEMANTIC_TOP_K),
        "min_similarity": float(settings.SEMANTIC_MIN_SIMILARITY),
    }


def record_semantic_run(
    *,
    cache_hits: int = 0,
    cache_misses: int = 0,
    document_chunks_embedded: int = 0,
    query_texts_embedded: int = 0,
    pgvector_status: str | None = None,
    outcome: str,
    error_type: str | None = None,
) -> None:
    """Record one semantic attempt; error details are class names only."""
    with _LOCK:
        _RUNTIME["runs"] += 1
        _RUNTIME["cache_hits"] += int(cache_hits)
        _RUNTIME["cache_misses"] += int(cache_misses)
        _RUNTIME["document_chunks_embedded"] += int(document_chunks_embedded)
        _RUNTIME["query_texts_embedded"] += int(query_texts_embedded)
        if outcome == "PROVIDER_FALLBACK":
            _RUNTIME["provider_failures"] += 1
        else:
            _RUNTIME["provider_successes"] += 1
        if pgvector_status == "AVAILABLE":
            _RUNTIME["pgvector_successes"] += 1
        elif pgvector_status == "UNAVAILABLE":
            _RUNTIME["pgvector_failures"] += 1
        _RUNTIME["last_outcome"] = outcome
        _RUNTIME["last_pgvector_status"] = pgvector_status
        _RUNTIME["last_error_type"] = error_type
        _RUNTIME["last_run_at"] = _utc_now()


def get_semantic_counters() -> dict[str, Any]:
    """Counters belong to this process only, never the entire worker fleet."""
    with _LOCK:
        runtime = dict(_RUNTIME)
    cache_total = int(runtime["cache_hits"]) + int(runtime["cache_misses"])
    runtime["cache_hit_rate"] = (
        round(int(runtime["cache_hits"]) / cache_total, 6) if cache_total else None
    )
    return runtime


def get_semantic_diagnostics() -> dict[str, Any]:
    """Legacy environment diagnostics (not the managed worker control)."""
    config = semantic_configuration()
    runtime = get_semantic_counters()
    if config["configured_state"] in {"DISABLED", "MISCONFIGURED"}:
        state = config["configured_state"]
    elif runtime["runs"] == 0:
        state = "READY_UNVERIFIED"
    elif runtime["last_outcome"] == "PROVIDER_FALLBACK":
        state = "DEGRADED_FALLBACK"
    elif runtime["last_pgvector_status"] == "UNAVAILABLE":
        state = "OPERATIONAL_IN_MEMORY_PGVECTOR_UNAVAILABLE"
    else:
        state = "OPERATIONAL"
    return {**config, "state": state, "runtime": runtime}


def reset_semantic_diagnostics() -> None:
    """Reset counters; intended for tests and controlled process restarts."""
    with _LOCK:
        _RUNTIME.update({
            "runs": 0,
            "provider_successes": 0,
            "provider_failures": 0,
            "pgvector_successes": 0,
            "pgvector_failures": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "document_chunks_embedded": 0,
            "query_texts_embedded": 0,
            "last_outcome": None,
            "last_pgvector_status": None,
            "last_error_type": None,
            "last_run_at": None,
        })
