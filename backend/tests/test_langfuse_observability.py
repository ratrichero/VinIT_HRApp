import json

import pytest


class FakeSpan:
    def __init__(self, client, kwargs):
        self.client = client
        self.kwargs = kwargs
        self.updates = []
        self.scores = []
        self.trace_scores = []
        self.trace_id = "trace-123"

    def update(self, **kwargs):
        self.updates.append(kwargs)

    def score(self, **kwargs):
        self.scores.append(kwargs)

    def score_trace(self, **kwargs):
        self.trace_scores.append(kwargs)


class FakeContext:
    def __init__(self, span):
        self.span = span
        self.exit_exc = None

    def __enter__(self):
        return self.span

    def __exit__(self, exc_type, exc, traceback):
        self.exit_exc = exc_type
        return False


class FakeClient:
    def __init__(self):
        self.contexts = []
        self.scores = []
        self.flushed = False

    def start_as_current_observation(self, **kwargs):
        span = FakeSpan(self, kwargs)
        context = FakeContext(span)
        self.contexts.append(context)
        return context

    def create_score(self, **kwargs):
        self.scores.append(kwargs)

    def create_trace_id(self, seed=None):
        return "a" * 32

    def flush(self):
        self.flushed = True


@pytest.fixture(autouse=True)
def reset_observability(monkeypatch):
    from app.core.config import settings
    from app.services import langfuse_observability as observability

    observability.reset_observability_client(None)
    monkeypatch.setattr(settings, "LANGFUSE_ENABLED", False)
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", None)
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", None)
    monkeypatch.setattr(settings, "LANGFUSE_CAPTURE_CONTENT", False)
    monkeypatch.setattr(settings, "APP_ENV", "testing")
    yield
    observability.reset_observability_client()


def test_disabled_observability_is_noop():
    from app.services import langfuse_observability as observability

    with observability.generation("hra.llm.test", model="synthetic") as generation:
        generation.update(output={"status": "ok"})
        generation.score(name="evidence_coverage", value=0.5, data_type="NUMERIC")

    assert observability.get_client() is None
    assert observability.get_observability_status()["enabled"] is False


def test_sanitize_metadata_drops_secrets_and_candidate_content():
    from app.services.langfuse_observability import sanitize_metadata

    clean = sanitize_metadata({
        "operation_id": "op-1",
        "application_id": "app-1",
        "api_key": "secret-value",
        "cv_text": "candidate content",
        "cv_text_sha256": "a" * 64,
        "prompt_version": "matching-prompt-v2.0",
        "user_prompt": "do not export",
        "candidate_name": "Synthetic Person",
        "criterion_count": 3,
        "tags": ["staging", "synthetic"],
        "nested": {"hidden": True},
    })

    assert clean["operation_id"] == "op-1"
    assert clean["application_id"] == "app-1"
    assert clean["criterion_count"] == 3
    assert clean["cv_text_sha256"] == "a" * 64
    assert "prompt_version" not in clean  # prompt content/version keys stay out of generic metadata
    assert "api_key" not in clean
    assert "cv_text" not in clean
    assert "user_prompt" not in clean
    assert "candidate_name" not in clean
    assert "nested" not in clean


def test_content_summary_hashes_without_exporting_text():
    from app.services.langfuse_observability import content_summary

    summary = content_summary("Synthetic CV text that must not leave the backend")

    assert summary["content_capture"] == "disabled"
    assert summary["content_characters"] > 10
    assert "Synthetic CV" not in json.dumps(summary)


def test_content_capture_is_blocked_in_production(monkeypatch):
    from app.core.config import settings
    from app.services import langfuse_observability as observability

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "LANGFUSE_CAPTURE_CONTENT", True)

    summary = observability.content_summary("production content")

    assert observability.capture_content_enabled() is False
    assert summary["content_capture"] == "disabled"
    assert "production content" not in json.dumps(summary)


def test_fake_client_records_generation_and_observation_score():
    from app.services import langfuse_observability as observability

    fake = FakeClient()
    observability.reset_observability_client(fake)

    with observability.generation(
        "hra.llm.profile_extraction",
        model="synthetic-model",
        metadata={"application_id": "app-1", "api_key": "must-not-export"},
        version="profile-prompt-v2.0",
        input_data="synthetic input",
    ) as generation:
        generation.update(output={"status": "COMPLETED"})
        generation.score(name="evidence_coverage", value=0.75, data_type="NUMERIC")

    span = fake.contexts[0].span
    assert span.kwargs["as_type"] == "generation"
    assert span.kwargs["model"] == "synthetic-model"
    assert span.kwargs["metadata"] == {"application_id": "app-1"}
    assert span.kwargs["input"]["content_capture"] == "disabled"
    assert span.scores[0]["name"] == "evidence_coverage"
    assert span.scores[0]["value"] == 0.75


def test_fake_client_marks_generation_error_and_reraises():
    from app.services import langfuse_observability as observability

    fake = FakeClient()
    observability.reset_observability_client(fake)

    with pytest.raises(ValueError):
        with observability.generation("hra.llm.test", model="synthetic"):
            raise ValueError("synthetic failure")

    span = fake.contexts[0].span
    assert any(update.get("level") == "ERROR" for update in span.updates)
    assert fake.contexts[0].exit_exc is None  # never export exception message or traceback


def test_status_never_returns_keys_or_host(monkeypatch):
    from app.core.config import settings
    from app.services import langfuse_observability as observability

    monkeypatch.setattr(settings, "LANGFUSE_ENABLED", True)
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "pk-lf-synthetic")
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", "sk-lf-synthetic")
    monkeypatch.setattr(settings, "LANGFUSE_HOST", "https://langfuse.example.invalid")

    status = observability.get_observability_status()
    rendered = json.dumps(status)

    assert status["configured"] is True
    assert "pk-lf-synthetic" not in rendered
    assert "sk-lf-synthetic" not in rendered
    assert "langfuse.example.invalid" not in rendered


def test_llm_output_summary_contains_counts_not_reasoning_or_quotes():
    from app.services.llm_client import _parsed_output_summary, _usage_details

    summary = _parsed_output_summary({
        "findings": [
            {"outcome": "MATCH", "reasoning": "private reasoning", "evidence": {"verbatim_quote": "private quote"}},
            {"outcome": "UNCLEAR", "requires_verification": True},
        ]
    })
    rendered = json.dumps(summary)

    assert summary["findings_count"] == 2
    assert summary["finding_outcome_counts"] == {"MATCH": 1, "UNCLEAR": 1}
    assert "private reasoning" not in rendered
    assert "private quote" not in rendered
    assert _usage_details({"usage": {"prompt_tokens": 10, "completion_tokens": 5}}) == {
        "input": 10,
        "output": 5,
    }


def test_langfuse_requires_explicit_destination(monkeypatch):
    from app.core.config import settings
    from app.services import langfuse_observability as obs
    monkeypatch.setattr(settings, 'LANGFUSE_ENABLED', True)
    monkeypatch.setattr(settings, 'LANGFUSE_PUBLIC_KEY', 'synthetic')
    monkeypatch.setattr(settings, 'LANGFUSE_SECRET_KEY', 'synthetic')
    monkeypatch.setattr(settings, 'LANGFUSE_BASE_URL', None)
    monkeypatch.setattr(settings, 'LANGFUSE_HOST', None)
    assert not obs.observability_configured()
    assert obs._create_client() is None


def test_langfuse_context_failures_never_change_business_result():
    from app.services import langfuse_observability as obs
    class Context:
        def __init__(self, enter_fails=False): self.enter_fails = enter_fails
        def __enter__(self):
            if self.enter_fails: raise RuntimeError('enter')
            return FakeSpan(None, {})
        def __exit__(self, *args): raise RuntimeError('exit')
    class Client:
        def __init__(self, fail): self.fail = fail
        def start_as_current_observation(self, **kwargs): return Context(self.fail)
    for fail in (True, False):
        obs.reset_observability_client(Client(fail))
        with obs.generation('synthetic'):
            result = 42
        assert result == 42
        with pytest.raises(ValueError, match='business'):
            with obs.generation('synthetic'):
                raise ValueError('business')


def test_model_output_and_usage_do_not_export_arbitrary_provider_text():
    from app.services.llm_client import _parsed_output_summary, _safe_observability_usage
    secret = 'Synthetic private CV content'
    summary = _parsed_output_summary({
        secret: 1, 'criteria': [{'category': secret}], 'findings': [{'outcome': secret}],
    })
    assert secret not in json.dumps(summary)
    assert summary['criteria_category_counts'] == {'UNKNOWN': 1}
    assert summary['finding_outcome_counts'] == {'UNKNOWN': 1}
    usage = _safe_observability_usage({'usage': {'prompt_tokens': 5, 'completion_tokens': 2, secret: 10, 'total_tokens': -1}})
    assert usage == {'input': 5, 'output': 2}


def test_real_sdk_in_memory_traces_are_nested_and_do_not_capture_exception():
    # No network: a private in-memory OpenTelemetry exporter replaces OTLP.
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from app.services import langfuse_observability as obs
    exporter = InMemorySpanExporter()
    client = Langfuse(public_key='pk-lf-offline-test', secret_key='sk-lf-offline-test',
                      base_url='https://example.invalid', tracer_provider=TracerProvider(),
                      span_exporter=exporter, flush_at=1)
    obs.reset_observability_client(client)
    secret = 'synthetic confidential CV and secret'
    try:
        with obs.span('hra.worker.operation', metadata={'operation_id': 'synthetic-op'}):
            with pytest.raises(ValueError, match=secret):
                with obs.generation('hra.llm.synthetic', model='synthetic-model', input_data=secret) as generation:
                    generation.update(usage_details={'input': 4, 'output': 2})
                    raise ValueError(secret)
        # The worker executes async LLM code in a per-thread event loop.
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            async def child_work():
                with obs.generation('hra.llm.async', model='synthetic-model'):
                    return 1
            with obs.span('hra.worker.async'):
                assert loop.run_until_complete(child_work()) == 1
        finally:
            loop.close()
        client.flush()
        spans = {span.name: span for span in exporter.get_finished_spans()}
        assert set(spans) == {'hra.worker.operation', 'hra.llm.synthetic', 'hra.worker.async', 'hra.llm.async'}
        assert spans['hra.llm.async'].parent.span_id == spans['hra.worker.async'].context.span_id
        parent = spans['hra.worker.operation']
        child = spans['hra.llm.synthetic']
        assert child.parent.span_id == parent.context.span_id
        assert child.context.trace_id == parent.context.trace_id
        assert child.attributes['langfuse.observation.type'] == 'generation'
        assert child.attributes['langfuse.observation.model.name'] == 'synthetic-model'
        assert secret not in str(child.attributes) and secret not in str(child.events) and secret not in str(child.status.description)
        assert not any(event.name == 'exception' for event in child.events)
    finally:
        client.shutdown()
        obs.reset_observability_client(None)


@pytest.mark.asyncio
async def test_invalid_llm_json_still_traces_safe_provider_usage(monkeypatch):
    import httpx
    from tenacity import wait_none
    from app.core.config import settings
    from app.services import langfuse_observability as obs
    from app.services.ai_config import runtime_context
    from app.services.llm_client import LLMClient, LLMError
    import app.services.llm_client as llm
    class HttpClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, **kwargs):
            return httpx.Response(200, request=httpx.Request('POST', url), json={
                'usage': {'prompt_tokens': 8, 'completion_tokens': 3, 'synthetic sensitive key': 10},
                'choices': [{'message': {'content': 'not valid json'}}],
            })
    fake = FakeClient()
    obs.reset_observability_client(fake)
    monkeypatch.setattr(llm.httpx, 'AsyncClient', HttpClient)
    monkeypatch.setattr(llm, 'record_attempt', lambda *args, **kwargs: None)
    monkeypatch.setattr(LLMClient._call_llm_one.retry, 'wait', wait_none())
    monkeypatch.setattr(settings, 'ALLOW_EXTERNAL_API', False)
    token = runtime_context.set({'provider': 'compatible', 'model_name': 'synthetic', 'api_base': 'http://127.0.0.1:11434/v1', 'temperature_default': 0})
    try:
        with pytest.raises(LLMError): await LLMClient()._call_llm('system', 'synthetic')
        assert len(fake.contexts) == 3
        for ctx in fake.contexts:
            assert {'usage_details': {'input': 8, 'output': 3}} in ctx.span.updates
            assert 'synthetic sensitive key' not in str(ctx.span.updates)
            assert any(update.get('level') == 'ERROR' for update in ctx.span.updates)
    finally:
        runtime_context.reset(token)
