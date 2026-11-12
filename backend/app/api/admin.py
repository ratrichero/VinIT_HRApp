import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text

from app.core.config import settings
from app.core.permissions import require_admin_role
from app.db.database import SessionLocal
from app.services.ai_config import (
    AIConfigError,
    allowed_endpoints,
    allowed_models,
    canonical_endpoint,
    get_active_runtime,
    get_runtime_by_id,
    public_runtime,
    validate_runtime,
)
from app.services.ai_runtime_controls import lock_service_for_update, service_enabled, set_service_enabled
from app.services.ai_secrets import (
    AISecretConfigurationError,
    AISecretError,
    api_key_hint,
    decrypt_api_key,
    encrypt_api_key,
    encryption_ready,
    normalize_api_key,
)
from app.services.audit_integrity import verify_audit_chain
from app.services.bge_routes import load_active_bge_chain, load_bge_route, provider_for_pinned_route
from app.services.embedding import EmbeddingError
from app.services.langfuse_observability import get_observability_status
from app.services.llm_client import LLMError, llm_client
from app.services.ltr import LTRError, LTRModel, artifact_sha256
from app.services.ltr_managed import approved_model, current_selection
from app.services.semantic_diagnostics import get_semantic_counters
from app.services.reranker import MODEL as RERANKER_MODEL, RerankerError, cloudflare_rerank_endpoint, current_reranker

router = APIRouter()


class AIConfigUpdateRequest(BaseModel):
    # api_key is write-only: it is encrypted before storage and is never
    # returned by any endpoint, audit record or operation snapshot.
    model_config = ConfigDict(extra="forbid")
    provider: Literal["local", "openai", "azure", "compatible"]
    provider_name: str | None = Field(default=None, max_length=120)
    model_name: str = Field(min_length=1, max_length=200)
    api_base: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=500, repr=False)
    temperature_default: float = Field(default=0.1, ge=0, le=1)
    fallback_config_ids: list[UUID] = Field(default_factory=list, max_length=3)
    fallback_destinations_approved: bool = False

    @field_validator("fallback_config_ids")
    @classmethod
    def _unique_fallbacks(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate LLM fallback configuration")
        return value

    @field_validator("provider_name", "model_name", "api_base", mode="before")
    @classmethod
    def _strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("api_key", mode="before")
    @classmethod
    def _empty_api_key_is_omitted(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class BGEDraftRequest(BaseModel):
    """Write-only credentials for a non-active embedding configuration draft."""
    model_config = ConfigDict(extra="forbid")
    provider_name: str = Field(min_length=1, max_length=120)
    model_name: str = Field(min_length=1, max_length=200)
    api_base: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=500, repr=False)
    dimension: Literal[1024] = 1024
    index_version: str = Field(min_length=1, max_length=120)
    top_k: int = Field(default=5, ge=1, le=5)
    min_similarity: float = Field(default=0.35, ge=0, le=1)

    @field_validator("provider_name", "model_name", "api_base", "index_version", mode="before")
    @classmethod
    def _strip_and_validate(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if any(ord(character) < 32 or ord(character) == 127 for character in value):
                raise ValueError("Control characters are not allowed")
        return value


class BGERouteSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_config_ids: list[UUID] = Field(min_length=1, max_length=4)
    destinations_approved: bool = False

    @field_validator("route_config_ids")
    @classmethod
    def _unique_routes(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate BGE route")
        return value


class RerankerEnableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bge_config_id: UUID
    destinations_approved: bool = False


class LTRDraftRequest(BaseModel):
    """LTR is a registry model, not a chat or embedding endpoint."""
    model_config = ConfigDict(extra="forbid")
    mode: Literal["OFF", "SHADOW", "ACTIVE"] = "OFF"
    model_version: str | None = Field(default=None, max_length=200)

    @field_validator("model_version", mode="before")
    @classmethod
    def _clean_version(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if any(ord(character) < 32 or ord(character) == 127 for character in value):
                raise ValueError("Control characters are not allowed")
            return value or None
        return value


class LTRSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["OFF", "SHADOW", "ACTIVE"]
    draft_config_id: UUID | None = None
    model_version: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)
    shadow_approved: bool = False
    active_approved: bool = False

    @field_validator("reason", "model_version", mode="before")
    @classmethod
    def _strip_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class LTRModelReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def _strip_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


def _lock_active_admin(db, user_id: str) -> None:
    """Keep account/role revocation from racing a configuration write."""
    account = db.execute(text("SELECT account_status FROM app_private.user_profiles WHERE user_id=:user FOR SHARE"),
                         {"user": user_id}).scalar_one_or_none()
    roles = db.execute(text("""
        SELECT role_code FROM app_private.user_role_assignments
        WHERE user_id=:user AND role_code='ADMIN' AND revoked_at IS NULL FOR SHARE
    """), {"user": user_id}).scalars().all()
    if account != "ACTIVE" or not roles:
        raise HTTPException(status_code=403, detail="Admin role required for this endpoint")


def _validate_choice(runtime: dict, *, require_provider_name: bool = False) -> dict:
    try:
        normalized = validate_runtime(runtime, require_provider_name=require_provider_name)
        # The database/UI cannot override the environment's egress decision.
        llm_client._check_endpoint_policy(normalized["api_base"])
        return normalized
    except (AIConfigError, LLMError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


def _stored_key_config_id_for_endpoint(db, runtime: dict) -> str | None:
    """Return the ACTIVE config whose stored key may be reused for this URL."""
    active = db.execute(text("""
        SELECT config_id, api_base, api_key_ciphertext
        FROM app_private.ai_configuration_versions
        WHERE status = 'ACTIVE' LIMIT 1
    """)).mappings().first()
    if not active or not active["api_key_ciphertext"] or not active["api_base"]:
        return None
    try:
        same_endpoint = canonical_endpoint(active["api_base"]) == runtime["api_base"]
    except AIConfigError:
        return None
    return str(active["config_id"]) if same_endpoint else None


def _validate_llm_fallbacks(db, fallback_ids: list[str], *, primary_id: str | None = None) -> None:
    if len(fallback_ids) > 3 or len(set(fallback_ids)) != len(fallback_ids):
        raise HTTPException(status_code=400, detail="Danh sách LLM dự phòng không hợp lệ")
    for fallback_id in fallback_ids:
        if fallback_id == primary_id:
            raise HTTPException(status_code=400, detail="LLM chính không thể là dự phòng của chính nó")
        try:
            route = get_runtime_by_id(db, fallback_id, include_secret=True)
        except AIConfigError:
            raise HTTPException(status_code=503, detail="Không thể đọc cấu hình LLM dự phòng") from None
        if not route:
            raise HTTPException(status_code=400, detail="Không tìm thấy cấu hình LLM dự phòng")
        _validate_choice(route, require_provider_name=route["provider"] == "compatible")


@router.get("/ai/options")
async def get_ai_options(current_user: dict = Depends(require_admin_role)):
    try:
        return {"models": allowed_models(), "endpoints": allowed_endpoints(),
                "external_api_allowed": settings.ALLOW_EXTERNAL_API,
                "custom_openai_compatible": {
                    "api_key_encryption_configured": encryption_ready(),
                }}
    except AIConfigError:
        raise HTTPException(status_code=503, detail="Danh sách endpoint của môi trường không hợp lệ") from None


@router.get("/ai/config")
async def list_ai_configs(current_user: dict = Depends(require_admin_role)):
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT config_id, provider, provider_name, model_name, deployment_mode, api_base,
                   temperature_default, status, created_by, created_at, enabled_at, disabled_at,
                   fallback_config_ids,
                   (api_key_ciphertext IS NOT NULL) AS api_key_configured, api_key_hint
            FROM app_private.ai_configuration_versions ORDER BY created_at DESC, config_id DESC LIMIT 100
        """)).mappings().all()
        return [dict(row) for row in rows]
    finally:
        db.close()


@router.post("/ai/config", status_code=201)
async def create_ai_config(request: AIConfigUpdateRequest, current_user: dict = Depends(require_admin_role)):
    submitted = request.model_dump()
    api_key = submitted.pop("api_key")
    fallback_ids = [str(value) for value in submitted.pop("fallback_config_ids")]
    approved = submitted.pop("fallback_destinations_approved")
    if fallback_ids and not approved:
        raise HTTPException(status_code=400, detail="Cần xác nhận từng nhà cung cấp dự phòng đã được phê duyệt xử lý dữ liệu")
    runtime = _validate_choice(
        submitted,
        require_provider_name=submitted["provider"] == "compatible",
    )
    if api_key is not None and runtime["provider"] != "compatible":
        raise HTTPException(
            status_code=400,
            detail="API key chỉ áp dụng cho nhà cung cấp OpenAI Compatible.",
        )

    api_key_ciphertext = None
    stored_hint = None
    if api_key is not None:
        try:
            normalized_key = normalize_api_key(api_key)
            api_key_ciphertext = encrypt_api_key(normalized_key)
            stored_hint = api_key_hint(normalized_key)
        except AISecretConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        except AISecretError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    db = SessionLocal()
    try:
        _lock_active_admin(db, current_user["user_id"])
        _validate_llm_fallbacks(db, fallback_ids)
        if runtime["provider"] == "compatible" and api_key is None:
            # Reuse is endpoint-bound: changing only the provider display name,
            # model or temperature at the same Base URL must not force the
            # Admin to retype a key, and the key is never copied to a new URL.
            active = db.execute(text("""
                SELECT api_base, api_key_ciphertext, api_key_hint
                FROM app_private.ai_configuration_versions
                WHERE status = 'ACTIVE' LIMIT 1
            """)).mappings().first()
            if active and active["api_key_ciphertext"] and active["api_base"]:
                try:
                    same_endpoint = canonical_endpoint(active["api_base"]) == runtime["api_base"]
                except AIConfigError:
                    same_endpoint = False
                if same_endpoint:
                    api_key_ciphertext = active["api_key_ciphertext"]
                    stored_hint = active["api_key_hint"]
        row = db.execute(text("""
            INSERT INTO app_private.ai_configuration_versions
                (provider, provider_name, model_name, deployment_mode, api_base,
                 temperature_default, api_key_ciphertext, api_key_hint, fallback_config_ids, created_by, status)
            VALUES (:provider, :provider_name, :model_name, :provider, :api_base,
                    :temperature_default, :api_key_ciphertext, :api_key_hint, CAST(:fallback_ids AS jsonb), :user_id, 'DRAFT')
            RETURNING config_id, provider, provider_name, model_name, api_base,
                      temperature_default, status, created_at, fallback_config_ids,
                      (api_key_ciphertext IS NOT NULL) AS api_key_configured, api_key_hint
        """), {**runtime, "api_key_ciphertext": api_key_ciphertext,
               "api_key_hint": stored_hint, "fallback_ids": json.dumps(fallback_ids),
               "user_id": current_user["user_id"]}).mappings().one()
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, outcome)
            VALUES (:user_id, 'CREATE_AI_CONFIG', 'AI_CONFIG', :id, 'DRAFT')
        """), {"user_id": current_user["user_id"], "id": row["config_id"]})
        db.commit()
        return dict(row)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/ai/test-connection")
async def test_ai_connection(request: AIConfigUpdateRequest, current_user: dict = Depends(require_admin_role)):
    """Test the entered provider values without creating a config version."""
    submitted = request.model_dump()
    api_key = submitted.pop("api_key")
    submitted.pop("fallback_config_ids")
    submitted.pop("fallback_destinations_approved")
    runtime = _validate_choice(
        submitted,
        require_provider_name=submitted["provider"] == "compatible",
    )
    if api_key is not None and runtime["provider"] != "compatible":
        raise HTTPException(
            status_code=400,
            detail="API key chỉ áp dụng cho nhà cung cấp OpenAI Compatible.",
        )
    runtime["source"] = "connection_test"

    db = SessionLocal()
    try:
        _lock_active_admin(db, current_user["user_id"])
        if api_key is not None:
            try:
                runtime["api_key"] = normalize_api_key(api_key)
                runtime["api_key_configured"] = True
            except AISecretError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from None
        elif runtime["provider"] == "compatible":
            reusable_config_id = _stored_key_config_id_for_endpoint(db, runtime)
            if reusable_config_id:
                runtime["config_id"] = reusable_config_id
                runtime["api_key_configured"] = True
    finally:
        db.close()

    try:
        return await llm_client.test_provider_connection(runtime)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/ai/config/{config_id}/enable")
async def enable_ai_config(config_id: UUID, current_user: dict = Depends(require_admin_role)):
    db = SessionLocal()
    try:
        _lock_active_admin(db, current_user["user_id"])
        # Serialize activations across all API instances and make the switch
        # atomic. Existing worker attempts keep their already-pinned snapshot.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('hra-ai-activation', 418630021))"))
        row = db.execute(text("""
            SELECT config_id, provider, provider_name, model_name, api_base,
                   temperature_default, status, api_key_ciphertext, fallback_config_ids
            FROM app_private.ai_configuration_versions WHERE config_id = :id FOR UPDATE
        """), {"id": str(config_id)}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản cấu hình AI")
        _validate_choice(
            dict(row),
            require_provider_name=row["provider"] == "compatible",
        )
        _validate_llm_fallbacks(db, row["fallback_config_ids"] or [], primary_id=str(config_id))
        if row["api_key_ciphertext"]:
            try:
                decrypt_api_key(row["api_key_ciphertext"])
            except AISecretError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from None
        db.execute(text("""
            UPDATE app_private.ai_configuration_versions SET status = 'DISABLED', disabled_at = NOW()
            WHERE status = 'ACTIVE' AND config_id != :id
        """), {"id": str(config_id)})
        db.execute(text("""
            UPDATE app_private.ai_configuration_versions SET status = 'ACTIVE', enabled_at = NOW(), disabled_at = NULL
            WHERE config_id = :id
        """), {"id": str(config_id)})
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, outcome)
            VALUES (:user_id, 'ENABLE_AI_CONFIG', 'AI_CONFIG', :id, 'ACTIVE')
        """), {"user_id": current_user["user_id"], "id": str(config_id)})
        db.commit()
        return {"config_id": str(config_id), "status": "ACTIVE"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/ai/active-config")
async def get_active_ai_config(current_user: dict = Depends(require_admin_role)):
    db = SessionLocal()
    try:
        runtime = get_active_runtime(db, include_secret=False)
    finally:
        db.close()
    try:
        validate_runtime(
            runtime,
            require_provider_name=(
                runtime.get("source") == "database" and runtime.get("provider") == "compatible"
            ),
        )
        llm_client._check_endpoint_policy(runtime["api_base"])
        allowed = True
    except (AIConfigError, LLMError):
        allowed = False
    return {"active": True, "source": runtime["source"], "allowed_by_this_process": allowed,
            "config": {**public_runtime(runtime), "external_api_allowed": settings.ALLOW_EXTERNAL_API}}


@router.get("/langfuse/health")
async def get_langfuse_health(current_user: dict = Depends(require_admin_role)):
    """Safe Langfuse configuration state; never returns keys or host."""
    return get_observability_status()


@router.get("/ai/auxiliary-drafts")
async def list_auxiliary_drafts(current_user: dict = Depends(require_admin_role)):
    """List write-only credential drafts; activation is a separate action."""
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT config_id, service_type, config, (api_key_ciphertext IS NOT NULL) AS api_key_configured,
                   api_key_hint, created_at FROM app_private.ai_auxiliary_config_drafts
            ORDER BY created_at DESC, config_id DESC LIMIT 100
        """)).mappings().all()
        return [dict(row) for row in rows]
    finally:
        db.close()


def _save_auxiliary_draft(service_type: str, config: dict, ciphertext: str | None,
                          hint: str | None, current_user: dict) -> dict:
    db = SessionLocal()
    try:
        _lock_active_admin(db, current_user["user_id"])
        if service_type == "LTR" and config.get("model_version"):
            found = db.execute(text("SELECT 1 FROM app_private.ltr_model_versions WHERE model_version=:version"),
                               {"version": config["model_version"]}).scalar_one_or_none()
            if not found:
                raise HTTPException(status_code=400, detail="Không tìm thấy model LTR trong registry")
        row = db.execute(text("""
            INSERT INTO app_private.ai_auxiliary_config_drafts
                (service_type, config, api_key_ciphertext, api_key_hint, created_by)
            VALUES (:service, CAST(:config AS jsonb), :ciphertext, :hint, :user_id)
            RETURNING config_id, service_type, config, (api_key_ciphertext IS NOT NULL) AS api_key_configured,
                      api_key_hint, created_at
        """), {"service": service_type, "config": json.dumps(config), "ciphertext": ciphertext,
               "hint": hint, "user_id": current_user["user_id"]}).mappings().one()
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, outcome)
            VALUES (:user_id, 'CREATE_AI_AUXILIARY_DRAFT', 'AI_AUXILIARY_CONFIG', :id, 'DRAFT')
        """), {"user_id": current_user["user_id"], "id": row["config_id"]})
        db.commit()
        return {**dict(row), "runtime_active": False}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/ai/bge/drafts", status_code=201)
async def create_bge_draft(request: BGEDraftRequest, current_user: dict = Depends(require_admin_role)):
    submitted = request.model_dump()
    api_key = submitted.pop("api_key")
    try:
        submitted["api_base"] = canonical_endpoint(submitted["api_base"])
        ciphertext = encrypt_api_key(api_key) if api_key else None
        hint = api_key_hint(api_key) if api_key else None
    except AISecretConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except (AIConfigError, AISecretError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _save_auxiliary_draft("BGE", submitted, ciphertext, hint, current_user)


@router.get("/ai/bge/route-set")
async def get_bge_route_set(current_user: dict = Depends(require_admin_role)):
    db = SessionLocal()
    try:
        try:
            chain = load_active_bge_chain(db)
        except EmbeddingError:
            chain = None
        return {"route_set": chain, "enabled": service_enabled(db, "BGE"),
                "worker_status": "unknown", "network_policy_external_allowed": bool(settings.ALLOW_EXTERNAL_API)}
    finally:
        db.close()


@router.post("/ai/bge/route-set", status_code=201)
async def create_bge_route_set(request: BGERouteSetRequest, current_user: dict = Depends(require_admin_role)):
    if not request.destinations_approved:
        raise HTTPException(status_code=400, detail="Cần xác nhận từng endpoint BGE đã được phê duyệt xử lý dữ liệu")
    ids = [str(item) for item in request.route_config_ids]
    db = SessionLocal()
    try:
        _lock_active_admin(db, current_user["user_id"])
        lock_service_for_update(db, "BGE")
        for route_id in ids:
            try:
                route = load_bge_route(db, route_id)
                provider = provider_for_pinned_route(db, route)
                if provider.dimension != 1024:
                    raise EmbeddingError("BGE dimension must be 1024")
                provider._check_endpoint_policy()
            except (EmbeddingError, KeyError, ValueError, TypeError) as exc:
                raise HTTPException(status_code=400, detail=f"Cấu hình BGE không hợp lệ: {type(exc).__name__}") from None
        db.execute(text("UPDATE app_private.bge_route_sets SET status='DISABLED', disabled_at=NOW() WHERE status='ACTIVE'"))
        set_service_enabled(db, "BGE", True, current_user["user_id"])
        row = db.execute(text("""
            INSERT INTO app_private.bge_route_sets(route_config_ids, status, created_by)
            VALUES (CAST(:ids AS jsonb), 'ACTIVE', :user_id) RETURNING route_set_id
        """), {"ids": json.dumps(ids), "user_id": current_user["user_id"]}).mappings().one()
        db.execute(text("""
            INSERT INTO app_private.audit_events(actor_user_id, action_type, object_type, object_id, outcome)
            VALUES (:user_id, 'SELECT_BGE_ROUTE_SET', 'BGE_ROUTE_SET', :id, 'ACTIVE')
        """), {"user_id": current_user["user_id"], "id": row["route_set_id"]})
        db.commit()
        return {"route_set_id": str(row["route_set_id"]), "enabled": True, "worker_status": "unknown"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/ai/bge/disable")
async def disable_bge(current_user: dict = Depends(require_admin_role)):
    db = SessionLocal()
    try:
        _lock_active_admin(db, current_user["user_id"])
        lock_service_for_update(db, "BGE")
        set_service_enabled(db, "BGE", False, current_user["user_id"])
        db.execute(text("UPDATE app_private.bge_route_sets SET status='DISABLED', disabled_at=NOW() WHERE status='ACTIVE'"))
        db.execute(text("""
            INSERT INTO app_private.audit_events(actor_user_id, action_type, object_type, outcome)
            VALUES (:user, 'DISABLE_BGE', 'BGE_ROUTE_SET', 'OFF')
        """), {"user": current_user["user_id"]})
        db.commit()
        return {"enabled": False, "worker_status": "unknown"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/ai/reranker")
async def get_reranker(current_user: dict = Depends(require_admin_role)):
    db = SessionLocal()
    try:
        selection = current_reranker(db)
        return {"enabled": selection is not None, "selection": selection, "worker_status": "unknown"}
    finally:
        db.close()


@router.post("/ai/reranker/enable", status_code=201)
async def enable_reranker(request: RerankerEnableRequest, current_user: dict = Depends(require_admin_role)):
    if not request.destinations_approved:
        raise HTTPException(status_code=400, detail="Cần phê duyệt gửi dữ liệu đến Cloudflare reranker")
    db = SessionLocal()
    try:
        _lock_active_admin(db, current_user["user_id"])
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('hra-reranker-selection', 418630021))"))
        try:
            route = load_bge_route(db, str(request.bge_config_id), include_secret=True)
            endpoint = cloudflare_rerank_endpoint(route['config'].get('api_base') or '')
            if not route.get('api_key'):
                raise RerankerError('Cloudflare API key is required')
            from app.services.embedding import BGEHttpEmbeddingProvider
            if not settings.ALLOW_EXTERNAL_API:
                raise RerankerError('External API disabled')
            BGEHttpEmbeddingProvider(api_base=endpoint)._check_endpoint_policy()
        except (RerankerError, EmbeddingError, ValueError, KeyError, TypeError):
            raise HTTPException(status_code=400, detail="Cấu hình Cloudflare hoặc chính sách mạng không hợp lệ") from None
        db.execute(text("UPDATE app_private.reranker_selections SET current=false, retired_at=NOW() WHERE current"))
        selection_id = db.execute(text("""
            INSERT INTO app_private.reranker_selections(bge_config_id, model_name, created_by)
            VALUES (:config_id, :model, :user) RETURNING selection_id
        """), {"config_id": str(request.bge_config_id), "model": RERANKER_MODEL,
                "user": current_user['user_id']}).scalar_one()
        db.execute(text("""
            INSERT INTO app_private.audit_events(actor_user_id, action_type, object_type, object_id, outcome, metadata)
            VALUES (:user, 'ENABLE_RERANKER', 'RERANKER_SELECTION', :id, 'ON', CAST(:metadata AS jsonb))
        """), {"user": current_user['user_id'], "id": selection_id,
                "metadata": json.dumps({"model_name": RERANKER_MODEL, "bge_config_id": str(request.bge_config_id)})})
        db.commit()
        return {"enabled": True, "selection_id": str(selection_id), "worker_status": "unknown"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/ai/reranker/disable")
async def disable_reranker(current_user: dict = Depends(require_admin_role)):
    db = SessionLocal()
    try:
        _lock_active_admin(db, current_user["user_id"])
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('hra-reranker-selection', 418630021))"))
        db.execute(text("UPDATE app_private.reranker_selections SET current=false, retired_at=NOW() WHERE current"))
        db.execute(text("""
            INSERT INTO app_private.audit_events(actor_user_id, action_type, object_type, outcome)
            VALUES (:user, 'DISABLE_RERANKER', 'RERANKER_SELECTION', 'OFF')
        """), {"user": current_user['user_id']})
        db.commit()
        return {"enabled": False, "worker_status": "unknown"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/ai/ltr/drafts", status_code=201)
async def create_ltr_draft(request: LTRDraftRequest, current_user: dict = Depends(require_admin_role)):
    submitted = request.model_dump()
    if submitted["mode"] != "OFF" and not submitted.get("model_version"):
        raise HTTPException(status_code=400, detail="Cần chọn model LTR trong registry")
    return _save_auxiliary_draft("LTR", submitted, None, None, current_user)


@router.get("/semantic/health")
async def get_semantic_health(current_user: dict = Depends(require_admin_role)):
    """Database intent plus process-local counters, never proof of worker health."""
    db = SessionLocal()
    try:
        enabled = service_enabled(db, "BGE")
        state = "DISABLED"
        if enabled:
            try:
                load_active_bge_chain(db)
                state = "READY_UNVERIFIED"
            except EmbeddingError:
                state = "MISCONFIGURED"
        return {"enabled": enabled, "state": state,
                "worker_status": "unknown", "counter_scope": "this API process only",
                "runtime": get_semantic_counters()}
    finally:
        db.close()


@router.get("/audit/verify")
async def verify_audit_integrity(current_user: dict = Depends(require_admin_role)):
    """Verify the audit hash chain without exposing audit metadata."""
    db = SessionLocal()
    try:
        return verify_audit_chain(db)
    finally:
        db.close()


@router.get("/ltr/models")
async def list_ltr_models(current_user: dict = Depends(require_admin_role)):
    """List LTR registry metadata without returning model artifacts."""
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT model_version, status, metrics, feature_names, training_examples,
                   training_groups, data_sha256, artifact_sha256, registered_by,
                   reviewed_by, reviewed_at, review_reason, created_at, approved_at
            FROM app_private.ltr_model_versions
            ORDER BY created_at DESC, model_version DESC
            LIMIT 100
        """)).mappings().all()
        return [dict(row) for row in rows]
    finally:
        db.close()


def _review_ltr_model(model_version: str, action: str, reason: str, current_user: dict) -> dict:
    target_status = "APPROVED" if action == "APPROVED" else "REJECTED"
    db = SessionLocal()
    try:
        _lock_active_admin(db, current_user["user_id"])
        row = db.execute(text("""
            SELECT model_version, artifact, metrics, data_sha256, artifact_sha256, status
            FROM app_private.ltr_model_versions
            WHERE model_version = :model_version
            FOR UPDATE
        """), {"model_version": model_version}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy LTR model version")
        if str(row["status"] or "").upper() != "DRAFT":
            raise HTTPException(status_code=409, detail="Chỉ có thể phê duyệt hoặc từ chối model ở trạng thái DRAFT")
        artifact = row["artifact"]
        if isinstance(artifact, str):
            artifact = json.loads(artifact)
        try:
            model = LTRModel.from_artifact(artifact)
        except (LTRError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=f"Artifact LTR không hợp lệ: {exc}") from None
        current_hash = artifact_sha256(artifact)
        if model.model_version != model_version:
            raise HTTPException(status_code=409, detail="Artifact LTR không khớp model version trong registry")
        if row["artifact_sha256"] and str(row["artifact_sha256"]) != current_hash:
            raise HTTPException(status_code=409, detail="Artifact hash trong registry không khớp nội dung artifact")
        if action == "APPROVED" and not model.passes_gates(
            min_ndcg=float(settings.LTR_MIN_NDCG_AT_10),
            min_pairwise=float(settings.LTR_MIN_PAIRWISE_ACCURACY),
            min_test_examples=int(settings.LTR_MIN_HOLDOUT_EXAMPLES),
            min_test_groups=int(settings.LTR_MIN_HOLDOUT_GROUPS),
        ):
            raise HTTPException(status_code=400, detail="Artifact chưa đạt quality gates để phê duyệt")

        db.execute(text("""
            UPDATE app_private.ltr_model_versions
            SET status = :status,
                artifact_sha256 = :artifact_sha256,
                reviewed_by = :user_id,
                reviewed_at = NOW(),
                review_reason = :reason,
                approved_at = CASE WHEN :status = 'APPROVED' THEN NOW() ELSE NULL END
            WHERE model_version = :model_version
        """), {
            "status": target_status, "artifact_sha256": current_hash,
            "user_id": current_user["user_id"], "reason": reason,
            "model_version": model_version,
        })
        metrics = row["metrics"] if isinstance(row["metrics"], dict) else {}
        db.execute(text("""
            INSERT INTO app_private.ltr_model_review_events
                (model_version, artifact_sha256, actor_user_id, action, from_status,
                 to_status, reason, metrics, data_sha256)
            VALUES (:model_version, :artifact_sha256, :user_id, :action, 'DRAFT',
                    :status, :reason, CAST(:metrics AS jsonb), :data_sha256)
        """), {
            "model_version": model_version, "artifact_sha256": current_hash,
            "user_id": current_user["user_id"], "action": action,
            "status": target_status, "reason": reason,
            "metrics": json.dumps(metrics, ensure_ascii=False),
            "data_sha256": row["data_sha256"],
        })
        db.execute(text("""
            INSERT INTO app_private.audit_events
                (actor_user_id, action_type, object_type, object_id, outcome, metadata)
            VALUES (:user_id, :action_type, 'LTR_MODEL', NULL, :status,
                    CAST(:metadata AS jsonb))
        """), {
            "user_id": current_user["user_id"],
            "action_type": f"LTR_MODEL_{action}",
            "status": target_status,
            "metadata": json.dumps({
                "model_version": model_version,
                "artifact_sha256": current_hash,
            }, ensure_ascii=False),
        })
        updated = db.execute(text("""
            SELECT model_version, status, artifact_sha256, reviewed_by, reviewed_at,
                   review_reason, approved_at
            FROM app_private.ltr_model_versions
            WHERE model_version = :model_version
        """), {"model_version": model_version}).mappings().one()
        db.commit()
        return dict(updated)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/ltr/models/{model_version}/approve")
async def approve_ltr_model(
    model_version: str,
    request: LTRModelReviewRequest,
    current_user: dict = Depends(require_admin_role),
):
    return _review_ltr_model(model_version, "APPROVED", request.reason, current_user)


@router.post("/ltr/models/{model_version}/reject")
async def reject_ltr_model(
    model_version: str,
    request: LTRModelReviewRequest,
    current_user: dict = Depends(require_admin_role),
):
    return _review_ltr_model(model_version, "REJECTED", request.reason, current_user)


@router.get("/worker/health")
async def get_worker_health(current_user: dict = Depends(require_admin_role)):
    """Queue indicators, not a substitute for external alerting/liveness probes."""
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT COUNT(*) FILTER (WHERE status = 'PENDING') AS pending,
                   COUNT(*) FILTER (WHERE status = 'PROCESSING') AS processing,
                   COUNT(*) FILTER (WHERE status = 'PROCESSING' AND
                       (heartbeat_at IS NULL OR heartbeat_at < NOW() - INTERVAL '2 minutes')) AS stale_heartbeat,
                   COUNT(*) FILTER (WHERE status = 'PROCESSING' AND attempt_started_at < NOW() - INTERVAL '30 minutes') AS long_running,
                   COUNT(*) FILTER (WHERE status = 'FAILED' AND completed_at >= NOW() - INTERVAL '24 hours') AS failed_24h,
                   (SELECT COUNT(*) FROM app_private.operation_recovery_events WHERE recovered_at >= NOW() - INTERVAL '24 hours') AS recoveries_24h,
                   COALESCE(EXTRACT(EPOCH FROM (NOW() - MIN(created_at) FILTER (WHERE status = 'PENDING'))), 0)::integer AS oldest_pending_seconds
            FROM app_private.operations WHERE capability IN ('CV_PROCESSING', 'ASSESSMENT', 'RANKING')
        """)).mappings().one()
        return {**dict(row), "stale_after_seconds": 120, "long_running_after_seconds": 1800}
    finally:
        db.close()


@router.get("/ai/ltr/selection")
async def get_ltr_selection(current_user: dict = Depends(require_admin_role)):
    db = SessionLocal()
    try:
        return {"selection": current_selection(db), "enabled": service_enabled(db, "LTR"),
                "worker_status": "unknown"}
    finally:
        db.close()


@router.post("/ai/ltr/selection", status_code=201)
async def select_ltr_shadow(request: LTRSelectionRequest, current_user: dict = Depends(require_admin_role)):
    if request.mode != "OFF" and bool(request.draft_config_id) == bool(request.model_version):
        raise HTTPException(status_code=400, detail="Cần chọn một model hoặc draft LTR")
    if request.mode == "SHADOW" and not request.shadow_approved:
        raise HTTPException(status_code=400, detail="Cần xác nhận phê duyệt phạm vi SHADOW")
    if request.mode == "ACTIVE" and not request.active_approved:
        raise HTTPException(status_code=400, detail="Cần xác nhận phê duyệt ACTIVE, chất lượng và kế hoạch rollback")
    if request.mode == "OFF" and (request.draft_config_id or request.model_version):
        raise HTTPException(status_code=400, detail="OFF không chọn model hoặc draft")
    db = SessionLocal()
    try:
        _lock_active_admin(db, current_user["user_id"])
        lock_service_for_update(db, "LTR")
        version, digest = None, None
        draft_id = str(request.draft_config_id) if request.draft_config_id else None
        if request.mode != "OFF":
            if draft_id:
                row = db.execute(text("""
                    SELECT config, service_type FROM app_private.ai_auxiliary_config_drafts
                    WHERE config_id=:id FOR SHARE
                """), {"id": draft_id}).mappings().first()
                if not row or row['service_type'] != 'LTR' or not isinstance(row['config'], dict) or row['config'].get('mode') != request.mode:
                    raise HTTPException(status_code=400, detail="Draft LTR không khớp chế độ lựa chọn")
                version = row['config'].get('model_version')
            else:
                version = request.model_version
            if not isinstance(version, str) or not version:
                raise HTTPException(status_code=400, detail="Cấu hình LTR thiếu model version")
            try:
                model = approved_model(db, version, lock=True)
                digest = model.artifact_sha256
            except (LTRError, ValueError, TypeError, KeyError):
                raise HTTPException(status_code=409, detail="Model LTR chưa được phê duyệt hoặc không đạt kiểm tra artifact/gate") from None
            if request.mode == "ACTIVE":
                observed = db.execute(text("""
                    SELECT 1 FROM app_private.ranking_runs r
                    JOIN app_private.ltr_managed_selections s ON s.selection_id=r.ltr_selection_id
                    WHERE r.status='COMPLETED' AND r.ltr_mode='SHADOW'
                      AND s.model_version=:version AND s.artifact_sha256=:digest
                      AND EXISTS (SELECT 1 FROM app_private.ranking_items i
                                  WHERE i.ranking_run_id=r.ranking_run_id AND i.ltr_score IS NOT NULL
                                    AND i.ltr_score::text NOT IN ('NaN', 'Infinity', '-Infinity'))
                    LIMIT 1
                """), {"version": version, "digest": digest}).first()
                if not observed:
                    raise HTTPException(status_code=409, detail="Cần có ít nhất một ranking SHADOW hoàn tất với đúng artifact trước ACTIVE")
            if not draft_id:
                draft_id = str(db.execute(text("""
                    INSERT INTO app_private.ai_auxiliary_config_drafts(service_type, config, created_by)
                    VALUES ('LTR', CAST(:config AS jsonb), :user) RETURNING config_id
                """), {"config": json.dumps({"mode": request.mode, "model_version": version}),
                        "user": current_user['user_id']}).scalar_one())
        db.execute(text("UPDATE app_private.ltr_managed_selections SET current=false, retired_at=NOW() WHERE current"))
        selection_id = db.execute(text("""
            INSERT INTO app_private.ltr_managed_selections
                (draft_config_id, mode, model_version, artifact_sha256, reason, created_by)
            VALUES (:draft_id, :mode, :model, :hash, :reason, :user_id) RETURNING selection_id
        """), {"draft_id": draft_id, "mode": request.mode, "model": version, "hash": digest,
               "reason": request.reason, "user_id": current_user['user_id']}).scalar_one()
        set_service_enabled(db, "LTR", request.mode != "OFF", current_user['user_id'])
        db.execute(text("""
            INSERT INTO app_private.audit_events(actor_user_id, action_type, object_type, object_id, outcome, metadata)
            VALUES (:user, 'SELECT_LTR_MANAGED', 'LTR_SELECTION', :id, :mode, CAST(:metadata AS jsonb))
        """), {"user": current_user['user_id'], "id": selection_id, "mode": request.mode,
                "metadata": json.dumps({"model_version": version, "artifact_sha256": digest, "reason": request.reason,
                                        "active_approved": request.active_approved})})
        db.commit()
        return {"selection_id": str(selection_id), "mode": request.mode,
                "enabled": request.mode != "OFF", "worker_status": "unknown"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
