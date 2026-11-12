"""Cloudflare evidence reranker. Scores reorder only; never create findings."""
from __future__ import annotations

import asyncio
import math
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text

from app.services.bge_routes import load_bge_route
from app.core.config import settings
from app.services.embedding import BGEHttpEmbeddingProvider
from app.services.redaction import redact_text

MODEL = '@cf/baai/bge-reranker-base'
# Bound egress and latency; Cloudflare may truncate further at its token limit.
MAX_QUERY_CHARS = 800
MAX_CONTEXT_CHARS = 1500
MAX_CONTEXTS = 5
TIMEOUT_SECONDS = 15.0
_ACCOUNT_PATH = re.compile(r'^/client/v4/accounts/([a-fA-F0-9]{32})/ai/v1/?$')


class RerankerError(RuntimeError):
    """Invalid reranker config or response, or provider unavailable."""


def cloudflare_rerank_endpoint(base: str) -> str:
    parsed = urlsplit(base)
    match = _ACCOUNT_PATH.fullmatch(parsed.path)
    if (parsed.scheme != 'https' or parsed.hostname != 'api.cloudflare.com'
            or parsed.port not in (None, 443) or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not match):
        raise RerankerError('A Cloudflare Workers AI account /ai/v1 URL is required')
    return f'https://api.cloudflare.com/client/v4/accounts/{match.group(1)}/ai/run/{MODEL}'


def current_reranker(db) -> dict[str, Any] | None:
    row = db.execute(text("""
        SELECT selection_id::text AS selection_id, bge_config_id::text AS bge_config_id, model_name
        FROM app_private.reranker_selections WHERE current
    """)).mappings().first()
    return dict(row) if row else None


def provider_for_pin(db, pinned: dict[str, Any]) -> tuple[str, str]:
    """Recheck selection and hydrate the credential only for the pinned account."""
    if not isinstance(pinned, dict) or pinned.get('model_name') != MODEL or current_reranker(db) != pinned:
        raise RerankerError('Reranker selection is unavailable or changed')
    route = load_bge_route(db, pinned['bge_config_id'], include_secret=True)
    base = route['config'].get('api_base')
    if not isinstance(base, str) or not route.get('api_key'):
        raise RerankerError('Cloudflare credential unavailable')
    endpoint = cloudflare_rerank_endpoint(base)
    # Same independent worker network policy as BGE; never inherit proxies.
    if not settings.ALLOW_EXTERNAL_API:
        raise RerankerError('External API disabled')
    BGEHttpEmbeddingProvider(api_base=endpoint)._check_endpoint_policy()
    return endpoint, route['api_key']


async def rerank(endpoint: str, api_key: str, query: str, chunks: list[dict]) -> list[dict]:
    """Reorder an exact permutation, preserving original chunks and provenance.

    Only bounded, best-effort redacted text leaves the process. Cloudflare
    outputs raw relevance logits, not calibrated probabilities. Any invalid or
    partial response is rejected and the caller retains the original ordering.
    """
    if not 2 <= len(chunks) <= MAX_CONTEXTS:
        return chunks
    query_text = redact_text(query).strip()[:MAX_QUERY_CHARS]
    contexts = [redact_text(str(item.get('text') or '')).strip()[:MAX_CONTEXT_CHARS] for item in chunks]
    if not query_text or any(not value for value in contexts):
        raise RerankerError('Empty reranker input')
    payload = {'query': query_text, 'contexts': [{'text': value} for value in contexts], 'top_k': len(contexts)}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, trust_env=False) as client:
            response = await asyncio.wait_for(
                client.post(endpoint, json=payload, headers={'Authorization': f'Bearer {api_key}'}),
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError, asyncio.TimeoutError) as exc:
        raise RerankerError(f'Reranker request failed: {type(exc).__name__}') from None
    result = data.get('result') if isinstance(data, dict) and data.get('success') is True else None
    rows = result.get('response') if isinstance(result, dict) else None
    if not isinstance(rows, list) or len(rows) != len(contexts):
        raise RerankerError('Invalid reranker response')
    scores: dict[int, float] = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get('id')) is not int or type(row.get('score')) not in (int, float):
            raise RerankerError('Invalid reranker row')
        idx, score = row['id'], float(row['score'])
        if idx < 0 or idx >= len(contexts) or idx in scores or not math.isfinite(score):
            raise RerankerError('Invalid reranker index or score')
        scores[idx] = score
    return [chunks[idx] for idx in sorted(scores, key=lambda idx: (-scores[idx], idx))]
