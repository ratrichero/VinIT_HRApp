from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.admin import AIConfigUpdateRequest
from app.services.llm_usage import usage_estimate


def test_price_and_token_estimate_with_unknown_and_zero():
    prices = {'input_price_per_million_usd': '0.15', 'output_price_per_million_usd': '0.6'}
    result = usage_estimate(prices, {'usage': {'prompt_tokens': 1000000, 'completion_tokens': 500000}})
    assert result['estimated_cost_usd'] == Decimal('0.45')
    assert usage_estimate({**prices, 'model_name': 'expected'}, {'model': 'other', 'usage': {'prompt_tokens': 1, 'completion_tokens': 1}})['estimated_cost_usd'] is None
    assert usage_estimate(prices, {'usage': {'prompt_tokens': 1}})['estimated_cost_usd'] is None
    assert usage_estimate({}, {'usage': {'prompt_tokens': 1, 'completion_tokens': 1}})['estimated_cost_usd'] is None
    assert usage_estimate({'input_price_per_million_usd': 0, 'output_price_per_million_usd': 0}, {'usage': {'input_tokens': 1, 'output_tokens': 1}})['estimated_cost_usd'] == 0
    for invalid in (True, -1, 1.2, '10', 1_000_000_001):
        assert usage_estimate(prices, {'usage': {'prompt_tokens': invalid, 'completion_tokens': 1}})['estimated_cost_usd'] is None


@pytest.mark.parametrize('price', ['-1', 'NaN', 'Infinity', '1000001', '0.0000001'])
def test_price_validation(price):
    with pytest.raises(ValidationError):
        AIConfigUpdateRequest(provider='compatible', provider_name='synthetic', model_name='synthetic',
                              api_base='https://example.test/v1', input_price_per_million_usd=price)


@pytest.mark.asyncio
async def test_usage_captured_per_http_attempt_and_failure_is_unknown(monkeypatch):
    import httpx
    from tenacity import wait_none
    from app.services.ai_config import runtime_context
    from app.services.llm_client import LLMClient
    import app.services.llm_client as llm
    from app.core.config import settings
    calls, records = [], []
    class Client:
        def __init__(self, **kwargs): assert kwargs['trust_env'] is False
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, **kwargs):
            calls.append(url)
            request = httpx.Request('POST', url)
            if len(calls) == 1:
                return httpx.Response(503, request=request)
            return httpx.Response(200, request=request, json={'usage': {'prompt_tokens': 100, 'completion_tokens': 25}, 'choices': [{'message': {'content': '{"ok":true}'}}]})
    monkeypatch.setattr(llm.httpx, 'AsyncClient', Client)
    monkeypatch.setattr(llm, 'record_attempt', lambda runtime, task, success, data=None: records.append((success, usage_estimate(runtime, data))))
    monkeypatch.setattr(LLMClient._call_llm_one.retry, 'wait', wait_none())
    monkeypatch.setattr(settings, 'ALLOW_EXTERNAL_API', False)
    runtime = {'provider': 'compatible', 'provider_name': 'synthetic', 'model_name': 'synthetic',
               'api_base': 'http://127.0.0.1:11434/v1', 'temperature_default': 0,
               'input_price_per_million_usd': .15, 'output_price_per_million_usd': .6}
    token = runtime_context.set(runtime)
    try:
        assert await LLMClient()._call_llm('system', 'synthetic') == {'ok': True}
        assert len(records) == 2 and not records[0][0] and records[0][1]['estimated_cost_usd'] is None
        assert records[1][0] and records[1][1]['estimated_cost_usd'] == Decimal('0.00003')
    finally:
        runtime_context.reset(token)
