"""Ba mảnh của cùng một lỗi: tiêu chí "bằng cấp" không nêu bậc.

Audit `doc/AUDIT_2026-11-27_NANG_CAP_GAN_DAY.md` tìm ra ba chỗ, và chúng phải
được sửa cùng nhau — sửa một chỗ thì lỗi chỉ đổi hình dạng:

* (a) ``if kind == "DEGREE" and required_degree is None: required_degree = None``
  là dead code, chẳng xử lý gì.
* (b) ``_schema_safe_spec`` **bỏ** spec khỏi response khi thiếu ngưỡng, nên HR
  không bao giờ thấy ô "Bậc bằng tối thiểu" để điền — đúng ô cần điền lại bị giấu.
* (c) ``required = spec.required_degree_level or 3`` chấm ngầm theo bậc đại học.

Hệ quả người dùng thấy: giao diện ghi "Để trống thì tiêu chí chỉ dò từ khoá",
máy lại so với bậc đại học; và bấm Lưu trong trạng thái đó thì spec DEGREE bị
ghi đè thành SKILL.
"""
import logging

import pytest
from pydantic import ValidationError

from app.api.criteria import _schema_safe_spec, _sanitize_criteria_response
from app.schemas.criteria import RequirementSpec
from app.services.deterministic_matching import deterministic_matcher

logging.disable(logging.CRITICAL)

CV_COLLEGE = """Nguyen Van A
Học vấn: Bằng cao đẳng chuyên ngành Công nghệ thông tin.
Kỹ năng: Python.
"""

CV_UNIVERSITY = """Nguyen Van A
Học vấn: Bằng đại học chuyên ngành Công nghệ thông tin.
Kỹ năng: Python.
"""


def criterion(name, description, keywords, spec=None):
    return {
        "criterion_id": "c1", "name": name, "description": description,
        "category": "MUST_HAVE", "weight_in_group": 100.0,
        "expected_evidence_keywords": keywords, "requirement_spec": spec,
    }


# --- (b) response phải GIỮ spec và đánh cờ, không bỏ -------------------------

def test_spec_without_threshold_is_kept_and_flagged():
    """HR phải thấy được loại DEGREE để có ô "Bậc bằng tối thiểu" mà điền."""
    spec, pending = _schema_safe_spec(
        {"kind": "DEGREE", "terms": ["hoc van"], "required_degree_level": None})
    assert pending is True
    assert spec is not None, "spec bị bỏ → giao diện đọc ra SKILL → giấu mất ô bậc bằng"
    assert spec["kind"] == "DEGREE"
    # Giá trị điền tạm phải qua được schema, nhưng KHÔNG phải bậc HR đã chọn.
    RequirementSpec.model_validate(spec)


def test_spec_with_threshold_is_returned_untouched_and_not_flagged():
    spec, pending = _schema_safe_spec(
        {"kind": "DEGREE", "terms": ["hoc van"], "required_degree_level": 4})
    assert pending is False
    assert spec["required_degree_level"] == 4


def test_years_without_a_number_is_also_kept_and_flagged():
    spec, pending = _schema_safe_spec({"kind": "YEARS", "terms": ["python"], "min_years": None})
    assert pending is True
    assert spec["kind"] == "YEARS"


def test_spec_that_is_broken_for_another_reason_is_still_dropped():
    """Chỉ điền tạm khi thiếu ĐÚNG ngưỡng. Lỗi khác thì bỏ, đừng đoán che lỗi."""
    spec, pending = _schema_safe_spec({"kind": "DEGREE", "terms": []})
    assert (spec, pending) == (None, False)


def test_deep_clean_marks_every_criterion_not_just_the_first():
    version = {"criteria": [
        {"requirement_spec": {"kind": "DEGREE", "terms": ["a"], "required_degree_level": None}},
        {"requirement_spec": {"kind": "YEARS", "terms": ["b"], "min_years": None}},
        {"requirement_spec": None},
    ]}
    out = _sanitize_criteria_response(version)
    assert [c.get("threshold_pending") for c in out["criteria"]] == [True, True, False]


# --- (c) không chấm ngầm theo bậc đại học -----------------------------------

def test_degree_without_a_level_never_decides_anything():
    """Chưa có bậc thì tiêu chí phải thành unresolved, không phải NO_MATCH.

    Trước đây ``or 3`` khiến ứng viên có bằng cao đẳng bị NO_MATCH vì một ngưỡng
    chưa ai đặt — và NO_MATCH là kết luận có sức nặng, nó loại ứng viên.
    """
    result = deterministic_matcher.evaluate_criteria(
        CV_COLLEGE,
        [criterion("Học vấn", "Có bằng cấp liên quan", [],
                   {"kind": "DEGREE", "terms": ["hoc van"], "required_degree_level": None})],
        {"education": ["Bằng cao đẳng Công nghệ thông tin"]},
    )
    assert "c1" in result["unresolved_criterion_ids"], "không được tự quyết khi thiếu ngưỡng"
    for finding in result.get("findings", []):
        assert finding.get("outcome") not in ("NO_MATCH", "STRONG_MATCH", "MATCH")


def test_degree_with_an_explicit_level_still_decides():
    """Sửa ``or 3`` không được làm mất khả năng kết luận khi HR ĐÃ chọn bậc."""
    result = deterministic_matcher.evaluate_criteria(
        CV_UNIVERSITY,
        [criterion("Học vấn", "Bằng đại học trở lên", [],
                   {"kind": "DEGREE", "terms": ["hoc van"], "required_degree_level": 3})],
        {},
    )
    outcomes = [f.get("outcome") for f in result.get("findings", [])]
    assert outcomes, "có ngưỡng rõ ràng thì phải có kết luận"
    assert outcomes[0] in ("MATCH", "STRONG_MATCH")


def test_schema_still_rejects_a_degree_spec_without_a_level():
    """Rào của schema KHÔNG bị nới — đó là chủ ý của audit M1.

    Nếu nới, tiêu chí chưa có tiêu chuẩn sẽ lưu được và đi thẳng vào chấm điểm.
    Việc "HR cần điền bậc" được giải quyết ở response (cờ threshold_pending),
    không phải bằng cách cho lưu spec thiếu.
    """
    with pytest.raises(ValidationError):
        RequirementSpec(kind="DEGREE", terms=["hoc van"])
