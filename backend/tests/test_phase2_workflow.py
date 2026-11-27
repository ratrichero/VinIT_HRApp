"""Phase 2 tests use only disposable PostgreSQL and synthetic fixtures."""
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from test_phase1_integration import seed as seed, client as client, headers, uid
from app.api.scorecards import three_business_days
from app.db.database import engine

pytestmark = pytest.mark.skipif(not os.environ.get('TEST_DATABASE_URL'), reason='Disposable PostgreSQL required')


def lead(seed):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_private.user_role_assignments(user_id,role_code) VALUES (:id,'HR_LEAD')"), {'id': seed['other']})


def test_rubric_publish_clone_apply_and_approval(client, seed):
    lead(seed)
    base='/v1/rubric-library'
    assert client.get(base+'/families',headers=headers(seed['hm'])).status_code == 403
    families=client.get(base+'/families',headers=headers(seed['hr'])).json()
    assert {f['code'] for f in families} == {'IT_DIGITAL','ADMIN_OPERATIONS'}
    item={'name':'Synthetic Python','description':'Synthetic test only','category':'MUST_HAVE','weight_in_group':100,'expected_evidence_keywords':['Python']}
    created=client.post(base+'/templates',headers=headers(seed['hr']),json={'job_family_id':families[0]['job_family_id'],'title':'Synthetic rubric','items':[item]})
    assert created.status_code == 201, created.text
    v=created.json()['template_version_id']
    assert client.post(base+f'/versions/{v}/publish',headers=headers(seed['hr']),json={'expected_revision':1}).status_code == 403
    assert client.post(base+f'/versions/{v}/publish',headers=headers(seed['other']),json={'expected_revision':1}).status_code == 200
    assert client.put(base+f'/versions/{v}',headers=headers(seed['hr']),json={'expected_revision':1,'items':[item]}).status_code == 409
    # Existing draft is not silently replaced.
    assert client.post(base+f"/positions/{seed['pos']}/apply",headers=headers(seed['hr']),json={'template_version_id':v}).status_code == 409
    with engine.begin() as conn:
        conn.execute(text("UPDATE app_private.criteria_versions SET status='REJECTED' WHERE criteria_version_id=:id"), {'id':seed['cv']})
    applied=client.post(base+f"/positions/{seed['pos']}/apply",headers=headers(seed['hr']),json={'template_version_id':v})
    assert applied.status_code == 201, applied.text
    new=applied.json()['criteria_version_id']
    assert applied.json()['status']=='DRAFT'
    assert client.post(f'/v1/criteria/{new}/approve',headers=headers(seed['hr']),json={'action':'APPROVE'}).json()['status']=='PENDING_HM_APPROVAL'
    assert client.post(f'/v1/criteria/{new}/approve',headers=headers(seed['hm']),json={'action':'APPROVE'}).json()['status']=='APPROVED'
    clone=client.post(base+f'/versions/{v}/clone',headers=headers(seed['hr']))
    assert clone.status_code == 201 and clone.json()['status']=='DRAFT'
    assert client.post(base+f"/versions/{clone.json()['template_version_id']}/publish",headers=headers(seed['other']),json={'expected_revision':1}).status_code == 200
    with engine.connect() as conn:
        assert conn.execute(text('SELECT status FROM app_private.rubric_template_versions WHERE template_version_id=:id'),{'id':v}).scalar_one() == 'ARCHIVED'
        assert conn.execute(text('SELECT source_template_version_id FROM app_private.criteria_versions WHERE criteria_version_id=:id'),{'id':new}).scalar_one() is not None


def create_snapshot(seed):
    document,profile,assessment=uid(),uid(),uid()
    with engine.begin() as conn:
        conn.execute(text("UPDATE app_private.criteria_versions SET status='APPROVED' WHERE criteria_version_id=:id"), {'id':seed['cv']})
        conn.execute(text("UPDATE app_private.applications SET application_status='SHORTLIST' WHERE application_id=:id"), {'id':seed['app']})
        conn.execute(text("""INSERT INTO app_private.application_documents(document_id,application_id,bucket,storage_path,original_filename,mime_type,size_bytes)
            VALUES (:doc,:app,'cv-originals','synthetic','test.pdf','application/pdf',10)"""), {'doc':document,'app':seed['app']})
        conn.execute(text("INSERT INTO app_private.profile_versions(profile_version_id,application_id,source_document_id,version_number,status) VALUES (:id,:app,:doc,1,'COMPLETED')"), {'id':profile,'app':seed['app'],'doc':document})
        conn.execute(text("""INSERT INTO app_private.assessment_runs(assessment_id,position_id,application_id,jd_version_id,criteria_version_id,profile_version_id,status,matching_status)
            VALUES (:id,:pos,:app,:jd,:cv,:profile,'COMPLETED','MEETS_MANDATORY')"""), {'id':assessment,'pos':seed['pos'],'app':seed['app'],'jd':seed['jd'],'cv':seed['cv'],'profile':profile})


def test_scorecard_share_submit_reopen_revoke(client,seed):
    create_snapshot(seed)
    response=client.post('/v1/shortlist/share',headers=headers(seed['hr']),json={'position_id':seed['pos'],'shared_with_user_id':seed['hm'],'application_ids':[seed['app']]})
    assert response.status_code==201, response.text
    share=response.json()['share_id']
    cards=client.get('/v1/scorecards/share/'+share,headers=headers(seed['hm']))
    assert cards.status_code==200, cards.text
    card=cards.json()[0]; cid=card['scorecard_id']
    assert card['criteria_version_id']==seed['cv'] and card['criteria'][0]['criterion_id']==seed['criterion']
    assert client.get('/v1/scorecards/'+cid,headers=headers(seed['other'])).status_code==403
    assert client.post('/v1/scorecards/'+cid+'/submit',headers=headers(seed['hm']),json={'expected_revision':1}).status_code==400
    payload={'expected_revision':1,'overall_recommendation':'CONSIDER','ratings':[{'criterion_id':seed['criterion'],'insufficient_evidence':True}]}
    assert client.put('/v1/scorecards/'+cid,headers=headers(seed['hm']),json={**payload, 'overall_recommendation': 'invalid'}).status_code==422
    edited=client.put('/v1/scorecards/'+cid,headers=headers(seed['hm']),json=payload)
    assert edited.status_code==200, edited.text
    assert client.put('/v1/scorecards/'+cid,headers=headers(seed['hm']),json=payload).status_code==409
    submitted=client.post('/v1/scorecards/'+cid+'/submit',headers=headers(seed['hm']),json={'expected_revision':2})
    assert submitted.status_code==200 and submitted.json()['status']=='SUBMITTED'
    assert client.put('/v1/scorecards/'+cid,headers=headers(seed['hm']),json={**payload,'expected_revision':3}).status_code==409
    reopened=client.post('/v1/scorecards/'+cid+'/reopen',headers=headers(seed['hr']),json={'expected_revision':3,'reason':'synthetic reason'})
    assert reopened.status_code==200 and reopened.json()['status']=='IN_PROGRESS'
    assert client.get('/v1/scorecards/'+cid+'/reopen-history',headers=headers(seed['hm'])).status_code==403
    history = client.get('/v1/scorecards/'+cid+'/reopen-history',headers=headers(seed['hr']))
    assert history.status_code==200 and history.json()[0]['reason']=='synthetic reason'
    assert client.post('/v1/shortlist/'+share+'/revoke',headers=headers(seed['hr'])).status_code==200
    assert client.get('/v1/scorecards/'+cid,headers=headers(seed['hm'])).status_code==403
    history = client.get('/v1/scorecards/'+cid,headers=headers(seed['hr']))
    assert history.status_code==200 and not history.json()['can_change_due'] and not history.json()['can_reopen']
    assert any(item['share_id'] == share and item['status'] == 'REVOKED' for item in client.get('/v1/shortlist/shared-with-me', headers=headers(seed['hr'])).json())
    assert all(item['share_id'] != share for item in client.get('/v1/shortlist/shared-with-me', headers=headers(seed['hm'])).json())


def test_three_business_days_excludes_weekends():
    assert three_business_days(datetime(2026,11,6,12,tzinfo=timezone.utc)) == datetime(2026,11,11,12,tzinfo=timezone.utc)


def test_snapshot_missing_and_legacy_share(client, seed):
    with engine.begin() as conn:
        conn.execute(text("UPDATE app_private.applications SET application_status='SHORTLIST' WHERE application_id=:id"), {'id': seed['app']})
        legacy = conn.execute(text("""INSERT INTO app_private.shortlist_shares(position_id,created_by,shared_with)
            VALUES (:pos,:hr,:hm) RETURNING share_id"""), {'pos': seed['pos'], 'hr': seed['hr'], 'hm': seed['hm']}).scalar_one()
        conn.execute(text("INSERT INTO app_private.shortlist_share_items(share_id,position_id,application_id) VALUES (:share,:pos,:app)"),
                     {'share': legacy, 'pos': seed['pos'], 'app': seed['app']})
    assert client.get(f'/v1/scorecards/share/{legacy}', headers=headers(seed['hm'])).json() == []
    new = client.post('/v1/shortlist/share', headers=headers(seed['hr']), json={
        'position_id': seed['pos'], 'shared_with_user_id': seed['hm'], 'application_ids': [seed['app']]})
    assert new.status_code == 201
    card = client.get('/v1/scorecards/share/' + new.json()['share_id'], headers=headers(seed['hm'])).json()[0]
    assert card['waiting_for_assessment'] and card['criteria'] == []
    assert client.post('/v1/scorecards/' + card['scorecard_id'] + '/submit', headers=headers(seed['hm']), json={'expected_revision': 1}).status_code == 400


def test_due_date_changes_revision_and_restricts_access(client, seed):
    create_snapshot(seed)
    share = client.post('/v1/shortlist/share', headers=headers(seed['hr']), json={
        'position_id': seed['pos'], 'shared_with_user_id': seed['hm'], 'application_ids': [seed['app']]})
    card = client.get('/v1/scorecards/share/' + share.json()['share_id'], headers=headers(seed['hr'])).json()[0]
    cid = card['scorecard_id']
    payload = {'expected_revision': 1, 'due_at': '2099-01-01T12:00:00Z'}
    assert client.put('/v1/scorecards/' + cid + '/due-date', headers=headers(seed['hm']), json=payload).status_code == 403
    assert client.put('/v1/scorecards/' + cid + '/due-date', headers=headers(seed['hr']), json=payload).status_code == 200
    assert client.put('/v1/scorecards/' + cid + '/due-date', headers=headers(seed['hr']), json=payload).status_code == 409
    assert client.put('/v1/scorecards/' + cid + '/due-date', headers=headers(seed['hr']), json={'expected_revision': 2, 'due_at': '2099-01-01T12:00:00'}).status_code == 422


def test_direct_approval_after_template_apply(client, seed):
    lead(seed)
    family = client.get('/v1/rubric-library/families', headers=headers(seed['hr'])).json()[0]
    created = client.post('/v1/rubric-library/templates', headers=headers(seed['hr']), json={
        'job_family_id': family['job_family_id'], 'title': 'Synthetic direct', 'items': [
            {'name': 'Test', 'description': 'Test', 'category': 'MUST_HAVE', 'weight_in_group': 100}]})
    v = created.json()['template_version_id']
    assert client.post(f'/v1/rubric-library/versions/{v}/publish', headers=headers(seed['other']),json={'expected_revision':1}).status_code == 200
    with engine.begin() as conn:
        conn.execute(text("UPDATE app_private.criteria_versions SET status='REJECTED' WHERE criteria_version_id=:id"), {'id': seed['cv']})
    applied = client.post(f"/v1/rubric-library/positions/{seed['pos']}/apply", headers=headers(seed['hr']), json={'template_version_id': v})
    cv = applied.json()['criteria_version_id']
    approved = client.post(f'/v1/criteria/{cv}/approve', headers=headers(seed['other']), json={'action': 'DIRECT_APPROVE'})
    assert approved.status_code == 200 and approved.json()['status'] == 'APPROVED'


def test_business_day_uses_vietnam_weekday():
    # Friday 18:30 UTC is already Saturday in Vietnam.
    assert three_business_days(datetime(2026, 11, 6, 18, 30, tzinfo=timezone.utc)) == datetime(2026, 11, 10, 18, 30, tzinfo=timezone.utc)


def test_scorecard_revoked_after_hm_change_and_retention_cascade(client, seed):
    create_snapshot(seed)
    response = client.post('/v1/shortlist/share', headers=headers(seed['hr']), json={
        'position_id': seed['pos'], 'shared_with_user_id': seed['hm'], 'application_ids': [seed['app']]})
    card = client.get('/v1/scorecards/share/' + response.json()['share_id'], headers=headers(seed['hm'])).json()[0]
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_private.user_role_assignments(user_id,role_code) VALUES (:id,'HIRING_MANAGER')"), {'id': seed['other']})
    current = client.get(f"/v1/positions/{seed['pos']}/hiring-managers", headers=headers(seed['hr']))
    changed = client.put(f"/v1/positions/{seed['pos']}/hiring-manager", headers=headers(seed['hr']), json={
        'hiring_manager_user_id': seed['other'], 'expected_assignments': [x['version'] for x in current.json()]})
    assert changed.status_code == 200, changed.text
    cid = card['scorecard_id']
    assert client.get('/v1/scorecards/' + cid, headers=headers(seed['hm'])).status_code == 403
    assert client.get('/v1/scorecards/' + cid, headers=headers(seed['other'])).status_code == 403
    assert client.get('/v1/scorecards/' + cid, headers=headers(seed['hr'])).status_code == 200
    # Retention removes share items before assessment; scorecard data must cascade.
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM app_private.shortlist_share_items WHERE application_id=:app'), {'app': seed['app']})
        assert conn.execute(text('SELECT count(*) FROM app_private.shortlist_scorecards WHERE scorecard_id=:id'), {'id': cid}).scalar_one() == 0
        assert conn.execute(text('SELECT count(*) FROM app_private.shortlist_scorecard_criteria WHERE scorecard_id=:id'), {'id': cid}).scalar_one() == 0


def test_published_template_is_immutable_and_private(client, seed):
    from sqlalchemy.exc import DBAPIError
    lead(seed)
    family = client.get('/v1/rubric-library/families', headers=headers(seed['hr'])).json()[0]
    created = client.post('/v1/rubric-library/templates', headers=headers(seed['hr']), json={
        'job_family_id': family['job_family_id'], 'title': 'Synthetic immutable', 'items': [
            {'name': 'Synthetic', 'description': 'Example', 'category': 'MUST_HAVE', 'weight_in_group': 100}]})
    v = created.json()['template_version_id']
    assert client.post(f'/v1/rubric-library/versions/{v}/publish', headers=headers(seed['other']),json={'expected_revision':1}).status_code == 200
    for sql in ("UPDATE app_private.rubric_template_items SET name='tampered' WHERE template_version_id=:id",
                "UPDATE app_private.rubric_template_versions SET created_at=now() WHERE template_version_id=:id",
                "DELETE FROM app_private.rubric_template_versions WHERE template_version_id=:id",
                "UPDATE app_private.rubric_templates SET title='tampered' WHERE template_id=(SELECT template_id FROM app_private.rubric_template_versions WHERE template_version_id=:id)"):
        with pytest.raises(DBAPIError):
            with engine.begin() as conn:
                conn.execute(text(sql), {'id': v})
    with engine.connect() as conn:
        for role in ('anon', 'authenticated'):
            for table in ('rubric_templates', 'rubric_template_versions', 'rubric_template_items', 'shortlist_scorecards', 'shortlist_scorecard_criteria', 'scorecard_reopen_events'):
                assert not conn.execute(text("SELECT has_table_privilege(:role, :table, 'SELECT')"), {'role': role, 'table': 'app_private.' + table}).scalar_one()


def test_stale_publish_and_capabilities(client, seed):
    lead(seed)
    assert client.get('/v1/rubric-library/capabilities', headers=headers(seed['hm'])).status_code == 403
    assert client.get('/v1/rubric-library/capabilities', headers=headers(seed['hr'])).json()['can_publish'] is False
    family = client.get('/v1/rubric-library/families', headers=headers(seed['hr'])).json()[0]
    item = {'name': 'Synthetic', 'description': 'Only a test', 'category': 'MUST_HAVE', 'weight_in_group': 100}
    created = client.post('/v1/rubric-library/templates', headers=headers(seed['hr']), json={
        'job_family_id': family['job_family_id'], 'title': 'Stale publication', 'items': [item]}).json()
    path = '/v1/rubric-library/versions/' + created['template_version_id']
    updated = client.put(path, headers=headers(seed['hr']), json={'expected_revision': 1, 'items': [item]})
    assert updated.status_code == 200 and updated.json()['revision'] == 2
    assert client.post(path + '/publish', headers=headers(seed['other']), json={'expected_revision': 1}).status_code == 409
    assert client.post(path + '/publish', headers=headers(seed['other']), json={'expected_revision': 2}).status_code == 200


def test_reminders_due_access_and_revoke(client, seed):
    create_snapshot(seed)
    share = client.post('/v1/shortlist/share', headers=headers(seed['hr']), json={
        'position_id': seed['pos'], 'shared_with_user_id': seed['hm'], 'application_ids': [seed['app']]}).json()['share_id']
    cards = client.get('/v1/scorecards/share/' + share, headers=headers(seed['hr'])).json()
    cid = cards[0]['scorecard_id']
    assert client.get('/v1/scorecards/reminders', headers=headers(seed['hm'])).json() == []
    with engine.begin() as conn:
        conn.execute(text("UPDATE app_private.shortlist_scorecards SET due_at=now()-interval '1 second' WHERE scorecard_id=:id"), {'id': cid})
    for user in ('hr', 'hm'):
        reminders = client.get('/v1/scorecards/reminders', headers=headers(seed[user]))
        assert reminders.status_code == 200 and len(reminders.json()) == 1
        assert reminders.json()[0]['overdue_count'] == 1 and reminders.json()[0]['share_id'] == share
        assert 'application_id' not in reminders.json()[0]
    assert client.get('/v1/scorecards/reminders', headers=headers(seed['other'])).json() == []
    assert client.post('/v1/shortlist/' + share + '/revoke', headers=headers(seed['hr'])).status_code == 200
    assert client.get('/v1/scorecards/reminders', headers=headers(seed['hm'])).json() == []
    assert client.get('/v1/scorecards/reminders', headers=headers(seed['hr'])).json() == []


def test_retention_purges_scorecard_and_reopen_events(client, seed, monkeypatch):
    from test_phase1_integration import _due_retention_case
    import app.services.retention as retention
    create_snapshot(seed)
    share = client.post('/v1/shortlist/share', headers=headers(seed['hr']), json={
        'position_id': seed['pos'], 'shared_with_user_id': seed['hm'], 'application_ids': [seed['app']]}).json()['share_id']
    card = client.get('/v1/scorecards/share/' + share, headers=headers(seed['hm'])).json()[0]
    cid = card['scorecard_id']
    saved = client.put('/v1/scorecards/' + cid, headers=headers(seed['hm']), json={
        'expected_revision': 1, 'overall_recommendation': 'RECOMMEND', 'strengths': 'synthetic',
        'ratings': [{'criterion_id': seed['criterion'], 'rating': 4, 'comment': 'synthetic'}]})
    assert saved.status_code == 200
    assert client.post('/v1/scorecards/' + cid + '/submit', headers=headers(seed['hm']), json={'expected_revision': 2}).status_code == 200
    assert client.post('/v1/scorecards/' + cid + '/reopen', headers=headers(seed['hr']), json={'expected_revision': 3, 'reason': 'synthetic reason'}).status_code == 200
    with engine.begin() as conn:
        conn.execute(text("UPDATE app_private.application_documents SET file_processing_status='COMPLETED' WHERE application_id=:app"), {'app': seed['app']})
    case = _due_retention_case(client, seed, confirm=True)
    monkeypatch.setattr(retention, 'delete_storage_objects', lambda *args: {'files_deleted_count': 0})
    result = client.post(f'/v1/retention/cases/{case}/execute', headers=headers(seed['hr']))
    assert result.status_code == 200, result.text
    with engine.connect() as conn:
        for table in ('shortlist_scorecards', 'shortlist_scorecard_criteria', 'scorecard_reopen_events'):
            assert conn.execute(text(f'SELECT count(*) FROM app_private.{table} WHERE scorecard_id=:id'), {'id': cid}).scalar_one() == 0
        summary = conn.execute(text('SELECT result_summary FROM app_private.deletion_jobs WHERE retention_case_id=:id'), {'id': case}).scalar_one()
        assert summary['shortlist_scorecards'] == summary['scorecard_criteria'] == summary['scorecard_reopen_events'] == 1


def test_scorecard_save_rechecks_revocation_after_position_lock(client, seed):
    from concurrent.futures import ThreadPoolExecutor
    import time
    create_snapshot(seed)
    share = client.post('/v1/shortlist/share', headers=headers(seed['hr']), json={
        'position_id': seed['pos'], 'shared_with_user_id': seed['hm'], 'application_ids': [seed['app']]}).json()['share_id']
    card = client.get('/v1/scorecards/share/' + share, headers=headers(seed['hm'])).json()[0]
    payload = {'expected_revision': 1, 'overall_recommendation': 'RECOMMEND',
               'ratings': [{'criterion_id': seed['criterion'], 'rating': 5}]}
    with ThreadPoolExecutor(max_workers=1) as pool:
        with engine.connect() as conn:
            txn = conn.begin()
            try:
                conn.execute(text('SELECT 1 FROM app_private.positions WHERE position_id=:id FOR UPDATE'), {'id': seed['pos']})
                conn.execute(text("UPDATE app_private.shortlist_shares SET status='REVOKED',revoked_at=now() WHERE share_id=:id"), {'id': share})
                future = pool.submit(client.put, '/v1/scorecards/' + card['scorecard_id'], headers=headers(seed['hm']), json=payload)
                waiting = 0
                for _ in range(200):
                    conn.execute(text('SELECT pg_stat_clear_snapshot()'))
                    waiting = conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%positions WHERE position_id=%FOR UPDATE%' ")).scalar_one()
                    if waiting: break
                    time.sleep(.02)
                assert waiting and not future.done()
            finally:
                txn.commit()
        response = future.result(timeout=10)
    assert response.status_code == 403
    with engine.connect() as conn:
        assert conn.execute(text('SELECT revision FROM app_private.shortlist_scorecards WHERE scorecard_id=:id'), {'id': card['scorecard_id']}).scalar_one() == 1


def test_scorecard_remains_bound_to_original_assessment_snapshot(client, seed):
    create_snapshot(seed)
    share = client.post('/v1/shortlist/share', headers=headers(seed['hr']), json={
        'position_id': seed['pos'], 'shared_with_user_id': seed['hm'], 'application_ids': [seed['app']]}).json()['share_id']
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_private.application_private_notes(application_id,created_by,content) VALUES (:app,:hr,'synthetic private note')"), {'app': seed['app'], 'hr': seed['hr']})
        replacement = uid()
        conn.execute(text("INSERT INTO app_private.criteria_versions(criteria_version_id,position_id,jd_version_id,version_number,status) VALUES (:id,:pos,:jd,2,'APPROVED')"), {'id': replacement, 'pos': seed['pos'], 'jd': seed['jd']})
        conn.execute(text("INSERT INTO app_private.criteria_items(criteria_version_id,name,description,category,weight_in_group) VALUES (:id,'New','New','MUST_HAVE',100)"), {'id': replacement})
    response = client.get('/v1/scorecards/share/' + share, headers=headers(seed['hm']))
    assert response.status_code == 200
    card = response.json()[0]
    assert card['criteria_version_id'] == seed['cv'] and [c['criterion_id'] for c in card['criteria']] == [seed['criterion']]
    assert 'synthetic private note' not in response.text


def test_position_family_create_update_legacy_and_permissions(client, seed):
    from test_phase1_integration import create_test_department
    department = create_test_department()
    families = client.get('/v1/rubric-library/families', headers=headers(seed['hr'])).json()
    family = next(f for f in families if f['code'] == 'ADMIN_OPERATIONS')
    created = client.post('/v1/positions', headers=headers(seed['hr']), json={
        'department_id': department, 'title': 'Synthetic', 'jd_content': 'Synthetic JD',
        'hiring_manager_user_id': seed['hm'], 'job_family_id': family['job_family_id']})
    assert created.status_code == 201, created.text
    assert created.json()['job_family_id'] == family['job_family_id'] and created.json()['job_family'] == family['name']
    assert client.patch(f"/v1/positions/{seed['pos']}", headers=headers(seed['hm']), json={'job_family_id': family['job_family_id']}).status_code == 403
    updated = client.patch(f"/v1/positions/{seed['pos']}", headers=headers(seed['hr']), json={'job_family_id': family['job_family_id']})
    assert updated.status_code == 200 and updated.json()['job_family'] == family['name']
    with engine.begin() as conn:
        conn.execute(text('UPDATE app_private.job_families SET is_active=false WHERE job_family_id=:id'), {'id': family['job_family_id']})
    try:
        assert client.patch(f"/v1/positions/{seed['pos']}", headers=headers(seed['hr']), json={'job_family_id': family['job_family_id']}).status_code == 400
        assert client.patch(f"/v1/positions/{seed['pos']}", headers=headers(seed['hr']), json={'title': 'Updated'}).json()['job_family_id'] == family['job_family_id']
        cleared = client.patch(f"/v1/positions/{seed['pos']}", headers=headers(seed['hr']), json={'job_family_id': None})
        assert cleared.status_code == 200 and cleared.json()['job_family_id'] is None and cleared.json()['job_family'] is None
    finally:
        with engine.begin() as conn:
            conn.execute(text('UPDATE app_private.job_families SET is_active=true WHERE job_family_id=:id'), {'id': family['job_family_id']})


def test_publish_weight_validation_and_snapshot_provenance(client, seed):
    lead(seed)
    family = client.get('/v1/rubric-library/families', headers=headers(seed['hr'])).json()[0]
    item = {'name': 'Synthetic', 'description': 'Example', 'category': 'MUST_HAVE', 'weight_in_group': 70}
    response = client.post('/v1/rubric-library/templates', headers=headers(seed['hr']), json={'job_family_id': family['job_family_id'], 'title': 'Weights', 'items': [item]})
    v = response.json()['template_version_id']
    assert client.post(f'/v1/rubric-library/versions/{v}/publish', headers=headers(seed['other']), json={'expected_revision': 1}).status_code == 400
    item['weight_in_group'] = 100
    assert client.put(f'/v1/rubric-library/versions/{v}', headers=headers(seed['hr']), json={'expected_revision': 1, 'items': [item]}).status_code == 200
    assert client.post(f'/v1/rubric-library/versions/{v}/publish', headers=headers(seed['other']), json={'expected_revision': 2}).status_code == 200
    with engine.begin() as conn:
        conn.execute(text("UPDATE app_private.criteria_versions SET status='REJECTED' WHERE criteria_version_id=:id"), {'id': seed['cv']})
    applied = client.post(f"/v1/rubric-library/positions/{seed['pos']}/apply", headers=headers(seed['hr']), json={'template_version_id': v})
    assert applied.status_code == 201
    details = client.get('/v1/criteria/' + applied.json()['criteria_version_id'], headers=headers(seed['hr'])).json()
    assert details['source_template_version_id'] == v and details['criteria'][0]['source_template_item_id']


def test_share_explicit_due_date_and_invalid_criterion(client, seed):
    create_snapshot(seed)
    data = {'position_id': seed['pos'], 'shared_with_user_id': seed['hm'], 'application_ids': [seed['app']]}
    assert client.post('/v1/shortlist/share', headers=headers(seed['hr']), json={**data, 'due_at': '2099-01-01T12:00:00'}).status_code == 422
    assert client.post('/v1/shortlist/share', headers=headers(seed['hr']), json={**data, 'due_at': '2000-01-01T12:00:00Z'}).status_code == 400
    share = client.post('/v1/shortlist/share', headers=headers(seed['hr']), json={**data, 'due_at': '2099-01-01T12:00:00Z'}).json()['share_id']
    card = client.get('/v1/scorecards/share/' + share, headers=headers(seed['hm'])).json()[0]
    assert card['due_at'].startswith('2099-01-01T12:00:00')
    invalid = client.put('/v1/scorecards/' + card['scorecard_id'], headers=headers(seed['hm']), json={
        'expected_revision': 1, 'overall_recommendation': 'RECOMMEND', 'ratings': [{'criterion_id': uid(), 'rating': 5}]})
    assert invalid.status_code == 400


def test_hr_can_save_proposed_rubric_as_draft(client, seed):
    import json
    from pathlib import Path
    proposal = json.loads((Path(__file__).resolve().parents[2] / 'frontend/src/data/rubric-proposal-it-backend.json').read_text(encoding='utf-8'))
    family_code = proposal.pop('job_family_code')
    family = next(f for f in client.get('/v1/rubric-library/families', headers=headers(seed['hr'])).json() if f['code'] == family_code)
    response = client.post('/v1/rubric-library/templates', headers=headers(seed['hr']), json={**proposal, 'job_family_id': family['job_family_id']})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['status'] == 'DRAFT' and result['created_by'] == seed['hr'] and len(result['items']) == 5
    assert result['items'][0]['requirement_spec']['min_years'] == 4
    assert client.post('/v1/rubric-library/versions/' + result['template_version_id'] + '/publish', headers=headers(seed['hr']), json={'expected_revision': 1}).status_code == 403


def test_admin_can_build_rubric_library_but_not_publish(client, seed):
    """ADMIN dựng được thư viện rubric nhưng vẫn không xuất bản.

    Lỗi gốc: `capabilities.can_create` và `_require_editor` chỉ tính
    HR_RECRUITER/HR_LEAD. ADMIN vào thư viện thì thấy "Chưa có rubric nào" mà
    không có nút nào tạo được — với tài khoản quản trị (người dựng hệ thống)
    thư viện rỗng vĩnh viễn, tính năng chết. Mọi endpoint phân quyền khác
    (positions, scorecards, dashboard, shortlist) đều đã tính ADMIN; riêng chỗ
    này bỏ sót. Xuất bản vẫn là quyền riêng của HR_LEAD.
    """
    admin = uid()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO auth.users(id) VALUES (:id)"), {"id": admin})
        conn.execute(text("INSERT INTO app_private.user_profiles(user_id, display_name) VALUES (:id, 'ADMIN')"), {"id": admin})
        conn.execute(text("INSERT INTO app_private.user_role_assignments(user_id, role_code) VALUES (:id, 'ADMIN')"), {"id": admin})

    base = '/v1/rubric-library'
    caps = client.get(base + '/capabilities', headers=headers(admin))
    assert caps.status_code == 200, caps.text
    assert caps.json()['can_create'] is True
    # Xuất bản là quyền của HR_LEAD, không mở cho ADMIN.
    assert caps.json()['can_publish'] is False

    families = client.get(base + '/families', headers=headers(admin)).json()
    item = {'name': 'Synthetic admin', 'description': 'Synthetic test only',
            'category': 'MUST_HAVE', 'weight_in_group': 100}
    created = client.post(base + '/templates', headers=headers(admin), json={
        'job_family_id': families[0]['job_family_id'], 'title': 'Rubric do ADMIN dựng', 'items': [item]})
    assert created.status_code == 201, created.text
    version = created.json()['template_version_id']
    # Sửa được bản nháp mình tạo (owner truyền vào), và không xuất bản được.
    updated = client.put(base + '/versions/' + version, headers=headers(admin),
                         json={'expected_revision': 1, 'items': [item]})
    assert updated.status_code == 200, updated.text
    assert client.post(base + '/versions/' + version + '/publish', headers=headers(admin),
                       json={'expected_revision': 2}).status_code == 403
