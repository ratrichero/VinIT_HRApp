"""Synthetic-only reranker tests; no network or candidate data."""
import asyncio
import json

import httpx
import pytest

from app.core.config import settings
from app.services.ai_config import runtime_context
from app.services import reranker as module
from app.workers.processor import ProcessingWorker

ACCOUNT = 'a' * 32
BASE = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/v1'
ENDPOINT = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/{module.MODEL}'
CHUNKS = [{'chunk_id': '1', 'text': 'Synthetic Python contact fake@example.com'},
          {'chunk_id': '2', 'text': 'Synthetic distributed systems'}]


def test_strict_fixed_endpoint():
    assert module.cloudflare_rerank_endpoint(BASE) == ENDPOINT
    for bad in [BASE.replace('https:', 'http:'), BASE + '?x=y', BASE.replace('api.cloudflare.com', 'api.cloudflare.com.evil.test'), BASE + '/embeddings', BASE.replace(ACCOUNT, '../x')]:
        with pytest.raises((module.RerankerError, ValueError)):
            module.cloudflare_rerank_endpoint(bad)


def fake_client(monkeypatch, response):
    requests = []
    original = httpx.AsyncClient
    def client(**kwargs):
        assert kwargs['trust_env'] is False
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=response)
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(module.httpx, 'AsyncClient', client)
    return requests


def test_rerank_permutation_redacts_and_preserves_original(monkeypatch):
    requests = fake_client(monkeypatch, {'success': True, 'result': {'response': [{'id': 0, 'score': -2}, {'id': 1, 'score': 4}]}})
    result = asyncio.run(module.rerank(ENDPOINT, 'synthetic-key', 'Python fake@example.com', CHUNKS))
    assert result == [CHUNKS[1], CHUNKS[0]]
    payload = json.loads(requests[0].content)
    assert 'fake@example.com' not in json.dumps(payload)
    assert payload['top_k'] == 2 and len(payload['contexts']) == 2
    assert requests[0].headers['authorization'] == 'Bearer synthetic-key'


@pytest.mark.parametrize('rows', [[], [{'id': 0, 'score': 2}, {'id': 0, 'score': 1}],
    [{'id': 0, 'score': 2}, {'id': 2, 'score': 1}], [{'id': 0, 'score': float('nan')}, {'id': 1, 'score': 2}],
    [{'id': True, 'score': 2}, {'id': 1, 'score': 2}], [{'id': 0, 'score': '2'}, {'id': 1, 'score': 2}]])
def test_invalid_response_rejected(monkeypatch, rows):
    # MockTransport's JSON serializer disallows NaN; pass as raw response instead.
    original = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=json.dumps({'success': True, 'result': {'response': rows}}))), **kwargs))
    with pytest.raises(module.RerankerError):
        asyncio.run(module.rerank(ENDPOINT, 'synthetic-key', 'query', CHUNKS))


def test_pin_checks_selection_and_external_gate(monkeypatch):
    pin = {'selection_id': 'a', 'bge_config_id': 'b', 'model_name': module.MODEL}
    monkeypatch.setattr(module, 'current_reranker', lambda db: pin)
    monkeypatch.setattr(module, 'load_bge_route', lambda *a, **k: {'config': {'api_base': BASE}, 'api_key': 'key'})
    monkeypatch.setattr(settings, 'ALLOW_EXTERNAL_API', False)
    with pytest.raises(module.RerankerError): module.provider_for_pin(None, pin)
    monkeypatch.setattr(settings, 'ALLOW_EXTERNAL_API', True)
    assert module.provider_for_pin(None, pin) == (ENDPOINT, 'key')
    monkeypatch.setattr(module, 'current_reranker', lambda db: None)
    with pytest.raises(module.RerankerError): module.provider_for_pin(None, pin)


def test_worker_failure_keeps_order_and_off_never_calls(monkeypatch):
    import app.workers.processor as worker
    class DB:
        def begin_nested(self):
            from contextlib import nullcontext
            return nullcontext()
    monkeypatch.setattr(worker, 'provider_for_pin', lambda *args: (_ for _ in ()).throw(RuntimeError('fail')))
    w = ProcessingWorker.__new__(ProcessingWorker)
    loop = asyncio.new_event_loop()
    try:
        token = runtime_context.set({'reranker': {'selection_id': 'id'}})
        result, stats = w._rerank_fallback_chunks(DB(), loop, {'c': CHUNKS}, [{'criterion_id': 'c', 'name': 'Python'}], {})
        assert result['c'] == CHUNKS and stats == {'attempted': 1, 'succeeded': 0, 'failed': 1}
        runtime_context.reset(token)
        token = runtime_context.set({'reranker': {'status': 'OFF'}})
        _, stats = w._rerank_fallback_chunks(DB(), loop, {'c': CHUNKS}, [{'criterion_id': 'c'}], {})
        assert stats['attempted'] == 0
        runtime_context.reset(token)
    finally:
        loop.close()


def test_worker_success_only_changes_chunk_order(monkeypatch):
    import app.workers.processor as worker
    from contextlib import nullcontext
    class DB:
        def begin_nested(self): return nullcontext()
    calls = []
    monkeypatch.setattr(worker, 'provider_for_pin', lambda db, pin: (ENDPOINT, 'synthetic'))
    async def fake_rerank(endpoint, key, query, chunks):
        calls.append((endpoint, query))
        return list(reversed(chunks))
    monkeypatch.setattr(worker, 'rerank', fake_rerank)
    token = runtime_context.set({'reranker': {'selection_id': 'synthetic'}})
    loop = asyncio.new_event_loop()
    try:
        data = {'criterion': list(CHUNKS), 'other': [{'text': 'single chunk'}]}
        result, stats = ProcessingWorker.__new__(ProcessingWorker)._rerank_fallback_chunks(
            DB(), loop, data, [{'criterion_id': 'criterion', 'name': 'Python'}, {'criterion_id': 'other'}], {})
        assert result['criterion'] == list(reversed(CHUNKS)) and data['criterion'] == CHUNKS
        assert result['other'] == data['other'] and calls[0][1] == 'Python'
        assert stats == {'attempted': 1, 'succeeded': 1, 'failed': 0}
    finally:
        runtime_context.reset(token)
        loop.close()
