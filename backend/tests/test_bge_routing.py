from __future__ import annotations

import asyncio
import copy

from app.core.config import settings
from app.services.ai_config import runtime_context, runtime_snapshot
from app.services.bge_routes import route_index_version
from app.services.embedding import EmbeddingError, semantic_config_fingerprint
from app.workers.processor import ProcessingWorker


class FailedDb:
    class Nested:
        def __enter__(self): return None
        def __exit__(self, *args): return False
    def begin_nested(self): return self.Nested()
    def execute(self, *args, **kwargs): raise RuntimeError("test-only pgvector unavailable")


class FakeProvider:
    model = "same-bge-model"
    dimension = 2
    def __init__(self, name, fail_query=False):
        self.name = name
        self.fail_query = fail_query
        self.calls = []
    async def embed(self, texts, *, kind="document"):
        self.calls.append(kind)
        if kind == "query" and self.fail_query:
            raise EmbeddingError("test failure")
        # Different vector spaces ensure a mixed query/document pair would fail.
        return [[1.0, 0.0] if self.name == "primary" else [0.0, 1.0] for _ in texts]


def test_managed_bge_fallback_recomputes_documents_and_queries_without_mixing(monkeypatch):
    import app.workers.processor as module
    monkeypatch.setattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", False)
    monkeypatch.setattr(settings, "ALLOW_MANAGED_BGE_ROUTING", False)
    primary, backup = FakeProvider("primary", True), FakeProvider("backup")
    routes = [
        {"config_id": "primary", "api_key_configured": True, "config": {"model_name": "same", "top_k": 5, "min_similarity": .5}},
        {"config_id": "backup", "api_key_configured": True, "config": {"model_name": "same", "top_k": 5, "min_similarity": .5}},
    ]
    monkeypatch.setattr(module, "bge_pin_is_current", lambda db, chain: True)
    monkeypatch.setattr(module, "provider_for_pinned_route", lambda db, route: primary if route['config_id'] == 'primary' else backup)
    assert route_index_version(routes[0]) != route_index_version(routes[1])
    token = runtime_context.set({"bge_chain": {"route_set_id": "set", "routes": routes}})
    data = {"chunks": [{"chunk_id": "c", "text": "Synthetic CV", "char_start": 0, "char_end": 12}],
            "fallback_chunks": {"criterion": []}, "requirement_specs": {"criterion": {"name": "Test"}}}
    loop = asyncio.new_event_loop()
    try:
        result = ProcessingWorker.__new__(ProcessingWorker)._semantic_fallback_chunks(
            FailedDb(), loop, application_id="a", document_id="d", deterministic_result=data,
            unresolved_criteria=[{"criterion_id": "criterion"}])
        assert primary.calls == ["document", "query"]
        assert backup.calls == ["document", "query"]
        assert result["criterion"][0]["chunk_id"] == "c"
        assert data["_semantic_route_used"]["route_config_id"] == "backup"
        assert data["_semantic_route_used"]["fallback_index"] == 1
        assert semantic_config_fingerprint()["managed_routes"]["route_set_id"] == "set"
        assert all("api_key" not in route for route in runtime_snapshot(runtime_context.get())["bge_chain"]["routes"])
    finally:
        loop.close()
        runtime_context.reset(token)


def test_route_cache_namespace_changes_with_config_and_id():
    base = {"config_id": "a", "config": {"model_name": "bge", "api_base": "https://one.test/v1"}}
    other = copy.deepcopy(base)
    other["config"]["api_base"] = "https://two.test/v1"
    assert route_index_version(base) != route_index_version(other)
    other = copy.deepcopy(base)
    other["config_id"] = "b"
    assert route_index_version(base) != route_index_version(other)


def test_gates_and_all_provider_failures_leave_only_lexical(monkeypatch):
    import app.workers.processor as module
    monkeypatch.setattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", True)
    primary, backup = FakeProvider("primary", True), FakeProvider("backup", True)
    routes = [{"config_id": name, "config": {"model_name": "same"}} for name in ("a", "b")]
    monkeypatch.setattr(module, "provider_for_pinned_route", lambda db, route: primary if route['config_id'] == 'a' else backup)
    monkeypatch.setattr(module, "bge_pin_is_current", lambda db, chain: False)
    data = {"chunks": [{"chunk_id": "c", "text": "synthetic"}], "fallback_chunks": {"x": [{"chunk_id": "lexical"}]}}
    token = runtime_context.set({"bge_chain": {"routes": routes}})
    loop = asyncio.new_event_loop()
    try:
        worker = ProcessingWorker.__new__(ProcessingWorker)
        args = dict(application_id="a", document_id="d", deterministic_result=data, unresolved_criteria=[{"criterion_id": "x"}])
        assert worker._semantic_fallback_chunks(FailedDb(), loop, **args) == data['fallback_chunks']
        assert not primary.calls and not backup.calls
        monkeypatch.setattr(module, "bge_pin_is_current", lambda db, chain: True)
        assert worker._semantic_fallback_chunks(FailedDb(), loop, **args) == data['fallback_chunks']
        assert primary.calls == ["document", "query"] and backup.calls == ["document", "query"]
        assert data['_semantic_route_used']['status'] == 'LEXICAL_FALLBACK'
    finally:
        runtime_context.reset(token)
        loop.close()


def test_embedding_endpoint_policy_blocks_external_without_gate(monkeypatch):
    import socket
    import pytest
    from app.services.embedding import BGEHttpEmbeddingProvider
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))])
    monkeypatch.setattr(settings, 'ALLOW_EXTERNAL_API', False)
    with pytest.raises(EmbeddingError):
        BGEHttpEmbeddingProvider(api_base='https://example.test/v1')._check_endpoint_policy()
    monkeypatch.setattr(settings, 'ALLOW_EXTERNAL_API', True)
    with pytest.raises(EmbeddingError):
        BGEHttpEmbeddingProvider(api_base='http://example.test/v1')._check_endpoint_policy()
    BGEHttpEmbeddingProvider(api_base='https://example.test/v1')._check_endpoint_policy()


def test_snapshot_strips_pinned_route_secret():
    runtime = {'bge_chain': {'routes': [{'config_id': 'test', 'api_key': 'DO_NOT_PERSIST', 'api_key_ciphertext': 'CIPHER', 'config': {}}]}}
    snapshot = runtime_snapshot(runtime)
    assert 'DO_NOT_PERSIST' not in str(snapshot) and 'CIPHER' not in str(snapshot)
    assert snapshot['bge_chain']['routes'][0]['api_key_configured'] is True


def test_endpoint_policy_checked_per_route_before_synthetic_transport(monkeypatch):
    import httpx
    import socket
    import app.workers.processor as module
    from app.services.embedding import BGEHttpEmbeddingProvider
    monkeypatch.setattr(settings, 'SEMANTIC_RETRIEVAL_ENABLED', True)
    monkeypatch.setattr(settings, 'ALLOW_MANAGED_BGE_ROUTING', True)
    monkeypatch.setattr(settings, 'ALLOW_EXTERNAL_API', False)
    def dns(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8' if host == 'public.test' else '127.0.0.1', 443))]
    monkeypatch.setattr(socket, 'getaddrinfo', dns)
    requests = []
    def handler(request):
        requests.append(request.url.host)
        import json
        payload = json.loads(request.content)
        return httpx.Response(200, json={'data': [{'index': i, 'embedding': [1.0, 0.0] + [0.0] * 1022} for i, _ in enumerate(payload['input'])]})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    routes = [{'config_id': name, 'config': {'api_base': base, 'model_name': 'test', 'min_similarity': 0}}
              for name, base in [('primary', 'https://public.test/v1'), ('backup', 'http://internal.test/v1')]]
    monkeypatch.setattr(module, 'bge_pin_is_current', lambda db, chain: True)
    monkeypatch.setattr(module, 'provider_for_pinned_route', lambda db, route: BGEHttpEmbeddingProvider(
        api_base=route['config']['api_base'], api_key='', model='test', dimension=1024))
    data = {'chunks': [{'chunk_id': 'c', 'text': 'synthetic'}], 'fallback_chunks': {'x': []}}
    token = runtime_context.set({'bge_chain': {'route_set_id': 'synthetic', 'routes': routes}})
    loop = asyncio.new_event_loop()
    try:
        ProcessingWorker.__new__(ProcessingWorker)._semantic_fallback_chunks(FailedDb(), loop,
            application_id='a', document_id='d', deterministic_result=data, unresolved_criteria=[{'criterion_id': 'x', 'name': 'test'}])
        assert requests == ['internal.test', 'internal.test']
        assert data['_semantic_route_used']['route_config_id'] == 'backup'
    finally:
        loop.close()
        runtime_context.reset(token)


def test_missing_control_database_fails_closed_even_with_old_env_flags(monkeypatch):
    import app.workers.processor as module
    monkeypatch.setattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", True)
    monkeypatch.setattr(settings, "ALLOW_MANAGED_BGE_ROUTING", True)
    monkeypatch.setattr(module, "provider_for_pinned_route", lambda *args: (_ for _ in ()).throw(AssertionError("must not call provider")))
    data = {"chunks": [{"chunk_id": "c", "text": "synthetic"}], "fallback_chunks": {"x": []}}
    token = runtime_context.set({"bge_chain": {"route_set_id": "set", "routes": [{"config_id": "a", "config": {}}]}})
    loop = asyncio.new_event_loop()
    try:
        result = ProcessingWorker.__new__(ProcessingWorker)._semantic_fallback_chunks(
            FailedDb(), loop, application_id="a", document_id="d", deterministic_result=data,
            unresolved_criteria=[{"criterion_id": "x"}])
        assert result == data["fallback_chunks"]
        assert data["_semantic_route_used"]["status"] == "LEXICAL_FALLBACK"
    finally:
        loop.close()
        runtime_context.reset(token)
