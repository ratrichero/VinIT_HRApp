from typing import List, Optional
from uuid import UUID
from fastapi import HTTPException, status, Depends, Request
from app.core.security import get_current_user
from app.db.database import SessionLocal
from sqlalchemy import text


class PositionAccessChecker:
    """FastAPI dependency for checking position-level RBAC.

    Usage in endpoints:
        @router.get("/{position_id}")
        async def get_position(
            position_id: UUID,
            _: bool = Depends(PositionAccessChecker()),
        ):
            ...
    """

    def __init__(self, required_roles: Optional[List[str]] = None, param_name: str = "position_id"):
        self.required_roles = required_roles
        self.param_name = param_name

    async def __call__(self, request: Request, current_user: dict = Depends(get_current_user)) -> bool:
        value = request.path_params.get(self.param_name)
        try:
            position_id = UUID(str(value))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid position id")
        await check_position_access(position_id, current_user, required_roles=self.required_roles)
        return True


def require_admin_role(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency requiring ADMIN system role for accessing admin endpoints."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user credentials",
        )

    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT 1 FROM app_private.user_role_assignments
            WHERE user_id = :user_id
              AND revoked_at IS NULL
              AND role_code = 'ADMIN'
            LIMIT 1
        """), {"user_id": user_id})

        if not result.fetchone():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role required for this endpoint",
            )
        return current_user
    finally:
        db.close()


async def check_position_access(
    position_id: UUID,
    current_user: dict,
    required_roles: Optional[List[str]] = None,
    application_id: Optional[UUID] = None,
) -> str:
    """Check position access and return position_id (looked up from application_id if needed).

    Raises HTTPException 403 if access is denied.
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user credentials",
        )

    # If application_id is provided but position_id isn't, look up position_id
    lookup_position_id = str(position_id) if position_id else None

    db = SessionLocal()
    try:
        if application_id and not position_id:
            app_result = db.execute(text("""
                SELECT position_id FROM app_private.applications
                WHERE application_id = :application_id
            """), {"application_id": str(application_id)})
            app_row = app_result.fetchone()
            if not app_row:
                raise HTTPException(status_code=404, detail="Application not found")
            lookup_position_id = str(app_row[0])

        # Check global admin/HR Lead access
        admin_check = db.execute(text("""
            SELECT 1 FROM app_private.user_role_assignments
            WHERE user_id = :user_id
              AND revoked_at IS NULL
              AND role_code IN ('ADMIN', 'HR_LEAD')
            LIMIT 1
        """), {"user_id": user_id})
        if admin_check.fetchone():
            return lookup_position_id

        # Check position assignment
        query = """
            SELECT 1 FROM app_private.position_assignments
            WHERE position_id = :position_id
              AND user_id = :user_id
              AND revoked_at IS NULL
        """
        params = {"position_id": lookup_position_id, "user_id": user_id}
        if required_roles:
            query += " AND position_role = ANY(:required_roles)"
            params["required_roles"] = list(set(required_roles) | ({"HR_LEAD"} if "HR_RECRUITER" in required_roles else set()))

        assignment_check = db.execute(text(query), params)
        if assignment_check.fetchone():
            return lookup_position_id

        # A generic grant must not bypass a role requirement on a write action.
        if not required_roles:
            grant_check = db.execute(text("""
                SELECT 1 FROM app_private.position_access_grants
                WHERE position_id = :position_id
                  AND user_id = :user_id
                  AND revoked_at IS NULL
                LIMIT 1
            """), {"position_id": lookup_position_id, "user_id": user_id})
            if grant_check.fetchone():
                return lookup_position_id

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this position",
        )
    finally:
        db.close()


def is_system_admin(user_id: str) -> bool:
    """True when the account holds the ADMIN system role."""
    db = SessionLocal()
    try:
        return db.execute(text("""
            SELECT 1 FROM app_private.user_role_assignments
            WHERE user_id = :user_id AND revoked_at IS NULL AND role_code = 'ADMIN'
            LIMIT 1
        """), {"user_id": user_id}).fetchone() is not None
    finally:
        db.close()


def can_update_application_status(user_id: str, position_id: str) -> bool:
    """Check if user can update application status (HR_RECRUITER on the position, or ADMIN/HR_LEAD)."""
    db = SessionLocal()
    try:
        admin_check = db.execute(text("""
            SELECT 1 FROM app_private.user_role_assignments
            WHERE user_id = :user_id AND revoked_at IS NULL AND role_code IN ('ADMIN', 'HR_LEAD')
            LIMIT 1
        """), {"user_id": user_id})
        if admin_check.fetchone():
            return True

        hr_check = db.execute(text("""
            SELECT 1 FROM app_private.position_assignments
            WHERE position_id = :position_id
              AND user_id = :user_id
              AND position_role IN ('HR_RECRUITER', 'HR_LEAD')
              AND revoked_at IS NULL
            LIMIT 1
        """), {"position_id": position_id, "user_id": user_id})
        return hr_check.fetchone() is not None
    finally:
        db.close()


def application_access(user_id: str, position_id: str, application_id: str, db=None) -> dict:
    """Resolve access to a single candidate without granting all CVs to an HM.

    Recruiters on the position and global HR leads/admins have full access;
    everyone else needs an active share containing this application. CV access
    additionally requires the share's allow_cv_view flag.
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT
                EXISTS (SELECT 1 FROM app_private.user_role_assignments ur
                        WHERE ur.user_id = :user_id AND ur.revoked_at IS NULL
                          AND ur.role_code IN ('ADMIN', 'HR_LEAD'))
                OR EXISTS (SELECT 1 FROM app_private.position_assignments pa
                           WHERE pa.user_id = :user_id AND pa.position_id = :position_id
                             AND pa.revoked_at IS NULL AND pa.position_role IN ('HR_RECRUITER', 'HR_LEAD')) AS hr_access,
                EXISTS (SELECT 1 FROM app_private.user_role_assignments ur
                        WHERE ur.user_id = :user_id AND ur.revoked_at IS NULL AND ur.role_code = 'HR_LEAD')
                OR EXISTS (SELECT 1 FROM app_private.position_assignments pa
                           WHERE pa.user_id = :user_id AND pa.position_id = :position_id
                             AND pa.revoked_at IS NULL AND pa.position_role IN ('HR_RECRUITER', 'HR_LEAD')) AS hr_notes_access,
                EXISTS (SELECT 1 FROM app_private.shortlist_shares s
                        JOIN app_private.shortlist_share_items si ON si.share_id = s.share_id
                        WHERE s.shared_with = :user_id AND s.position_id = :position_id
                          AND s.status = 'ACTIVE' AND si.application_id = :application_id
                          AND EXISTS (SELECT 1 FROM app_private.position_assignments hm
                                      WHERE hm.position_id = s.position_id AND hm.user_id = :user_id
                                        AND hm.position_role = 'HIRING_MANAGER' AND hm.revoked_at IS NULL)) AS shared,
                EXISTS (SELECT 1 FROM app_private.shortlist_shares s
                        JOIN app_private.shortlist_share_items si ON si.share_id = s.share_id
                        WHERE s.shared_with = :user_id AND s.position_id = :position_id
                          AND s.status = 'ACTIVE' AND s.allow_cv_view = TRUE
                          AND si.application_id = :application_id
                          AND EXISTS (SELECT 1 FROM app_private.position_assignments hm
                                      WHERE hm.position_id = s.position_id AND hm.user_id = :user_id
                                        AND hm.position_role = 'HIRING_MANAGER' AND hm.revoked_at IS NULL)) AS shared_cv
        """), {"user_id": user_id, "position_id": position_id, "application_id": application_id}).mappings().one()
        if not row["hr_access"] and not row["shared"]:
            raise HTTPException(status_code=403, detail="Bạn không có quyền xem hồ sơ này")
        return {"can_update_status": bool(row["hr_access"]),
                "can_manage_hr_notes": bool(row["hr_notes_access"]),
                "can_view_cv": bool(row["hr_access"] or row["shared_cv"])}
    finally:
        if own_session:
            db.close()
