from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import bindparam, text

from app.core.config import settings
from app.core.exceptions import CriteriaNotApprovedError, NotFoundError
from app.core.permissions import application_access, check_position_access, is_system_admin
from app.services.ai_config import sanitize_provider_snapshot
from app.core.security import get_current_user
from app.db.database import SessionLocal
from app.schemas.applications import AssessmentRun, RankingItem
from app.schemas.common import OperationResponse

router = APIRouter()


async def _queue_position_operation(position_id: UUID, user: dict, capability: str) -> OperationResponse:
    await check_position_access(position_id, user, required_roles=["HR_RECRUITER"])
    db = SessionLocal()
    try:
        position = str(position_id)
        # Serialize check-and-queue across API requests for the same position.
        if not db.execute(text("SELECT 1 FROM app_private.positions WHERE position_id = :id FOR UPDATE"), {"id": position}).first():
            raise NotFoundError("Position")
        from app.services.retention import position_has_inflight_purge
        if position_has_inflight_purge(db, position):
            raise HTTPException(status_code=409, detail="Vị trí có case xóa đang xử lý hoặc cần phục hồi")
        if not db.execute(text("""SELECT 1 FROM app_private.criteria_versions WHERE position_id = :id AND status = 'APPROVED'
            AND jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions WHERE position_id = :id ORDER BY version_number DESC LIMIT 1) LIMIT 1"""), {"id": position}).first():
            raise CriteriaNotApprovedError()
        active = db.execute(text("""
            SELECT operation_id FROM app_private.operations WHERE position_id = :id
              AND capability IN ('CV_PROCESSING', 'ASSESSMENT', 'RANKING') AND status IN ('PENDING', 'PROCESSING')
            ORDER BY created_at LIMIT 1
        """), {"id": position}).scalar_one_or_none()
        if active:
            return OperationResponse(operation_id=active, status="processing", message="Vị trí đang được xử lý; hệ thống sẽ tiếp tục cập nhật tiến trình.")
        if capability == "ASSESSMENT" and not db.execute(text("SELECT 1 FROM app_private.applications WHERE position_id = :id LIMIT 1"), {"id": position}).first():
            # Even a no-op gets a real completed operation so polling clients do
            # not receive a made-up ID that immediately returns 404.
            operation_id = db.execute(text("""
                INSERT INTO app_private.operations
                    (position_id, capability, status, requested_by, started_at, completed_at)
                VALUES (:position, 'ASSESSMENT', 'COMPLETED', :user_id, NOW(), NOW()) RETURNING operation_id
            """), {"position": position, "user_id": user["user_id"]}).scalar_one()
            db.commit()
            return OperationResponse(operation_id=operation_id, status="completed", message="Không có hồ sơ nào cần đánh giá")
        operation_id = db.execute(text("""
            INSERT INTO app_private.operations (position_id, capability, status, requested_by)
            VALUES (:position, :capability, 'PENDING', :user_id) RETURNING operation_id
        """), {"position": position, "capability": capability, "user_id": user["user_id"]}).scalar_one()
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, position_id, outcome)
            VALUES (:user_id, :action, 'POSITION', :position, :position, 'QUEUED')
        """), {"user_id": user["user_id"], "action": "RUN_" + capability, "position": position})
        db.commit()
        return OperationResponse(operation_id=operation_id, status="pending", message="Đã đưa yêu cầu vào hàng đợi xử lý.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/run/{position_id}", response_model=OperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_assessment_for_position(position_id: UUID, current_user: dict = Depends(get_current_user)):
    """Assess eligible applications and then refresh ranking for this position."""
    return await _queue_position_operation(position_id, current_user, "ASSESSMENT")


@router.get("/{assessment_id}", response_model=AssessmentRun)
async def get_assessment(assessment_id: UUID, current_user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT * FROM app_private.assessment_runs WHERE assessment_id = :id"), {"id": str(assessment_id)}).mappings().first()
        if not row:
            raise NotFoundError("Assessment run")
        access = application_access(current_user["user_id"], str(row["position_id"]), str(row["application_id"]))
        if not access["can_view_cv"]:
            raise HTTPException(status_code=403, detail="Shortlist này chỉ cho phép xem tóm tắt")
        if not access["can_update_status"] and not db.execute(text("""
            SELECT 1 FROM app_private.shortlist_share_items si
            JOIN app_private.shortlist_shares s ON s.share_id = si.share_id
            JOIN app_private.position_assignments hm ON hm.position_id = s.position_id
                AND hm.user_id = s.shared_with AND hm.position_role = 'HIRING_MANAGER' AND hm.revoked_at IS NULL
            JOIN app_private.applications a ON a.application_id = si.application_id
            JOIN app_private.assessment_runs ar ON ar.assessment_id = si.assessment_id
            WHERE s.shared_with = :user_id AND s.status = 'ACTIVE' AND s.allow_cv_view
              AND si.assessment_id = :assessment_id
              AND ar.profile_version_id = (SELECT profile_version_id FROM app_private.profile_versions
                  WHERE application_id = a.application_id AND status = 'COMPLETED' ORDER BY version_number DESC LIMIT 1)
              AND ar.criteria_version_id = (SELECT c.criteria_version_id FROM app_private.criteria_versions c
                  WHERE c.position_id = a.position_id AND c.status = 'APPROVED'
                    AND c.jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions
                        WHERE position_id = a.position_id ORDER BY version_number DESC LIMIT 1)
                  ORDER BY c.version_number DESC LIMIT 1)
        """), {"user_id": current_user["user_id"], "assessment_id": str(assessment_id)}).first():
            raise HTTPException(status_code=403, detail="Bạn không có quyền xem đánh giá này")
        assessment = dict(row)
        assessment["provider_model_snapshot"] = sanitize_provider_snapshot(
            assessment.get("provider_model_snapshot"),
            operations_access=is_system_admin(current_user["user_id"]),
        )
        results = db.execute(text("""
            SELECT r.*, c.name AS criterion_name, c.category, r.requires_hr_verification AS requires_verification
            FROM app_private.criterion_assessment_results r JOIN app_private.criteria_items c USING (criterion_id)
            WHERE r.assessment_id = :id ORDER BY c.display_order, c.criterion_id
        """), {"id": str(assessment_id)}).mappings().all()
        assessment["criterion_results"] = []
        for result in results:
            item = dict(result)
            item["evidence"] = [dict(e) for e in db.execute(text("""
                SELECT evidence_id, verbatim_quote, page_number, verification_status FROM app_private.evidence_items
                WHERE criterion_result_id = :id ORDER BY created_at
            """), {"id": str(item["result_id"])}).mappings().all()]
            assessment["criterion_results"].append(item)
        return assessment
    finally:
        db.close()


@router.post("/ranking/generate/{position_id}", response_model=OperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_ranking(position_id: UUID, current_user: dict = Depends(get_current_user)):
    return await _queue_position_operation(position_id, current_user, "RANKING")


@router.get("/ranking/latest/{position_id}", response_model=list[RankingItem])
async def get_latest_ranking(position_id: UUID, current_user: dict = Depends(get_current_user)):
    await check_position_access(position_id, current_user, required_roles=["HR_RECRUITER"])
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT ri.application_id, ri.assessment_id, ri.rank_number, ri.ranking_status AS matching_status,
                   ri.matching_score, ri.evidence_coverage, ri.ltr_score, COALESCE(i.display_name, 'Chưa có tên') AS candidate_name
            FROM app_private.ranking_items ri
            JOIN app_private.applications a ON a.application_id = ri.application_id
            JOIN app_private.assessment_runs ar ON ar.assessment_id = ri.assessment_id
            LEFT JOIN app_private.application_identities i ON i.application_id = ri.application_id
            WHERE a.application_status IN ('NEW', 'IN_REVIEW', 'SHORTLIST')
                  AND ar.profile_version_id = (SELECT profile_version_id FROM app_private.profile_versions
                      WHERE application_id = a.application_id AND status = 'COMPLETED' ORDER BY version_number DESC LIMIT 1)
                  AND ar.criteria_version_id = (SELECT c.criteria_version_id FROM app_private.criteria_versions c
                      WHERE c.position_id = a.position_id AND c.status = 'APPROVED'
                        AND c.jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions
                            WHERE position_id = a.position_id ORDER BY version_number DESC LIMIT 1)
                      ORDER BY c.version_number DESC LIMIT 1)
              AND ri.ranking_run_id = (
                SELECT ranking_run_id FROM app_private.ranking_runs
                WHERE position_id = :position AND status = 'COMPLETED'
                  AND criteria_version_id = (
                      SELECT criteria_version_id FROM app_private.criteria_versions
                      WHERE position_id = :position AND status = 'APPROVED'
                        AND jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions
                            WHERE position_id = :position ORDER BY version_number DESC LIMIT 1)
                      ORDER BY version_number DESC LIMIT 1
                  )
                ORDER BY created_at DESC, ranking_run_id DESC LIMIT 1
            )
            ORDER BY ri.rank_number ASC NULLS LAST, ri.application_id
        """), {"position": str(position_id)}).mappings().all()
        items = []
        for row in rows:
            item = dict(row)
            item["matching_status"] = item["matching_status"] or "NOT_ASSESSED"
            item["has_mismatch"] = item["matching_status"] == "POSSIBLE_MISMATCH"
            item["needs_verification"] = item["matching_status"] == "NEEDS_HR_VERIFICATION" or (item["evidence_coverage"] or 0) < settings.MIN_EVIDENCE_COVERAGE
            items.append(item)
        # Attach the per-criterion breakdown of the exact assessment each
        # ranking row points at, so the list can explain a (partial) score
        # without opening every application.
        assessment_ids = [str(item["assessment_id"]) for item in items if item.get("assessment_id")]
        if assessment_ids:
            detail_rows = db.execute(text("""
                SELECT r.assessment_id, r.criterion_id, c.name AS criterion_name, c.category,
                       r.outcome, r.score, r.requires_hr_verification AS requires_verification,
                       (CASE WHEN c.category = 'MUST_HAVE' THEN cv.mandatory_weight_total
                             ELSE cv.nice_to_have_weight_total END) * c.weight_in_group / 100.0 AS effective_weight
                FROM app_private.criterion_assessment_results r
                JOIN app_private.criteria_items c USING (criterion_id)
                JOIN app_private.criteria_versions cv ON cv.criteria_version_id = c.criteria_version_id
                WHERE r.assessment_id IN :assessment_ids
                ORDER BY r.assessment_id, c.display_order, c.criterion_id
            """).bindparams(bindparam("assessment_ids", expanding=True)),
                {"assessment_ids": assessment_ids}).mappings().all()
            by_assessment: dict[str, list[dict]] = {}
            for detail in detail_rows:
                entry = dict(detail)
                if entry.get("effective_weight") is not None:
                    entry["effective_weight"] = round(float(entry["effective_weight"]), 1)
                by_assessment.setdefault(str(entry.pop("assessment_id")), []).append(entry)
            for item in items:
                item["criterion_results"] = by_assessment.get(str(item.get("assessment_id")), [])
        for item in items:
            item.pop("assessment_id", None)
        return items
    finally:
        db.close()
