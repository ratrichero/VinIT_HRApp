"""Hợp đồng `requirement_spec` giữa giao diện và schema.

Bối cảnh — một lỗi có thật, đã lọt qua vì kiểm sai cách: giao diện chỉ cho HR
chọn *loại* tiêu chí nên gửi `{"kind": "YEARS"}` trần. Schema (cố ý, theo audit
M1) đòi `min_years` khi kind=YEARS ⇒ **mọi lần đổi loại đều 422**. Lúc kiểm tôi
chỉ thử `{}` nên tưởng schema chấp nhận spec thiếu trường.

Ranh giới trách nhiệm, và test này ghim đúng ranh giới đó:

* **Schema giữ chặt.** Một tiêu chí YEARS không có ngưỡng là tiêu chí không ai
  quyết nó so với cái gì; cho lưu là để nó lọt vào chấm điểm mà không có tiêu
  chuẩn. Audit M1 chốt điều này có chủ đích.
* **Giao diện phải gửi đủ.** Nếu HR chọn YEARS mà form chưa có ngưỡng, form
  phải hỏi hoặc điền sẵn — không được gửi lên một spec sẽ bị từ chối.
"""
import pytest
from pydantic import ValidationError

from app.schemas.criteria import RequirementSpec
from app.services.deterministic_matching import deterministic_matcher

CV = (
    "Nguyen Van A\n"
    "Kỹ sư phần mềm, 5 năm kinh nghiệm backend.\n"
    "Học vấn: Bằng đại học chuyên ngành Công nghệ thông tin.\n"
    "Kỹ năng: Python, FastAPI, PostgreSQL.\n"
    "Ngoại ngữ: Tiếng Anh IELTS 7.0.\n"
)


def criterion(name, description, keywords, spec=None):
    return {
        "criterion_id": "c1", "name": name, "description": description,
        "category": "MUST_HAVE", "weight_in_group": 100.0,
        "expected_evidence_keywords": keywords,
        "requirement_spec": spec,
    }


def test_complete_spec_for_each_kind_is_accepted():
    """Thứ mà `buildSpec()` phải dựng ra, và schema phải nhận."""
    accepted = [
        {"kind": "SKILL", "terms": ["python"]},
        {"kind": "CERTIFICATION", "terms": ["aws"]},
        {"kind": "YEARS", "terms": ["python"], "min_years": 3},
        {"kind": "DEGREE", "terms": ["cntt"], "required_degree_level": 3},
        {"kind": "LANGUAGE", "required_languages": ["english"]},
    ]
    for raw in accepted:
        assert RequirementSpec(**raw).kind == raw["kind"]


def test_kind_without_its_threshold_is_rejected_on_purpose():
    """Audit M1: YEARS không có ngưỡng thì không được lưu.

    Đây KHÔNG phải rào thừa. Tiêu chí "số năm kinh nghiệm" mà không nêu bao
    nhiêu năm là tiêu chí chưa có tiêu chuẩn; nếu vẫn lưu thì nó đi vào chấm
    điểm và mỗi lần chấm lại cho một kết quả khác nhau tuỳ dữ liệu CV.
    """
    with pytest.raises(ValidationError):
        RequirementSpec(kind="YEARS", terms=["python"])
    with pytest.raises(ValidationError):
        RequirementSpec(kind="DEGREE", terms=["cntt"])


def test_engine_still_handles_partial_specs_that_reach_the_db():
    """Dữ liệu cũ có thể thiếu trường dù schema mới chặt hơn.

    ``_materialize_requirement_specs`` chỉ điền spec khi trống, và cột là JSONB
    tự do — nên engine vẫn phải chịu được spec khuyết. Nếu không, lỗi dời từ
    422 (lúc lưu, HR thấy ngay) sang 500 (lúc chấm, sau khi đã duyệt).
    """
    for raw in (
        {"kind": "YEARS", "terms": ["python"]},
        {"kind": "DEGREE", "terms": ["cntt"]},
        {"kind": "SKILL", "terms": ["python"]},
    ):
        result = deterministic_matcher.evaluate_criteria(
            CV, [criterion("Kinh nghiệm", "Mô tả chung", [], raw)], {})
        assert "findings" in result


def test_degree_without_a_level_never_reports_strong_match():
    """Ngưỡng trống nghĩa là *chưa ai quyết*, không phải *ai cũng đạt*.

    Đây chính là lý do schema phải chặn: nếu tiêu chí này lọt vào chấm điểm và
    báo khớp mạnh, ứng viên được điểm cho một tiêu chí chưa có tiêu chuẩn.
    """
    result = deterministic_matcher.evaluate_criteria(
        CV,
        [criterion("Học vấn", "Có bằng cấp liên quan", [],
                   {"kind": "DEGREE", "terms": ["hoc van"]})],
        {})
    for finding in result.get("findings", []):
        assert finding.get("outcome") != "STRONG_MATCH"
