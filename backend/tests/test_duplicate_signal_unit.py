"""In-process authorization contract; PostgreSQL scope/races are integration-tested."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.api import positions
from app.core.security import get_current_user
from app.main import app


class Result:
    def __init__(self, value):
        self.value = value
    def scalar_one_or_none(self):
        return self.value
    def scalars(self):
        return self
    def mappings(self):
        return self
    def all(self):
        return self.value


class FakeDB:
    def __init__(self, role, account="ACTIVE"):
        self.role = role
        self.account = account
        self.queries = []
    def execute(self, sql, params):
        query = str(sql)
        self.queries.append(query)
        if "account_status FROM" in query:
            return Result(self.account)
        if "user_role_assignments" in query:
            return Result([self.role] if self.role in ("ADMIN", "HR_LEAD") else [])
        if "position_assignments" in query:
            return Result([self.role] if self.role in ("HR_RECRUITER", "POSITION_HR_LEAD") else [])
        assert "a1.position_id = d.position_id" in query and "a2.position_id = d.position_id" in query
        assert "d.position_id = :position_id" in query
        return Result([])
    def close(self):
        pass


@pytest.mark.parametrize("role,account,expected", [
    ("HR_RECRUITER", "ACTIVE", 200), ("HR_LEAD", "ACTIVE", 200),
    ("ADMIN", "ACTIVE", 200), ("HIRING_MANAGER", "ACTIVE", 403),
    ("UNASSIGNED", "ACTIVE", 403), ("HR_RECRUITER", "LOCKED", 403),
])
def test_duplicate_read_roles(monkeypatch, role, account, expected):
    db = FakeDB(role, account)
    monkeypatch.setattr(positions, "SessionLocal", lambda: db)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": str(uuid4())}
    try:
        with TestClient(app) as client:
            response = client.get(f"/v1/positions/{uuid4()}/duplicate-signals")
        assert response.status_code == expected, response.text
        if expected == 200:
            assert response.json() == []
    finally:
        app.dependency_overrides.clear()
