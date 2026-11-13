"""Optional Langfuse observability for AI and assessment pipelines.

The integration is deliberately metadata-first and fail-open:

* disabled by default;
* never required for an LLM, embedding, worker or assessment operation;
* never sends prompt/CV/JD/evidence content unless content capture is
  explicitly enabled outside production;
* drops metadata keys that can carry secrets, free text or candidate PII;
* keeps PostgreSQL as the source of truth for business and audit records.

Langfuse is an observability/evaluation side channel only. A Langfuse outage
must not change matching results, workflow state or HR/HM decisions.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_UNSET = object()
_client: Any = _UNSET
_client_lock = threading.Lock()
_client_error_type: str | None = None

_SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "cv",
    "database_url",
    "email",
    "evidence",
    "filename",
    "file_name",
    "free_text",
    "jd_text",
    "password",
    "phone",
    "prompt",
    "quote",
    "reasoning",
    "secret",
    "service_role",
    "supabase",
    "token",
)
_SENSITIVE_EXACT_KEYS = {
    "address",
    "api_base",
    "base_url",
    "candidate_name",
    "content",
    "display_name",
    "full_name",
    "input",
    "name",
    "output",
    "profile",
    "text",
    "title",
}


def _resolved_host() -> str:
    return (getattr(settings, "LANGFUSE_BASE_URL", None) or getattr(settings, "LANGFUSE_HOST", None) or "").strip()


def _sample_rate() -> float:
    try:
        value = float(getattr(settings, "LANGFUSE_SAMPLE_RATE", 1.0))
    except (TypeError, ValueError):
        return 0.0
    return value if 0 <= value <= 1 else 0.0


def observability_enabled() -> bool:
    return bool(getattr(settings, "LANGFUSE_ENABLED", False))


def observability_configured() -> bool:
    return bool(
        observability_enabled()
        and _resolved_host()
        and (getattr(settings, "LANGFUSE_PUBLIC_KEY", None) or "").strip()
        and (getattr(settings, "LANGFUSE_SECRET_KEY", None) or "").strip()
        and _sample_rate() > 0
    )


def capture_content_enabled() -> bool:
    """Content capture is unavailable in production even if misconfigured."""
    return bool(
        getattr(settings, "LANGFUSE_CAPTURE_CONTENT", False)
        and str(getattr(settings, "APP_ENV", "")).strip().lower() != "production"
    )


def _sdk_available() -> bool:
    try:
        return importlib.util.find_spec("langfuse") is not None
    except Exception:
        return False


def _create_client() -> Any | None:
    global _client_error_type
    if not observability_configured():
        return None
    try:
        from langfuse import Langfuse

        kwargs: dict[str, Any] = {
            "public_key": settings.LANGFUSE_PUBLIC_KEY,
            "secret_key": settings.LANGFUSE_SECRET_KEY,
            "environment": (getattr(settings, "LANGFUSE_ENVIRONMENT", None) or settings.APP_ENV),
            "sample_rate": _sample_rate(),
        }
        host = _resolved_host()
        if host:
            kwargs["base_url"] = host
        release = (getattr(settings, "LANGFUSE_RELEASE", None) or "").strip()
        if release:
            kwargs["release"] = release
        return Langfuse(**kwargs)
    except Exception as exc:  # observability must never break the AI pipeline
        _client_error_type = type(exc).__name__
        logger.warning("Langfuse client unavailable", error_type=_client_error_type)
        return None


def get_client() -> Any | None:
    """Return the lazy Langfuse client, or ``None`` for the no-op path."""
    global _client
    if _client is not _UNSET:
        return None if _client is None else _client
    with _client_lock:
        if _client is _UNSET:
            _client = _create_client()
    return None if _client is None else _client


def reset_observability_client(client: Any = _UNSET) -> None:
    """Reset or inject a client; intended for tests and process shutdown."""
    global _client, _client_error_type
    with _client_lock:
        _client = client
        if client is _UNSET:
            _client_error_type = None


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    if normalized.endswith("_sha256"):
        return False  # hashes are correlation metadata, not content
    return normalized in _SENSITIVE_EXACT_KEYS or any(
        fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS
    )


def sanitize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep only scalar operational metadata that is safe to export."""
    clean: dict[str, Any] = {}
    for key, value in dict(metadata or {}).items():
        key_text = str(key)
        if _is_sensitive_key(key_text) or value is None:
            continue
        if isinstance(value, bool):
            clean[key_text] = value
        elif isinstance(value, int):
            clean[key_text] = value
        elif isinstance(value, float):
            clean[key_text] = value if value == value and value not in (float("inf"), float("-inf")) else None
            if clean[key_text] is None:
                clean.pop(key_text, None)
        elif isinstance(value, (list, tuple, set)):
            values = [str(item)[:80] for item in value if isinstance(item, (str, int, float, bool))]
            if values:
                clean[key_text] = ",".join(values)[:256]
        elif isinstance(value, Mapping):
            continue
        else:
            text = str(value).strip()
            if text:
                clean[key_text] = text[:256]
    return clean


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def content_summary(value: Any) -> dict[str, Any]:
    """Represent content by hash/size unless controlled capture is enabled."""
    if value is None:
        return {"content_capture": "empty"}
    if capture_content_enabled():
        return {"content_capture": "enabled", "content": _truncate_content(value)}
    rendered = value if isinstance(value, str) else _stable_json(value)
    return {
        "content_capture": "disabled",
        "content_type": type(value).__name__,
        "content_characters": len(rendered),
        "content_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    }


def _truncate_content(value: Any, *, limit: int = 20_000) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, Mapping):
        return {str(key): _truncate_content(item, limit=limit) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_truncate_content(item, limit=limit) for item in value]
    return value


class Observation:
    """Fail-open wrapper around a Langfuse span/generation."""

    def __init__(self, span: Any = None, client: Any = None) -> None:
        self._span = span
        self._client = client

    @property
    def trace_id(self) -> str | None:
        for source in (self._span, self._client):
            if source is None:
                continue
            for attribute in ("trace_id", "get_current_trace_id"):
                value = getattr(source, attribute, None)
                try:
                    resolved = value() if callable(value) else value
                except Exception:
                    continue
                if resolved:
                    return str(resolved)
        return None

    def update(self, **kwargs: Any) -> None:
        if self._span is None:
            return
        payload = {key: value for key, value in kwargs.items() if value is not None}
        if "metadata" in payload:
            payload["metadata"] = sanitize_metadata(payload["metadata"])
        try:
            self._span.update(**payload)
        except Exception as exc:
            logger.warning("Langfuse observation update failed", error_type=type(exc).__name__)

    def score_trace(
        self,
        *,
        name: str,
        value: Any,
        data_type: str | None = None,
        comment: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "name": name,
            "value": value,
            "data_type": data_type,
            "comment": comment,
            "metadata": sanitize_metadata(metadata),
        }
        kwargs = {key: item for key, item in kwargs.items() if item is not None}
        try:
            if self._span is not None and hasattr(self._span, "score_trace"):
                self._span.score_trace(**kwargs)
                return
            trace_id = self.trace_id
            if self._client is not None and trace_id:
                self._client.create_score(trace_id=trace_id, **kwargs)
        except Exception as exc:
            logger.warning("Langfuse trace score failed", error_type=type(exc).__name__)

    def score(
        self,
        *,
        name: str,
        value: Any,
        data_type: str | None = None,
        comment: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Attach a score to this observation rather than the whole trace."""
        kwargs: dict[str, Any] = {
            "name": name,
            "value": value,
            "data_type": data_type,
            "comment": comment,
            "metadata": sanitize_metadata(metadata),
        }
        kwargs = {key: item for key, item in kwargs.items() if item is not None}
        try:
            if self._span is not None and hasattr(self._span, "score"):
                self._span.score(**kwargs)
        except Exception as exc:
            logger.warning("Langfuse observation score failed", error_type=type(exc).__name__)


@contextmanager
def observation(
    name: str,
    *,
    as_type: str = "span",
    model: str | None = None,
    model_parameters: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    version: str | None = None,
    input_data: Any = None,
    output_data: Any = None,
) -> Iterator[Observation]:
    client = get_client()
    if client is None:
        yield Observation()
        return

    kwargs: dict[str, Any] = {
        "as_type": as_type,
        "name": name,
        "metadata": sanitize_metadata(metadata),
    }
    if model:
        kwargs["model"] = model
    if model_parameters:
        kwargs["model_parameters"] = {
            str(key): value for key, value in model_parameters.items()
            if isinstance(value, (str, int, float, bool)) or value is None
        }
    if version:
        kwargs["version"] = version
    if input_data is not None:
        kwargs["input"] = content_summary(input_data)
    if output_data is not None:
        kwargs["output"] = content_summary(output_data)

    try:
        context = client.start_as_current_observation(**kwargs)
    except Exception as exc:
        logger.warning("Langfuse observation start failed", error_type=type(exc).__name__)
        yield Observation()
        return

    try:
        active_span = context.__enter__()
    except Exception as exc:
        logger.warning("Langfuse observation enter failed", error_type=type(exc).__name__)
        yield Observation()
        return
    observation_handle = Observation(span=active_span, client=client)
    try:
        yield observation_handle
    except BaseException as exc:
        observation_handle.update(level="ERROR", status_message=type(exc).__name__)
        try:
            # The SDK records exception messages and stack traces on exit. They
            # can contain CV/JD or credentials; export only the error type above.
            context.__exit__(None, None, None)
        except Exception as exit_exc:
            logger.warning("Langfuse observation exit failed", error_type=type(exit_exc).__name__)
        raise
    else:
        try:
            context.__exit__(None, None, None)
        except Exception as exc:
            logger.warning("Langfuse observation exit failed", error_type=type(exc).__name__)


@contextmanager
def span(name: str, **kwargs: Any) -> Iterator[Observation]:
    with observation(name, as_type="span", **kwargs) as handle:
        yield handle


@contextmanager
def generation(name: str, **kwargs: Any) -> Iterator[Observation]:
    with observation(name, as_type="generation", **kwargs) as handle:
        yield handle


@contextmanager
def embedding(name: str, **kwargs: Any) -> Iterator[Observation]:
    with observation(name, as_type="embedding", **kwargs) as handle:
        yield handle


def create_score(
    *,
    trace_id: str | None,
    name: str,
    value: Any,
    data_type: str | None = None,
    comment: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    client = get_client()
    if client is None or not trace_id:
        return
    kwargs: dict[str, Any] = {
        "trace_id": trace_id,
        "name": name,
        "value": value,
        "data_type": data_type,
        "comment": comment,
        "metadata": sanitize_metadata(metadata),
    }
    kwargs = {key: item for key, item in kwargs.items() if item is not None}
    try:
        client.create_score(**kwargs)
    except Exception as exc:
        logger.warning("Langfuse score failed", error_type=type(exc).__name__)


def trace_id_for_seed(seed: str) -> str:
    """Return a deterministic trace ID for offline score correlation."""
    client = get_client()
    if client is not None:
        try:
            return str(client.create_trace_id(seed=seed))
        except Exception as exc:
            logger.warning("Langfuse trace ID creation failed", error_type=type(exc).__name__)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def flush() -> None:
    client = get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as exc:
        logger.warning("Langfuse flush failed", error_type=type(exc).__name__)


def shutdown() -> None:
    global _client
    client = get_client()
    if client is None:
        reset_observability_client()
        return
    try:
        client.shutdown()
    except Exception as exc:
        logger.warning("Langfuse shutdown failed", error_type=type(exc).__name__)
    finally:
        reset_observability_client()


def get_observability_status() -> dict[str, Any]:
    """Safe status for Admin diagnostics; never returns keys or host."""
    return {
        "enabled": observability_enabled(),
        "configured": observability_configured(),
        "sdk_available": _sdk_available(),
        "client_initialized": _client is not _UNSET and _client is not None,
        "client_error_type": _client_error_type,
        "environment": (getattr(settings, "LANGFUSE_ENVIRONMENT", None) or settings.APP_ENV),
        "release_configured": bool((getattr(settings, "LANGFUSE_RELEASE", None) or "").strip()),
        "sample_rate": _sample_rate(),
        "capture_content": capture_content_enabled(),
        "capture_content_configured": bool(getattr(settings, "LANGFUSE_CAPTURE_CONTENT", False)),
    }
