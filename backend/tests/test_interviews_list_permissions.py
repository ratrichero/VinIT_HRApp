"""`GET /interviews` — mỗi đường vào có mức quyền riêng.

Lỗi được audit `doc/AUDIT_2026-11-27_NANG_CAP_GAN_DAY.md` tìm ra: gọi list
**không tham số** thì `clauses` vẫn là `["1=1"]`, vì việc kiểm tra quyền chỉ nằm
trong `if position_id:` và `if mine:`. Nên bất kỳ tài khoản đang hoạt động —
người phỏng vấn, OBSERVER, HM — nhận tới 200 buổi của **mọi vị trí** kèm
`candidate_name`, tức toàn bộ lịch phỏng vấn và tên ứng viên của công ty.

Docstring của chính hàm nói ngược lại điều đó, `get_interview` (một buổi) thì có
kiểm tra 403 — chỉ đường list là thiếu, và không test nào khoá.

Test này dựng DB giả, không cần PostgreSQL: nó kiểm **quyết định** (có ném 403
hay không, và có thêm mệnh đề lọc vào SQL hay không), không kiểm dữ liệu trả về.
"""
import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api import interviews as module

ACTOR = str(uuid.uuid4())
POSITION = str(uuid.uuid4())
OTHER_POSITION = str(uuid.uuid4())
APPLICATION = str(uuid.uuid4())


class _Result:
    def __init__(self, *, scalar=None, one=None, all_=None, first=None):
        self._scalar, self._one, self._all, self._first = scalar, one, all_ or [], first

    def mappings(self): return self
    def scalars(self): return self
    def scalar_one(self): return self._scalar
    def one(self): return self._one
    def all(self): return self._all
    def first(self): return self._first


class FakeDB:
    def __init__(self, results):
        self._results = list(results)
        self.issued = []
        self.closed = False

    def execute(self, statement, params=None):
        self.issued.append((str(statement), params or {}))
        if not self._results:
            raise AssertionError(f"execute thừa: {str(statement)[:90]}")
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        self.closed = True

    def sql(self):
        return " ".join(s for s, _ in self.issued)


def _call(db, **kwargs):
    # `mine` có mặc định `Query(False)` — một ĐỐI TƯỢNG, không phải `False`.
    # Gọi hàm trực tiếp (không qua FastAPI) thì mặc định đó là truthy, nên phải
    # truyền tường minh. Qua HTTP, FastAPI mới thay bằng giá trị thật.
    kwargs.setdefault("mine", False)
    kwargs.setdefault("user", {"user_id": ACTOR})
    with patch.object(module, "SessionLocal", lambda: db), \
         patch.object(module, "_require_active", lambda *_a, **_k: None):
        return module.list_interviews(**kwargs)


def test_bare_list_is_forbidden_for_a_regular_hr_recruiter():
    """Đường nguy hiểm nhất: không tham số, không phải HR toàn cục."""
    db = FakeDB([
        _Result(scalar=False),   # không phải ADMIN/HR_LEAD
    ])
    with pytest.raises(HTTPException) as caught:
        _call(db)
    assert caught.value.status_code == 403
    # Không được chạy câu SELECT danh sách nào — chặn TRƯỚC khi đọc dữ liệu.
    assert "interview_participants" not in db.sql() or len(db.issued) == 1


def test_bare_list_is_allowed_for_hr_lead_and_admin():
    """Người vốn xem được mọi vị trí thì không cần nêu vị trí."""
    db = FakeDB([
        _Result(scalar=True),      # là ADMIN/HR_LEAD
        _Result(all_=[]),          # câu SELECT danh sách
    ])
    assert _call(db) == []


def test_mine_still_works_for_anyone_active():
    """`mine=true` là lịch của chính mình — không đòi quyền vị trí."""
    db = FakeDB([_Result(all_=[])])
    assert _call(db, mine=True) == []
    sql, params = db.issued[0]
    assert "ip.user_id = :actor" in sql
    assert params["actor"] == ACTOR


def test_position_scoped_list_checks_position_rights():
    db = FakeDB([_Result(scalar=False)])
    with pytest.raises(HTTPException) as caught:
        _call(db, position_id=uuid.UUID(POSITION))
    assert caught.value.status_code == 403


def test_application_scoped_list_checks_rights_on_the_owning_position():
    """Màn chi tiết ứng viên lọc theo hồ sơ — quyền xét trên vị trí của hồ sơ."""
    db = FakeDB([
        _Result(first={"position_id": POSITION}),   # hồ sơ thuộc vị trí nào
        _Result(scalar=False),                       # không có quyền vị trí đó
    ])
    with pytest.raises(HTTPException) as caught:
        _call(db, application_id=uuid.UUID(APPLICATION))
    assert caught.value.status_code == 403


def test_application_scoped_list_filters_in_sql_not_in_the_client():
    """Lọc ở máy chủ: trước đây client kéo 200 buổi của mọi vị trí rồi tự lọc."""
    db = FakeDB([
        _Result(first={"position_id": POSITION}),
        _Result(scalar=True),
        _Result(all_=[]),
    ])
    assert _call(db, application_id=uuid.UUID(APPLICATION)) == []
    sql, params = db.issued[-1]
    assert "i.application_id = :application" in sql
    assert params["application"] == APPLICATION


def test_application_scoped_list_404s_for_an_unknown_application():
    # NotFoundError là lớp riêng của dự án (mang `code` cho client), không phải
    # HTTPException — bắt nhầm kiểu thì test pass mà endpoint vẫn sai.
    from app.core.exceptions import NotFoundError

    db = FakeDB([_Result(first=None)])
    with pytest.raises(NotFoundError) as caught:
        _call(db, application_id=uuid.UUID(APPLICATION))
    assert caught.value.status_code == 404


def test_bare_list_never_reaches_the_database_for_unprivileged_users():
    """Chốt chặn phải nằm TRƯỚC câu SELECT, không phải sau rồi lọc bớt."""
    db = FakeDB([_Result(scalar=False)])
    with pytest.raises(HTTPException):
        _call(db)
    assert len(db.issued) == 1, f"đã chạy thêm {len(db.issued) - 1} câu truy vấn trước khi chặn"
