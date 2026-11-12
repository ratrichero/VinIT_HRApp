"""Unit tests for BGE/pgvector plumbing and offline LTR safety gates."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.services.embedding import (
    BGEHttpEmbeddingProvider,
    EmbeddingError,
    HashEmbeddingProvider,
    cosine_similarity,
    normalize_vector,
    parse_vector_literal,
    requirement_query_text,
    semantic_config_fingerprint,
    vector_literal,
)
from app.services.semantic_diagnostics import (
    get_semantic_diagnostics,
    record_semantic_run,
    reset_semantic_diagnostics,
)
from app.services.ltr import (
    LTRError,
    LTRModel,
    artifact_sha256,
    extract_ranking_features,
    train_ltr_model,
)
from app.services.matching import MatchingEngine
from app.services.semantic_retrieval import merge_candidate_chunks, retrieve_semantic_candidates
from app.workers.processor import ProcessingWorker


def test_semantic_fingerprint_is_disabled_by_default(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", False)
    assert semantic_config_fingerprint() is None


def test_semantic_fingerprint_changes_with_model(monkeypatch):
    from app.services.ai_config import runtime_context
    route = {"config_id": "a", "config": {"model_name": "BAAI/bge-m3"}}
    token = runtime_context.set({"bge_chain": {"route_set_id": "set", "routes": [route]}})
    try:
        import copy
        first = copy.deepcopy(semantic_config_fingerprint())
        route["config"]["model_name"] = "BAAI/bge-large-en-v1.5"
        assert semantic_config_fingerprint() != first
    finally:
        runtime_context.reset(token)


def test_normalize_and_cosine():
    assert normalize_vector([3, 4]) == pytest.approx([0.6, 0.8])
    assert cosine_similarity([1, 0], [1, 0]) == 1.0
    with pytest.raises(EmbeddingError):
        normalize_vector([0, 0])


def test_hash_embedding_is_deterministic_and_query_document_differ():
    provider = HashEmbeddingProvider(dimension=16)
    first = asyncio.run(provider.embed(["Python SQL"], kind="document"))[0]
    second = asyncio.run(provider.embed(["Python SQL"], kind="document"))[0]
    query = asyncio.run(provider.embed(["Python SQL"], kind="query"))[0]
    assert first == second
    assert first != query
    assert len(first) == 16




class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"data": [
            {"index": 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ]}


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, *, json, headers):
        assert url.endswith("/embeddings")
        assert json["model"] == "BAAI/bge-m3"
        assert len(json["input"]) == 2
        return _FakeResponse()


def test_bge_provider_reorders_response_rows_and_validates_dimension(monkeypatch):
    import app.services.embedding as embedding_module

    monkeypatch.setattr(embedding_module.httpx, "AsyncClient", _FakeAsyncClient)
    provider = BGEHttpEmbeddingProvider(
        api_base="https://embeddings.internal.example", model="BAAI/bge-m3", dimension=2)
    monkeypatch.setattr(provider, "_check_endpoint_policy", lambda: None)
    vectors = asyncio.run(provider.embed(["first", "second"], kind="document"))
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]

    bad_provider = BGEHttpEmbeddingProvider(
        api_base="https://embeddings.internal.example", model="BAAI/bge-m3", dimension=3)
    monkeypatch.setattr(bad_provider, "_check_endpoint_policy", lambda: None)
    with pytest.raises(EmbeddingError, match="dimension"):
        asyncio.run(bad_provider.embed(["first", "second"], kind="document"))


def test_bge_provider_requires_configured_endpoint():
    provider = BGEHttpEmbeddingProvider(api_base="", model="BAAI/bge-m3", dimension=2)
    with pytest.raises(EmbeddingError, match="not configured"):
        asyncio.run(provider.embed(["text"], kind="document"))


def test_parse_vector_literal_round_trip():
    vector = parse_vector_literal(vector_literal([3.0, 4.0]))
    assert vector == pytest.approx([0.6, 0.8])
    with pytest.raises(EmbeddingError):
        parse_vector_literal("not-a-vector")


def test_semantic_diagnostics_distinguish_configuration_and_fallback(monkeypatch):
    from app.core.config import settings

    reset_semantic_diagnostics()
    monkeypatch.setattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", False)
    assert get_semantic_diagnostics()["state"] == "DISABLED"

    monkeypatch.setattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", True)
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "disabled")
    diagnostics = get_semantic_diagnostics()
    assert diagnostics["state"] == "MISCONFIGURED"
    assert diagnostics["issues"]

    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "bge_http")
    monkeypatch.setattr(settings, "EMBEDDING_API_BASE", "https://embeddings.example")
    assert get_semantic_diagnostics()["state"] == "READY_UNVERIFIED"

    record_semantic_run(outcome="PROVIDER_FALLBACK", error_type="EmbeddingError")
    diagnostics = get_semantic_diagnostics()
    assert diagnostics["state"] == "DEGRADED_FALLBACK"
    assert diagnostics["runtime"]["provider_failures"] == 1
    reset_semantic_diagnostics()


def test_requirement_query_text_from_structured_spec():
    query = requirement_query_text({
        "name": "Backend experience",
        "kind": "experience",
        "terms": [{"label": "Python"}, "PostgreSQL"],
        "min_years": 3,
    })
    assert "Python" in query and "PostgreSQL" in query and "3" in query


def test_semantic_retrieval_and_merge_prefer_dual_source_chunks():
    chunks = [
        {"chunk_id": "c1", "text": "Python", "page_number": 1, "char_start": 0, "char_end": 6},
        {"chunk_id": "c2", "text": "Cooking", "page_number": 1, "char_start": 7, "char_end": 14},
    ]
    semantic = retrieve_semantic_candidates(
        [1.0, 0.0], chunks, [[1.0, 0.0], [0.0, 1.0]], min_similarity=0.5)
    assert [chunk["chunk_id"] for chunk in semantic] == ["c1"]
    merged = merge_candidate_chunks(
        [{"chunk_id": "c1", "retrieval_source": "LEXICAL"}], semantic, limit=2)
    assert merged[0]["retrieval_source"] == "LEXICAL+SEMANTIC"
    assert merged[0]["semantic_similarity"] == 1.0




class _FakeDb:
    class _Nested:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    def begin_nested(self):
        return self._Nested()

    def execute(self, *args, **kwargs):
        raise RuntimeError("pgvector unavailable in unit test")


def test_worker_semantic_fallback_uses_in_memory_when_pgvector_fails(monkeypatch):
    import app.workers.processor as processor_module
    from app.core.config import settings

    monkeypatch.setattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", True)
    monkeypatch.setattr(settings, "SEMANTIC_MIN_SIMILARITY", 0.1)
    monkeypatch.setattr(settings, "SEMANTIC_TOP_K", 5)
    from app.services.ai_config import runtime_context
    monkeypatch.setattr(processor_module, "bge_pin_is_current", lambda db, chain: True)
    monkeypatch.setattr(processor_module, "provider_for_pinned_route", lambda db, route: HashEmbeddingProvider(dimension=32))
    token = runtime_context.set({"bge_chain": {"route_set_id": "test", "routes": [{"config_id": "test", "config": {}}]}})
    worker = ProcessingWorker.__new__(ProcessingWorker)
    loop = asyncio.new_event_loop()
    try:
        result = worker._semantic_fallback_chunks(
            _FakeDb(), loop,
            application_id="app-1", document_id="doc-1",
            deterministic_result={
                "chunks": [
                    {"chunk_id": "c1", "text": "Python SQL backend APIs",
                     "page_number": 1, "char_start": 0, "char_end": 25},
                    {"chunk_id": "c2", "text": "Cooking gardening travel",
                     "page_number": 1, "char_start": 26, "char_end": 50},
                ],
                "fallback_chunks": {"crit-1": []},
                "requirement_specs": {
                    "crit-1": {"name": "Backend", "kind": "skill",
                               "terms": [{"label": "Python"}, {"label": "SQL"}]},
                },
            },
            unresolved_criteria=[{"criterion_id": "crit-1"}],
        )
    finally:
        loop.close()
        runtime_context.reset(token)
    assert result["crit-1"][0]["chunk_id"] == "c1"
    assert result["crit-1"][0]["retrieval_source"] == "SEMANTIC"


class _CacheResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeEmbeddingCacheDb:
    class _Nested:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    def __init__(self):
        self.store = {}

    def begin_nested(self):
        return self._Nested()

    def execute(self, statement, params=None):
        params = params or {}
        sql = str(statement)
        if "embedding::text AS embedding_text" in sql:
            hashes = set(params["chunk_hashes"])
            return _CacheResult([
                {"chunk_id": chunk_id, "chunk_text_sha256": chunk_hash,
                 "embedding_text": vector_literal(vector)}
                for (chunk_id, chunk_hash), vector in self.store.items()
                if chunk_hash in hashes
            ])
        if "INSERT INTO app_private.cv_chunk_embeddings" in sql:
            self.store[(params["chunk_id"], params["chunk_hash"])] = parse_vector_literal(
                params["embedding"])
            return _CacheResult([])
        if "1 - (embedding <=>" in sql:
            query_vector = parse_vector_literal(params["query_vector"])
            rows = [
                {"chunk_id": chunk_id,
                 "similarity": sum(a * b for a, b in zip(query_vector, vector))}
                for (chunk_id, _), vector in self.store.items()
            ]
            rows.sort(key=lambda row: -row["similarity"])
            return _CacheResult(rows[:params["top_k"]])
        raise AssertionError(f"Unexpected SQL in cache test: {sql}")


class _CountingHashProvider(HashEmbeddingProvider):
    def __init__(self):
        super().__init__(dimension=32)
        self.document_batch_sizes = []

    async def embed(self, texts, *, kind="document"):
        if kind == "document":
            self.document_batch_sizes.append(len(texts))
        return await super().embed(texts, kind=kind)


def test_worker_semantic_embedding_cache_avoids_repeat_document_calls(monkeypatch):
    import app.workers.processor as processor_module
    from app.core.config import settings

    reset_semantic_diagnostics()
    monkeypatch.setattr(settings, "SEMANTIC_RETRIEVAL_ENABLED", True)
    monkeypatch.setattr(settings, "SEMANTIC_MIN_SIMILARITY", 0.1)
    monkeypatch.setattr(settings, "SEMANTIC_TOP_K", 5)
    provider = _CountingHashProvider()
    from app.services.ai_config import runtime_context
    monkeypatch.setattr(processor_module, "bge_pin_is_current", lambda db, chain: True)
    monkeypatch.setattr(processor_module, "provider_for_pinned_route", lambda db, route: provider)
    token = runtime_context.set({"bge_chain": {"route_set_id": "test", "routes": [{"config_id": "test", "config": {}}]}})
    worker = ProcessingWorker.__new__(ProcessingWorker)
    db = _FakeEmbeddingCacheDb()
    deterministic_result = {
        "chunks": [
            {"chunk_id": "c1", "text": "Python SQL backend APIs",
             "page_number": 1, "char_start": 0, "char_end": 25},
            {"chunk_id": "c2", "text": "Cooking gardening travel",
             "page_number": 1, "char_start": 26, "char_end": 50},
        ],
        "fallback_chunks": {"crit-1": []},
        "requirement_specs": {
            "crit-1": {"name": "Backend", "kind": "skill",
                       "terms": [{"label": "Python"}, {"label": "SQL"}]},
        },
    }
    loop = asyncio.new_event_loop()
    try:
        for _ in range(2):
            result = worker._semantic_fallback_chunks(
                db, loop, application_id="app-1", document_id="doc-1",
                deterministic_result=deterministic_result,
                unresolved_criteria=[{"criterion_id": "crit-1"}],
            )
            assert result["crit-1"][0]["chunk_id"] == "c1"
    finally:
        loop.close()
        runtime_context.reset(token)
    assert provider.document_batch_sizes == [2]
    diagnostics = get_semantic_diagnostics()
    assert diagnostics["runtime"]["cache_hits"] == 2
    assert diagnostics["runtime"]["cache_misses"] == 2
    assert diagnostics["runtime"]["cache_hit_rate"] == 0.5
    reset_semantic_diagnostics()


def _ltr_examples(group_count: int = 6, per_group: int = 8):
    examples = []
    for group in range(group_count):
        for rank in range(per_group):
            score = (per_group - rank) / per_group
            label = 3 if rank < 2 else 2 if rank < 4 else 1 if rank < 6 else 0
            examples.append({
                "group_id": f"position-{group}",
                "application_id": f"app-{group}-{rank}",
                "label": label,
                "features": {
                    "matching_score": score,
                    "evidence_coverage": score,
                    "mandatory_match_ratio": score,
                    "mandatory_verified_ratio": score,
                    "nice_to_have_match_ratio": score,
                    "llm_fallback_ratio": 0.0,
                    "verified_evidence_count": float(per_group - rank),
                    "strong_evidence_ratio": score,
                },
            })
    return examples




class _FakeMappingsResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _FakeRegistryDb:
    def __init__(self, row):
        self._row = row

    def execute(self, *args, **kwargs):
        return _FakeMappingsResult(self._row)


def test_worker_ltr_registry_requires_approval_for_active(monkeypatch):
    from app.core.config import settings

    artifact = train_ltr_model(
        _ltr_examples(group_count=20), min_examples=30, min_groups=5, epochs=80)
    monkeypatch.setattr(settings, "LTR_MODE", "ACTIVE")
    monkeypatch.setattr(settings, "LTR_MODEL_VERSION", artifact["model_version"])
    monkeypatch.setattr(settings, "LTR_MODEL_PATH", None)
    worker = ProcessingWorker.__new__(ProcessingWorker)

    draft = worker._load_ltr_model(_FakeRegistryDb({"artifact": artifact, "status": "DRAFT"}))
    assert draft is None
    approved = worker._load_ltr_model(_FakeRegistryDb({
        "artifact": artifact,
        "status": "APPROVED",
        "artifact_sha256": artifact_sha256(artifact),
    }))
    assert approved is not None
    assert approved.model_version == artifact["model_version"]


def test_ltr_artifact_hash_is_stable_and_worker_rejects_tampered_registry_artifact(monkeypatch):
    from app.core.config import settings

    artifact = train_ltr_model(
        _ltr_examples(group_count=20), min_examples=30, min_groups=5, epochs=80)
    reordered = dict(reversed(list(artifact.items())))
    assert artifact_sha256(artifact) == artifact_sha256(reordered)
    tampered = {**artifact, "weights": [0.0] * len(artifact["weights"])}
    assert artifact_sha256(tampered) != artifact_sha256(artifact)

    monkeypatch.setattr(settings, "LTR_MODE", "ACTIVE")
    monkeypatch.setattr(settings, "LTR_MODEL_VERSION", artifact["model_version"])
    monkeypatch.setattr(settings, "LTR_MODEL_PATH", None)
    worker = ProcessingWorker.__new__(ProcessingWorker)
    for missing_hash in (None, "", "   "):
        loaded = worker._load_ltr_model(_FakeRegistryDb({
            "artifact": artifact,
            "status": "APPROVED",
            "artifact_sha256": missing_hash,
        }))
        assert loaded is None
    loaded = worker._load_ltr_model(_FakeRegistryDb({
        "artifact": artifact,
        "status": "APPROVED",
        "artifact_sha256": "0" * 64,
    }))
    assert loaded is None


def test_worker_ltr_file_artifact_is_blocked_for_active_in_production(monkeypatch, tmp_path):
    import json

    from app.core.config import settings

    artifact = train_ltr_model(
        _ltr_examples(group_count=20), min_examples=30, min_groups=5, epochs=80)
    artifact_path = tmp_path / "ltr.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(settings, "LTR_MODE", "ACTIVE")
    monkeypatch.setattr(settings, "LTR_MODEL_VERSION", None)
    monkeypatch.setattr(settings, "LTR_MODEL_PATH", str(artifact_path))
    worker = ProcessingWorker.__new__(ProcessingWorker)

    monkeypatch.setattr(settings, "APP_ENV", "production")
    assert worker._load_ltr_model() is None

    monkeypatch.setattr(settings, "APP_ENV", "staging")
    assert worker._load_ltr_model() is not None


class _FakeAdminResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row

    def one(self):
        return self._row


class _FakeAdminDb:
    def __init__(self, row):
        self.row = row
        self.sql = []
        self.committed = False

    def execute(self, statement, params=None):
        sql = str(statement)
        self.sql.append(sql)
        if "FOR UPDATE" in sql:
            return _FakeAdminResult(self.row)
        if sql.strip().startswith("SELECT model_version, status, artifact_sha256"):
            return _FakeAdminResult({
                "model_version": self.row["model_version"],
                "status": "APPROVED",
                "artifact_sha256": artifact_sha256(self.row["artifact"]),
                "reviewed_by": "admin-1",
                "reviewed_at": "2026-11-07T00:00:00Z",
                "review_reason": "Đạt gate holdout",
                "approved_at": "2026-11-07T00:00:00Z",
            })
        return _FakeAdminResult()

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


def test_admin_ltr_review_records_approval_and_rejects_non_draft(monkeypatch):
    import app.api.admin as admin_module

    artifact = train_ltr_model(
        _ltr_examples(group_count=20), min_examples=30, min_groups=5, epochs=80)
    row = {
        "model_version": artifact["model_version"],
        "artifact": artifact,
        "metrics": artifact["metrics"],
        "data_sha256": artifact["training"]["data_sha256"],
        "artifact_sha256": artifact_sha256(artifact),
        "status": "DRAFT",
    }
    fake_db = _FakeAdminDb(row)
    monkeypatch.setattr(admin_module, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(admin_module, "_lock_active_admin", lambda db, user_id: None)

    result = admin_module._review_ltr_model(
        artifact["model_version"], "APPROVED", "Đạt gate holdout", {"user_id": "admin-1"})
    assert result["status"] == "APPROVED"
    assert fake_db.committed is True
    assert any("ltr_model_review_events" in sql for sql in fake_db.sql)
    assert any("audit_events" in sql for sql in fake_db.sql)

    row["status"] = "APPROVED"
    with pytest.raises(admin_module.HTTPException) as exc_info:
        admin_module._review_ltr_model(
            artifact["model_version"], "REJECTED", "Thử reject", {"user_id": "admin-1"})
    assert exc_info.value.status_code == 409


def test_ltr_training_and_group_holdout_metrics():
    artifact = train_ltr_model(_ltr_examples(), min_examples=30, min_groups=5, epochs=80)
    assert artifact["training"]["examples"] == 48
    assert artifact["training"]["groups"] == 6
    assert artifact["training"]["test_groups"] >= 1
    assert artifact["metrics"]["test"]["ndcg_at_10"] > 0.8
    model = LTRModel.from_artifact(artifact)
    high = model.score({"matching_score": 0.95, "evidence_coverage": 0.9})
    low = model.score({"matching_score": 0.1, "evidence_coverage": 0.1})
    assert high > low
    assert model.passes_gates(min_ndcg=0.7, min_pairwise=0.65)


def test_ltr_training_rejects_small_or_single_level_data():
    with pytest.raises(LTRError):
        train_ltr_model(_ltr_examples(group_count=2), min_examples=30, min_groups=5)
    one_level = _ltr_examples()
    for example in one_level:
        example["label"] = 1
    with pytest.raises(LTRError, match="relevance"):
        train_ltr_model(one_level, min_examples=30, min_groups=5)


def test_ltr_features_from_criterion_aggregates():
    features = extract_ranking_features(
        {"matching_score": 80, "evidence_coverage": 0.75, "matching_status": "MEETS_MANDATORY"},
        [
            {"outcome": "MATCH", "decision_source": "RULE",
             "evidence_strength": 0.9, "category": "MUST_HAVE"},
            {"outcome": "NO_MATCH", "decision_source": "LLM",
             "evidence_strength": 0.0, "category": "MUST_HAVE"},
            {"outcome": "MATCH", "decision_source": "RULE",
             "evidence_strength": 0.3, "category": "NICE_TO_HAVE"},
        ],
    )
    assert features["matching_score"] == pytest.approx(0.8)
    assert features["match_rate"] == pytest.approx(2 / 3)
    assert features["no_match_rate"] == pytest.approx(1 / 3)
    assert features["rule_decision_rate"] == pytest.approx(2 / 3)
    assert features["llm_decision_rate"] == pytest.approx(1 / 3)
    assert features["avg_evidence_strength"] == pytest.approx(0.4)
    assert features["mandatory_no_match"] == 1.0
    assert features["meets_mandatory"] == 1.0


def test_ltr_scoring_rejects_nonfinite_intermediate_values():
    artifact = train_ltr_model(_ltr_examples(), min_examples=30, min_groups=5, epochs=20)
    artifact['stds'][0] = 1e-320
    artifact['means'][0] = 0.0
    model = LTRModel(artifact)
    with pytest.raises(LTRError):
        model.score({'matching_score': 1.0})


def test_ltr_shadow_does_not_change_ranking_and_active_stays_inside_gate():
    engine = MatchingEngine()
    criteria = []
    applications = [
        {"application_id": "b", "latest_assessment": {
            "matching_status": "MEETS_MANDATORY", "matching_score": 80,
            "evidence_coverage": 0.9}},
        {"application_id": "a", "latest_assessment": {
            "matching_status": "MEETS_MANDATORY", "matching_score": 85,
            "evidence_coverage": 0.9}},
        {"application_id": "blocked", "latest_assessment": {
            "matching_status": "POSSIBLE_MISMATCH", "matching_score": 99,
            "evidence_coverage": 1.0}},
    ]
    scores = {"a": 0.1, "b": 0.9, "blocked": 1.0}
    shadow = engine.rank_applications(applications, criteria, ltr_scores=scores, ltr_mode="SHADOW")
    assert [item["application_id"] for item in shadow] == ["a", "b", "blocked"]
    assert shadow[1]["ltr_score"] == 0.9

    active = engine.rank_applications(applications, criteria, ltr_scores=scores, ltr_mode="ACTIVE")
    assert [item["application_id"] for item in active] == ["b", "a", "blocked"]
    assert active[-1]["application_id"] == "blocked"


def test_frontend_types_expose_ltr_score_contract():
    types_file = Path(__file__).resolve().parents[2] / "frontend/src/types/index.ts"
    assert "ltr_score?: number | null" in types_file.read_text(encoding="utf-8")


def test_ltr_rejects_nonfinite_or_nonpositive_scalers_and_invalid_metrics():
    import copy
    artifact = train_ltr_model(_ltr_examples(group_count=20), min_examples=30, min_groups=5, epochs=80)
    for field, value in (('means', float('nan')), ('weights', float('inf')), ('stds', 0.0), ('stds', -1.0)):
        invalid = copy.deepcopy(artifact)
        invalid[field][0] = value
        with pytest.raises(LTRError):
            LTRModel(invalid)
    for value in (float('nan'), float('inf'), 1.1, True):
        invalid = copy.deepcopy(artifact)
        invalid['metrics']['test']['ndcg_at_10'] = value
        assert not LTRModel(invalid).passes_gates(min_ndcg=.7, min_pairwise=.65)
