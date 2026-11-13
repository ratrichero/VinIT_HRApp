"""Tests for operator smoke script; all HTTP and credentials are synthetic."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def load_script():
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'cloudflare_reranker_smoke.py'
    spec = importlib.util.spec_from_file_location('cloudflare_smoke', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_uses_fixed_inputs_and_never_prints_key_or_endpoint(monkeypatch, capsys):
    script = load_script()
    monkeypatch.setattr(sys, 'argv', ['smoke', '--send'])
    monkeypatch.setattr(script.settings, 'ALLOW_EXTERNAL_API', True)
    class DB:
        def close(self): pass
    monkeypatch.setattr(script, 'SessionLocal', DB)
    route = {'config_id': 'fake', 'api_key_configured': True, 'config': {'api_base': 'https://api.cloudflare.com/client/v4/accounts/' + 'a' * 32 + '/ai/v1'}}
    monkeypatch.setattr(script, 'load_active_bge_chain', lambda db: {'routes': [route]})
    monkeypatch.setattr(script, 'provider_for_pinned_route', lambda db, pinned: SimpleNamespace(api_key='secret-test-only'))
    calls = []
    async def fake_rerank(endpoint, key, query, chunks):
        calls.append((endpoint, key, query, chunks))
        return [chunks[2], chunks[0], chunks[1]]
    monkeypatch.setattr(script, 'rerank', fake_rerank)
    assert script.main() == 0
    output = capsys.readouterr().out
    assert 'PASS' in output and 'synthetic-3' in output
    assert 'secret-test-only' not in output and 'api.cloudflare.com' not in output
    assert len(calls) == 1 and calls[0][2] == script.QUERY and calls[0][3] == script.CHUNKS


def test_smoke_requires_explicit_send_and_external_gate(monkeypatch, capsys):
    script = load_script()
    monkeypatch.setattr(sys, 'argv', ['smoke'])
    assert script.main() == 2 and 'NO_REQUEST' in capsys.readouterr().out
    monkeypatch.setattr(sys, 'argv', ['smoke', '--send'])
    monkeypatch.setattr(script.settings, 'ALLOW_EXTERNAL_API', False)
    assert script.main() == 2 and 'no request sent' in capsys.readouterr().out


def test_smoke_does_not_leak_errors(monkeypatch, capsys):
    script = load_script()
    monkeypatch.setattr(sys, 'argv', ['smoke', '--send'])
    monkeypatch.setattr(script.settings, 'ALLOW_EXTERNAL_API', True)
    def failure(): raise RuntimeError('secret-test-only')
    monkeypatch.setattr(script, 'SessionLocal', failure)
    assert script.main() == 1
    out = capsys.readouterr().out
    assert 'RuntimeError' in out and 'secret-test-only' not in out
