from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from uuid import UUID
from app.core.security import get_current_user
from app.core.exceptions import NotFoundError
from app.core.permissions import check_position_access, can_update_application_status
from app.schemas.positions import Position, PositionCreate, PositionUpdate, PositionWithStats, PositionStatus, JDVersionCreate, HiringManagerChange
from app.db.database import SessionLocal
from app.services.departments import DepartmentError, next_position_code
from app.services.workspace import build_workflow
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
import json
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

# Return real metrics, scoped to applications the caller may see. In particular,
# an assigned hiring manager can see only applications actively shared with them.
_POSITION_WITH_STATS = """
    WITH privileges AS (
        SELECT EXISTS (
            SELECT 1 FROM app_private.user_role_assignments
            WHERE user_id = :user_id AND revoked_at IS NULL
              AND role_code IN ('ADMIN', 'HR_LEAD')
        ) AS global_access
    )
    SELECT p.*, d.name AS department_name, d.code_format AS department_code_format, latest.status AS criteria_status,
        EXISTS (SELECT 1 FROM app_private.criteria_versions approved
                WHERE approved.position_id = p.position_id AND approved.status = 'APPROVED'
                  AND approved.jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions
                      WHERE position_id = p.position_id ORDER BY version_number DESC LIMIT 1)) AS criteria_approved,
        stats.total_applications, stats.new_applications, stats.in_review, stats.shortlisted
    FROM app_private.positions p
    CROSS JOIN privileges priv
    LEFT JOIN app_private.departments d ON d.department_id = p.department_id
    LEFT JOIN LATERAL (
        SELECT status FROM app_private.criteria_versions
        WHERE position_id = p.position_id ORDER BY version_number DESC LIMIT 1
    ) latest ON TRUE
    LEFT JOIN LATERAL (
        SELECT COUNT(*) AS total_applications,
            COUNT(*) FILTER (WHERE a.application_status = 'NEW') AS new_applications,
            COUNT(*) FILTER (WHERE a.application_status = 'IN_REVIEW') AS in_review,
            COUNT(*) FILTER (WHERE a.application_status = 'SHORTLIST') AS shortlisted
        FROM app_private.applications a
        WHERE a.position_id = p.position_id AND (
            priv.global_access OR EXISTS (
                SELECT 1 FROM app_private.position_assignments hr
                WHERE hr.position_id = p.position_id AND hr.user_id = :user_id
                  AND hr.position_role IN ('HR_RECRUITER', 'HR_LEAD') AND hr.revoked_at IS NULL
            ) OR EXISTS (
                SELECT 1 FROM app_private.shortlist_shares share
                JOIN app_private.shortlist_share_items item ON item.share_id = share.share_id
                WHERE share.position_id = p.position_id AND share.shared_with = :user_id
                  AND share.status = 'ACTIVE' AND item.application_id = a.application_id
                  AND EXISTS (SELECT 1 FROM app_private.position_assignments hm
                              WHERE hm.position_id = p.position_id AND hm.user_id = :user_id
                                AND hm.position_role = 'HIRING_MANAGER' AND hm.revoked_at IS NULL)
            )
        )
    ) stats ON TRUE
"""


@router.get("", response_model=List[PositionWithStats])
async def list_positions(
    status_filter: Optional[PositionStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """List only positions assigned to the user or shared with them."""
    db = SessionLocal()
    try:
        rows = db.execute(text(_POSITION_WITH_STATS + """
            WHERE (CAST(:status_filter AS text) IS NULL OR p.status = :status_filter)
              AND (priv.global_access OR EXISTS (
                  SELECT 1 FROM app_private.position_assignments pa
                  WHERE pa.position_id = p.position_id AND pa.user_id = :user_id AND pa.revoked_at IS NULL
              ))
            ORDER BY p.created_at DESC, p.position_id DESC LIMIT :page_size OFFSET :offset
        """), {"user_id": current_user["user_id"], "status_filter": status_filter.value if status_filter else None,
                "page_size": page_size, "offset": (page - 1) * page_size}).mappings().all()
        return [dict(row) for row in rows]
    finally:
        db.close()


@router.post("", response_model=Position, status_code=status.HTTP_201_CREATED)
async def create_position(
    position_data: PositionCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create the position, JD and assignments atomically."""
    user_id = current_user["user_id"]
    for field in ("title", "jd_content"):
        value = getattr(position_data, field).strip()
        if not value or (field != "jd_content" and len(value) > 200):
            raise HTTPException(status_code=400, detail="Tên vị trí và nội dung JD không được để trống")
        setattr(position_data, field, value)
    if not position_data.hiring_manager_user_id:
        raise HTTPException(status_code=400, detail="Vui lòng chọn Hiring Manager phụ trách vị trí")
    hm_id = str(position_data.hiring_manager_user_id)
    db = SessionLocal()
    try:
        actor_status = db.execute(text("""
            SELECT account_status FROM app_private.user_profiles WHERE user_id = :user_id FOR SHARE
        """), {"user_id": user_id}).scalar_one_or_none()
        actor_roles = db.execute(text("""
            SELECT role_code FROM app_private.user_role_assignments WHERE user_id = :user_id
              AND revoked_at IS NULL AND role_code IN ('ADMIN', 'HR_LEAD', 'HR_RECRUITER') FOR SHARE
        """), {"user_id": user_id}).scalars().all()
        position_roles = db.execute(text("""
            SELECT position_role FROM app_private.position_assignments WHERE user_id = :user_id
              AND revoked_at IS NULL AND position_role IN ('HR_RECRUITER', 'HR_LEAD') FOR SHARE
        """), {"user_id": user_id}).scalars().all()
        if actor_status != 'ACTIVE' or not (actor_roles or position_roles):
            raise HTTPException(status_code=403, detail="Chỉ HR được phép tạo vị trí tuyển dụng")
        if hm_id == str(user_id):
            raise HTTPException(status_code=400, detail="HR và Hiring Manager phải là hai tài khoản khác nhau.")
        hm_status = db.execute(text("""
            SELECT account_status FROM app_private.user_profiles WHERE user_id = :user_id FOR SHARE
        """), {"user_id": hm_id}).scalar_one_or_none()
        hm_roles = db.execute(text("""
            SELECT role_code FROM app_private.user_role_assignments WHERE user_id = :user_id
              AND role_code = 'HIRING_MANAGER' AND revoked_at IS NULL FOR SHARE
        """), {"user_id": hm_id}).scalars().all()
        if hm_status != 'ACTIVE' or not hm_roles:
            raise HTTPException(status_code=400, detail="Hiring Manager phải có tài khoản hoạt động và vai trò HM.")
        department = db.execute(text("""
            SELECT * FROM app_private.departments
            WHERE department_id = :department_id FOR UPDATE
        """), {"department_id": str(position_data.department_id)}).mappings().first()
        if not department:
            raise HTTPException(status_code=400, detail="Không tìm thấy đơn vị/phòng ban")
        if not department["is_active"]:
            raise HTTPException(status_code=400, detail="Đơn vị/phòng ban đã ngừng hoạt động")
        position_code, department_sequence = next_position_code(db, dict(department))
        params = position_data.model_dump(exclude={"jd_content", "hiring_manager_user_id"})
        params.update({
            "position_code": position_code,
            "org_unit": department["name"],
            "department_id": str(position_data.department_id),
            "department_sequence": department_sequence,
            "created_by": user_id,
        })
        new_position = db.execute(text("""
            INSERT INTO app_private.positions (position_code, title, job_family, org_unit, level, work_location,
                work_mode, employment_type, headcount, created_by, department_id, department_sequence)
            VALUES (:position_code, :title, :job_family, :org_unit, :level, :work_location,
                :work_mode, :employment_type, :headcount, :created_by, :department_id, :department_sequence) RETURNING *
        """), params).mappings().one()
        position_id = new_position["position_id"]
        db.execute(text("""
            UPDATE app_private.departments
            SET next_sequence = :next_sequence, updated_at = NOW()
            WHERE department_id = :department_id
        """), {"next_sequence": department_sequence + 1, "department_id": str(position_data.department_id)})
        db.execute(text("""
            INSERT INTO app_private.jd_versions (position_id, version_number, content_text, language_code, created_by)
            VALUES (:position_id, 1, :content, 'en', :user_id)
        """), {"position_id": position_id, "content": position_data.jd_content, "user_id": user_id})
        for assigned_user, role in ((user_id, "HR_RECRUITER"), (hm_id, "HIRING_MANAGER")):
            db.execute(text("""
                INSERT INTO app_private.position_assignments (position_id, user_id, position_role, assigned_by)
                VALUES (:position_id, :assigned_user, :role, :user_id)
            """), {"position_id": position_id, "assigned_user": assigned_user, "role": role, "user_id": user_id})
        db.commit()
        created = dict(new_position)
        created["department_name"] = department["name"]
        created["department_code_format"] = department["code_format"]
        return created
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Mã vị trí đã tồn tại hoặc dữ liệu vị trí không hợp lệ")
    except DepartmentError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/{position_id}", response_model=PositionWithStats)
async def get_position(
    position_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get details for a position visible to the current user."""
    await check_position_access(position_id, current_user)
    db = SessionLocal()
    try:
        result = db.execute(text(_POSITION_WITH_STATS + " WHERE p.position_id = :id"),
                            {"id": str(position_id), "user_id": current_user["user_id"]}).mappings().first()
        if not result:
            raise NotFoundError("Position")
        return dict(result)
    finally:
        db.close()


@router.get("/{position_id}/workspace")
async def get_position_workspace(
    position_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Workspace summary, workflow stepper and next action for one position."""
    await check_position_access(position_id, current_user)
    from app.api.dashboard import load_position_application_counts

    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT p.position_id, p.position_code, p.title, p.status, d.name AS department_name,
                jd.jd_version_id AS latest_jd_version_id, jd.version_number AS latest_jd_version,
                crit.criteria_version_id AS current_criteria_version_id,
                crit.status AS current_criteria_status, crit.version_number AS current_criteria_version,
                crit.jd_version_id AS current_criteria_jd_version_id,
                EXISTS (SELECT 1 FROM app_private.criteria_versions approved
                        WHERE approved.position_id = p.position_id AND approved.status = 'APPROVED'
                          AND approved.jd_version_id = jd.jd_version_id) AS criteria_approved,
                COALESCE((SELECT array_remove(array_agg(pa.position_role), NULL)
                          FROM app_private.position_assignments pa
                          WHERE pa.position_id = p.position_id AND pa.user_id = :user_id
                            AND pa.revoked_at IS NULL), ARRAY[]::text[]) AS position_roles,
                COALESCE((SELECT array_remove(array_agg(ur.role_code), NULL)
                          FROM app_private.user_role_assignments ur
                          WHERE ur.user_id = :user_id AND ur.revoked_at IS NULL), ARRAY[]::text[]) AS system_roles,
                op.operation_id AS active_operation_id, op.status AS active_operation_status,
                op.capability AS active_operation_stage,
                (SELECT COUNT(DISTINCT si.application_id) FROM app_private.shortlist_shares s
                 JOIN app_private.shortlist_share_items si ON si.share_id = s.share_id
                 WHERE s.position_id = p.position_id AND s.status = 'ACTIVE') AS shared_shortlisted_any,
                (SELECT COUNT(DISTINCT si.application_id) FROM app_private.shortlist_shares s
                 JOIN app_private.shortlist_share_items si ON si.share_id = s.share_id
                 WHERE s.position_id = p.position_id AND s.status = 'ACTIVE'
                   AND (s.created_by = :user_id OR s.shared_with = :user_id)) AS shared_shortlisted_own
            FROM app_private.positions p
            LEFT JOIN app_private.departments d ON d.department_id = p.department_id
            LEFT JOIN LATERAL (
                SELECT jd_version_id, version_number FROM app_private.jd_versions
                WHERE position_id = p.position_id ORDER BY version_number DESC LIMIT 1
            ) jd ON TRUE
            LEFT JOIN LATERAL (
                SELECT criteria_version_id, status, version_number, jd_version_id FROM app_private.criteria_versions
                WHERE position_id = p.position_id ORDER BY version_number DESC LIMIT 1
            ) crit ON TRUE
            LEFT JOIN LATERAL (
                SELECT operation_id, status, capability FROM app_private.operations
                WHERE position_id = p.position_id AND capability IN ('CV_PROCESSING', 'ASSESSMENT', 'RANKING')
                  AND status IN ('PENDING', 'PROCESSING')
                ORDER BY created_at ASC LIMIT 1
            ) op ON TRUE
            WHERE p.position_id = :id
        """), {"id": str(position_id), "user_id": current_user["user_id"]}).mappings().first()
        if not row:
            raise NotFoundError("Position")
        row = dict(row)
    finally:
        db.close()

    counts = load_position_application_counts(current_user["user_id"], position_id)
    position_roles = {str(role) for role in (row.get("position_roles") or []) if role}
    system_roles = {str(role) for role in (row.get("system_roles") or []) if role}
    is_hr = bool(position_roles & {"HR_RECRUITER", "HR_LEAD"} or system_roles & {"ADMIN", "HR_LEAD"})
    is_hm = "HIRING_MANAGER" in position_roles
    criteria_stale = bool(
        row.get("current_criteria_jd_version_id")
        and row.get("latest_jd_version_id")
        and str(row["current_criteria_jd_version_id"]) != str(row["latest_jd_version_id"])
    )
    active_operation = None
    if row.get("active_operation_id"):
        active_operation = {
            "operation_id": str(row["active_operation_id"]),
            "status": row.get("active_operation_status"),
            "stage": row.get("active_operation_stage"),
        }
    shared_shortlisted = int(row.get("shared_shortlisted_any") or 0) if is_hr else int(row.get("shared_shortlisted_own") or 0)
    workflow = build_workflow(
        position_id=str(position_id),
        position_status=row.get("status"),
        jd_exists=bool(row.get("latest_jd_version_id")),
        criteria_status=row.get("current_criteria_status"),
        criteria_stale=criteria_stale,
        criteria_approved=bool(row.get("criteria_approved")),
        counts=counts,
        active_operation=active_operation,
        is_hr=is_hr,
        is_hm=is_hm,
        shared_shortlisted=shared_shortlisted,
    )
    return {
        "position": {
            "position_id": str(row["position_id"]),
            "position_code": row.get("position_code"),
            "title": row.get("title"),
            "status": row.get("status"),
            "department_name": row.get("department_name"),
        },
        "jd": {
            "latest_version_id": str(row["latest_jd_version_id"]) if row.get("latest_jd_version_id") else None,
            "version_number": row.get("latest_jd_version"),
        },
        "criteria": {
            "current_version_id": str(row["current_criteria_version_id"]) if row.get("current_criteria_version_id") else None,
            "current_status": row.get("current_criteria_status"),
            "version_number": row.get("current_criteria_version"),
            "approved_for_latest_jd": bool(row.get("criteria_approved")),
            "is_stale_for_latest_jd": criteria_stale,
        },
        "counts": counts,
        "active_operation": active_operation,
        "workflow": workflow,
        "viewer": {
            "is_hr": is_hr,
            "is_hm": is_hm,
            "position_roles": sorted(position_roles),
            "system_roles": sorted(system_roles),
        },
    }


@router.get("/{position_id}/hiring-managers")
async def get_hiring_managers(position_id: UUID, current_user: dict = Depends(get_current_user)):
    """Current assignments for HR; used as the optimistic concurrency token."""
    actor = current_user["user_id"]
    if not can_update_application_status(actor, str(position_id)):
        raise HTTPException(status_code=403, detail="Chỉ HR phụ trách, HR Lead hoặc Admin được quản lý Hiring Manager")
    db = SessionLocal()
    try:
        if not db.execute(text("SELECT 1 FROM app_private.positions WHERE position_id=:id"), {"id": str(position_id)}).first():
            raise NotFoundError("Position")
        rows = db.execute(text("""
            SELECT pa.user_id, up.display_name, up.account_status,
                   CAST(pa.assignment_id AS text) || ':' || CAST(EXTRACT(EPOCH FROM pa.assigned_at) AS text) AS version
            FROM app_private.position_assignments pa
            JOIN app_private.user_profiles up ON up.user_id=pa.user_id
            WHERE pa.position_id=:id AND pa.position_role='HIRING_MANAGER' AND pa.revoked_at IS NULL
            ORDER BY pa.user_id
        """), {"id": str(position_id)}).mappings().all()
        return [dict(row) for row in rows]
    finally:
        db.close()


@router.put("/{position_id}/hiring-manager")
async def change_hiring_manager(position_id: UUID, request: HiringManagerChange,
                                current_user: dict = Depends(get_current_user)):
    """Transfer the position's HM assignment and revoke previous HM shares atomically."""
    actor, target, position = str(current_user["user_id"]), str(request.hiring_manager_user_id), str(position_id)
    db = SessionLocal()
    try:
        # Same first lock as criteria approval, share creation/feedback and retention.
        if not db.execute(text("SELECT 1 FROM app_private.positions WHERE position_id=:id FOR UPDATE"), {"id": position}).first():
            raise NotFoundError("Position")
        profiles = db.execute(text("""
            SELECT user_id, account_status FROM app_private.user_profiles
            WHERE user_id IN (:actor, :target) ORDER BY user_id FOR SHARE
        """), {"actor": actor, "target": target}).mappings().all()
        states = {str(row['user_id']): row['account_status'] for row in profiles}
        if states.get(actor) != 'ACTIVE':
            raise HTTPException(status_code=403, detail="Tài khoản chưa được kích hoạt hoặc đã bị khóa")
        roles = db.execute(text("""
            SELECT user_id, role_code FROM app_private.user_role_assignments
            WHERE user_id IN (:actor, :target) AND revoked_at IS NULL ORDER BY user_id, role_code FOR SHARE
        """), {"actor": actor, "target": target}).mappings().all()
        actor_roles = {r['role_code'] for r in roles if str(r['user_id']) == actor}
        target_roles = {r['role_code'] for r in roles if str(r['user_id']) == target}
        assignments = db.execute(text("""
            SELECT assignment_id, user_id, position_role, assigned_by, assigned_at,
                   CAST(assignment_id AS text) || ':' || CAST(EXTRACT(EPOCH FROM assigned_at) AS text) AS version
            FROM app_private.position_assignments
            WHERE position_id=:position AND revoked_at IS NULL
              AND (position_role='HIRING_MANAGER' OR (user_id=:actor AND position_role IN ('HR_RECRUITER','HR_LEAD')))
            ORDER BY user_id, position_role FOR UPDATE
        """), {"position": position, "actor": actor}).mappings().all()
        authorized = bool(actor_roles & {'ADMIN', 'HR_LEAD'}) or any(
            str(row['user_id']) == actor and row['position_role'] in ('HR_RECRUITER', 'HR_LEAD') for row in assignments)
        if not authorized:
            raise HTTPException(status_code=403, detail="Chỉ HR phụ trách, HR Lead hoặc Admin được quản lý Hiring Manager")
        if states.get(target) != 'ACTIVE' or 'HIRING_MANAGER' not in target_roles:
            raise HTTPException(status_code=400, detail="Hiring Manager phải có tài khoản hoạt động và vai trò HM.")
        if actor == target or db.execute(text("""
            SELECT 1 FROM app_private.position_assignments WHERE position_id=:position AND user_id=:target
              AND position_role IN ('HR_RECRUITER','HR_LEAD') AND revoked_at IS NULL
        """), {"position": position, "target": target}).first():
            raise HTTPException(status_code=400, detail="Hiring Manager phải khác HR phụ trách vị trí.")
        previous = sorted(str(row['user_id']) for row in assignments if row['position_role'] == 'HIRING_MANAGER')
        expected = sorted(request.expected_assignments)
        versions = sorted(row['version'] for row in assignments if row['position_role'] == 'HIRING_MANAGER')
        if len(expected) != len(set(expected)) or expected != versions:
            raise HTTPException(status_code=409, detail="Phân công Hiring Manager đã thay đổi. Vui lòng tải lại trước khi lưu.")
        if previous == [target]:
            return {"changed": False, "hiring_manager_user_id": target, "revoked_shares": 0}
        from app.services.retention import position_has_inflight_purge
        if position_has_inflight_purge(db, position):
            raise HTTPException(status_code=409, detail="Vị trí có case xóa đang xử lý hoặc cần phục hồi")
        # Revoke the previous recipients' shares AND stale active shares of a
        # returning target, so reassignment cannot silently reopen old access.
        affected = sorted(set(previous + [target]))
        shares = db.execute(text("""
            UPDATE app_private.shortlist_shares SET status='REVOKED', revoked_at=now()
            WHERE position_id=:position AND status='ACTIVE' AND CAST(shared_with AS text)=ANY(:affected)
            RETURNING share_id
        """), {"position": position, "affected": affected}).scalars().all()
        for share_id in shares:
            db.execute(text("""
                INSERT INTO app_private.audit_events (actor_user_id,action_type,object_type,object_id,position_id,outcome,metadata)
                VALUES (:actor,'REVOKE_SHORTLIST','SHORTLIST_SHARE',:share,:position,'SUCCESS',CAST(:metadata AS jsonb))
            """), {"actor": actor, "share": str(share_id), "position": position,
                    "metadata": json.dumps({"reason_code": "HIRING_MANAGER_CHANGE"})})
        old_assignments = [{'user_id': str(row['user_id']), 'assignment_id': str(row['assignment_id']),
                            'assigned_by': str(row['assigned_by']) if row['assigned_by'] else None,
                            'assigned_at': row['assigned_at'].isoformat() if row['assigned_at'] else None}
                           for row in assignments if row['position_role'] == 'HIRING_MANAGER']
        db.execute(text("""
            UPDATE app_private.position_assignments SET revoked_at=now()
            WHERE position_id=:position AND position_role='HIRING_MANAGER' AND revoked_at IS NULL
        """), {"position": position})
        db.execute(text("""
            INSERT INTO app_private.position_assignments (position_id,user_id,position_role,assigned_by)
            VALUES (:position,:target,'HIRING_MANAGER',:actor)
            ON CONFLICT (position_id,user_id,position_role) DO UPDATE
            SET revoked_at=NULL, assigned_by=EXCLUDED.assigned_by, assigned_at=now()
        """), {"position": position, "target": target, "actor": actor})
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id,action_type,object_type,object_id,position_id,outcome,metadata)
            VALUES (:actor,'CHANGE_HIRING_MANAGER','POSITION',:position,:position,'SUCCESS',CAST(:metadata AS jsonb))
        """), {"actor": actor, "position": position, "metadata": json.dumps({
            'previous_assignments': old_assignments, 'new_hiring_manager_id': target,
            'revoked_share_ids': [str(share) for share in shares],
        })})
        db.commit()
        return {"changed": True, "hiring_manager_user_id": target, "revoked_shares": len(shares)}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.patch("/{position_id}", response_model=Position)
async def update_position(position_id: UUID, update: PositionUpdate, current_user: dict = Depends(get_current_user)):
    """Update a position and record its status change in the same transaction."""
    user_id = current_user["user_id"]
    if not can_update_application_status(user_id, str(position_id)):
        raise HTTPException(status_code=403, detail="Chỉ HR phụ trách mới có thể cập nhật vị trí")
    values = update.model_dump(exclude_unset=True)
    if "status" in values and values["status"] is not None:
        values["status"] = values["status"].value
    allowed = {k: v for k, v in values.items() if k in {"title", "job_family", "org_unit", "level", "work_location", "work_mode", "employment_type", "headcount", "status"} and v is not None}
    if not allowed:
        raise HTTPException(status_code=400, detail="Không có nội dung cần cập nhật")
    if "title" in allowed:
        allowed["title"] = allowed["title"].strip()
        if not allowed["title"] or len(allowed["title"]) > 200:
            raise HTTPException(status_code=400, detail="Tên vị trí phải có từ 1 đến 200 ký tự")
    db = SessionLocal()
    try:
        previous = db.execute(text("SELECT status FROM app_private.positions WHERE position_id = :id FOR UPDATE"), {"id": str(position_id)}).scalar_one_or_none()
        if not previous:
            raise NotFoundError("Position")
        if "status" in allowed and allowed["status"] != "CLOSED":
            from app.services.retention import position_has_inflight_purge
            if position_has_inflight_purge(db, str(position_id)):
                raise HTTPException(status_code=409, detail="Vị trí có case xóa đang xử lý hoặc cần phục hồi; chưa thể mở lại")
        sets = ", ".join(f"{key} = :{key}" for key in allowed)
        if "status" in allowed:
            # closed_at represents the current closure; the status-event trail
            # preserves earlier closures when a position is reopened.
            sets += ", closed_at = CASE WHEN :status = 'CLOSED' AND status <> 'CLOSED' THEN NOW() WHEN :status <> 'CLOSED' THEN NULL ELSE closed_at END"
        updated = db.execute(text(f"UPDATE app_private.positions SET {sets}, updated_at = NOW() WHERE position_id = :id RETURNING *"),
                             {**allowed, "id": str(position_id)}).mappings().one()
        if "status" in allowed and previous != allowed["status"]:
            db.execute(text("""
                INSERT INTO app_private.position_status_events (position_id, previous_status, new_status, changed_by)
                VALUES (:id, :previous, :new_status, :user_id)
            """), {"id": str(position_id), "previous": previous, "new_status": allowed["status"], "user_id": user_id})
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, position_id, outcome, metadata)
            VALUES (:user_id, 'UPDATE_POSITION', 'POSITION', :id, :id, 'SUCCESS', CAST(:metadata AS jsonb))
        """), {"user_id": user_id, "id": str(position_id), "metadata": json.dumps({"fields": sorted(allowed)})})
        db.commit()
        return dict(updated)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/{position_id}/jd-versions")
async def list_jd_versions(position_id: UUID, current_user: dict = Depends(get_current_user)):
    """All immutable JD versions for users assigned to the position."""
    await check_position_access(position_id, current_user)
    db = SessionLocal()
    try:
        return [dict(row) for row in db.execute(text("""
            SELECT jd_version_id, position_id, version_number, content_text, language_code, created_by, created_at
            FROM app_private.jd_versions WHERE position_id = :id ORDER BY version_number DESC
        """), {"id": str(position_id)}).mappings().all()]
    finally:
        db.close()


@router.post("/{position_id}/jd-versions", status_code=status.HTTP_201_CREATED)
async def create_jd_version(position_id: UUID, request: JDVersionCreate, current_user: dict = Depends(get_current_user)):
    """Save an immutable version with optimistic concurrency and audit history."""
    await check_position_access(position_id, current_user, required_roles=["HR_RECRUITER"])
    content = request.content_text.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Nội dung JD không được để trống")
    db = SessionLocal()
    try:
        position = str(position_id)
        if not db.execute(text("SELECT 1 FROM app_private.positions WHERE position_id = :id FOR UPDATE"), {"id": position}).first():
            raise NotFoundError("Position")
        latest = db.execute(text("""
            SELECT jd_version_id, version_number, content_text FROM app_private.jd_versions
            WHERE position_id = :id ORDER BY version_number DESC LIMIT 1
        """), {"id": position}).mappings().first()
        if not latest or str(latest["jd_version_id"]) != str(request.expected_jd_version_id):
            raise HTTPException(status_code=409, detail="JD đã thay đổi. Vui lòng tải lại trước khi lưu phiên bản mới.")
        if latest["content_text"] == content:
            raise HTTPException(status_code=400, detail="Nội dung JD không có thay đổi")
        if db.execute(text("""
            SELECT 1 FROM app_private.operations WHERE position_id = :id
              AND capability IN ('CV_PROCESSING', 'ASSESSMENT', 'RANKING')
              AND status IN ('PENDING', 'PROCESSING') LIMIT 1
        """), {"id": position}).first():
            raise HTTPException(status_code=409, detail="Vị trí đang xử lý hồ sơ. Vui lòng đợi tác vụ hoàn tất trước khi sửa JD.")
        row = db.execute(text("""
            INSERT INTO app_private.jd_versions (position_id, version_number, content_text, language_code, created_by)
            VALUES (:position, :version, :content, :language, :user_id) RETURNING *
        """), {"position": position, "version": latest["version_number"] + 1, "content": content,
                "language": request.language_code, "user_id": current_user["user_id"]}).mappings().one()
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, position_id, outcome)
            VALUES (:user_id, 'CREATE_JD_VERSION', 'JD_VERSION', :id, :position, 'SUCCESS')
        """), {"user_id": current_user["user_id"], "id": row["jd_version_id"], "position": position})
        db.commit()
        return dict(row)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/{position_id}/duplicate-signals")
async def list_duplicate_signals(position_id: UUID, current_user: dict = Depends(get_current_user)):
    """Read existing signals only; both applications must belong to this position."""
    from app.api.candidate_details import _require_hr_locked

    db = SessionLocal()
    try:
        _require_hr_locked(db, current_user["user_id"], str(position_id), include_admin=True)
        rows = db.execute(text("""
            SELECT d.signal_id, d.signal_type, d.confidence, d.detector_version,
                   d.review_status, d.created_at,
                   a1.application_id AS application_id_1, i1.display_name AS candidate_name_1,
                   a2.application_id AS application_id_2, i2.display_name AS candidate_name_2
            FROM app_private.duplicate_signals d
            JOIN app_private.applications a1 ON a1.application_id = d.application_id_1
                AND a1.position_id = d.position_id
            JOIN app_private.applications a2 ON a2.application_id = d.application_id_2
                AND a2.position_id = d.position_id
            LEFT JOIN app_private.application_identities i1 ON i1.application_id = a1.application_id
            LEFT JOIN app_private.application_identities i2 ON i2.application_id = a2.application_id
            WHERE d.position_id = :position_id
            ORDER BY d.created_at DESC, d.signal_id DESC
        """), {"position_id": str(position_id)}).mappings().all()
        return [dict(row) for row in rows]
    finally:
        db.close()
