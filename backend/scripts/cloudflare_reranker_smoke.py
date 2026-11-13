#!/usr/bin/env python3
"""One synthetic-only Cloudflare reranker request; never changes runtime controls.

Run from backend/ using the same server-side .env as HRA. The active BGE
route set supplies the first matching Cloudflare account and encrypted key.
No API key, account ID, candidate/JD content, provider payload or provider
error text is printed. This is an isolated contract check, not an assessment.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Works both when checked out and when the script is copied to /tmp and run
# from backend/ without fetching/restarting an application process.
sys.path.insert(0, str(Path.cwd()))

from app.core.config import settings
from app.db.database import SessionLocal
from app.services.bge_routes import load_active_bge_chain, provider_for_pinned_route
from app.services.embedding import BGEHttpEmbeddingProvider
from app.services.reranker import cloudflare_rerank_endpoint, rerank

QUERY = 'Experience building Python services and maintaining APIs'
CHUNKS = [
    {'chunk_id': 'synthetic-1', 'text': 'Built Python API services and maintained automated tests.'},
    {'chunk_id': 'synthetic-2', 'text': 'Designed a vegetable garden and planted fruit trees.'},
    {'chunk_id': 'synthetic-3', 'text': 'Maintained backend services and improved API observability.'},
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send', action='store_true', help='Send exactly one synthetic request')
    args = parser.parse_args()
    if not args.send:
        print('NO_REQUEST: rerun with --send to send one synthetic request.')
        return 2
    if not settings.ALLOW_EXTERNAL_API:
        print('BLOCKED: ALLOW_EXTERNAL_API is disabled in this process; no request sent.')
        return 2
    db = None
    try:
        db = SessionLocal()
        chain = load_active_bge_chain(db)
        route = None
        for candidate in chain.get('routes', []):
            try:
                endpoint = cloudflare_rerank_endpoint(candidate['config']['api_base'])
            except (KeyError, TypeError, ValueError, RuntimeError):
                continue
            if candidate.get('api_key_configured'):
                route = candidate
                break
        if route is None:
            print('BLOCKED: no Cloudflare BGE route with a stored key in the active route set; no request sent.')
            return 2
        BGEHttpEmbeddingProvider(api_base=endpoint)._check_endpoint_policy()
        provider = provider_for_pinned_route(db, route)
        if not provider.api_key:
            print('BLOCKED: the selected route has no usable key; no request sent.')
            return 2
        # Close DB before network I/O; no runtime selection, cache, assessment,
        # operation or control row is created or changed.
        db.close()
        db = None
        started = time.monotonic()
        result = asyncio.run(rerank(endpoint, provider.api_key, QUERY, CHUNKS))
        elapsed_ms = round((time.monotonic() - started) * 1000)
        ids = [chunk.get('chunk_id') for chunk in result]
        if len(ids) != len(CHUNKS) or set(ids) != {chunk['chunk_id'] for chunk in CHUNKS}:
            print('FAIL: response did not preserve the synthetic chunk set.')
            return 1
        print(json.dumps({'result': 'PASS', 'model': '@cf/baai/bge-reranker-base',
                          'synthetic_context_count': len(ids), 'ordered_ids': ids,
                          'elapsed_ms': elapsed_ms, 'runtime_controls_changed': False}, ensure_ascii=False))
        return 0
    except Exception as exc:
        # Never print exception messages: they may contain URLs or credentials.
        print(f'FAIL: synthetic test failed; error_type={type(exc).__name__}. No secrets or provider response printed.')
        return 1
    finally:
        if db is not None:
            db.close()


if __name__ == '__main__':
    raise SystemExit(main())
