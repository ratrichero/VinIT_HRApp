"""`GET /interviews` trên PostgreSQL thật — quyền và phạm vi của từng đường vào.

Vì sao có file này bên cạnh `test_interviews_list_permissions.py`:

* File kia dựng DB giả nên chỉ kiểm **quyết định** (có ném 403 hay không, SQL có
  thêm mệnh đề lọc hay không). Nó không chứng minh được câu trả lời thật sự
  chứa đúng buổi của mình và **không** chứa buổi của người khác.
* Lỗi gốc của audit là "gọi không tham số thì trả lịch của mọi vị trí kèm tên
  ứng viên". Chỉ một test đọc dữ liệu thật mới khoá được điều đó.

File tự dựng dữ liệu riêng (vị trí, hồ sơ, hai buổi của hai người phỏng vấn khác
nhau) rồi xoá phần vị trí trước mỗi lần chạy, nên không phụ thuộc thứ tự test.
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import get_current_user
from app.db.database import engine
from app.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL to a disposable local migrated *_test database",
)

T0 = datetime(2026, 12, 1, 7, 0, tzinfo=timezone.utc)


def headers(user):
    return {"x-test-user": user}


@pytest.fixture
def client():
    async def identity(request):
        return {"user_id": request.headers["x-test-user"], "email": "test@example.org"}

    from starlette.requests import Request

    identity.__annotations__["request"] = Request
    app.dependency_overrides[get_current_user] = identity
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
    test_client.close()


@pytest.fixture
def calendar():
    """Hai buổi của hai người phỏng vấn khác nhau, cùng một vị trí.

    `interviewer` chỉ là người tham gia — không có vai trò HR nào. `outsider`
    cũng vậy, nhưng tham gia buổi khác. Nhờ hai buổi khác nhau mà phép kiểm
    `mine=true` phân biệt được "lọc đúng" với "trả hết".
    """
    ids = {key: str(uuid4()) for key in (
        "hr", "interviewer", "outsider", "pos", "app_a", "app_b", "iv_a", "iv_b",
    )}
    with engine.begin() as conn:
        # RESTART IDENTITY: CASCADE xoá `audit_events` nhưng không đặt lại
        # `app_private.audit_event_chain_seq`, nên lần chạy sau sẽ nối tiếp
        # chuỗi hash của lần trước trên cùng DB.
        conn.execute(text("TRUNCATE app_private.positions RESTART IDENTITY CASCADE"))
        for key in ("hr", "interviewer", "outsider"):
            conn.execute(text("INSERT INTO auth.users(id) VALUES (:id)"), {"id": ids[key]})
            conn.execute(
                text("INSERT INTO app_private.user_profiles(user_id, display_name) VALUES (:id, :name)"),
                {"id": ids[key], "name": key.upper()},
            )
        conn.execute(
            text("INSERT INTO app_private.user_role_assignments(user_id, role_code) VALUES (:id, 'HR_RECRUITER')"),
            {"id": ids["hr"]},
        )
        conn.execute(
            text("INSERT INTO app_private.positions(position_id, position_code, title, created_by) VALUES (:id, :code, 'Backend', :hr)"),
            {"id": ids["pos"], "code": ids["pos"], "hr": ids["hr"]},
        )
        conn.execute(
            text("INSERT INTO app_private.position_assignments(position_id, user_id, position_role) VALUES (:pos, :hr, 'HR_RECRUITER')"),
            {"pos": ids["pos"], "hr": ids["hr"]},
        )
        for key, name in (("app_a", "Candidate A"), ("app_b", "Candidate B")):
            conn.execute(
                text("INSERT INTO app_private.applications(application_id, position_id, created_by) VALUES (:id, :pos, :hr)"),
                {"id": ids[key], "pos": ids["pos"], "hr": ids["hr"]},
            )
            conn.execute(
                text("INSERT INTO app_private.application_identities(application_id, display_name) VALUES (:id, :name)"),
                {"id": ids[key], "name": name},
            )
        for iv, app, participant in (("iv_a", "app_a", "interviewer"), ("iv_b", "app_b", "outsider")):
            conn.execute(
                text("""
                    INSERT INTO app_private.interviews
                        (interview_id, application_id, round_number, starts_at, ends_at, location_kind, created_by)
                    VALUES (:id, :app, 1, :starts, :ends, 'ONSITE', :hr)
                """),
                {"id": ids[iv], "app": ids[app], "starts": T0, "ends": T0 + timedelta(hours=1), "hr": ids["hr"]},
            )
            conn.execute(
                text("INSERT INTO app_private.interview_participants(interview_id, user_id, participant_role) VALUES (:iv, :user, 'INTERVIEWER')"),
                {"iv": ids[iv], "user": ids[participant]},
            )
    return ids


def test_bare_list_is_forbidden_for_an_interviewer(calendar, client):
    """Người phỏng vấn gọi list không tham số phải nhận 403, không phải lịch của cả công ty."""
    response = client.get("/v1/interviews", headers=headers(calendar["interviewer"]))
    assert response.status_code == 403, response.text
    # Không được rò tên ứng viên qua thân lỗi.
    assert "Candidate" not in response.text


def test_mine_true_returns_only_my_own_sessions(calendar, client):
    """`mine=true` vẫn dùng được cho người phỏng vấn, và chỉ trả buổi của chính họ."""
    response = client.get("/v1/interviews", params={"mine": "true"}, headers=headers(calendar["interviewer"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["interview_id"] for item in body] == [calendar["iv_a"]]
    assert body[0]["candidate_name"] == "Candidate A"
    # Buổi của người khác không được lọt vào, dù cùng vị trí.
    assert calendar["iv_b"] not in [item["interview_id"] for item in body]


def test_hr_still_sees_the_whole_position_calendar(calendar, client):
    """Đối chứng: 403 ở trên là do thiếu quyền, không phải vì endpoint chặn tất cả."""
    response = client.get("/v1/interviews", params={"position_id": calendar["pos"]}, headers=headers(calendar["hr"]))
    assert response.status_code == 200, response.text
    assert {item["interview_id"] for item in response.json()} == {calendar["iv_a"], calendar["iv_b"]}


def test_application_scoped_list_returns_only_that_application(calendar, client):
    """Màn chi tiết hồ sơ lọc theo hồ sơ: một buổi, không phải cả lịch vị trí."""
    response = client.get(
        "/v1/interviews", params={"application_id": calendar["app_a"]}, headers=headers(calendar["hr"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["interview_id"] for item in body] == [calendar["iv_a"]]
    assert [item["candidate_name"] for item in body] == ["Candidate A"]


def test_application_scoped_list_is_forbidden_for_an_interviewer(calendar, client):
    """Người phỏng vấn không phải HR của vị trí: lịch của hồ sơ là đường của HR."""
    response = client.get(
        "/v1/interviews", params={"application_id": calendar["app_a"]}, headers=headers(calendar["interviewer"]),
    )
    assert response.status_code == 403, response.text
