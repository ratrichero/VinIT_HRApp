from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from uuid import UUID
from app.core.security import get_current_user
from app.core.permissions import check_position_access, can_update_application_status
from app.core.logging import get_logger
from app.core.exceptions import NotFoundError
from app.schemas.criteria import (
    CriteriaItemWeightsUpdate,
    CriteriaVersion,
    CriteriaWeightsUpdate,
    Criterion,
    CriterionCreate,
    CriterionUpdate,
    ApprovalAction,
    CriteriaApprovalRequest,
    RequirementSpec
)
from app.db.database import SessionLocal
from sqlalchemy import text
from pydantic import ValidationError
import json
from decimal import Decimal
from app.services.llm_client import llm_client, LLMError, llm_user_message
from app.services.rubric_normalizer import (
    coerce_category as _coerce_category,
    coerce_keywords as _coerce_keywords,
    coerce_text as _coerce_text,
    coerce_weight as _coerce_weight,
    normalize_weights_in_group as _normalize_weights_in_group,
    stored_requirement_spec as _stored_requirement_spec,
)

router = APIRouter()
logger = get_logger(__name__)


def _load_criteria(db, version_id):
    row = db.execute(text("SELECT * FROM app_private.criteria_versions WHERE criteria_version_id = :id"), {"id": str(version_id)}).mappings().first()
    if not row:
        raise NotFoundError("Criteria version")
    result = dict(row)
    result["criteria"] = [dict(item) for item in db.execute(text("""
        SELECT * FROM app_private.criteria_items WHERE criteria_version_id = :id ORDER BY display_order, criterion_id
    """), {"id": str(version_id)}).mappings().all()]
    return result


def _sanitize_criteria_response(version: dict) -> dict:
    """Drop ``requirement_spec`` values the response schema would reject.

    Rows written before the schema/spec fix may already hold a spec such as
    ``{"kind": "LANGUAGE"}`` with no language or threshold. Serializing such a
    row fails inside FastAPI and returns a bare 500 with no ``detail``, hiding
    the real cause from the UI. The spec is optional, so dropping it keeps the
    endpoint usable; the matcher re-infers a spec later.
    """
    if not isinstance(version, dict):
        return version
    for criterion in version.get("criteria") or []:
        if isinstance(criterion, dict) and "requirement_spec" in criterion:
            criterion["requirement_spec"], pending = _schema_safe_spec(criterion["requirement_spec"])
            criterion["threshold_pending"] = pending
    return version


#: Giá trị hợp lệ để hiển thị khi một tiêu chí chưa có ngưỡng. Không dùng để
#: chấm điểm — chỉ để response serialize được, còn ``threshold_pending`` mới là
#: thứ nói cho giao diện biết "chưa có".
_PENDING_FILL = {
    "YEARS": ("min_years", 0.0),
    "DEGREE": ("required_degree_level", 1),
}


def _schema_safe_spec(spec) -> tuple[Optional[dict], bool]:
    """Chuẩn hoá ``spec`` cho vừa schema response. Trả ``(spec, threshold_pending)``.

    Vấn đề: ``requirement_spec`` lưu trong DB có thể **thiếu ngưỡng** — HR chọn
    loại DEGREE nhưng chưa chọn bậc. Đó là trạng thái hợp lệ của quy trình, và
    cột JSONB không ràng buộc gì. Nhưng response schema thì chặt, nên trả nguyên
    trạng làm FastAPI không serialize nổi và trả 500 trắng.

    Cách cũ (bỏ spec, trả ``None``) chữa được 500 nhưng gây lỗi nặng hơn: giao
    diện đọc ``kind`` từ ``null`` ra ``SKILL``, nên **HR không bao giờ thấy ô
    "Bậc bằng tối thiểu"** để điền — đúng ô cần điền lại bị giấu. Và nếu HR bấm
    Lưu ở trạng thái đó, form ghi ``SKILL`` đè lên ``DEGREE`` trong DB.

    Cách nay: **giữ** spec, điền tạm một giá trị hợp lệ để qua schema, và bật cờ
    ``threshold_pending`` để giao diện biết giá trị đó chưa phải quyết định của
    ai. Ngưỡng thật vẫn trống cho tới khi HR điền.
    """
    if not isinstance(spec, dict):
        return None, False
    try:
        RequirementSpec.model_validate(spec)
        return spec, False
    except ValidationError:
        pass

    kind = str(spec.get("kind") or "").upper()
    fill = _PENDING_FILL.get(kind)
    terms = [str(t) for t in (spec.get("terms") or []) if str(t).strip()]
    if fill and terms:
        field, value = fill
        # Chỉ điền khi thiếu đúng ngưỡng đó; spec sai vì lý do khác thì vẫn bỏ,
        # vì đoán thêm chỉ che một lỗi thật.
        patched = {**spec, field: value}
        try:
            RequirementSpec.model_validate(patched)
        except ValidationError:
            patched = None
        if patched:
            logger.info("requirement_spec has no threshold yet; flagged as pending",
                        kind=kind)
            return patched, True

    logger.warning("requirement_spec omitted from response: failed schema validation",
                   kind=spec.get("kind"))
    return None, False


def _item_weight_totals(db, criteria_version_id: str) -> dict[str, Decimal]:
    rows = db.execute(text("""
        SELECT category, COALESCE(SUM(weight_in_group), 0) AS total, COUNT(*) AS item_count
        FROM app_private.criteria_items WHERE criteria_version_id = :id GROUP BY category
    """), {"id": str(criteria_version_id)}).mappings().all()
    return {str(row["category"]): Decimal(str(row["total"])) for row in rows if int(row["item_count"]) > 0}


def _validate_item_weight_totals(db, criteria_version_id: str) -> None:
    totals = _item_weight_totals(db, criteria_version_id)
    if "MUST_HAVE" not in totals:
        raise HTTPException(status_code=400, detail="Cần có ít nhất một tiêu chí bắt buộc trước khi duyệt.")
    invalid = [category for category, total in totals.items() if total != Decimal("100.00")]
    if invalid:
        labels = {"MUST_HAVE": "Bắt buộc", "NICE_TO_HAVE": "Ưu tiên"}
        details = ", ".join(f"{labels.get(category, category)}={totals[category]}%" for category in invalid)
        raise HTTPException(
            status_code=400,
            detail=f"Tổng trọng số trong mỗi nhóm tiêu chí phải bằng 100%. Hiện tại: {details}.",
        )


def _lock_editable_criteria_version(db, criteria_version_id: UUID, user_id: str):
    version = db.execute(text("""
        SELECT position_id, status FROM app_private.criteria_versions
        WHERE criteria_version_id = :id FOR UPDATE
    """), {"id": str(criteria_version_id)}).mappings().first()
    if not version:
        raise NotFoundError("Criteria version")
    if not can_update_application_status(user_id, str(version["position_id"])):
        raise HTTPException(status_code=403, detail="Chỉ HR phụ trách mới có thể sửa tiêu chí")
    if version["status"] not in ("DRAFT", "PENDING_HR_REVIEW"):
        raise HTTPException(status_code=400, detail="Chỉ có thể sửa tiêu chí ở trạng thái bản nháp")
    return version


def _materialize_requirement_specs(db, criteria_version_id: str) -> int:
    """Store inferred specs for legacy criteria before HR approval."""
    rows = db.execute(text("""
        SELECT criterion_id, name, description, category, expected_evidence_keywords, requirement_spec
        FROM app_private.criteria_items WHERE criteria_version_id = :id
    """), {"id": criteria_version_id}).mappings().all()
    materialized = 0
    for row in rows:
        item = dict(row)
        if item.get("requirement_spec"):
            continue
        db.execute(text("""
            UPDATE app_private.criteria_items
            SET requirement_spec = CAST(:spec AS jsonb)
            WHERE criterion_id = :criterion_id
        """), {"spec": json.dumps(_stored_requirement_spec(item)),
               "criterion_id": str(item["criterion_id"])})
        materialized += 1
    return materialized


@router.get("/position/{position_id}/versions", response_model=List[CriteriaVersion])
async def list_criteria_versions(position_id: UUID, current_user: dict = Depends(get_current_user)):
    await check_position_access(position_id, current_user)
    db = SessionLocal()
    try:
        ids = db.execute(text("SELECT criteria_version_id FROM app_private.criteria_versions WHERE position_id = :id ORDER BY version_number DESC"), {"id": str(position_id)}).scalars().all()
        return [_sanitize_criteria_response(_load_criteria(db, item)) for item in ids]
    finally:
        db.close()


@router.get("/{criteria_version_id}", response_model=CriteriaVersion)
async def get_criteria_version(criteria_version_id: UUID, current_user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        result = _load_criteria(db, criteria_version_id)
        await check_position_access(result["position_id"], current_user)
        return _sanitize_criteria_response(result)
    finally:
        db.close()


@router.post("/generate/{position_id}", response_model=CriteriaVersion, status_code=status.HTTP_202_ACCEPTED)
async def generate_criteria_from_jd(position_id: UUID, current_user: dict = Depends(get_current_user)):
    """Generate a draft only; HR and HM still have to approve it."""
    await check_position_access(position_id, current_user, required_roles=["HR_RECRUITER"])
    db = SessionLocal()
    try:
        position = db.execute(text("SELECT position_code, title FROM app_private.positions WHERE position_id = :id"), {"id": str(position_id)}).mappings().first()
        if not position:
            raise NotFoundError("Position")
        jd = db.execute(text("""
            SELECT jd_version_id, content_text FROM app_private.jd_versions WHERE position_id = :id
            ORDER BY version_number DESC LIMIT 1
        """), {"id": str(position_id)}).mappings().first()
        if not jd:
            raise HTTPException(status_code=400, detail="Vị trí chưa có mô tả công việc")
        position, jd = dict(position), dict(jd)
    finally:
        db.close()
    try:
        draft = await llm_client.extract_criteria_from_jd(
            jd_text=jd["content_text"],
            requisition_id=position["position_code"],
            job_title=position["title"],
            position_id=str(position_id),
        )
    except LLMError as exc:
        # Log giữ chuỗi kỹ thuật; người dùng nhận câu theo VIỆC PHẢI LÀM.
        logger.error("Criteria generation failed", error_type=type(exc).__name__,
                     failure_code=getattr(exc, "code", None))
        message, kind = llm_user_message(exc)
        raise HTTPException(status_code=503, detail=message,
                            headers={"X-AI-Error-Kind": kind} if kind else None)
    try:
        raw = draft["criteria"]
        if not isinstance(raw, list) or not raw or len(raw) > 100:
            raise ValueError("Empty or oversized rubric")
        items = []
        for criterion in raw:
            if not isinstance(criterion, dict):
                raise ValueError("Criterion is not an object")
            name = _coerce_text(criterion.get("name"))
            # Description is required by the rubric, but a model that omits it
            # while giving a usable name should not sink the whole batch: the
            # name is what HR approves and what matching scores against.
            description = _coerce_text(criterion.get("description")) or name
            category = _coerce_category(criterion.get("category"))
            weight = _coerce_weight(criterion.get("weight", criterion.get("weight_in_group")))
            keywords = _coerce_keywords(criterion.get("expected_evidence_keywords"))
            if not name or len(name) > 200 or not description or len(description) > 4000 or category is None or weight is None or not 0 <= weight <= 100:
                raise ValueError(
                    f"Invalid criterion: name={name[:40]!r} category={category!r} weight={weight!r}"
                )
            draft_item = {"name": name, "description": description, "category": category,
                          "weight": weight, "keywords": keywords}
            draft_item["requirement_spec"] = _stored_requirement_spec({
                "name": name, "description": description, "category": category,
                "expected_evidence_keywords": keywords,
            })
            items.append(draft_item)
        if not any(c["category"] == "MUST_HAVE" and c["weight"] > 0 for c in items):
            raise ValueError("No weighted mandatory criterion")
        if any(sum(c["weight"] for c in items if c["category"] == category) <= 0
               for category in {c["category"] for c in items}):
            raise ValueError("A criterion group has no weight")
        items = _normalize_weights_in_group(items)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        # Log the concrete reason: without it, a 502 here is undiagnosable from
        # the outside. The message sent to the client stays generic on purpose,
        # but the shape of the model output must be visible in the logs.
        logger.error(
            "AI criteria output rejected by local validation",
            reason=f"{type(exc).__name__}: {exc}",
            criteria_count=len(raw) if isinstance(raw, list) else None,
            first_criterion_keys=sorted(raw[0].keys()) if (isinstance(raw, list) and raw and isinstance(raw[0], dict)) else None,
        )
        raise HTTPException(status_code=502, detail="AI trả về bộ tiêu chí không hợp lệ. Vui lòng thử lại.")
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1 FROM app_private.positions WHERE position_id = :id FOR UPDATE"), {"id": str(position_id)})
        latest_jd = db.execute(text("SELECT jd_version_id FROM app_private.jd_versions WHERE position_id = :id ORDER BY version_number DESC LIMIT 1"), {"id": str(position_id)}).scalar_one_or_none()
        if str(latest_jd) != str(jd["jd_version_id"]):
            raise HTTPException(status_code=409, detail="JD đã thay đổi trong lúc tạo tiêu chí. Vui lòng thử lại.")
        version = db.execute(text("SELECT COALESCE(MAX(version_number), 0) + 1 FROM app_private.criteria_versions WHERE position_id = :id"), {"id": str(position_id)}).scalar_one()
        version_id = db.execute(text("""
            INSERT INTO app_private.criteria_versions (position_id, jd_version_id, version_number, origin, status)
            VALUES (:position, :jd, :version, 'AI_DRAFT', 'DRAFT') RETURNING criteria_version_id
        """), {"position": str(position_id), "jd": jd["jd_version_id"], "version": version}).scalar_one()
        for index, item in enumerate(items):
            db.execute(text("""
                INSERT INTO app_private.criteria_items (criteria_version_id, name, description, category, weight_in_group,
                    expected_evidence_keywords, requirement_spec, display_order)
                VALUES (:id, :name, :description, :category, :weight, CAST(:keywords AS jsonb),
                        CAST(:requirement_spec AS jsonb), :display_order)
            """), {**item, "id": version_id, "keywords": json.dumps(item["keywords"]),
                    "requirement_spec": json.dumps(item["requirement_spec"]), "display_order": index})
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, position_id, outcome)
            VALUES (:user_id, 'GENERATE_CRITERIA_DRAFT', 'CRITERIA_VERSION', :id, :position, 'SUCCESS')
        """), {"user_id": current_user["user_id"], "id": version_id, "position": str(position_id)})
        result = _load_criteria(db, version_id)
        db.commit()
        return _sanitize_criteria_response(result)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def criteria_decision(current_status: str, action: ApprovalAction, position_roles: set[str], system_roles: set[str]) -> tuple[str, str]:
    """Return the next state and reviewer capacity after checking the actor's active roles."""
    is_hr = bool({"HR_RECRUITER", "HR_LEAD"} & position_roles) or bool({"ADMIN", "HR_LEAD"} & system_roles)
    is_hm = "HIRING_MANAGER" in position_roles
    # The approval trail records the capacity used; system roles are preserved
    # separately in audit metadata.
    hr_role = "HR_LEAD" if "HR_LEAD" in (system_roles | position_roles) and "HR_RECRUITER" not in position_roles else "HR_RECRUITER"
    can_direct_approve = bool({"ADMIN", "HR_LEAD"} & system_roles) or "HR_LEAD" in position_roles
    direct_role = "ADMIN" if "ADMIN" in system_roles else "HR_LEAD"

    if action == ApprovalAction.DIRECT_APPROVE:
        if current_status in ("DRAFT", "PENDING_HR_REVIEW", "PENDING_HM_APPROVAL"):
            if not can_direct_approve:
                raise HTTPException(status_code=403, detail="Chỉ Admin hoặc HR Lead mới có thể duyệt trực tiếp, không qua Hiring Manager")
            return "APPROVED", direct_role
    elif action == ApprovalAction.APPROVE:
        if current_status in ("DRAFT", "PENDING_HR_REVIEW"):
            if not is_hr:
                raise HTTPException(status_code=403, detail="Chỉ HR phụ trách mới có thể duyệt và gửi tiêu chí cho Hiring Manager")
            return "PENDING_HM_APPROVAL", hr_role
        if current_status == "PENDING_HM_APPROVAL":
            if not is_hm:
                raise HTTPException(status_code=403, detail="Chỉ Hiring Manager được phân công mới có thể duyệt chuyên môn")
            return "APPROVED", "HIRING_MANAGER"
    elif action == ApprovalAction.REQUEST_CHANGES and current_status == "PENDING_HM_APPROVAL":
        if not is_hm:
            raise HTTPException(status_code=403, detail="Chỉ Hiring Manager được phân công mới có thể yêu cầu chỉnh sửa")
        return "DRAFT", "HIRING_MANAGER"
    elif action == ApprovalAction.REJECT and current_status in ("DRAFT", "PENDING_HR_REVIEW"):
        if not is_hr:
            raise HTTPException(status_code=403, detail="Chỉ HR phụ trách mới có thể từ chối tiêu chí")
        return "REJECTED", hr_role

    raise HTTPException(status_code=400, detail=f"Không thể thực hiện thao tác này khi tiêu chí ở trạng thái {current_status}")


@router.post("/{criteria_version_id}/approve", response_model=CriteriaVersion)
async def approve_criteria(
    criteria_version_id: UUID,
    request: CriteriaApprovalRequest,
    current_user: dict = Depends(get_current_user)
):
    """Record HR/HM decisions atomically, plus the Admin/HR Lead direct path."""
    user_id = current_user["user_id"]
    cv_id_str = str(criteria_version_id)
    comment = (request.comment or "").strip() or None
    if request.action in (ApprovalAction.REJECT, ApprovalAction.REQUEST_CHANGES) and not comment:
        raise HTTPException(status_code=400, detail="Vui lòng nhập lý do từ chối hoặc yêu cầu chỉnh sửa")
    if comment and len(comment) > 2000:
        raise HTTPException(status_code=400, detail="Nội dung phản hồi không được vượt quá 2000 ký tự")
    db = SessionLocal()
    try:
        # Acquire the position lock in the same order as the upload/queue APIs.
        # A new approval cannot become active halfway through an assessment and
        # change the rubric used by its ranking snapshot.
        position = db.execute(text("""
            SELECT position_id FROM app_private.criteria_versions WHERE criteria_version_id = :cv_id
        """), {"cv_id": cv_id_str}).scalar_one_or_none()
        if not position or not db.execute(text("SELECT 1 FROM app_private.positions WHERE position_id = :id FOR UPDATE"), {"id": str(position)}).first():
            raise NotFoundError("Criteria version")
        cv = db.execute(text("""
            SELECT position_id, jd_version_id, status, version_number, mandatory_weight_total, nice_to_have_weight_total, approved_by_hr
            FROM app_private.criteria_versions WHERE criteria_version_id = :cv_id FOR UPDATE
        """), {"cv_id": cv_id_str}).mappings().first()
        if not cv:
            raise NotFoundError("Criteria version")
        position_id = str(cv["position_id"])
        account = db.execute(text("SELECT account_status FROM app_private.user_profiles WHERE user_id = :id FOR SHARE"), {"id": user_id}).scalar_one_or_none()
        if account != 'ACTIVE':
            raise HTTPException(status_code=403, detail="Tài khoản chưa được kích hoạt hoặc đã bị khóa")
        position_roles = set(db.execute(text("""
            SELECT position_role FROM app_private.position_assignments
            WHERE position_id = :position_id AND user_id = :user_id AND revoked_at IS NULL FOR SHARE
        """), {"position_id": position_id, "user_id": user_id}).scalars())
        system_roles = set(db.execute(text("""
            SELECT role_code FROM app_private.user_role_assignments
            WHERE user_id = :user_id AND revoked_at IS NULL FOR SHARE
        """), {"user_id": user_id}).scalars())
        new_status, reviewer_role = criteria_decision(cv["status"], request.action, position_roles, system_roles)
        if new_status in ("PENDING_HM_APPROVAL", "APPROVED"):
            latest_jd = db.execute(text("SELECT jd_version_id FROM app_private.jd_versions WHERE position_id = :id ORDER BY version_number DESC LIMIT 1"), {"id": position_id}).scalar_one_or_none()
            if str(latest_jd) != str(cv["jd_version_id"]):
                raise HTTPException(status_code=409, detail="JD đã thay đổi. Vui lòng tạo và duyệt tiêu chí cho phiên bản JD mới nhất.")
        if new_status == "APPROVED" and request.action != ApprovalAction.DIRECT_APPROVE:
            # One account may hold both roles.  The position and criteria rows
            # are locked above so this check and the decision are indivisible.
            # DIRECT_APPROVE is the explicit Admin/HR Lead bypass, so it does
            # not require a prior, distinct HR approver.
            if not cv["approved_by_hr"] or str(cv["approved_by_hr"]) == str(user_id):
                raise HTTPException(status_code=409, detail="Hai bước duyệt phải do hai tài khoản khác nhau thực hiện")
        if new_status == "APPROVED" and db.execute(text("""
            SELECT 1 FROM app_private.operations WHERE position_id = :position_id
              AND capability IN ('CV_PROCESSING', 'ASSESSMENT', 'RANKING')
              AND status IN ('PENDING', 'PROCESSING') LIMIT 1
        """), {"position_id": position_id}).first():
            raise HTTPException(status_code=409, detail="Vị trí đang xử lý hồ sơ. Vui lòng đợi tác vụ hoàn tất trước khi duyệt phiên bản mới.")
        if new_status in ("PENDING_HM_APPROVAL", "APPROVED"):
            if (cv["mandatory_weight_total"] <= 0 or cv["nice_to_have_weight_total"] < 0
                    or cv["mandatory_weight_total"] + cv["nice_to_have_weight_total"] != 100):
                raise HTTPException(status_code=400, detail="Trọng số hai nhóm không hợp lệ hoặc không bằng 100%")
        if new_status == "PENDING_HM_APPROVAL":
            _materialize_requirement_specs(db, cv_id_str)
            _validate_item_weight_totals(db, cv_id_str)
        if new_status == "APPROVED":
            if request.action == ApprovalAction.DIRECT_APPROVE:
                # A direct approval may start from a draft, before the normal
                # HR step would have materialized inferred requirement specs.
                _materialize_requirement_specs(db, cv_id_str)
            _validate_item_weight_totals(db, cv_id_str)

        # Một vị trí chỉ được có MỘT bộ tiêu chí đang hiệu lực. Không làm việc
        # này thì duyệt bộ mới (ví dụ bộ chép từ rubric mẫu, sau khi bộ AI đã
        # duyệt) để lại hai bộ cùng APPROVED cho một JD. Người đọc sau đó
        # không biết ứng viên cũ đã chấm bằng bộ nào, và mỗi chỗ đọc tự chọn
        # "bộ APPROVED mới nhất" theo một kiểu khác nhau.
        #
        # Dùng SUPERSEDED chứ không dùng ARCHIVED: ARCHIVED / REJECTED đã được
        # dùng cho nghĩa khác (loại bỏ có chủ ý), và một bộ từng duyệt rồi bị
        # thay thế KHÔNG phải bộ bị loại — nó vẫn là bằng chứng đã duyệt và
        # đã chấm ứng viên cũ. Ghi kèm ai duyệt bộ thay thế để truy được.
        if new_status == "APPROVED":
            superseded = db.execute(text("""
                UPDATE app_private.criteria_versions
                SET status = 'SUPERSEDED', updated_at = NOW()
                WHERE position_id = :position_id AND status = 'APPROVED'
                  AND criteria_version_id <> :cv_id
                RETURNING criteria_version_id, version_number
            """), {"position_id": position_id, "cv_id": cv_id_str}).mappings().all()
            for row in superseded:
                db.execute(text("""
                    INSERT INTO app_private.audit_events
                        (actor_user_id, action_type, object_type, object_id, position_id, outcome, metadata)
                    VALUES (:user_id, 'SUPERSEDE_CRITERIA_VERSION', 'CRITERIA_VERSION', :old_id, :position_id,
                            'SUCCESS', CAST(:metadata AS jsonb))
                """), {"user_id": user_id, "old_id": str(row["criteria_version_id"]),
                        "position_id": position_id,
                        "metadata": json.dumps({"version_number": row["version_number"],
                                                "superseded_by": cv_id_str,
                                                "superseded_by_version": cv["version_number"]})})

        db.execute(text("""
            UPDATE app_private.criteria_versions
            SET status = :new_status,
                approved_by_hr = CASE WHEN :new_status = 'PENDING_HM_APPROVAL' THEN :user_id
                                      WHEN :new_status = 'DRAFT' THEN NULL ELSE approved_by_hr END,
                approved_by_hr_at = CASE WHEN :new_status = 'PENDING_HM_APPROVAL' THEN NOW()
                                         WHEN :new_status = 'DRAFT' THEN NULL ELSE approved_by_hr_at END,
                approved_by_hm = CASE WHEN :new_status = 'APPROVED' AND NOT :direct_approve THEN CAST(:user_id AS uuid)
                                      WHEN :new_status = 'APPROVED' THEN approved_by_hm ELSE NULL END,
                approved_by_hm_at = CASE WHEN :new_status = 'APPROVED' AND NOT :direct_approve THEN NOW()
                                         WHEN :new_status = 'APPROVED' THEN approved_by_hm_at ELSE NULL END,
                updated_at = NOW()
            WHERE criteria_version_id = :cv_id
        """), {"new_status": new_status, "user_id": user_id, "cv_id": cv_id_str,
                "direct_approve": request.action == ApprovalAction.DIRECT_APPROVE})
        db.execute(text("""
            INSERT INTO app_private.criteria_approval_events
                (criteria_version_id, reviewed_by, reviewer_role, decision, comment)
            VALUES (:cv_id, :user_id, :reviewer_role, :decision, :comment)
        """), {"cv_id": cv_id_str, "user_id": user_id, "reviewer_role": reviewer_role,
                "decision": request.action.value, "comment": comment})
        db.execute(text("""
            INSERT INTO app_private.audit_events
                (actor_user_id, action_type, object_type, object_id, position_id, outcome, metadata)
            VALUES (:user_id, 'REVIEW_CRITERIA', 'CRITERIA_VERSION', :cv_id, :position_id,
                    :outcome, CAST(:metadata AS jsonb))
        """), {"user_id": user_id, "cv_id": cv_id_str, "position_id": position_id,
                "outcome": new_status, "metadata": json.dumps({"decision": request.action.value,
                    "reviewer_role": reviewer_role, "system_roles": sorted(system_roles),
                    "position_roles": sorted(position_roles),
                    "direct_approve": request.action == ApprovalAction.DIRECT_APPROVE,
                    "bypassed_hm": request.action == ApprovalAction.DIRECT_APPROVE})})
        updated = dict(db.execute(text("SELECT * FROM app_private.criteria_versions WHERE criteria_version_id = :id"),
                                  {"id": cv_id_str}).mappings().one())
        updated["criteria"] = [dict(row) for row in db.execute(text("""
            SELECT * FROM app_private.criteria_items WHERE criteria_version_id = :id ORDER BY display_order
        """), {"id": cv_id_str}).mappings().all()]
        db.commit()
        return updated
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/{criteria_version_id}/approval-events")
async def list_approval_events(criteria_version_id: UUID, current_user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        position_id = db.execute(text("SELECT position_id FROM app_private.criteria_versions WHERE criteria_version_id = :id"),
                                 {"id": str(criteria_version_id)}).scalar_one_or_none()
        if not position_id:
            raise NotFoundError("Criteria version")
        await check_position_access(position_id, current_user)
        rows = db.execute(text("""
            SELECT e.event_id, e.reviewed_by, e.reviewer_role, e.decision, e.comment, e.decided_at,
                   p.display_name AS reviewer_name
            FROM app_private.criteria_approval_events e
            LEFT JOIN app_private.user_profiles p ON p.user_id = e.reviewed_by
            WHERE e.criteria_version_id = :id ORDER BY e.decided_at, e.event_id
        """), {"id": str(criteria_version_id)}).mappings().all()
        return [dict(row) for row in rows]
    finally:
        db.close()


@router.patch("/{criteria_version_id}/weights", response_model=CriteriaVersion)
async def update_criteria_weights(criteria_version_id: UUID, update: CriteriaWeightsUpdate,
                                  current_user: dict = Depends(get_current_user)):
    """Edit group weights only on a draft; the approved version remains immutable."""
    db = SessionLocal()
    try:
        version = db.execute(text("""
            SELECT position_id, status FROM app_private.criteria_versions
            WHERE criteria_version_id = :id FOR UPDATE
        """), {"id": str(criteria_version_id)}).mappings().first()
        if not version:
            raise NotFoundError("Criteria version")
        if not can_update_application_status(current_user["user_id"], str(version["position_id"])):
            raise HTTPException(status_code=403, detail="Chỉ HR phụ trách mới có thể sửa trọng số")
        if version["status"] not in ("DRAFT", "PENDING_HR_REVIEW"):
            raise HTTPException(status_code=400, detail="Chỉ có thể sửa trọng số của bản nháp")
        db.execute(text("""
            UPDATE app_private.criteria_versions
            SET mandatory_weight_total = :mandatory, nice_to_have_weight_total = :nice, updated_at = NOW()
            WHERE criteria_version_id = :id
        """), {"mandatory": update.mandatory_weight_total, "nice": update.nice_to_have_weight_total,
                "id": str(criteria_version_id)})
        db.execute(text("""
            INSERT INTO app_private.audit_events
                (actor_user_id, action_type, object_type, object_id, position_id, outcome, metadata)
            VALUES (:user_id, 'UPDATE_CRITERIA_WEIGHTS', 'CRITERIA_VERSION', :id, :position_id, 'SUCCESS', CAST(:metadata AS jsonb))
        """), {"user_id": current_user["user_id"], "id": str(criteria_version_id),
                "position_id": str(version["position_id"]), "metadata": json.dumps({
                    "mandatory_weight_total": str(update.mandatory_weight_total),
                    "nice_to_have_weight_total": str(update.nice_to_have_weight_total)})})
        result = _load_criteria(db, criteria_version_id)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/{criteria_version_id}/items", response_model=Criterion, status_code=status.HTTP_201_CREATED)
async def create_criterion(criteria_version_id: UUID, request: CriterionCreate,
                           current_user: dict = Depends(get_current_user)):
    """Add a criterion to a draft rubric when the AI proposal is incomplete."""
    name, description = request.name.strip(), request.description.strip()
    if not name or len(name) > 200 or not description or len(description) > 4000:
        raise HTTPException(status_code=400, detail="Tên hoặc mô tả tiêu chí không hợp lệ")
    db = SessionLocal()
    try:
        version = _lock_editable_criteria_version(db, criteria_version_id, current_user["user_id"])
        spec = (request.requirement_spec.model_dump() if request.requirement_spec is not None else _stored_requirement_spec({
            "name": name, "description": description, "category": request.category.value,
            "expected_evidence_keywords": request.expected_evidence_keywords,
        }))
        display_order = db.execute(text("""
            SELECT COALESCE(MAX(display_order), -1) + 1 FROM app_private.criteria_items
            WHERE criteria_version_id = :id
        """), {"id": str(criteria_version_id)}).scalar_one()
        criterion_id = db.execute(text("""
            INSERT INTO app_private.criteria_items
                (criteria_version_id, name, description, category, weight_in_group,
                 expected_evidence_keywords, requirement_spec, evidence_guidance, jd_reference_text, display_order)
            VALUES (:version_id, :name, :description, :category, :weight, CAST(:keywords AS jsonb),
                    CAST(:spec AS jsonb), :guidance, :jd_reference, :display_order)
            RETURNING criterion_id
        """), {"version_id": str(criteria_version_id), "name": name, "description": description,
                "category": request.category.value, "weight": request.weight_in_group,
                "keywords": json.dumps(request.expected_evidence_keywords), "spec": json.dumps(spec),
                "guidance": request.evidence_guidance, "jd_reference": request.jd_reference_text,
                "display_order": int(display_order)}).scalar_one()
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, position_id, outcome)
            VALUES (:user_id, 'CREATE_CRITERION', 'CRITERION', :criterion_id, :position_id, 'SUCCESS')
        """), {"user_id": current_user["user_id"], "criterion_id": str(criterion_id),
                "position_id": str(version["position_id"])})
        result = db.execute(text("SELECT * FROM app_private.criteria_items WHERE criterion_id = :id"),
                            {"id": str(criterion_id)}).mappings().one()
        db.commit()
        return dict(result)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.patch("/{criteria_version_id}/items/weights", response_model=CriteriaVersion)
async def update_criterion_weights(criteria_version_id: UUID, update: CriteriaItemWeightsUpdate,
                                   current_user: dict = Depends(get_current_user)):
    """Replace all draft item weights atomically; each present group totals 100."""
    db = SessionLocal()
    try:
        version = _lock_editable_criteria_version(db, criteria_version_id, current_user["user_id"])
        rows = db.execute(text("""
            SELECT criterion_id, category FROM app_private.criteria_items WHERE criteria_version_id = :id
        """), {"id": str(criteria_version_id)}).mappings().all()
        existing = {str(row["criterion_id"]): str(row["category"]) for row in rows}
        submitted = {str(item.criterion_id): item.weight_in_group for item in update.items}
        if set(submitted) != set(existing):
            raise HTTPException(status_code=400, detail="Cần gửi trọng số cho toàn bộ tiêu chí trong bộ tiêu chí.")
        totals: dict[str, Decimal] = {}
        for criterion_id, weight in submitted.items():
            category = existing[criterion_id]
            totals[category] = totals.get(category, Decimal("0")) + weight
        invalid = [category for category, total in totals.items() if total != Decimal("100.00")]
        if invalid:
            labels = {"MUST_HAVE": "Bắt buộc", "NICE_TO_HAVE": "Ưu tiên"}
            details = ", ".join(f"{labels.get(category, category)}={totals[category]}%" for category in invalid)
            raise HTTPException(status_code=400, detail=f"Tổng trọng số trong mỗi nhóm tiêu chí phải bằng 100%. Hiện tại: {details}.")
        for criterion_id, weight in submitted.items():
            db.execute(text("""
                UPDATE app_private.criteria_items SET weight_in_group = :weight
                WHERE criterion_id = :criterion_id AND criteria_version_id = :version_id
            """), {"weight": weight, "criterion_id": criterion_id, "version_id": str(criteria_version_id)})
        db.execute(text("""
            INSERT INTO app_private.audit_events
                (actor_user_id, action_type, object_type, object_id, position_id, outcome, metadata)
            VALUES (:user_id, 'UPDATE_CRITERION_WEIGHTS', 'CRITERIA_VERSION', :id, :position_id, 'SUCCESS', CAST(:metadata AS jsonb))
        """), {"user_id": current_user["user_id"], "id": str(criteria_version_id),
                "position_id": str(version["position_id"]),
                "metadata": json.dumps({"item_weight_totals": {category: str(total) for category, total in totals.items()}})})
        result = _load_criteria(db, criteria_version_id)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.patch("/{criteria_version_id}/items/{criterion_id}")
async def update_criterion(criteria_version_id: UUID, criterion_id: UUID, update: CriterionUpdate,
                           current_user: dict = Depends(get_current_user)):
    """HR may revise a draft; approved and pending versions are immutable."""
    fields = update.model_dump(exclude_unset=True)
    allowed = {key: value for key, value in fields.items()
               if key in ("name", "description", "category", "weight_in_group", "expected_evidence_keywords")
               and value is not None}
    if "category" in allowed:
        allowed["category"] = allowed["category"].value if hasattr(allowed["category"], "value") else str(allowed["category"])
    if "requirement_spec" in fields:
        allowed["requirement_spec"] = (
            json.dumps(fields["requirement_spec"]) if fields["requirement_spec"] is not None else None
        )
    if not allowed:
        raise HTTPException(status_code=400, detail="Không có nội dung cần cập nhật")
    for key in ("name", "description"):
        if key in allowed:
            allowed[key] = allowed[key].strip()
            if not allowed[key] or len(allowed[key]) > (200 if key == "name" else 4000):
                raise HTTPException(status_code=400, detail="Tên hoặc mô tả tiêu chí không hợp lệ")
    db = SessionLocal()
    try:
        version = _lock_editable_criteria_version(db, criteria_version_id, current_user["user_id"])
        set_parts = []
        for name in allowed:
            if name in ("expected_evidence_keywords", "requirement_spec"):
                set_parts.append(f"{name} = CAST(:{name} AS jsonb)")
            else:
                set_parts.append(f"{name} = :{name}")
        if "expected_evidence_keywords" in allowed:
            allowed["expected_evidence_keywords"] = json.dumps(allowed["expected_evidence_keywords"])
        sets = ", ".join(set_parts)
        result = db.execute(text(f"""
            UPDATE app_private.criteria_items SET {sets}
            WHERE criterion_id = :criterion_id AND criteria_version_id = :version_id RETURNING criterion_id
        """), {**allowed, "criterion_id": str(criterion_id), "version_id": str(criteria_version_id)}).first()
        if not result:
            raise NotFoundError("Criterion")
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, position_id, outcome)
            VALUES (:user_id, 'UPDATE_CRITERION', 'CRITERION', :criterion_id, :position_id, 'SUCCESS')
        """), {"user_id": current_user["user_id"], "criterion_id": str(criterion_id), "position_id": str(version["position_id"])})
        db.commit()
        return {"status": "updated"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.delete("/{criteria_version_id}/items/{criterion_id}")
async def delete_criterion(criteria_version_id: UUID, criterion_id: UUID,
                           current_user: dict = Depends(get_current_user)):
    """Remove an unwanted AI-proposed criterion from a draft rubric."""
    db = SessionLocal()
    try:
        version = _lock_editable_criteria_version(db, criteria_version_id, current_user["user_id"])
        deleted = db.execute(text("""
            DELETE FROM app_private.criteria_items
            WHERE criterion_id = :criterion_id AND criteria_version_id = :version_id
            RETURNING criterion_id
        """), {"criterion_id": str(criterion_id), "version_id": str(criteria_version_id)}).first()
        if not deleted:
            raise NotFoundError("Criterion")
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, position_id, outcome)
            VALUES (:user_id, 'DELETE_CRITERION', 'CRITERION', :criterion_id, :position_id, 'SUCCESS')
        """), {"user_id": current_user["user_id"], "criterion_id": str(criterion_id),
                "position_id": str(version["position_id"])})
        db.commit()
        return {"status": "deleted"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.delete("/{criteria_version_id}/draft")
async def discard_draft_criteria(criteria_version_id: UUID, current_user: dict = Depends(get_current_user)):
    """Huỷ một bộ tiêu chí **nháp** để mở đường cho rubric mẫu.

    Vì sao cần: khi tạo vị trí, hệ thống tự sinh ngay một bộ tiêu chí AI ở
    trạng thái ``DRAFT``. Ở trạng thái đó ``apply_template`` từ chối (409 "Vị
    trí đã có tiêu chí đang xử lý"), nên HR muốn dùng rubric mẫu thì buộc phải
    đưa bộ AI qua **cả** vòng duyệt (HR → Hiring Manager) chỉ để mở một cái
    nút. Một vòng duyệt không ai cần.

    Năm điều kiện, tất cả đều cố ý:

    * Chỉ xoá ``DRAFT``. ``PENDING_HR_REVIEW`` trở đi là đã có người khác nhìn
      thấy và có ý kiến; huỷ im lặng ở đó là xoá việc của người khác.
    * Chỉ người sửa được tiêu chí của vị trí (HR phụ trách) — cùng lớp quyền
      với ``_lock_editable_criteria_version``.
    * Không xoá khi **đã có lần chấm nào** tham chiếu bộ này. Khoá ngoại từ
      ``assessment_runs`` không CASCADE, nên xoá sẽ lỗi ở tầng DB; kiểm trước
      để trả câu giải thích được thay vì lỗi ràng buộc.
    * Không xoá khi bộ này là bộ **đã duyệt** dùng cho JD hiện tại — đó là
      thước đang chấm thật.
    * Ghi audit trước khi xoá, giữ lại tên và số tiêu chí đã mất: sau khi xoá
      thì không còn gì để truy lại.
    """
    db = SessionLocal()
    try:
        version = db.execute(text("""
            SELECT position_id, status, version_number, jd_version_id, origin
            FROM app_private.criteria_versions
            WHERE criteria_version_id = :id FOR UPDATE
        """), {"id": str(criteria_version_id)}).mappings().first()
        if not version:
            raise NotFoundError("Criteria version")
        position_id = str(version["position_id"])
        if not can_update_application_status(current_user["user_id"], position_id):
            raise HTTPException(status_code=403, detail="Chỉ HR phụ trách mới có thể huỷ bản nháp tiêu chí")
        if version["status"] != "DRAFT":
            raise HTTPException(
                status_code=409,
                detail="Chỉ huỷ được bản nháp. Bộ tiêu chí đã được gửi duyệt hoặc đã duyệt thì không huỷ.",
            )
        if db.execute(text(
            "SELECT 1 FROM app_private.assessment_runs WHERE criteria_version_id = :id LIMIT 1"
        ), {"id": str(criteria_version_id)}).first():
            raise HTTPException(
                status_code=409,
                detail="Bộ tiêu chí này đã được dùng để chấm ứng viên nên không huỷ được.",
            )
        item_count = db.execute(text(
            "SELECT count(*) FROM app_private.criteria_items WHERE criteria_version_id = :id"
        ), {"id": str(criteria_version_id)}).scalar_one()
        # Cùng transaction với lệnh xoá: audit ghi sau khi xoá mà transaction
        # hỏng thì mất dấu; ghi trước thì luôn còn.
        db.execute(text("""
            INSERT INTO app_private.audit_events
                (actor_user_id, action_type, object_type, object_id, position_id, outcome, metadata)
            VALUES (:user_id, 'DISCARD_CRITERIA_DRAFT', 'CRITERIA_VERSION', :id, :position_id, 'SUCCESS',
                    CAST(:metadata AS jsonb))
        """), {"user_id": current_user["user_id"], "id": str(criteria_version_id), "position_id": position_id,
                "metadata": json.dumps({"version_number": version["version_number"], "origin": version["origin"],
                                        "item_count": int(item_count), "jd_version_id": str(version["jd_version_id"])})})
        # criteria_items CASCADE theo criteria_versions; ghi chú HR gắn tiêu chí
        # (00036) dùng ON DELETE SET NULL nên nội dung ghi chú vẫn ở lại.
        db.execute(text("DELETE FROM app_private.criteria_versions WHERE criteria_version_id = :id"),
                   {"id": str(criteria_version_id)})
        db.commit()
        return {"status": "discarded", "position_id": position_id, "item_count": int(item_count)}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/position/{position_id}/approved", response_model=Optional[CriteriaVersion])
async def get_latest_approved_criteria(position_id: UUID, current_user: dict = Depends(get_current_user)):
    await check_position_access(position_id, current_user)
    db = SessionLocal()
    try:
        version_id = db.execute(text("""
            SELECT criteria_version_id FROM app_private.criteria_versions WHERE position_id = :id AND status = 'APPROVED'
              AND jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions WHERE position_id = :id ORDER BY version_number DESC LIMIT 1)
            ORDER BY version_number DESC LIMIT 1
        """), {"id": str(position_id)}).scalar_one_or_none()
        return _load_criteria(db, version_id) if version_id else None
    finally:
        db.close()
