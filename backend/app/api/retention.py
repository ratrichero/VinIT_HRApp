"""Retention/deletion workflow API.

These endpoints expose the manual, per-application retention queue.  They do
not implement bulk auto-deletion: a case must be generated after its due date,
confirmed by an authorised user, and then executed explicitly.
"""
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.core.security import get_current_user
from app.db.database import SessionLocal
from app.services.retention import (
    RetentionError,
    can_confirm_retention,
    can_view_retention,
    cancel_retention_case,
    confirm_retention_case,
    execute_retention_case,
    generate_retention_cases,
    get_case,
    public_case,
)

router = APIRouter()


class RetentionActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Deprecated compatibility field. It is accepted so older clients do not
    # break, but it is intentionally ignored and never stored: free-text
    # reasons can accidentally contain candidate identifiers.
    reason: str | None = Field(
        default=None,
        max_length=500,
        deprecated=True,
        description=(
            "Deprecated compatibility field; accepted but intentionally "
            "ignored and never stored. Do not include candidate identifiers."
        ),
    )


class RetentionRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["EXECUTOR_STOPPED_AND_STORAGE_SETTLED"]


def _raise(error: RetentionError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from None


def _get_case_or_404(db, case_id: UUID) -> dict:
    try:
        return get_case(db, str(case_id))
    except RetentionError as exc:
        _raise(exc)


def _require_view(db, current_user: dict, position_id: str | None) -> None:
    if not position_id or not can_view_retention(db, current_user["user_id"], position_id):
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem retention của vị trí này")


def _require_confirm(db, current_user: dict, position_id: str | None) -> None:
    if not position_id or not can_confirm_retention(db, current_user["user_id"], position_id):
        raise HTTPException(status_code=403, detail="Bạn không có quyền xác nhận xóa dữ liệu của vị trí này")


@router.get("/positions/{position_id}/cases")
async def list_retention_cases(position_id: UUID, current_user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        _require_view(db, current_user, str(position_id))
        rows = db.execute(text("""
            SELECT c.retention_case_id, c.application_id, c.position_id, c.application_opaque_id,
                   c.policy_version, c.position_closed_at, c.due_date, c.status,
                   c.confirmed_by, c.confirmed_at, c.created_at, j.status AS execution_status
            FROM app_private.application_retention_cases c
            LEFT JOIN LATERAL (
                SELECT status FROM app_private.deletion_jobs
                WHERE retention_case_id=c.retention_case_id ORDER BY created_at DESC LIMIT 1
            ) j ON TRUE
            WHERE c.position_id = :position_id
            ORDER BY c.due_date, c.created_at, c.retention_case_id
        """), {"position_id": str(position_id)}).mappings().all()
        return [public_case(dict(row)) for row in rows]
    finally:
        db.close()


@router.post("/positions/{position_id}/cases/generate")
async def generate_cases(position_id: UUID, current_user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        _require_view(db, current_user, str(position_id))
        result = generate_retention_cases(
            db, position_id=str(position_id), actor_user_id=current_user["user_id"]
        )
        db.commit()
        return result
    except RetentionError as exc:
        db.rollback()
        _raise(exc)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/cases/{case_id}/confirm")
async def confirm_case(
    case_id: UUID,
    request: RetentionActionRequest | None = None,
    current_user: dict = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        case = _get_case_or_404(db, case_id)
        _require_confirm(db, current_user, case.get("position_id"))
        result = confirm_retention_case(db, case_id=str(case_id), actor_user_id=current_user["user_id"])
        db.commit()
        return result
    except RetentionError as exc:
        db.rollback()
        _raise(exc)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/cases/{case_id}/cancel")
async def cancel_case(
    case_id: UUID,
    request: RetentionActionRequest | None = None,
    current_user: dict = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        case = _get_case_or_404(db, case_id)
        _require_confirm(db, current_user, case.get("position_id"))
        result = cancel_retention_case(db, case_id=str(case_id), actor_user_id=current_user["user_id"])
        db.commit()
        return result
    except RetentionError as exc:
        db.rollback()
        _raise(exc)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/cases/{case_id}/execute")
async def execute_case(case_id: UUID, current_user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        case = _get_case_or_404(db, case_id)
        _require_confirm(db, current_user, case.get("position_id"))
    finally:
        db.close()
    try:
        return execute_retention_case(case_id=str(case_id), actor_user_id=current_user["user_id"])
    except RetentionError as exc:
        _raise(exc)


@router.post("/cases/{case_id}/recover")
async def recover_case(case_id: UUID, request: RetentionRecoveryRequest,
                       current_user: dict = Depends(get_current_user)):
    """Retry only after the operator verifies the old executor and storage I/O stopped."""
    db = SessionLocal()
    try:
        case = _get_case_or_404(db, case_id)
        _require_confirm(db, current_user, case.get("position_id"))
    finally:
        db.close()
    try:
        return execute_retention_case(case_id=str(case_id), actor_user_id=current_user["user_id"], recovery=True)
    except RetentionError as exc:
        _raise(exc)
