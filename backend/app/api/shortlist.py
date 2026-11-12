from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.exceptions import NotFoundError
from app.core.permissions import can_update_application_status
from app.core.security import get_current_user
from app.db.database import SessionLocal

router = APIRouter()


class CreateShortlistShareRequest(BaseModel):
    position_id: UUID
    shared_with_user_id: UUID
    application_ids: List[UUID] = Field(min_length=1, max_length=500)
    note: Optional[str] = Field(default=None, max_length=2000)
    allow_cv_view: bool = False


class ShortlistFeedbackRequest(BaseModel):
    application_id: Optional[UUID] = None
    content: str = Field(min_length=1, max_length=3000)


def _require_hr(user_id: str, position_id: UUID):
    if not can_update_application_status(user_id, str(position_id)):
        raise HTTPException(status_code=403, detail="Chỉ HR phụ trách mới được chia sẻ shortlist")


@router.get("/potential-recipients/{position_id}")
async def get_potential_recipients(position_id: UUID, current_user: dict = Depends(get_current_user)):
    """Only active Hiring Managers assigned to this position can receive a share."""
    _require_hr(current_user["user_id"], position_id)
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT pa.user_id, COALESCE(up.display_name, 'Hiring Manager') AS display_name,
                   pa.position_role AS role
            FROM app_private.position_assignments pa
            JOIN app_private.user_profiles up ON up.user_id = pa.user_id
            WHERE pa.position_id = :position_id AND pa.position_role = 'HIRING_MANAGER'
              AND pa.revoked_at IS NULL AND up.account_status = 'ACTIVE'
            ORDER BY display_name
        """), {"position_id": str(position_id)}).mappings().all()
        return [dict(row) for row in rows]
    finally:
        db.close()


@router.get("/shortlisted-applications/{position_id}")
async def list_shortlisted_applications(position_id: UUID, current_user: dict = Depends(get_current_user)):
    _require_hr(current_user["user_id"], position_id)
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT a.application_id, a.application_status, COALESCE(i.display_name, 'Chưa có tên') AS candidate_name,
                   ar.matching_status, ar.matching_score, ar.evidence_coverage
            FROM app_private.applications a
            LEFT JOIN app_private.application_identities i ON i.application_id = a.application_id
            LEFT JOIN LATERAL (
                SELECT ar.matching_status, ar.matching_score, ar.evidence_coverage FROM app_private.assessment_runs ar
                WHERE ar.application_id = a.application_id AND ar.status = 'COMPLETED'
                  AND ar.profile_version_id = (SELECT profile_version_id FROM app_private.profile_versions
                      WHERE application_id = a.application_id AND status = 'COMPLETED' ORDER BY version_number DESC LIMIT 1)
                  AND ar.criteria_version_id = (SELECT c.criteria_version_id FROM app_private.criteria_versions c
                      WHERE c.position_id = a.position_id AND c.status = 'APPROVED'
                        AND c.jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions
                            WHERE position_id = a.position_id ORDER BY version_number DESC LIMIT 1)
                      ORDER BY c.version_number DESC LIMIT 1)
                ORDER BY ar.created_at DESC LIMIT 1
            ) ar ON TRUE
            WHERE a.position_id = :position_id AND a.application_status = 'SHORTLIST'
            ORDER BY a.created_at DESC
        """), {"position_id": str(position_id)}).mappings().all()
        return [dict(row) for row in rows]
    finally:
        db.close()


@router.post("/share", status_code=status.HTTP_201_CREATED)
async def create_shortlist_share(request: CreateShortlistShareRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    _require_hr(user_id, request.position_id)
    position_id, recipient = str(request.position_id), str(request.shared_with_user_id)
    ids = [str(app_id) for app_id in request.application_ids]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=400, detail="Danh sách ứng viên có hồ sơ trùng")

    db = SessionLocal()
    try:
        from app.services.retention import position_has_inflight_purge
        db.execute(text("SELECT 1 FROM app_private.positions WHERE position_id=:id FOR UPDATE"), {"id": position_id})
        if position_has_inflight_purge(db, position_id):
            raise HTTPException(status_code=409, detail="Vị trí có case xóa đang xử lý hoặc cần phục hồi")
        recipient_ok = db.execute(text("""
            SELECT 1 FROM app_private.position_assignments pa
            JOIN app_private.user_profiles up ON up.user_id = pa.user_id
            WHERE pa.position_id = :position_id AND pa.user_id = :recipient
              AND pa.position_role = 'HIRING_MANAGER' AND pa.revoked_at IS NULL
              AND up.account_status = 'ACTIVE'
        """), {"position_id": position_id, "recipient": recipient}).first()
        if not recipient_ok:
            raise HTTPException(status_code=400, detail="Người nhận phải là Hiring Manager đang phụ trách vị trí")
        apps = db.execute(text("""
            SELECT application_id FROM app_private.applications
            WHERE position_id = :position_id AND application_status = 'SHORTLIST'
              AND CAST(application_id AS text) = ANY(:ids)
            FOR UPDATE
        """), {"position_id": position_id, "ids": ids}).scalars().all()
        if len(apps) != len(ids):
            raise HTTPException(status_code=400, detail="Chỉ có thể chia sẻ hồ sơ đang ở Shortlist của vị trí này")
        share_id = db.execute(text("""
            INSERT INTO app_private.shortlist_shares (position_id, created_by, shared_with, note, allow_cv_view)
            VALUES (:position_id, :user_id, :recipient, :note, :allow_cv_view) RETURNING share_id
        """), {"position_id": position_id, "user_id": user_id, "recipient": recipient,
                "note": request.note, "allow_cv_view": request.allow_cv_view}).scalar_one()
        for app_id in ids:
            db.execute(text("""
                INSERT INTO app_private.shortlist_share_items
                    (share_id, position_id, application_id, assessment_id, ranking_item_id)
                VALUES (:share_id, :position_id, :application_id,
                    (SELECT ar.assessment_id FROM app_private.assessment_runs ar
                     JOIN app_private.applications a ON a.application_id = ar.application_id
                     WHERE ar.application_id = :application_id AND ar.status = 'COMPLETED'
                  AND ar.profile_version_id = (SELECT profile_version_id FROM app_private.profile_versions
                      WHERE application_id = a.application_id AND status = 'COMPLETED' ORDER BY version_number DESC LIMIT 1)
                  AND ar.criteria_version_id = (SELECT c.criteria_version_id FROM app_private.criteria_versions c
                      WHERE c.position_id = a.position_id AND c.status = 'APPROVED'
                        AND c.jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions
                            WHERE position_id = a.position_id ORDER BY version_number DESC LIMIT 1)
                      ORDER BY c.version_number DESC LIMIT 1)
                     ORDER BY ar.created_at DESC LIMIT 1),
                    (SELECT ri.ranking_item_id FROM app_private.ranking_items ri
                     JOIN app_private.ranking_runs rr ON rr.ranking_run_id = ri.ranking_run_id
                     JOIN app_private.assessment_runs ar ON ar.assessment_id = ri.assessment_id
                     JOIN app_private.applications a ON a.application_id = ri.application_id
                     WHERE ri.application_id = :application_id AND rr.status = 'COMPLETED'
                  AND ar.profile_version_id = (SELECT profile_version_id FROM app_private.profile_versions
                      WHERE application_id = a.application_id AND status = 'COMPLETED' ORDER BY version_number DESC LIMIT 1)
                  AND ar.criteria_version_id = (SELECT c.criteria_version_id FROM app_private.criteria_versions c
                      WHERE c.position_id = a.position_id AND c.status = 'APPROVED'
                        AND c.jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions
                            WHERE position_id = a.position_id ORDER BY version_number DESC LIMIT 1)
                      ORDER BY c.version_number DESC LIMIT 1)
                     ORDER BY rr.created_at DESC LIMIT 1))
            """), {"share_id": share_id, "position_id": position_id, "application_id": app_id})
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, position_id, outcome)
            VALUES (:user_id, 'SHARE_SHORTLIST', 'SHORTLIST_SHARE', :share_id, :position_id, 'SUCCESS')
        """), {"user_id": user_id, "share_id": share_id, "position_id": position_id})
        db.commit()
        return {"share_id": share_id, "status": "ACTIVE", "position_id": position_id,
                "shared_with": recipient, "applications_count": len(ids)}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/shared-with-me")
async def get_shortlists_shared_with_me(current_user: dict = Depends(get_current_user)):
    """Inbox for recipients and shares managed by HR responsible for the position."""
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT s.*, p.title, p.position_code, creator.display_name AS creator_name,
                   recipient.display_name AS recipient_name,
                   (SELECT COUNT(*) FROM app_private.shortlist_share_items si WHERE si.share_id = s.share_id) AS application_count,
                   (SELECT COUNT(*) FROM app_private.shortlist_feedback f WHERE f.share_id = s.share_id) AS feedback_count
            FROM app_private.shortlist_shares s
            JOIN app_private.positions p ON p.position_id = s.position_id
            LEFT JOIN app_private.user_profiles creator ON creator.user_id = s.created_by
            LEFT JOIN app_private.user_profiles recipient ON recipient.user_id = s.shared_with
            WHERE s.status = 'ACTIVE' AND (
                (s.shared_with = :user_id AND EXISTS (
                    SELECT 1 FROM app_private.position_assignments hm WHERE hm.position_id = s.position_id
                      AND hm.user_id = :user_id AND hm.position_role = 'HIRING_MANAGER' AND hm.revoked_at IS NULL))
                OR EXISTS (SELECT 1 FROM app_private.position_assignments hr WHERE hr.position_id = s.position_id
                           AND hr.user_id = :user_id AND hr.position_role IN ('HR_RECRUITER', 'HR_LEAD') AND hr.revoked_at IS NULL)
                OR EXISTS (SELECT 1 FROM app_private.user_role_assignments ur WHERE ur.user_id = :user_id
                           AND ur.role_code IN ('ADMIN', 'HR_LEAD') AND ur.revoked_at IS NULL)
            )
            ORDER BY s.created_at DESC
        """), {"user_id": current_user["user_id"]}).mappings().all()
        return [_share_response(row, current_user["user_id"]) for row in rows]
    finally:
        db.close()


def _share_response(row, user_id: str) -> dict:
    result = dict(row)
    result["position"] = {"title": result.pop("title"), "position_code": result.pop("position_code")}
    result["created_by_profile"] = {"display_name": result.pop("creator_name")}
    result["recipient_profile"] = {"display_name": result.pop("recipient_name")}
    result["direction"] = "received" if str(result["shared_with"]) == user_id and str(result["created_by"]) != user_id else "sent"
    return result


def _get_share(db, share_id: str, user_id: str, lock: bool = False):
    row = db.execute(text("""
        SELECT s.*, p.title, p.position_code, creator.display_name AS creator_name,
               recipient.display_name AS recipient_name
        FROM app_private.shortlist_shares s
        JOIN app_private.positions p ON p.position_id = s.position_id
        LEFT JOIN app_private.user_profiles creator ON creator.user_id = s.created_by
        LEFT JOIN app_private.user_profiles recipient ON recipient.user_id = s.shared_with
        WHERE s.share_id = :share_id
    """ + (" FOR UPDATE OF s" if lock else "")), {"share_id": share_id}).mappings().first()
    if not row:
        raise NotFoundError("Shortlist share")
    hr_access = can_update_application_status(user_id, str(row["position_id"]))
    hm_access = str(row["shared_with"]) == user_id and bool(db.execute(text("""
        SELECT 1 FROM app_private.position_assignments WHERE position_id = :position AND user_id = :user_id
          AND position_role = 'HIRING_MANAGER' AND revoked_at IS NULL
    """), {"position": str(row["position_id"]), "user_id": user_id}).first())
    if not hr_access and not hm_access:
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem shortlist này")
    if row["status"] != "ACTIVE" and not hr_access:
        raise HTTPException(status_code=403, detail="Shortlist đã bị thu hồi")
    return row


@router.get("/{share_id}")
async def get_shortlist_detail(share_id: UUID, current_user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        result = _share_response(_get_share(db, str(share_id), current_user["user_id"]), current_user["user_id"])
        items = db.execute(text("""
            SELECT si.application_id, COALESCE(i.display_name, 'Chưa có tên') AS candidate_name,
                   a.application_status, ar.matching_status, ar.matching_score, ar.evidence_coverage
            FROM app_private.shortlist_share_items si
            JOIN app_private.applications a ON a.application_id = si.application_id
            LEFT JOIN app_private.application_identities i ON i.application_id = si.application_id
            LEFT JOIN app_private.assessment_runs ar ON ar.assessment_id = si.assessment_id
                  AND ar.profile_version_id = (SELECT profile_version_id FROM app_private.profile_versions
                      WHERE application_id = a.application_id AND status = 'COMPLETED' ORDER BY version_number DESC LIMIT 1)
                  AND ar.criteria_version_id = (SELECT c.criteria_version_id FROM app_private.criteria_versions c
                      WHERE c.position_id = a.position_id AND c.status = 'APPROVED'
                        AND c.jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions
                            WHERE position_id = a.position_id ORDER BY version_number DESC LIMIT 1)
                      ORDER BY c.version_number DESC LIMIT 1)
            WHERE si.share_id = :share_id ORDER BY si.created_at, si.share_item_id
        """), {"share_id": str(share_id)}).mappings().all()
        feedback = db.execute(text("""
            SELECT f.feedback_id, f.feedback_from, f.application_id, f.content, f.created_at,
                   up.display_name AS author_name
            FROM app_private.shortlist_feedback f
            LEFT JOIN app_private.user_profiles up ON up.user_id = f.feedback_from
            WHERE f.share_id = :share_id ORDER BY f.created_at, f.feedback_id
        """), {"share_id": str(share_id)}).mappings().all()
        result["applications"] = [dict(row) for row in items]
        result["feedback"] = [dict(row) for row in feedback]
        return result
    finally:
        db.close()


@router.post("/{share_id}/feedback", status_code=status.HTTP_201_CREATED)
async def add_shortlist_feedback(share_id: UUID, request: ShortlistFeedbackRequest,
                                 current_user: dict = Depends(get_current_user)):
    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Vui lòng nhập phản hồi")
    db = SessionLocal()
    try:
        from app.services.retention import position_has_inflight_purge
        share = _get_share(db, str(share_id), current_user["user_id"])
        position_id = str(share["position_id"])
        db.execute(text("SELECT 1 FROM app_private.positions WHERE position_id=:id FOR UPDATE"), {"id": position_id})
        if position_has_inflight_purge(db, position_id):
            raise HTTPException(status_code=409, detail="Vị trí có case xóa đang xử lý hoặc cần phục hồi")
        share = _get_share(db, str(share_id), current_user["user_id"], lock=True)
        if share["status"] != "ACTIVE":
            raise HTTPException(status_code=400, detail="Shortlist đã bị thu hồi")
        if not request.application_id and share["share_level_feedback_blocked"]:
            raise HTTPException(status_code=409, detail="Shortlist đã thay đổi do retention; hãy yêu cầu HR tạo shortlist mới để gửi phản hồi chung")
        if request.application_id and not db.execute(text("""
            SELECT 1 FROM app_private.shortlist_share_items
            WHERE share_id = :share_id AND application_id = :application_id
        """), {"share_id": str(share_id), "application_id": str(request.application_id)}).first():
            raise HTTPException(status_code=400, detail="Hồ sơ không thuộc shortlist này")
        row = db.execute(text("""
            INSERT INTO app_private.shortlist_feedback (share_id, application_id, feedback_from, content)
            VALUES (:share_id, :application_id, :user_id, :content) RETURNING *
        """), {"share_id": str(share_id), "application_id": str(request.application_id) if request.application_id else None,
                "user_id": current_user["user_id"], "content": content}).mappings().one()
        db.commit()
        return dict(row)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/{share_id}/revoke")
async def revoke_shortlist(share_id: UUID, current_user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        share = _get_share(db, str(share_id), current_user["user_id"], lock=True)
        if not can_update_application_status(current_user["user_id"], str(share["position_id"])):
            raise HTTPException(status_code=403, detail="Chỉ HR phụ trách mới có thể thu hồi shortlist")
        db.execute(text("""
            UPDATE app_private.shortlist_shares SET status = 'REVOKED', revoked_at = NOW()
            WHERE share_id = :share_id
        """), {"share_id": str(share_id)})
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, position_id, outcome)
            VALUES (:user_id, 'REVOKE_SHORTLIST', 'SHORTLIST_SHARE', :share_id, :position_id, 'SUCCESS')
        """), {"user_id": current_user["user_id"], "share_id": str(share_id), "position_id": str(share["position_id"])})
        db.commit()
        return {"status": "REVOKED", "share_id": share_id}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
