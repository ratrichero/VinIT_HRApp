"""Embedding providers for semantic CV retrieval.

Production semantic retrieval is designed around a BGE model served over
an OpenAI-compatible ``/embeddings`` endpoint (for example TEI, Xinference
or a vLLM server).  The worker never lets an embedding failure fail an
assessment: callers catch :class:`EmbeddingError` and keep the lexical
fallback chunks.

``hash`` is a deterministic local provider for tests and offline smoke
checks.  It is *not* BGE and must never be described as a semantic-quality
model; it only proves the pgvector/retrieval plumbing end to end.
"""

from __future__ import annotations

import hashlib
import ipaddress
import math
import socket
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.services import langfuse_observability as observability
from app.services.deterministic_matching import normalize_text


class EmbeddingError(RuntimeError):
    """The embedding provider is unavailable or returned invalid vectors."""


def normalize_vector(vector: list[float]) -> list[float]:
    """Return a unit vector, rejecting empty/non-finite input."""
    values = [float(value) for value in vector]
    if not values or not all(math.isfinite(value) for value in values):
        raise EmbeddingError("Embedding vector is empty or non-finite")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise EmbeddingError("Embedding vector has zero norm")
    return [value / norm for value in values]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise EmbeddingError("Embedding dimensions do not match")
    return sum(a * b for a, b in zip(normalize_vector(left), normalize_vector(right), strict=True))


def chunk_text_sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def vector_literal(vector: list[float]) -> str:
    """Format a vector for a pgvector cast without scientific notation."""
    return "[" + ",".join(f"{value:.8f}" for value in normalize_vector(vector)) + "]"


def parse_vector_literal(value: Any) -> list[float]:
    """Parse a pgvector text value (or an already-decoded sequence)."""
    if isinstance(value, (list, tuple)):
        return normalize_vector([float(item) for item in value])
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            inner = text[1:-1].strip()
            if not inner:
                raise EmbeddingError("Embedding vector is empty")
            try:
                return normalize_vector([float(item.strip()) for item in inner.split(",")])
            except ValueError:
                raise EmbeddingError("Embedding vector is malformed") from None
    raise EmbeddingError("Embedding vector has an unsupported representation")


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimension: int

    async def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]:
        """Embed texts; ``kind`` is ``document`` or ``query``."""
        ...


class DisabledEmbeddingProvider:
    name = "disabled"

    def __init__(self) -> None:
        self.model = settings.EMBEDDING_MODEL
        self.dimension = int(settings.EMBEDDING_DIMENSION)

    async def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]:
        raise EmbeddingError("Embedding provider is disabled")


class HashEmbeddingProvider:
    """Deterministic token-hash vectors for tests/local plumbing checks."""

    name = "hash"

    def __init__(self, dimension: int | None = None) -> None:
        self.model = "local-hash-embedding"
        self.dimension = int(dimension or settings.EMBEDDING_DIMENSION)

    async def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            for token in [f"provider_kind_{kind}", *normalize_text(text).split()]:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
                # A second projection reduces collisions between common terms.
                index2 = int.from_bytes(digest[5:9], "big") % self.dimension
                vector[index2] += 0.5
            vectors.append(normalize_vector(vector) if any(vector) else [1.0] + [0.0] * (self.dimension - 1))
        return vectors


class BGEHttpEmbeddingProvider:
    """BGE served through an OpenAI-compatible embeddings endpoint."""

    name = "bge_http"

    def __init__(
        self,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.api_base = (api_base if api_base is not None else settings.EMBEDDING_API_BASE or "").rstrip("/")
        self.api_key = api_key if api_key is not None else settings.EMBEDDING_API_KEY
        self.model = model or settings.EMBEDDING_MODEL
        self.dimension = int(dimension or settings.EMBEDDING_DIMENSION)
        self.timeout_seconds = float(timeout_seconds or settings.EMBEDDING_TIMEOUT_SECONDS)

    def _check_endpoint_policy(self) -> None:
        if not self.api_base:
            raise EmbeddingError("EMBEDDING_API_BASE is not configured")
        parsed = urlsplit(self.api_base)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise EmbeddingError("Invalid embedding endpoint")
        if settings.ALLOW_EXTERNAL_API and parsed.scheme == "https":
            return
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(
                    parsed.hostname,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            }
            if addresses and all(
                ipaddress.ip_address(address).is_private
                or ipaddress.ip_address(address).is_loopback
                for address in addresses
            ):
                return
        except (OSError, ValueError):
            pass
        if settings.ALLOW_EXTERNAL_API:
            raise EmbeddingError("External embedding endpoints require HTTPS")
        raise EmbeddingError("External embedding endpoints are disabled by configuration")

    async def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]:
        if not texts:
            return []
        self._check_endpoint_policy()
        prepared = list(texts)
        instruction = (settings.EMBEDDING_QUERY_INSTRUCTION or "").strip()
        if kind == "query" and instruction:
            prepared = [f"{instruction}\n{text}" for text in prepared]
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "input": prepared}
        with observability.embedding(
            "hra.embedding.bge",
            model=self.model,
            metadata={
                "embedding_provider": self.name,
                "embedding_kind": kind,
                "embedding_index_version": settings.EMBEDDING_INDEX_VERSION,
                "text_count": len(texts),
                "total_characters": sum(len(text) for text in texts),
            },
            version=settings.EMBEDDING_INDEX_VERSION,
            input_data={"kind": kind, "text_count": len(texts)},
        ) as embedding_observation:
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
                    response = await client.post(
                        f"{self.api_base}/embeddings", json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise EmbeddingError(f"BGE embedding request failed: {type(exc).__name__}") from None
            rows = data.get("data") if isinstance(data, dict) else None
            if not isinstance(rows, list) or len(rows) != len(texts):
                raise EmbeddingError("BGE endpoint returned an unexpected embeddings payload")
            indices = [row.get("index") if isinstance(row, dict) else None for row in rows]
            if (any(type(index) is not int for index in indices)
                    or sorted(indices) != list(range(len(texts)))):
                raise EmbeddingError("BGE endpoint returned invalid embedding indices")
            vectors: list[list[float]] = []
            for row in sorted(rows, key=lambda item: item["index"]):
                vector = row.get("embedding") if isinstance(row, dict) else None
                if not isinstance(vector, list) or len(vector) != self.dimension:
                    raise EmbeddingError(
                        f"BGE vector dimension does not match configured dimension {self.dimension}")
                vectors.append(normalize_vector([float(value) for value in vector]))
            embedding_observation.update(output={
                "vector_count": len(vectors),
                "embedding_dimension": self.dimension,
            })
            return vectors


def get_embedding_provider() -> EmbeddingProvider:
    provider = (settings.EMBEDDING_PROVIDER or "disabled").strip().lower()
    if provider == "bge_http":
        return BGEHttpEmbeddingProvider()
    if provider == "hash":
        return HashEmbeddingProvider()
    return DisabledEmbeddingProvider()


def semantic_config_fingerprint() -> dict[str, Any] | None:
    """Semantic configuration pinned into fingerprints when enabled.

    Disabled deployments return ``None`` so turning semantic retrieval on
    (or changing its model) creates a new fingerprint cohort instead of
    reusing assessments produced without semantic candidates.
    """
    if not settings.SEMANTIC_RETRIEVAL_ENABLED:
        return None
    from app.services.ai_config import runtime_context
    runtime = runtime_context.get() or {}
    if settings.ALLOW_MANAGED_BGE_ROUTING or runtime.get("bge_chain") is not None:
        from app.services.ai_config import runtime_snapshot
        return {"enabled": True, "managed_allowed": bool(settings.ALLOW_MANAGED_BGE_ROUTING),
                "managed_routes": runtime_snapshot(runtime).get("bge_chain"),
                "query_instruction": settings.EMBEDDING_QUERY_INSTRUCTION or ""}
    provider = get_embedding_provider()
    return {
        "enabled": True,
        "provider": provider.name,
        "model": provider.model,
        "dimension": int(provider.dimension),
        "index_version": settings.EMBEDDING_INDEX_VERSION,
        "top_k": int(settings.SEMANTIC_TOP_K),
        "min_similarity": float(settings.SEMANTIC_MIN_SIMILARITY),
        "query_instruction": settings.EMBEDDING_QUERY_INSTRUCTION or "",
    }


def semantic_reuse_scope(operation_id: str, semantic_config: dict[str, Any] | None) -> dict[str, str] | None:
    """Avoid cross-operation reuse when actual provider/availability is unknown.

    Within the same operation, already completed assessments remain immutable on
    recovery; incomplete ones are retried. Vector cache reuse is unaffected.
    """
    if semantic_config is None:
        return None
    if not operation_id:
        raise ValueError("Semantic assessment reuse requires an operation id")
    return {"policy": "operation-scoped-v1", "operation_id": str(operation_id)}


def requirement_query_text(spec: Any) -> str:
    """Build the BGE query for one requirement spec (object or stored dict)."""
    if isinstance(spec, dict):
        name = str(spec.get("name") or "")
        kind = str(spec.get("kind") or "")
        raw_terms = spec.get("terms") or []
        terms: list[str] = []
        for term in raw_terms:
            if isinstance(term, dict):
                terms.append(str(term.get("label") or ""))
            else:
                terms.append(str(term or ""))
        extras = [
            str(spec.get(key) or "")
            for key in ("min_years", "required_degree_level", "required_ielts",
                        "required_toeic", "required_cefr")
        ]
    else:
        name = str(getattr(spec, "name", "") or "")
        kind = str(getattr(spec, "kind", "") or "")
        terms = [str(term.label) for term in getattr(spec, "terms", ()) or ()]
        extras = [
            str(getattr(spec, key, "") or "")
            for key in ("min_years", "required_degree_level", "required_ielts",
                        "required_toeic", "required_cefr")
        ]
    return " ".join(part for part in [kind, name, *terms, *extras] if part).strip()

