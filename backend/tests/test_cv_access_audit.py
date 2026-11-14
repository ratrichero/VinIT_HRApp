"""Regression tests for CV proxy authorization and audit on disposable PostgreSQL."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

import pytest
from sqlalchemy import event, text

from test_phase1_integration import seed as seed, client as client, headers
from app.api import applications
from app.db.database import engine

pytestmark = pytest.mark.skipif(not os.environ.get('TEST_DATABASE_URL'), reason='Disposable PostgreSQL required')


def setup_cv(client, seed, monkeypatch, download=None, allow=True):
    with engine.begin() as conn:
        conn.execute(text("UPDATE app_private.applications SET application_status='SHORTLIST' WHERE application_id=:id"), {'id': seed['app']})
        conn.execute(text("""INSERT INTO app_private.application_documents
            (application_id,bucket,storage_path,original_filename,mime_type,size_bytes)
            VALUES (:id,'cv-originals','synthetic/path','synthetic.pdf','application/pdf',9)"""), {'id': seed['app']})
    share = client.post('/v1/shortlist/share', headers=headers(seed['hr']), json={'position_id': seed['pos'],
        'shared_with_user_id': seed['hm'], 'application_ids': [seed['app']], 'allow_cv_view': allow})
    assert share.status_code == 201, share.text
    bucket = Mock()
    if download:
        bucket.download.side_effect = download
    else:
        bucket.download.return_value = b'synthetic'
    storage = Mock()
    storage.storage.from_.return_value = bucket
    monkeypatch.setattr(applications.settings, 'STORAGE_BACKEND', 'supabase')
    monkeypatch.setattr(applications, 'get_supabase_client', lambda: storage)
    return share.json()['share_id'], bucket


def cv_audits(seed):
    with engine.connect() as conn:
        return conn.execute(text("""SELECT actor_user_id,object_id,position_id,outcome,metadata
            FROM app_private.audit_events WHERE action_type='CV_FILE_ACCESS_GRANTED'
              AND object_id=:app ORDER BY chain_sequence"""), {'app': seed['app']}).mappings().all()


def test_cv_proxy_audits_and_never_issues_bearer_url(client, seed, monkeypatch):
    share, bucket = setup_cv(client, seed, monkeypatch)
    base = f"/v1/applications/{seed['app']}"
    discovery = client.get(base+'/cv-download-url', headers=headers(seed['hm']))
    assert discovery.status_code == 200 and discovery.json()['file_url'] == base+'/cv-file'
    assert 'signed_url' not in discovery.json() and cv_audits(seed) == []
    assert 'no-store' in discovery.headers['cache-control']
    assert client.get(base+'/cv-file', headers=headers(seed['other'])).status_code == 403
    result = client.get(base+'/cv-file', headers=headers(seed['hm']))
    assert result.status_code == 200 and result.content == b'synthetic'
    assert 'no-store' in result.headers['cache-control'] and result.headers['x-content-type-options'] == 'nosniff'
    bucket.create_signed_url.assert_not_called()
    bucket.download.assert_called_once_with('synthetic/path')
    events = cv_audits(seed)
    assert len(events) == 1 and str(events[0]['actor_user_id']) == seed['hm']
    assert str(events[0]['object_id']) == seed['app'] and str(events[0]['position_id']) == seed['pos']
    assert events[0]['outcome'] == 'SUCCESS' and not events[0]['metadata']
    with engine.connect() as conn:
        valid = conn.execute(text("""SELECT event_hash = app_private.compute_audit_event_hash(previous_event_hash, e)
            FROM app_private.audit_events e WHERE action_type='CV_FILE_ACCESS_GRANTED' AND object_id=:app"""), {'app': seed['app']}).scalar_one()
        assert valid
    assert client.post(f'/v1/shortlist/{share}/revoke', headers=headers(seed['hr'])).status_code == 200
    assert client.get(base+'/cv-file', headers=headers(seed['hm'])).status_code == 403
    assert client.get(base+'/cv-download-url', headers=headers(seed['hm'])).status_code == 403
    assert len(cv_audits(seed)) == 1
    assert client.get(base+'/cv-file', headers=headers(seed['hr'])).content == b'synthetic'
    assert len(cv_audits(seed)) == 2


def test_cv_proxy_disallows_summary_share_and_failed_storage(client, seed, monkeypatch):
    _, bucket = setup_cv(client, seed, monkeypatch, allow=False)
    base = f"/v1/applications/{seed['app']}"
    assert client.get(base+'/cv-file', headers=headers(seed['hm'])).status_code == 403
    bucket.download.assert_not_called()
    bucket.download.side_effect = RuntimeError('sensitive-path-not-for-response')
    result = client.get(base+'/cv-file', headers=headers(seed['hr']))
    assert result.status_code == 502 and 'sensitive-path-not-for-response' not in result.text
    assert not cv_audits(seed)


def test_cv_proxy_fails_closed_if_audit_cannot_be_recorded(client, seed, monkeypatch):
    setup_cv(client, seed, monkeypatch)
    def fail_insert(conn, cursor, statement, parameters, context, executemany):
        if "'CV_FILE_ACCESS_GRANTED'" in statement:
            raise RuntimeError('audit unavailable')
    event.listen(engine, 'before_cursor_execute', fail_insert)
    try:
        with pytest.raises(RuntimeError, match='audit unavailable'):
            client.get(f"/v1/applications/{seed['app']}/cv-file", headers=headers(seed['hm']))
    finally:
        event.remove(engine, 'before_cursor_execute', fail_insert)
    assert not cv_audits(seed)


@pytest.mark.parametrize('action', ['revoke', 'change_hm', 'disable_account'])
def test_cv_proxy_rechecks_after_storage_fetch_race(client, seed, monkeypatch, action):
    entered, release = Event(), Event()
    def slow_download(path):
        entered.set()
        assert release.wait(10)
        return b'synthetic'
    share, _ = setup_cv(client, seed, monkeypatch, slow_download)
    base = f"/v1/positions/{seed['pos']}"
    versions = [p['version'] for p in client.get(base+'/hiring-managers', headers=headers(seed['hr'])).json()]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(client.get, f"/v1/applications/{seed['app']}/cv-file", headers=headers(seed['hm']))
            assert entered.wait(10)
            if action == 'revoke':
                assert client.post(f'/v1/shortlist/{share}/revoke', headers=headers(seed['hr'])).status_code == 200
            elif action == 'change_hm':
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO app_private.user_role_assignments(user_id,role_code) VALUES (:id,'HIRING_MANAGER')"), {'id': seed['other']})
                result = client.put(base+'/hiring-manager', headers=headers(seed['hr']), json={'hiring_manager_user_id': seed['other'], 'expected_assignments': versions})
                assert result.status_code == 200, result.text
            else:
                with engine.begin() as conn:
                    conn.execute(text("UPDATE app_private.user_profiles SET account_status='SUSPENDED' WHERE user_id=:id"), {'id': seed['hm']})
            release.set()
            assert future.result(timeout=10).status_code == 403
    finally:
        release.set()
    assert not cv_audits(seed)


def test_revoke_waits_for_locked_cv_authorization_and_blocks_next_request(client, seed, monkeypatch):
    share, _ = setup_cv(client, seed, monkeypatch)
    entered, release, revoke_started = Event(), Event(), Event()
    def pause_audit(conn, cursor, statement, parameters, context, executemany):
        if "'CV_FILE_ACCESS_GRANTED'" in statement:
            entered.set()
            assert release.wait(10)
    def revoke():
        revoke_started.set()
        return client.post(f'/v1/shortlist/{share}/revoke', headers=headers(seed['hr']))
    event.listen(engine, 'before_cursor_execute', pause_audit)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            access = pool.submit(client.get, f"/v1/applications/{seed['app']}/cv-file", headers=headers(seed['hm']))
            assert entered.wait(10)
            revocation = pool.submit(revoke)
            assert revoke_started.wait(10)
            # Postgres reports the waiting lock; avoid assuming a delay alone proves ordering.
            with engine.connect() as conn:
                import time
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    conn.execute(text("SELECT pg_stat_clear_snapshot()"))
                    waiting = conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%FOR UPDATE%'" )).scalar_one()
                    if waiting:
                        break
                    time.sleep(.02)
                assert waiting
            assert not revocation.done()
            release.set()
            assert access.result(timeout=10).status_code == 200
            assert revocation.result(timeout=10).status_code == 200
    finally:
        release.set()
        event.remove(engine, 'before_cursor_execute', pause_audit)
    assert len(cv_audits(seed)) == 1
    assert client.get(f"/v1/applications/{seed['app']}/cv-file", headers=headers(seed['hm'])).status_code == 403


def test_cv_proxy_rejects_oversized_storage_response(client, seed, monkeypatch):
    _, bucket = setup_cv(client, seed, monkeypatch)
    monkeypatch.setattr(applications.settings, 'MAX_FILE_SIZE_BYTES', 9)
    bucket.download.return_value = b'x' * 10
    result = client.get(f"/v1/applications/{seed['app']}/cv-file", headers=headers(seed['hm']))
    assert result.status_code == 502 and not cv_audits(seed)


def test_cv_proxy_rejects_document_replacement_during_fetch(client, seed, monkeypatch):
    def replace_document(path):
        with engine.begin() as conn:
            conn.execute(text("""INSERT INTO app_private.application_documents
                (application_id,bucket,storage_path,original_filename,mime_type,size_bytes,created_at)
                VALUES (:id,'cv-originals','new/path','new.pdf','application/pdf',3, now()+interval '1 minute')"""), {'id': seed['app']})
        return b'synthetic'
    setup_cv(client, seed, monkeypatch, replace_document)
    result = client.get(f"/v1/applications/{seed['app']}/cv-file", headers=headers(seed['hm']))
    assert result.status_code == 409 and not cv_audits(seed)
