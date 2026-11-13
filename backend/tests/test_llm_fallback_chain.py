from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.api.admin import AIConfigUpdateRequest
from app.services.ai_config import public_runtime, runtime_context
from app.services.llm_client import LLMClient, LLMError


def route(name):
    return {"provider": "compatible", "provider_name": name, "model_name": name,
            "api_base": f"http://{name}.internal/v1", "temperature_default": .1,
            "config_id": name, "api_key": "secret-" + name}


@pytest.mark.asyncio
async def test_ordered_fallback_and_actual_provider_metadata(monkeypatch):
    client = LLMClient()
    calls = []

    async def fake_once(*args, **kwargs):
        current = runtime_context.get()
        calls.append(current["model_name"])
        if current["model_name"] != "third":
            raise LLMError("unavailable")
        return {"ok": True}

    monkeypatch.setattr(client, "_call_llm_one", fake_once)
    primary = route("primary")
    primary["fallbacks"] = [route("second"), route("third")]
    token = runtime_context.set(primary)
    try:
        metadata = {}
        assert await client._call_llm("system", "synthetic", metadata_out=metadata) == {"ok": True}
        assert calls == ["primary", "second", "third"]
        assert metadata["actual_model"] == "third" and metadata["fallback_index"] == 2
        assert "secret" not in str(metadata)
        assert runtime_context.get() is primary
    finally:
        runtime_context.reset(token)


@pytest.mark.asyncio
async def test_all_routes_fail_without_leaking_upstream_error(monkeypatch):
    client = LLMClient()
    monkeypatch.setattr(client, "_call_llm_one", AsyncMock(side_effect=LLMError("private-secret")))
    primary = route("primary")
    primary["fallbacks"] = [route("secondary")]
    token = runtime_context.set(primary)
    try:
        with pytest.raises(LLMError, match="All configured LLM routes failed") as exc:
            await client._call_llm("system", "synthetic")
        assert "private-secret" not in str(exc.value)
        assert client._call_llm_one.await_count == 2
    finally:
        runtime_context.reset(token)


def test_fallback_secrets_removed_recursively():
    primary = route("primary")
    primary["fallbacks"] = [route("secondary")]
    sanitized = public_runtime(primary)
    assert "secret-" not in str(sanitized)
    assert sanitized["fallbacks"][0]["api_key_configured"] is True


def test_duplicate_fallback_ids_are_rejected():
    body = {"provider": "compatible", "provider_name": "p", "model_name": "m", "api_base": "https://example.test/v1"}
    with pytest.raises(ValidationError):
        AIConfigUpdateRequest(**body, fallback_config_ids=[
            "00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000001"])


@pytest.mark.asyncio
async def test_http_error_retries_primary_before_fallback_and_uses_only_own_key(monkeypatch):
    import httpx
    from tenacity import wait_none
    from app.core.config import settings

    calls = []

    class Reply:
        def __init__(self, url):
            self.request = httpx.Request("POST", url)
            self.status_code = 503 if "11434" in url else 200
            self.response = httpx.Response(503, request=self.request)
        def raise_for_status(self):
            if "11434" in str(self.request.url):
                raise httpx.HTTPStatusError("secret response", request=self.request, response=self.response)
        def json(self):
            return {"model": "backup-model", "choices": [{"message": {"content": '{"ok":true}'}}]}

    class Client:
        def __init__(self, **kwargs):
            assert kwargs.get("trust_env") is False
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, **kwargs):
            calls.append((url, kwargs["headers"].get("Authorization")))
            return Reply(url)

    monkeypatch.setattr("app.services.llm_client.httpx.AsyncClient", Client)
    monkeypatch.setattr(LLMClient._call_llm_one.retry, "wait", wait_none())
    monkeypatch.setattr(settings, "ALLOW_EXTERNAL_API", False)
    primary = {**route("primary"), "api_base": "http://127.0.0.1:11434/v1"}
    backup = {**route("backup"), "api_base": "http://127.0.0.1:11435/v1"}
    primary["fallbacks"] = [backup]
    token = runtime_context.set(primary)
    try:
        metadata = {}
        assert await LLMClient()._call_llm("system", "synthetic", metadata_out=metadata) == {"ok": True}
        assert len(calls) == 4
        assert all("11434" in url and key == "Bearer secret-primary" for url, key in calls[:3])
        assert "11435" in calls[-1][0] and calls[-1][1] == "Bearer secret-backup"
        assert metadata["actual_model"] == "backup" and metadata["fallback_index"] == 1
    finally:
        runtime_context.reset(token)


@pytest.mark.asyncio
async def test_fallback_on_schema_invalid_result(monkeypatch):
    from app.services.llm_client import JD_Criteria_Schema
    client = LLMClient()
    async def fake_once(*args, **kwargs):
        if runtime_context.get()["model_name"] == "primary":
            return {"invalid": True}
        return {"requisition_id": "synthetic", "job_title": "backend", "criteria": []}
    monkeypatch.setattr(client, "_call_llm_one", fake_once)
    primary = route("primary")
    primary["fallbacks"] = [route("backup")]
    token = runtime_context.set(primary)
    try:
        metadata = {}
        result = await client._call_llm("system", "synthetic", metadata_out=metadata,
                                        output_validator=JD_Criteria_Schema.model_validate)
        assert result["requisition_id"] == "synthetic"
        assert metadata["fallback_index"] == 1
    finally:
        runtime_context.reset(token)
