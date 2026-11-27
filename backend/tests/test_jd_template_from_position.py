"""Lấy JD từ vị trí khác trong cùng Nhóm vị trí.

Bốn quyết định đã chốt với người dùng, mỗi cái có test ở đây:

1. **Sao chép vào ô soạn thảo**, không lưu thẳng và không chuyển hẳn. Nên
   endpoint này chỉ ĐỌC: sau khi gọi, số phiên bản JD của cả hai vị trí không đổi.
2. **Chỉ cùng Nhóm vị trí.** Vị trí khác nhóm trả 404, và trả cùng mã với
   "không tồn tại" để không cho phép dò.
3. **Chỉ cần quyền trên vị trí ĐÍCH.** HR phụ trách vị trí mới lấy được JD từ
   vị trí của đồng nghiệp — nếu không, tính năng mất gần hết công dụng.
4. **Chỉ trả nội dung JD**, không trả dữ liệu tuyển dụng khác của vị trí nguồn.
"""
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db.database import engine
from test_phase1_integration import client as client, seed as seed  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get('TEST_DATABASE_URL'),
    reason='Disposable PostgreSQL required',
)


def _family(conn, name='IT_DIGITAL'):
    row = conn.execute(text("SELECT job_family_id FROM app_private.job_families WHERE code = :c"), {'c': name}).first()
    if row:
        return str(row[0])
    return str(conn.execute(text(
        "INSERT INTO app_private.job_families(code,name) VALUES (:c,:n) RETURNING job_family_id"
    ), {'c': name, 'n': name}).scalar_one())


def _set_family(conn, position_id, family_id):
    conn.execute(text("UPDATE app_private.positions SET job_family_id = :f WHERE position_id = :p"),
                 {'f': family_id, 'p': position_id})


def _add_jd(conn, position_id, content, user_id):
    return conn.execute(text("""
        INSERT INTO app_private.jd_versions(position_id, version_number, content_text, created_by)
        SELECT :p, COALESCE(MAX(version_number),0)+1, :c, :u FROM app_private.jd_versions WHERE position_id = :p
        RETURNING version_number, jd_version_id
    """), {'p': position_id, 'c': content, 'u': user_id}).mappings().one()


def _jd_count(conn, position_id):
    return conn.execute(text(
        "SELECT count(*) FROM app_private.jd_versions WHERE position_id = :p"), {'p': position_id}).scalar_one()


def test_copies_jd_from_same_family_and_writes_nothing(client, seed):
    """Đường thành công: cùng nhóm, cả hai vị trí cùng một người phụ trách."""
    with engine.begin() as conn:
        family = _family(conn)
        _set_family(conn, seed['pos'], family)
        _set_family(conn, seed['pos2'], family)
        _add_jd(conn, seed['pos2'], 'JD của vị trí nguồn: Backend Python 3 năm.', seed['hr2'])
        before_source = _jd_count(conn, seed['pos2'])
        before_target = _jd_count(conn, seed['pos'])

    # hr (phụ trách pos) lấy JD từ pos2 (do hr2 phụ trách): KHÔNG cần quyền trên pos2.
    response = client.post(
        f"/v1/positions/{seed['pos']}/jd-template",
        json={'source_position_id': seed['pos2']},
        headers={'x-test-user': seed['hr']},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['content_text'].startswith('JD của vị trí nguồn')
    assert body['source_position_id'] == seed['pos2']
    assert body['source_version_number'] >= 1

    # Chỉ đọc: không bên nào có thêm phiên bản JD.
    with engine.begin() as conn:
        assert _jd_count(conn, seed['pos2']) == before_source
        assert _jd_count(conn, seed['pos']) == before_target


def test_rejects_source_in_another_family_with_the_same_error_as_missing(client, seed):
    """Khác nhóm và không tồn tại phải trả cùng một câu.

    Nói khác nhau là cho phép dò: gửi một UUID bất kỳ rồi xem câu trả lời để
    biết vị trí đó có tồn tại và thuộc nhóm nào.
    """
    with engine.begin() as conn:
        it = _family(conn)
        ops = _family(conn, 'ADMIN_OPERATIONS')
        _set_family(conn, seed['pos'], it)
        _set_family(conn, seed['pos2'], ops)
        # Có JD đi nữa thì khác nhóm vẫn phải 404 — nếu không, test này chỉ đang
        # kiểm "vị trí chưa có JD" chứ không kiểm ranh giới nhóm.
        _add_jd(conn, seed['pos2'], 'JD của vị trí khác nhóm.', seed['hr2'])

    response = client.post(
        f"/v1/positions/{seed['pos']}/jd-template",
        json={'source_position_id': seed['pos2']},
        headers={'x-test-user': seed['hr']},
    )
    assert response.status_code == 404
    other_family = response.json()['detail']

    with engine.begin() as conn:
        _set_family(conn, seed['pos'], it)
    missing = client.post(
        f"/v1/positions/{seed['pos']}/jd-template",
        json={'source_position_id': str(uuid4())},
        headers={'x-test-user': seed['hr']},
    )
    assert missing.status_code == 404
    assert missing.json()['detail'] == other_family


def test_requires_edit_rights_on_the_target_position(client, seed):
    """Người không phụ trách vị trí đích thì không lấy được gì."""
    with engine.begin() as conn:
        family = _family(conn)
        _set_family(conn, seed['pos'], family)
        _set_family(conn, seed['pos2'], family)

    # hm chỉ là HIRING_MANAGER trên pos, không phải HR_RECRUITER
    response = client.post(
        f"/v1/positions/{seed['pos']}/jd-template",
        json={'source_position_id': seed['pos2']},
        headers={'x-test-user': seed['hm']},
    )
    assert response.status_code == 403


def test_source_must_differ_from_target(client, seed):
    with engine.begin() as conn:
        _set_family(conn, seed['pos'], _family(conn))
    response = client.post(
        f"/v1/positions/{seed['pos']}/jd-template",
        json={'source_position_id': seed['pos']},
        headers={'x-test-user': seed['hr']},
    )
    assert response.status_code == 400


def test_target_without_a_family_cannot_copy(client, seed):
    """Vị trí đích chưa có Nhóm vị trí thì không có gì để đối chiếu."""
    with engine.begin() as conn:
        conn.execute(text("UPDATE app_private.positions SET job_family_id = NULL WHERE position_id = :p"),
                     {'p': seed['pos']})
    response = client.post(
        f"/v1/positions/{seed['pos']}/jd-template",
        json={'source_position_id': seed['pos2']},
        headers={'x-test-user': seed['hr']},
    )
    assert response.status_code == 400
    assert 'Nhóm vị trí' in response.json()['detail']


def test_response_carries_only_jd_text_not_candidate_data(client, seed):
    """Chỉ nội dung JD — không dữ liệu tuyển dụng nào khác của vị trí nguồn."""
    with engine.begin() as conn:
        family = _family(conn)
        _set_family(conn, seed['pos'], family)
        _set_family(conn, seed['pos2'], family)
        # seed chỉ tạo JD cho `pos`; vị trí nguồn cần có JD mới lấy được.
        _add_jd(conn, seed['pos2'], 'JD nguồn để kiểm hình dạng phản hồi.', seed['hr2'])

    response = client.post(
        f"/v1/positions/{seed['pos']}/jd-template",
        json={'source_position_id': seed['pos2']},
        headers={'x-test-user': seed['hr']},
    )
    assert response.status_code == 200
    keys = set(response.json())
    assert keys == {
        'source_position_id', 'source_position_code', 'source_position_title',
        'source_version_number', 'content_text', 'note',
    }
    # Không kèm danh sách ứng viên hay số lượng hồ sơ.
    assert 'applications' not in response.text
    assert 'Candidate' not in response.text
