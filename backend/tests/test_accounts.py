"""Account integration tests: destructive, local disposable PostgreSQL only.

Supabase Auth is a deterministic in-memory fake backed by auth.users IDs. No
real Auth, email delivery, Storage or external service is contacted.
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import settings
from app.db.database import engine
from app.main import app

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires a disposable local migrated *_test database")
SECRET = "synthetic-jwt-secret-not-for-production-0123456789"
SETUP = "synthetic-one-time-setup-token-with-adequate-length"
TEMP = "temporary-password-123!"
NEW = "new-password-for-synthetic-user-456!"
VOLUNTARY = "voluntary-new-password-789!"
RESET_TEMP = "reset-temporary-password-123!"
FINAL = "member-final-password-456!"


class AuthError(Exception):
    def __init__(self, status, code=None):
        self.status, self.code = status, code


class FakeAuth:
    def __init__(self):
        self.users = {}
        self.lock = threading.Lock()
        self.created_ids = []
        self.deleted_ids = []
        self.fail_after_create = False

    def client(self):
        return SimpleNamespace(auth=FakeAuthSession(self))

    def seed(self, email, roles, name=None, status="ACTIVE", must_change=False):
        user_id = str(uuid4())
        with self.lock:
            self.users[email] = {"id": user_id, "email": email, "password": TEMP}
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO auth.users(id,email) VALUES (:id,:email)"), {"id": user_id, "email": email})
            conn.execute(text("""INSERT INTO app_private.user_profiles(user_id,display_name,account_status,must_change_password)
                VALUES (:id,:name,:status,:must_change)"""),
                {"id": user_id, "name": name or email, "status": status, "must_change": must_change})
            for role in roles:
                conn.execute(text("INSERT INTO app_private.user_role_assignments(user_id,role_code) VALUES (:id,:role)"), {"id": user_id, "role": role})
        return user_id

    def token(self, user_id, email, iat=None):
        now = int(time.time())
        return jwt.encode({"sub": user_id, "aud": "authenticated", "email": email,
                           "iat": now if iat is None else iat, "exp": now + 3600}, SECRET, algorithm="HS256")


class FakeAuthSession:
    def __init__(self, fake):
        self.fake = fake
        self.admin = FakeAuthAdmin(fake)
        self.current_email = None

    def sign_in_with_password(self, data):
        email = data["email"].lower()
        with self.fake.lock:
            user = self.fake.users.get(email)
            if not user or user["password"] != data["password"]:
                raise AuthError(400, "invalid_credentials")
            self.current_email = email
            user = dict(user)
        token = self.fake.token(user["id"], email)
        return SimpleNamespace(user=SimpleNamespace(id=user["id"], email=email),
                               session=SimpleNamespace(access_token=token, expires_in=3600))

    def update_user(self, data):
        with self.fake.lock:
            assert self.current_email
            self.fake.users[self.current_email]["password"] = data["password"]
        return SimpleNamespace()


class FakeAuthAdmin:
    def __init__(self, fake):
        self.fake = fake

    def create_user(self, data):
        assert data["email_confirm"] is True
        email, user_id = data["email"].lower(), data["id"]
        with self.fake.lock:
            if email in self.fake.users:
                raise AuthError(422, "email_exists")
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO auth.users(id,email) VALUES (:id,:email)"), {"id": user_id, "email": email})
            self.fake.users[email] = {"id": user_id, "email": email, "password": data["password"]}
            self.fake.created_ids.append(user_id)
        if self.fake.fail_after_create:
            raise TimeoutError("Synthetic timeout after Auth commit")
        return SimpleNamespace(user=SimpleNamespace(id=user_id, email=email))

    def delete_user(self, user_id):
        with self.fake.lock:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM auth.users WHERE id=:id"), {"id": user_id})
            self.fake.users = {email: user for email, user in self.fake.users.items() if user["id"] != user_id}
            self.fake.deleted_ids.append(user_id)

    def update_user_by_id(self, user_id, data):
        with self.fake.lock:
            for user in self.fake.users.values():
                if user["id"] == str(user_id):
                    user["password"] = data["password"]
                    return SimpleNamespace(user=SimpleNamespace(id=user_id))
        raise AuthError(404, "user_not_found")


def reset_disposable_database():
    with engine.begin() as conn:
        # Cascades through the entire test schema, not just account tables.
        # RESTART IDENTITY cũng đặt lại `app_private.audit_event_chain_seq`:
        # CASCADE xoá `audit_events` (FK tới auth.users) nhưng không tự đặt lại
        # sequence của bảng bị xoá qua cascade, nên lần chạy sau trên cùng DB sẽ
        # nối tiếp chuỗi hash của lần trước.
        conn.execute(text("TRUNCATE auth.users RESTART IDENTITY CASCADE"))
        conn.execute(text("UPDATE app_private.account_initialization SET initialized_at=NULL, initialized_by=NULL WHERE singleton=TRUE"))
        # The Auth cascade also truncates policy tables that refer to users.
        conn.exec_driver_sql("""INSERT INTO app_private.assessment_policy_versions
            (policy_version,score_mapping,min_evidence_coverage,confidence_thresholds,ranking_rules,status)
            VALUES ('v1.0', '{"STRONG_MATCH":100,"MATCH":80,"NO_MATCH":0,"UNCLEAR":null}'::jsonb,
                    0.70, '{"HIGH":0.8,"MEDIUM":0.6,"LOW":0.0}'::jsonb, 'synthetic', 'APPROVED'),
                   ('assessment-v2.0', '{"STRONG_MATCH":100,"MATCH":80,"NO_MATCH":0,"UNCLEAR":null}'::jsonb,
                    0.70, '{"min_evidence_strength":0.35}'::jsonb,
                    'must-have gate, matching score, evidence coverage, application_id', 'APPROVED')
            ON CONFLICT (policy_version) DO NOTHING""")
        conn.execute(text("""INSERT INTO app_private.retention_policy_versions
            (policy_version,retention_months,trigger_event,status) VALUES ('v1.0-12month',12,'POSITION_CLOSED','APPROVED')
            ON CONFLICT (policy_version) DO NOTHING"""))


@pytest.fixture
def fake_auth(monkeypatch):
    from app.api import auth
    from app.services import accounts
    reset_disposable_database()
    fake = FakeAuth()
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_TOKEN", SETUP)
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://synthetic.invalid")
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", "synthetic-anon")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "synthetic-service")
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(accounts, "get_supabase_client", fake.client)
    monkeypatch.setattr(auth, "create_client", lambda *_: fake.client())
    yield fake
    app.dependency_overrides.clear()
    reset_disposable_database()


@pytest.fixture
def client(fake_auth):
    with TestClient(app) as client:
        yield client


def bootstrap(client, email="admin@example.org"):
    return client.post("/v1/auth/bootstrap", json={"email": email, "display_name": "Admin",
                       "password": TEMP, "setup_token": SETUP})


def login(client, email, password=TEMP):
    result = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert result.status_code == 200, result.text
    return result.json()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def update(name, status, roles):
    return {"display_name": name, "account_status": status, "roles": roles}


def make_department(name="Engineering", code_format="REQ-ENG-{SEQ:000}"):
    with engine.begin() as conn:
        return str(conn.execute(text("""
            INSERT INTO app_private.departments (name, code_format)
            VALUES (:name, :code_format) RETURNING department_id
        """), {"name": name, "code_format": code_format}).scalar_one())


def test_bootstrap_disabled_wrong_secret_and_validation_redacts_credentials(client, fake_auth, monkeypatch):
    assert client.get('/v1/auth/bootstrap-status').json() == {"available": True}
    monkeypatch.setattr(settings, 'ADMIN_BOOTSTRAP_TOKEN', '')
    assert client.get('/v1/auth/bootstrap-status').json() == {"available": False}
    assert bootstrap(client).status_code == 403
    monkeypatch.setattr(settings, 'ADMIN_BOOTSTRAP_TOKEN', SETUP)
    body = {"email": "admin@example.org", "display_name": "Admin", "password": TEMP, "setup_token": "incorrect"}
    assert client.post('/v1/auth/bootstrap', json=body).status_code == 403
    assert not fake_auth.users
    sensitive = 'never-echo-password-654321'
    result = client.post('/v1/auth/bootstrap', json={**body, "email": "not-an-email", "password": sensitive, "setup_token": 's' * 300})
    assert result.status_code == 422
    assert sensitive not in result.text and 's' * 300 not in result.text
    unicode_result = client.post('/v1/auth/bootstrap', content=json.dumps({**body, 'setup_token': '\ud800', 'password': TEMP}),
                                 headers={'Content-Type': 'application/json'})
    assert unicode_result.status_code == 403 and 'temporary-password' not in unicode_result.text


def test_first_admin_bootstrap_is_durable_and_single_under_concurrency(client, fake_auth):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda i: bootstrap(client, f"admin{i}@example.org"), range(2)))
    assert sorted(response.status_code for response in results) == [201, 409]
    created = next(response.json()["user_id"] for response in results if response.status_code == 201)
    assert len(fake_auth.users) == 1 and fake_auth.created_ids == [created]
    assert client.get('/v1/auth/bootstrap-status').json() == {"available": False}
    with engine.begin() as conn:
        row = conn.execute(text("SELECT initialized_by, initialized_at FROM app_private.account_initialization WHERE singleton")).mappings().one()
        assert str(row['initialized_by']) == created and row['initialized_at'] is not None
        assert conn.execute(text("SELECT count(*) FROM app_private.audit_events WHERE action_type='BOOTSTRAP_ADMIN'" )).scalar_one() == 1
        conn.execute(text("DELETE FROM app_private.user_role_assignments WHERE user_id=:id AND role_code='ADMIN'"), {"id": created})
        conn.execute(text("UPDATE app_private.user_profiles SET account_status='SUSPENDED' WHERE user_id=:id"), {"id": created})
    assert client.get('/v1/auth/bootstrap-status').json() == {"available": False}
    assert bootstrap(client, 'another@example.org').status_code == 409


def test_manual_admin_assignment_also_permanently_closes_bootstrap(client, fake_auth):
    admin = fake_auth.seed('manual@example.org', ['ADMIN'])
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM app_private.user_role_assignments WHERE user_id=:id"), {"id": admin})
    assert client.get('/v1/auth/bootstrap-status').json() == {"available": False}
    assert bootstrap(client).status_code == 409


def test_admin_creates_roles_temporary_password_and_protected_routes(client, fake_auth):
    assert bootstrap(client).status_code == 201
    admin = login(client, 'admin@example.org')
    admin_headers = bearer(admin['access_token'])
    hr = fake_auth.seed('existing-hr@example.org', ['HR_RECRUITER'])
    hr_headers = bearer(fake_auth.token(hr, 'existing-hr@example.org'))
    assert client.get('/v1/admin/users', headers=hr_headers).status_code == 403
    assert client.post('/v1/admin/users', headers=hr_headers, json={"email":"x@example.org","display_name":"X","password":TEMP,"roles":["ADMIN"]}).status_code == 403
    for role, email in [('HR_RECRUITER', 'hr@example.org'), ('HIRING_MANAGER', 'hm@example.org')]:
        response = client.post('/v1/admin/users', headers=admin_headers,
                               json={"email": email, "display_name": role, "password": TEMP, "roles": [role]})
        assert response.status_code == 201, response.text
        assert response.json()['must_change_password'] is True and TEMP not in response.text
    duplicate = client.post('/v1/admin/users', headers=admin_headers,
                            json={"email": "hr@example.org", "display_name": "HR", "password": TEMP, "roles": ["ADMIN"]})
    assert duplicate.status_code == 409 and TEMP not in duplicate.text
    forbidden_role = client.post('/v1/admin/users', headers=admin_headers,
                                 json={"email": "a@example.org", "display_name": "A", "password": TEMP, "roles": ["SUPERUSER"]})
    assert forbidden_role.status_code == 422 and TEMP not in forbidden_role.text
    listed = client.get('/v1/admin/users?role=HIRING_MANAGER', headers=admin_headers)
    assert listed.status_code == 200 and [row['email'] for row in listed.json()['items']] == ['hm@example.org']
    first = login(client, 'hr@example.org')
    assert first['user']['must_change_password'] is True
    first_headers = bearer(first['access_token'])
    assert client.get('/v1/auth/me', headers=first_headers).json()['must_change_password'] is True
    assert client.get('/v1/positions', headers=first_headers).status_code == 403
    assert client.post('/v1/auth/change-password', headers=first_headers, json={"current_password":"wrong", "new_password":NEW}).status_code == 400
    assert client.post('/v1/auth/change-password', headers=first_headers, json={"current_password":TEMP, "new_password":TEMP}).status_code == 400
    assert client.post('/v1/auth/change-password', headers=first_headers, json={"current_password":TEMP, "new_password":NEW}).status_code == 200
    assert client.get('/v1/auth/me', headers=first_headers).status_code == 401
    time.sleep(1.1)  # Auth iat has second precision; cutoff rejects its entire second.
    changed = login(client, 'hr@example.org', NEW)
    assert changed['user']['must_change_password'] is False
    changed_headers = bearer(changed['access_token'])
    assert client.get('/v1/positions', headers=changed_headers).status_code == 200
    # Voluntary change: an active user who is not forced to change may still
    # rotate their own password, but only after reauthentication.
    assert client.post('/v1/auth/change-password', headers=changed_headers, json={"current_password": "wrong", "new_password": VOLUNTARY}).status_code == 400
    assert client.post('/v1/auth/change-password', headers=changed_headers, json={"current_password": NEW, "new_password": NEW}).status_code == 400
    assert client.post('/v1/auth/change-password', headers=changed_headers, json={"current_password": NEW, "new_password": VOLUNTARY}).status_code == 200
    assert client.get('/v1/auth/me', headers=changed_headers).status_code == 401
    assert client.post('/v1/auth/login', json={'email': 'hr@example.org', 'password': NEW}).status_code == 401
    time.sleep(1.1)  # Auth iat has second precision; cutoff rejects its entire second.
    voluntary = login(client, 'hr@example.org', VOLUNTARY)
    assert voluntary['user']['must_change_password'] is False
    with engine.connect() as conn:
        audit = conn.execute(text("SELECT action_type,metadata::text FROM app_private.audit_events ORDER BY created_at")).all()
    assert {row[0] for row in audit} >= {'BOOTSTRAP_ADMIN', 'CREATE_USER', 'CHANGE_TEMPORARY_PASSWORD', 'CHANGE_OWN_PASSWORD'}
    assert all(TEMP not in str(row) and NEW not in str(row) and VOLUNTARY not in str(row) for row in audit)


def test_admin_resets_member_password_and_forces_change(client, fake_auth):
    assert bootstrap(client).status_code == 201
    admin_headers = bearer(login(client, 'admin@example.org')['access_token'])
    target = fake_auth.seed('member@example.org', ['HR_RECRUITER'], name='Member')
    other = fake_auth.seed('other@example.org', ['HR_RECRUITER'], name='Other')
    other_headers = bearer(fake_auth.token(other, 'other@example.org'))
    suspended = fake_auth.seed('suspended@example.org', ['VIEWER'], name='Suspended', status='SUSPENDED')
    old_target_headers = bearer(fake_auth.token(target, 'member@example.org', int(time.time()) - 30))
    assert client.get('/v1/auth/me', headers=old_target_headers).status_code == 200
    assert client.post(f'/v1/admin/users/{target}/reset-password', headers=other_headers,
                       json={"new_password": RESET_TEMP}).status_code == 403
    weak = client.post(f'/v1/admin/users/{target}/reset-password', headers=admin_headers, json={"new_password": "short"})
    assert weak.status_code == 422 and RESET_TEMP not in weak.text
    assert client.post('/v1/admin/users/00000000-0000-0000-0000-000000000000/reset-password', headers=admin_headers,
                       json={"new_password": RESET_TEMP}).status_code == 404
    assert client.post(f'/v1/admin/users/{suspended}/reset-password', headers=admin_headers,
                       json={"new_password": RESET_TEMP}).status_code == 400
    result = client.post(f'/v1/admin/users/{target}/reset-password', headers=admin_headers,
                         json={"new_password": RESET_TEMP})
    assert result.status_code == 200, result.text
    assert result.json() == {'user_id': target, 'must_change_password': True} and RESET_TEMP not in result.text
    assert client.get('/v1/auth/me', headers=old_target_headers).status_code == 401
    assert client.post('/v1/auth/login', json={'email': 'member@example.org', 'password': TEMP}).status_code == 401
    time.sleep(1.1)  # A token issued in the reset second is also rejected by the cutoff.
    first = login(client, 'member@example.org', RESET_TEMP)
    assert first['user']['must_change_password'] is True
    first_headers = bearer(first['access_token'])
    assert client.get('/v1/positions', headers=first_headers).status_code == 403
    assert client.post('/v1/auth/change-password', headers=first_headers,
                       json={"current_password": RESET_TEMP, "new_password": FINAL}).status_code == 200
    assert client.get('/v1/auth/me', headers=first_headers).status_code == 401
    time.sleep(1.1)  # Auth iat has second precision; cutoff rejects its entire second.
    final = login(client, 'member@example.org', FINAL)
    assert final['user']['must_change_password'] is False
    assert client.get('/v1/positions', headers=bearer(final['access_token'])).status_code == 200
    with engine.connect() as conn:
        audit = conn.execute(text("SELECT action_type,metadata::text FROM app_private.audit_events ORDER BY created_at")).all()
    assert {row[0] for row in audit} >= {'RESET_USER_PASSWORD', 'CHANGE_TEMPORARY_PASSWORD'}
    assert all(RESET_TEMP not in str(row) and FINAL not in str(row) for row in audit)


def test_last_active_admin_and_concurrent_revocations(client, fake_auth):
    assert bootstrap(client).status_code == 201
    admin_a = login(client, 'admin@example.org')
    a = admin_a['user']['id']
    b = fake_auth.seed('second@example.org', ['ADMIN'], name='Second')
    a_headers = bearer(admin_a['access_token'])
    b_headers = bearer(fake_auth.token(b, 'second@example.org'))
    assert client.patch(f'/v1/admin/users/{a}', headers=a_headers, json=update('Admin', 'SUSPENDED', ['ADMIN'])).status_code == 409
    assert client.patch(f'/v1/admin/users/{a}', headers=a_headers, json=update('Admin', 'ACTIVE', ['HR_RECRUITER'])).status_code == 409
    upper_sub = bearer(fake_auth.token(a.upper(), 'admin@example.org'))
    assert client.patch(f'/v1/admin/users/{a}', headers=upper_sub, json=update('Admin', 'ACTIVE', ['HR_RECRUITER'])).status_code == 409
    requests = [(a, b_headers, 'Admin'), (b, a_headers, 'Second')]
    def suspend(item):
        target, headers, name = item
        return client.patch(f'/v1/admin/users/{target}', headers=headers, json=update(name, 'SUSPENDED', ['ADMIN'])).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(suspend, requests))
    assert results == [200, 403]
    with engine.connect() as conn:
        active = conn.execute(text("""SELECT count(*) FROM app_private.user_profiles p JOIN app_private.user_role_assignments r USING (user_id)
            WHERE p.account_status='ACTIVE' AND r.role_code='ADMIN' AND r.revoked_at IS NULL""")).scalar_one()
    assert active == 1
    assert client.get('/v1/auth/bootstrap-status').json() == {"available": False}


def test_hm_directory_position_creation_and_role_removal(client, fake_auth):
    assert bootstrap(client).status_code == 201
    admin = bearer(login(client, 'admin@example.org')['access_token'])
    hr = fake_auth.seed('hr@example.org', ['HR_RECRUITER', 'HIRING_MANAGER'], name='HR Person')
    hm = fake_auth.seed('hm@example.org', ['HIRING_MANAGER'], name='HM Person')
    not_hm = fake_auth.seed('viewer@example.org', ['VIEWER'], name='Viewer')
    disabled_hm = fake_auth.seed('disabled@example.org', ['HIRING_MANAGER'], name='Disabled', status='SUSPENDED')
    hr_headers = bearer(fake_auth.token(hr, 'hr@example.org'))
    response = client.get('/v1/users?role=HIRING_MANAGER', headers=hr_headers)
    assert response.status_code == 200, response.text
    assert [u['user_id'] for u in response.json()] == [hm]
    payload = {"department_id": make_department(), "title": "Engineer", "jd_content": "Synthetic JD", "hiring_manager_user_id": hm}
    for bad in [hr, not_hm, disabled_hm]:
        assert client.post('/v1/positions', headers=hr_headers, json={**payload, "hiring_manager_user_id": bad}).status_code == 400
    result = client.post('/v1/positions', headers=hr_headers, json=payload)
    assert result.status_code == 201, result.text
    assert result.json()['position_code'] == 'REQ-ENG-001'
    position = result.json()['position_id']
    hm_headers = bearer(fake_auth.token(hm, 'hm@example.org'))
    assert client.get('/v1/positions', headers=hm_headers).json()[0]['position_id'] == position
    changed = client.patch(f'/v1/admin/users/{hm}', headers=admin, json=update('HM Person', 'ACTIVE', ['VIEWER']))
    assert changed.status_code == 200, changed.text
    assert client.get('/v1/positions', headers=hm_headers).json() == []
    assert client.patch(f'/v1/admin/users/{hm}', headers=admin, json=update('HM Person', 'ACTIVE', ['HIRING_MANAGER'])).status_code == 200
    assert client.get('/v1/positions', headers=hm_headers).json() == []  # no automatic restoration
    with engine.connect() as conn:
        assignment = conn.execute(text("SELECT revoked_at FROM app_private.position_assignments WHERE position_id=:p AND user_id=:u AND position_role='HIRING_MANAGER'"), {"p":position,"u":hm}).scalar_one()
    assert assignment is not None


@pytest.mark.parametrize('creator_role', ['ADMIN', 'HR_LEAD'])
def test_removing_last_hr_capable_role_revokes_recruiter_assignments(client, fake_auth, creator_role):
    assert bootstrap(client).status_code == 201
    admin = bearer(login(client, 'admin@example.org')['access_token'])
    creator = fake_auth.seed('creator@example.org', [creator_role], name='Creator')
    hm = fake_auth.seed('hm@example.org', ['HIRING_MANAGER'], name='HM')
    headers = bearer(fake_auth.token(creator, 'creator@example.org'))
    payload = {'department_id': make_department('Creator', 'REQ-CREATOR-{SEQ:000}'), 'title': 'Engineer', 'jd_content': 'Synthetic JD',
               'hiring_manager_user_id': hm}
    created = client.post('/v1/positions', headers=headers, json=payload)
    assert created.status_code == 201, created.text
    position = created.json()['position_id']
    result = client.patch(f'/v1/admin/users/{creator}', headers=admin, json=update('Creator', 'ACTIVE', ['VIEWER']))
    assert result.status_code == 200, result.text
    with engine.connect() as conn:
        assignment = conn.execute(text("""SELECT revoked_at FROM app_private.position_assignments
            WHERE position_id=:p AND user_id=:u AND position_role='HR_RECRUITER'"""), {'p': position, 'u': creator}).scalar_one()
    assert assignment is not None
    assert client.get('/v1/positions', headers=headers).json() == []
    assert client.post('/v1/positions', headers=headers, json={**payload, 'title': 'Must fail'}).status_code == 403


def test_suspended_then_reactivated_account_cannot_reuse_old_access_token(client, fake_auth):
    assert bootstrap(client).status_code == 201
    admin = bearer(login(client, 'admin@example.org')['access_token'])
    hm = fake_auth.seed('hm@example.org', ['HIRING_MANAGER'], name='HM')
    old = bearer(fake_auth.token(hm, 'hm@example.org', int(time.time()) - 30))
    assert client.get('/v1/auth/me', headers=old).status_code == 200
    assert client.patch(f'/v1/admin/users/{hm}', headers=admin, json=update('HM', 'SUSPENDED', ['HIRING_MANAGER'])).status_code == 200
    assert client.get('/v1/auth/me', headers=old).status_code == 403
    assert client.patch(f'/v1/admin/users/{hm}', headers=admin, json=update('HM', 'ACTIVE', ['HIRING_MANAGER'])).status_code == 200
    assert client.get('/v1/auth/me', headers=old).status_code == 401
    no_iat = jwt.encode({'sub':hm, 'aud':'authenticated', 'email':'hm@example.org', 'exp':int(time.time())+100}, SECRET, algorithm='HS256')
    assert client.get('/v1/auth/me', headers=bearer(no_iat)).status_code == 401


def test_auth_password_policy_errors_are_safe_and_actionable(client, fake_auth, monkeypatch):
    def reject_create(self, data):
        raise AuthError(422, 'weak_password')
    with monkeypatch.context() as patch:
        patch.setattr(FakeAuthAdmin, 'create_user', reject_create)
        rejected = bootstrap(client)
        assert rejected.status_code == 400 and 'chính sách' in rejected.text and TEMP not in rejected.text
    assert bootstrap(client).status_code == 201
    admin_headers = bearer(login(client, 'admin@example.org')['access_token'])
    result = client.post('/v1/admin/users', headers=admin_headers, json={
        'email': 'hr@example.org', 'display_name': 'HR', 'password': TEMP, 'roles': ['HR_RECRUITER'],
    })
    assert result.status_code == 201
    temp_headers = bearer(login(client, 'hr@example.org')['access_token'])
    def reject_update(self, data):
        raise AuthError(422, 'weak_password')
    monkeypatch.setattr(FakeAuthSession, 'update_user', reject_update)
    changed = client.post('/v1/auth/change-password', headers=temp_headers,
                          json={'current_password': TEMP, 'new_password': NEW})
    assert changed.status_code == 400 and 'chính sách' in changed.text and NEW not in changed.text
    assert client.get('/v1/positions', headers=temp_headers).status_code == 403


def test_definite_precommit_failure_compensates_auth_identity(client, fake_auth, monkeypatch):
    from app.services import accounts
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic db-side failure')
    monkeypatch.setattr(accounts, 'json', SimpleNamespace(dumps=fail))
    result = bootstrap(client)
    assert result.status_code == 503
    assert not fake_auth.users and fake_auth.deleted_ids == fake_auth.created_ids
    assert client.get('/v1/auth/bootstrap-status').json() == {"available": True}


@pytest.mark.parametrize('committed', [True, False])
def test_unknown_db_commit_is_not_compensated(client, fake_auth, monkeypatch, committed):
    from app.api import auth
    original = auth.SessionLocal
    class UncertainSession:
        def __init__(self): self.inner = original()
        def __getattr__(self, name): return getattr(self.inner, name)
        def commit(self):
            if committed: self.inner.commit()
            raise RuntimeError('synthetic unknown commit outcome')
    monkeypatch.setattr(auth, 'SessionLocal', UncertainSession)
    result = bootstrap(client)
    assert result.status_code == 503 and len(fake_auth.users) == 1 and fake_auth.deleted_ids == []
    assert client.get('/v1/auth/bootstrap-status').json()['available'] is (not committed)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM app_private.user_profiles")).scalar_one() == (1 if committed else 0)
    if committed:
        assert bootstrap(client, 'another@example.org').status_code == 409


def test_unknown_auth_result_is_left_for_manual_reconciliation(client, fake_auth):
    fake_auth.fail_after_create = True
    result = bootstrap(client)
    assert result.status_code == 503 and 'Supabase Auth' in result.json()['detail']
    assert len(fake_auth.users) == 1 and fake_auth.deleted_ids == []
    assert client.get('/v1/auth/bootstrap-status').json() == {"available": True}
