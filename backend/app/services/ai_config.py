"""Versioned AI runtime choices.

Built-in deployment choices remain bounded by the environment allowlists. An
Admin may additionally define an OpenAI-compatible provider with its own
display name, base URL and model; its API key is stored only as ciphertext by
``ai_secrets`` and is exposed to callers of this module solely for the actual
provider request. Use ``public_runtime``/``runtime_snapshot`` whenever a
runtime is serialized or persisted.
"""
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text

from app.core.config import settings
from app.services.ai_secrets import AISecretError, decrypt_api_key


class AIConfigError(ValueError):
    pass


PROVIDERS = {"local", "openai", "azure", "compatible"}
_SECRET_FIELDS = {"api_key", "api_key_ciphertext"}

# Worker operations pin one version across all calls and across crash recovery.
# A synchronous API call without a pinned operation resolves the current version.
runtime_context: ContextVar[dict[str, Any] | None] = ContextVar("ai_runtime", default=None)


def canonical_endpoint(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or any(x in parsed.path for x in ("%", "..", "\\"))):
            raise ValueError()
        host = parsed.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        if port:
            host += f":{port}"
        return urlunsplit((parsed.scheme.lower(), host, parsed.path.rstrip("/"), "", ""))
    except (AttributeError, ValueError):
        raise AIConfigError("Endpoint không hợp lệ; không được chứa credential, query hoặc fragment") from None


def allowed_endpoints() -> list[str]:
    values = list(settings.LLM_ALLOWED_API_BASES)
    if settings.LLM_API_BASE:
        values.append(settings.LLM_API_BASE)
    return sorted({canonical_endpoint(value) for value in values})


def allowed_models() -> list[str]:
    return sorted(set(settings.LLM_ALLOWED_MODELS + [settings.LLM_MODEL_NAME]))


def _clean_provider_name(value: Any, *, required: bool = False) -> str | None:
    if value is None:
        name = None
    elif isinstance(value, str):
        name = value.strip()
    else:
        raise AIConfigError("Tên nhà cung cấp AI không hợp lệ")
    if not name:
        if required:
            raise AIConfigError("Vui lòng nhập tên nhà cung cấp OpenAI Compatible.")
        return None
    if len(name) > 120 or any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise AIConfigError("Tên nhà cung cấp AI không hợp lệ")
    return name


def _clean_model_name(value: Any) -> str:
    if not isinstance(value, str):
        raise AIConfigError("Model AI không hợp lệ")
    model = value.strip()
    if not model or len(model) > 200 or any(ord(character) < 32 or ord(character) == 127 for character in model):
        raise AIConfigError("Model AI không hợp lệ")
    return model


def validate_runtime(runtime: dict[str, Any], *, require_provider_name: bool = False) -> dict[str, Any]:
    """Validate a runtime and return a normalized copy.

    Non-compatible providers are still restricted to the operator's model and
    endpoint allowlists. A ``compatible`` provider is the explicit Admin-managed
    escape hatch: its model/base URL are free-form, while endpoint transport
    policy (private address handling, HTTPS and ``ALLOW_EXTERNAL_API``) remains
    enforced by ``LLMClient._check_endpoint_policy`` before any request.
    """
    provider = runtime.get("provider")
    if provider not in PROVIDERS:
        raise AIConfigError("Nhà cung cấp AI không hợp lệ")
    provider_name = _clean_provider_name(
        runtime.get("provider_name"),
        required=provider == "compatible" and require_provider_name,
    )
    base = runtime.get("api_base")
    if not base:
        raise AIConfigError("Endpoint AI chưa được cấu hình")
    canonical_base = canonical_endpoint(base)
    if provider == "compatible":
        model_name = _clean_model_name(runtime.get("model_name"))
    else:
        model_name = runtime.get("model_name")
        if model_name not in allowed_models():
            raise AIConfigError("Model không nằm trong danh sách được phép của môi trường")
        if canonical_base not in allowed_endpoints():
            raise AIConfigError("Endpoint không nằm trong danh sách được phép của môi trường")
    try:
        temperature = float(runtime.get("temperature_default"))
    except (TypeError, ValueError):
        raise AIConfigError("Temperature không hợp lệ") from None
    if not 0 <= temperature <= 1:
        raise AIConfigError("Temperature phải nằm trong khoảng 0–1")
    return {**runtime, "provider": provider, "provider_name": provider_name,
            "model_name": model_name, "api_base": canonical_base,
            "temperature_default": temperature}


def public_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    """Runtime data safe for API responses and persisted operation snapshots."""
    public = {key: value for key, value in runtime.items() if key not in _SECRET_FIELDS and key != "fallbacks"}
    if "fallbacks" in runtime:
        public["fallbacks"] = [public_runtime(item) for item in runtime["fallbacks"]]
    if isinstance(runtime.get("bge_chain"), dict):
        chain = runtime["bge_chain"]
        public["bge_chain"] = {**chain, "routes": [public_runtime(route) for route in chain.get("routes", [])]}
    public["api_key_configured"] = bool(
        runtime.get("api_key_configured") or runtime.get("api_key") or runtime.get("api_key_ciphertext")
    )
    return public


def runtime_snapshot(runtime: dict[str, Any]) -> dict[str, Any]:
    """The exact runtime representation stored on a worker operation."""
    return public_runtime(runtime)


def sanitize_provider_snapshot(
    snapshot: Any,
    *,
    operations_access: bool = False,
) -> dict[str, Any] | None:
    """Provider metadata safe for an assessment API response.

    Operations users may see the full public runtime snapshot.  Everyone
    else gets only model provenance needed to interpret a result: no base
    URL, provider configuration id, or API-key hint.
    """
    if not isinstance(snapshot, dict):
        return None
    if operations_access:
        result = dict(snapshot)
        runtime = result.get("runtime")
        if isinstance(runtime, dict):
            result["runtime"] = public_runtime(runtime)
        return result
    runtime = snapshot.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    reduced = {
        "model_name": snapshot.get("actual_model") or runtime.get("model_name"),
        "provider_returned_model": snapshot.get("provider_returned_model"),
        "system_fingerprint": snapshot.get("system_fingerprint"),
    }
    reduced = {key: value for key, value in reduced.items() if value is not None}
    return reduced or None


def environment_runtime() -> dict[str, Any]:
    return {"source": "environment", "config_id": None, "provider": settings.LLM_PROVIDER,
            "provider_name": settings.LLM_PROVIDER_NAME,
            "model_name": settings.LLM_MODEL_NAME, "api_base": settings.LLM_API_BASE,
            "temperature_default": settings.LLM_TEMPERATURE_DEFAULT,
            "input_price_per_million_usd": None, "output_price_per_million_usd": None,
            "api_key_configured": bool(settings.LLM_API_KEY), "api_key_hint": None}


def _database_runtime(row, *, include_secret: bool = True) -> dict[str, Any]:
    ciphertext = row.get("api_key_ciphertext")
    runtime = {"source": "database", "config_id": str(row["config_id"]), "provider": row["provider"],
               "provider_name": row.get("provider_name"),
               "model_name": row["model_name"], "api_base": row["api_base"],
               "temperature_default": float(row["temperature_default"]) if row["temperature_default"] is not None else None,
               "api_key_configured": bool(ciphertext), "api_key_hint": row.get("api_key_hint"),
               "input_price_per_million_usd": float(row["input_price_per_million_usd"]) if row.get("input_price_per_million_usd") is not None else None,
               "output_price_per_million_usd": float(row["output_price_per_million_usd"]) if row.get("output_price_per_million_usd") is not None else None}
    if ciphertext and include_secret:
        try:
            runtime["api_key"] = decrypt_api_key(ciphertext)
        except AISecretError as exc:
            raise AIConfigError(str(exc)) from None
    return runtime


def get_runtime_by_id(db, config_id: str, *, include_secret: bool = True) -> dict[str, Any] | None:
    row = db.execute(text("""
        SELECT config_id, provider, provider_name, model_name, api_base, temperature_default,
               input_price_per_million_usd, output_price_per_million_usd, api_key_ciphertext, api_key_hint
        FROM app_private.ai_configuration_versions WHERE config_id = :config_id
    """), {"config_id": str(config_id)}).mappings().first()
    return _database_runtime(row, include_secret=include_secret) if row else None


def get_active_runtime(db, *, include_secret: bool = False) -> dict[str, Any]:
    row = db.execute(text("""
        SELECT config_id, provider, provider_name, model_name, api_base, temperature_default,
               input_price_per_million_usd, output_price_per_million_usd, api_key_ciphertext, api_key_hint, fallback_config_ids
        FROM app_private.ai_configuration_versions WHERE status = 'ACTIVE'
        ORDER BY enabled_at DESC NULLS LAST LIMIT 1
    """)).mappings().first()
    if not row:
        return environment_runtime()
    runtime = _database_runtime(row, include_secret=include_secret)
    fallback_ids = row.get("fallback_config_ids") or []
    if (not isinstance(fallback_ids, list) or len(fallback_ids) > 3
            or not all(isinstance(item, str) for item in fallback_ids)
            or len(set(fallback_ids)) != len(fallback_ids)):
        raise AIConfigError("Invalid LLM fallback configuration")
    fallbacks = []
    for fallback_id in fallback_ids:
        if not isinstance(fallback_id, str) or fallback_id == runtime["config_id"]:
            raise AIConfigError("Invalid LLM fallback configuration")
        # Resolve fallback secrets lazily only if that route is attempted.
        fallback = get_runtime_by_id(db, fallback_id, include_secret=False)
        if not fallback:
            raise AIConfigError("LLM fallback configuration not found")
        fallbacks.append(fallback)
    runtime["fallbacks"] = fallbacks
    return runtime


def hydrate_runtime_secret(db, runtime: dict[str, Any]) -> dict[str, Any]:
    """Attach the stored key to a pinned public snapshot, in memory only."""
    if not runtime:
        return runtime
    hydrated = dict(runtime)
    if runtime.get("api_key") or not runtime.get("config_id"):
        return hydrated
    stored = get_runtime_by_id(db, str(runtime["config_id"]), include_secret=True)
    if not stored:
        if runtime.get("api_key_configured"):
            raise AIConfigError("Pinned AI configuration not found")
        return hydrated
    # Never attach a credential to a changed endpoint/model snapshot.
    if (stored.get("api_base") != runtime.get("api_base")
            or stored.get("model_name") != runtime.get("model_name")
            or stored.get("provider") != runtime.get("provider")):
        raise AIConfigError("Pinned AI configuration does not match stored version")
    if runtime.get("api_key_configured") and not stored.get("api_key"):
        raise AIConfigError("Pinned AI credential unavailable")
    if stored.get("api_key"):
        hydrated["api_key"] = stored["api_key"]
    hydrated["api_key_configured"] = bool(stored.get("api_key_configured"))
    hydrated["api_key_hint"] = stored.get("api_key_hint")
    if not hydrated.get("provider_name"):
        hydrated["provider_name"] = stored.get("provider_name")
    return hydrated
