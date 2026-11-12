"""Retention case workflow and candidate-data purge.

The workflow is deliberately manual and per application:

1. HR generates due cases for a CLOSED position (policy months after close).
2. An authorised HR Lead/Admin (or a user with a CONFIRM_DELETION position
   grant) confirms or cancels each case.
3. Execution first removes original/extracted files from the configured
   storage backend, then deletes candidate-derived database rows in one
   transaction.  The retention case, deletion job/event and audit events stay
   behind only as anonymised evidence keyed by an opaque hash.

No candidate name, email, filename, quote or CV text is written to retention
summaries or audit metadata.
"""
from __future__ import annotations

import calendar
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from sqlalchemy import text

from app.core.config import settings
from app.db.database import SessionLocal

RETENTION_CONFIRM_PERMISSIONS = ("CONFIRM_DELETION", "RETENTION_CONFIRM")


class RetentionError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def application_opaque_id(application_id: str) -> str:
    """Stable non-reversible identifier for post-purge evidence records."""
    return hashlib.sha256(
        f"vinuni-hra:application:{str(application_id).lower()}".encode("utf-8")
    ).hexdigest()


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + int(months)
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def extracted_storage_paths(extracted_path: str | None) -> list[str]:
    """Return an extracted-text path plus its sibling page map path."""
    if not extracted_path:
        return []
    path = PurePosixPath(str(extracted_path))
    paths = [path.as_posix()]
    if path.name == "extracted.txt":
        paths.append((path.parent / "pages.json").as_posix())
    return paths


def _safe_local_file(bucket: str, storage_path: str) -> Path:
    base = Path(settings.LOCAL_STORAGE_PATH).expanduser().resolve()
    bucket_dir = (base / bucket).resolve()
    candidate = (bucket_dir / storage_path).resolve()
    if candidate != bucket_dir and bucket_dir not in candidate.parents:
        raise RetentionError("Đường dẫn storage không hợp lệ", status_code=500)
    return candidate


def delete_storage_objects(
    originals: Iterable[dict[str, Any]],
    extracted_paths: Iterable[str],
) -> dict[str, int]:
    """Delete original CV and extracted-text objects from configured storage.

    Missing local objects are counted as already absent.  Any backend error is
    raised as a safe RetentionError; exception text/paths are not persisted.
    """
    targets: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(bucket: str, path: str | None) -> None:
        if not bucket or not path:
            return
        key = (str(bucket), str(path))
        if key not in seen:
            seen.add(key)
            targets.append(key)

    for document in originals:
        add(document.get("bucket"), document.get("storage_path"))
    for extracted_path in extracted_paths:
        for path in extracted_storage_paths(extracted_path):
            add(settings.SUPABASE_STORAGE_BUCKET_EXTRACTED, path)

    deleted = 0
    missing = 0
    if settings.STORAGE_BACKEND == "local":
        for bucket, storage_path in targets:
            candidate = _safe_local_file(bucket, storage_path)
            if candidate.exists():
                if not candidate.is_file():
                    raise RetentionError("Đối tượng storage không hợp lệ", status_code=500)
                candidate.unlink()
                deleted += 1
            else:
                missing += 1
        return {"storage_objects_deleted": deleted, "storage_objects_missing": missing}

    if settings.STORAGE_BACKEND == "supabase":
        from app.db.supabase import get_supabase_client

        client = get_supabase_client()
        if not client:
            raise RetentionError("Supabase storage chưa được cấu hình", status_code=503)
        by_bucket: dict[str, list[str]] = {}
        for bucket, storage_path in targets:
            by_bucket.setdefault(bucket, []).append(storage_path)
        try:
            for bucket, paths in by_bucket.items():
                if paths:
                    removed = client.storage.from_(bucket).remove(paths)
                    removed_count = len(removed) if isinstance(removed, (list, tuple)) else len(paths)
                    deleted += removed_count
                    missing += max(0, len(paths) - removed_count)
        except Exception as exc:  # provider errors must not leak paths/secrets
            raise RetentionError("Không thể xóa dữ liệu trên storage", status_code=502) from exc
        return {"storage_objects_deleted": deleted, "storage_objects_missing": missing}

    raise RetentionError("Storage backend không hợp lệ", status_code=500)


def public_case(row: dict[str, Any]) -> dict[str, Any]:
    due_date = row.get("due_date")
    status = row.get("status")
    return {
        "retention_case_id": str(row["retention_case_id"]),
        "application_id": str(row["application_id"]) if row.get("application_id") else None,
        "application_opaque_id": row.get("application_opaque_id"),
        "position_id": str(row["position_id"]) if row.get("position_id") else None,
        "policy_version": row.get("policy_version"),
        "position_closed_at": due_date and row.get("position_closed_at"),
        "due_date": due_date,
        "status": status,
        "execution_status": row.get("execution_status"),
        "execution_in_progress_or_recovery": row.get("execution_status") == "PROCESSING",
        "is_due": bool(due_date and _as_utc(due_date) <= _now() and status in ("PENDING", "SCHEDULED_FOR_DELETION")),
        "confirmed_by": str(row["confirmed_by"]) if row.get("confirmed_by") else None,
        "confirmed_at": row.get("confirmed_at"),
        "created_at": row.get("created_at"),
    }


def _case_query(*, for_update: bool = False) -> str:
    suffix = " FOR UPDATE OF c" if for_update else ""
    return f"""
        SELECT c.retention_case_id, c.application_id, c.position_id,
               c.application_opaque_id, c.policy_version, c.position_closed_at,
               c.due_date, c.status, c.confirmed_by, c.confirmed_at, c.created_at
        FROM app_private.application_retention_cases c
        WHERE c.retention_case_id = :case_id{suffix}
    """


def get_case(db, case_id: str, *, for_update: bool = False) -> dict[str, Any]:
    row = db.execute(text(_case_query(for_update=for_update)), {"case_id": case_id}).mappings().first()
    if not row:
        raise RetentionError("Không tìm thấy retention case", status_code=404)
    return dict(row)


def _lock_case_and_position(db, case_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Lock position before case, matching position-update/generate lock order."""
    snapshot = get_case(db, case_id)
    position_id = snapshot.get("position_id")
    if not position_id:
        raise RetentionError("Retention case không còn vị trí", status_code=409)
    position = db.execute(text("""
        SELECT position_id, status, closed_at FROM app_private.positions
        WHERE position_id = :position_id FOR UPDATE
    """), {"position_id": str(position_id)}).mappings().first()
    if not position:
        raise RetentionError("Retention case không còn vị trí", status_code=409)
    case = get_case(db, case_id, for_update=True)
    if str(case.get("position_id")) != str(position_id):
        raise RetentionError("Retention case đã thay đổi vị trí", status_code=409)
    return case, dict(position)


def _require_original_closure(case: dict[str, Any], position: dict[str, Any]) -> None:
    closed_at, snapshot = position.get("closed_at"), case.get("position_closed_at")
    if (position.get("status") != "CLOSED" or not closed_at or not snapshot
            or _as_utc(closed_at) != _as_utc(snapshot)):
        raise RetentionError("Vị trí đã mở lại hoặc thời điểm đóng đã thay đổi; hủy case cũ và tạo lại khi đủ điều kiện", status_code=409)


def _guard_share_level_text(db, application_id: str) -> None:
    """Block ambiguous free text; never erase unrelated candidates' feedback.

    Lock the application then its shares before examining text. Share creation
    locks applications, and feedback insertion/revoke locks the share, so no
    new ambiguous content can race storage deletion while this transaction runs.
    """
    db.execute(text("SELECT application_id FROM app_private.applications WHERE application_id=:id FOR UPDATE"),
               {"id": application_id})
    db.execute(text("""
        SELECT s.share_id FROM app_private.shortlist_shares s
        WHERE EXISTS (SELECT 1 FROM app_private.shortlist_share_items si
                      WHERE si.share_id=s.share_id AND si.application_id=:id)
        ORDER BY s.share_id FOR UPDATE OF s
    """), {"id": application_id}).all()
    ambiguous = db.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM app_private.shortlist_shares s
            WHERE EXISTS (SELECT 1 FROM app_private.shortlist_share_items si
                          WHERE si.share_id=s.share_id AND si.application_id=:id)
              AND (NULLIF(BTRIM(s.note), '') IS NOT NULL OR EXISTS (
                  SELECT 1 FROM app_private.shortlist_feedback f
                  WHERE f.share_id=s.share_id AND f.application_id IS NULL
              ))
        )
    """), {"id": application_id}).scalar_one()
    if ambiguous:
        raise RetentionError("Shortlist có ghi chú hoặc phản hồi chung cần HR/Privacy rà soát trước khi xóa", status_code=409)



def position_has_inflight_purge(db, position_id: str) -> bool:
    """Durable fence survives process death or a lost database connection.

    Call while holding the position row lock for writes that could reopen or
    enqueue work. PROCESSING is deliberately not cleared on uncertain failure.
    """
    return db.execute(text("""
        SELECT 1 FROM app_private.deletion_jobs j
        JOIN app_private.application_retention_cases c ON c.retention_case_id=j.retention_case_id
        WHERE c.position_id=:position_id AND j.status='PROCESSING' LIMIT 1
    """), {"position_id": position_id}).first() is not None


def _require_no_active_processing(db, position_id: str) -> None:
    # Existing workers may still write extracted objects; don't start deletion
    # until all position operations and document processing have quiesced.
    if db.execute(text("""
        SELECT 1 FROM app_private.operations WHERE position_id=:position_id
          AND capability IN ('CV_PROCESSING','ASSESSMENT','RANKING')
          AND status IN ('PENDING','PROCESSING') LIMIT 1
    """), {"position_id": position_id}).first() or db.execute(text("""
        SELECT 1 FROM app_private.application_documents d
        JOIN app_private.applications a ON a.application_id=d.application_id
        WHERE a.position_id=:position_id AND d.file_processing_status IN ('RECEIVED','PROCESSING') LIMIT 1
    """), {"position_id": position_id}).first():
        raise RetentionError("Vị trí còn tác vụ hoặc tài liệu đang xử lý; chưa thể xóa", status_code=409)

def _has_global_role(db, user_id: str, roles: tuple[str, ...]) -> bool:
    return db.execute(text("""
        SELECT 1 FROM app_private.user_role_assignments
        WHERE user_id = :user_id AND revoked_at IS NULL AND role_code = ANY(:roles)
        LIMIT 1
    """), {"user_id": user_id, "roles": list(roles)}).first() is not None


def can_view_retention(db, user_id: str, position_id: str) -> bool:
    if _has_global_role(db, user_id, ("ADMIN", "HR_LEAD")):
        return True
    return db.execute(text("""
        SELECT 1 FROM app_private.position_assignments
        WHERE position_id = :position_id AND user_id = :user_id
          AND revoked_at IS NULL AND position_role IN ('HR_RECRUITER', 'HR_LEAD')
        LIMIT 1
    """), {"position_id": position_id, "user_id": user_id}).first() is not None


def can_confirm_retention(db, user_id: str, position_id: str) -> bool:
    if _has_global_role(db, user_id, ("ADMIN", "HR_LEAD")):
        return True
    if db.execute(text("""
        SELECT 1 FROM app_private.position_assignments
        WHERE position_id = :position_id AND user_id = :user_id
          AND revoked_at IS NULL AND position_role = 'HR_LEAD'
        LIMIT 1
    """), {"position_id": position_id, "user_id": user_id}).first() is not None:
        return True
    return db.execute(text("""
        SELECT 1 FROM app_private.position_access_grants
        WHERE position_id = :position_id AND user_id = :user_id
          AND revoked_at IS NULL AND permission_code = ANY(:permissions)
        LIMIT 1
    """), {"position_id": position_id, "user_id": user_id,
           "permissions": list(RETENTION_CONFIRM_PERMISSIONS)}).first() is not None


def _audit(db, *, actor_user_id: str, action: str, case: dict, outcome: str, metadata: dict) -> None:
    db.execute(text("""
        INSERT INTO app_private.audit_events
            (actor_user_id, action_type, object_type, object_id, position_id, outcome, metadata)
        VALUES (:actor, :action, 'RETENTION_CASE', :case_id, :position_id, :outcome, CAST(:metadata AS jsonb))
    """), {
        "actor": actor_user_id, "action": action,
        "case_id": str(case["retention_case_id"]),
        "position_id": str(case["position_id"]) if case.get("position_id") else None,
        "outcome": outcome, "metadata": json.dumps(metadata, ensure_ascii=False),
    })


def generate_retention_cases(db, *, position_id: str, actor_user_id: str) -> dict:
    position = db.execute(text("""
        SELECT position_id, status, closed_at FROM app_private.positions
        WHERE position_id = :position_id FOR UPDATE
    """), {"position_id": position_id}).mappings().first()
    if not position:
        raise RetentionError("Không tìm thấy vị trí", status_code=404)
    if position["status"] != "CLOSED" or not position["closed_at"]:
        raise RetentionError("Chỉ tạo retention case cho vị trí đã đóng", status_code=409)

    policy = db.execute(text("""
        SELECT policy_version, retention_months FROM app_private.retention_policy_versions
        WHERE status = 'APPROVED'
        ORDER BY created_at DESC, policy_version DESC
        LIMIT 1
    """)).mappings().first()
    if not policy:
        raise RetentionError("Chưa có retention policy đã phê duyệt", status_code=503)
    months = int(policy["retention_months"] or settings.RETENTION_MONTHS)
    closed_at = _as_utc(position["closed_at"])
    due_date = add_months(closed_at, months)
    if due_date > _now():
        return {"position_id": position_id, "policy_version": policy["policy_version"],
                "retention_months": months, "due_date": due_date, "created_count": 0, "cases": []}

    applications = db.execute(text("""
        SELECT application_id FROM app_private.applications
        WHERE position_id = :position_id
          AND NOT EXISTS (
              SELECT 1 FROM app_private.application_retention_cases c
              WHERE c.application_id = applications.application_id
                AND c.status IN ('PENDING', 'SCHEDULED_FOR_DELETION', 'DELETED')
          )
        ORDER BY created_at, application_id
    """), {"position_id": position_id}).mappings().all()

    created = []
    for application in applications:
        application_id = str(application["application_id"])
        row = db.execute(text("""
            INSERT INTO app_private.application_retention_cases
                (application_id, position_id, application_opaque_id, policy_version,
                 position_closed_at, due_date, status)
            VALUES (:application_id, :position_id, :opaque_id, :policy_version,
                    :closed_at, :due_date, 'PENDING')
            RETURNING retention_case_id, application_id, position_id, application_opaque_id,
                      policy_version, position_closed_at, due_date, status,
                      confirmed_by, confirmed_at, created_at
        """), {
            "application_id": application_id, "position_id": position_id,
            "opaque_id": application_opaque_id(application_id),
            "policy_version": policy["policy_version"], "closed_at": closed_at,
            "due_date": due_date,
        }).mappings().one()
        created.append(dict(row))

    if created:
        _audit(db, actor_user_id=actor_user_id, action="GENERATE_RETENTION_CASES",
               case={"retention_case_id": created[0]["retention_case_id"], "position_id": position_id},
               outcome="SUCCESS", metadata={
                   "policy_version": policy["policy_version"], "created_count": len(created),
                   "position_id": position_id,
               })
    return {"position_id": position_id, "policy_version": policy["policy_version"],
            "retention_months": months, "due_date": due_date,
            "created_count": len(created), "cases": [public_case(row) for row in created]}


def confirm_retention_case(db, *, case_id: str, actor_user_id: str) -> dict:
    case, position = _lock_case_and_position(db, case_id)
    if case["status"] == "DELETED":
        raise RetentionError("Retention case đã được xóa dữ liệu", status_code=409)
    if case["status"] == "CANCELLED":
        raise RetentionError("Retention case đã bị hủy", status_code=409)
    if _as_utc(case["due_date"]) > _now():
        raise RetentionError("Retention case chưa đến hạn xóa", status_code=422)
    _require_original_closure(case, position)
    if case["status"] == "PENDING":
        db.execute(text("""
            UPDATE app_private.application_retention_cases
            SET status = 'SCHEDULED_FOR_DELETION', confirmed_by = :actor, confirmed_at = NOW()
            WHERE retention_case_id = :case_id
        """), {"actor": actor_user_id, "case_id": case_id})
        case.update({"status": "SCHEDULED_FOR_DELETION", "confirmed_by": actor_user_id,
                     "confirmed_at": _now()})
    job = db.execute(text("""
        SELECT job_id FROM app_private.deletion_jobs
        WHERE retention_case_id = :case_id AND status IN ('PENDING', 'PROCESSING')
        ORDER BY created_at DESC LIMIT 1
    """), {"case_id": case_id}).scalar_one_or_none()
    if not job:
        db.execute(text("""
            INSERT INTO app_private.deletion_jobs (retention_case_id, application_opaque_id, status)
            VALUES (:case_id, :opaque_id, 'PENDING')
        """), {"case_id": case_id, "opaque_id": case.get("application_opaque_id")})
    exists_event = db.execute(text("""
        SELECT 1 FROM app_private.deletion_events
        WHERE application_opaque_id = :opaque_id AND result = 'CONFIRMED'
        LIMIT 1
    """), {"opaque_id": case.get("application_opaque_id")}).first()
    if not exists_event:
        db.execute(text("""
            INSERT INTO app_private.deletion_events
                (application_opaque_id, confirmed_by, policy_version, confirmed_at, result)
            VALUES (:opaque_id, :actor, :policy_version, NOW(), 'CONFIRMED')
        """), {"opaque_id": case.get("application_opaque_id"), "actor": actor_user_id,
               "policy_version": case.get("policy_version")})
    _audit(db, actor_user_id=actor_user_id, action="CONFIRM_RETENTION_DELETION", case=case,
           outcome="SCHEDULED_FOR_DELETION", metadata={
               "application_opaque_id": case.get("application_opaque_id"),
               "policy_version": case.get("policy_version"),
           })
    return public_case(get_case(db, case_id))


def cancel_retention_case(db, *, case_id: str, actor_user_id: str) -> dict:
    case, _ = _lock_case_and_position(db, case_id)
    if case["status"] == "DELETED":
        raise RetentionError("Retention case đã được xóa dữ liệu", status_code=409)
    if db.execute(text("""
        SELECT 1 FROM app_private.deletion_jobs
        WHERE retention_case_id=:id AND status='PROCESSING' LIMIT 1
    """), {"id": case_id}).first():
        raise RetentionError("Case đang xóa hoặc cần đối soát phục hồi; không thể hủy", status_code=409)
    if case["status"] != "CANCELLED":
        db.execute(text("""
            UPDATE app_private.application_retention_cases
            SET status = 'CANCELLED'
            WHERE retention_case_id = :case_id
        """), {"case_id": case_id})
        db.execute(text("""
            UPDATE app_private.deletion_jobs
            SET status = 'FAILED', error = 'CANCELLED_BEFORE_EXECUTION', completed_at = NOW()
            WHERE retention_case_id = :case_id AND status IN ('PENDING', 'PROCESSING')
        """), {"case_id": case_id})
        _audit(db, actor_user_id=actor_user_id, action="CANCEL_RETENTION_CASE", case=case,
               outcome="CANCELLED", metadata={
                   "application_opaque_id": case.get("application_opaque_id"),
                   "policy_version": case.get("policy_version"),
               })
    return public_case(get_case(db, case_id))


def _mark_recovery_required(case: dict, job_id: str, actor_user_id: str, error_type: str) -> None:
    """Best effort diagnostic; the already committed PROCESSING fence stays put."""
    db = SessionLocal()
    try:
        current, _ = _lock_case_and_position(db, str(case["retention_case_id"]))
        if current["status"] == "SCHEDULED_FOR_DELETION":
            db.execute(text("""
                UPDATE app_private.deletion_jobs SET error=:error
                WHERE job_id=:job_id AND status='PROCESSING'
            """), {"job_id": job_id, "error": f"RECOVERY_REQUIRED:{error_type}"})
            _audit(db, actor_user_id=actor_user_id, action="EXECUTE_RETENTION_DELETION", case=case,
                   outcome="FAILED", metadata={"application_opaque_id": case.get("application_opaque_id"),
                                               "policy_version": case.get("policy_version"),
                                               "error_type": error_type, "recovery_required": True})
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _count(db, sql: str, params: dict) -> int:
    return int(db.execute(text(sql), params).scalar_one() or 0)


def execute_retention_case(*, case_id: str, actor_user_id: str, recovery: bool = False) -> dict:
    """Execute once, or resume a fenced job only after explicit operator review.

    PROCESSING is committed before storage is touched. It remains a durable
    fence on errors/crash; normal execute cannot implicitly retry uncertain I/O.
    Storage and PostgreSQL are still not an atomic transaction.
    """
    job_id: str | None = None
    case_snapshot: dict | None = None
    fenced = False
    guard = SessionLocal()
    db = SessionLocal()
    try:
        # A separate transaction-scoped lock spans both data transactions. If
        # this connection dies, the durable fence remains; explicit recovery
        # requires an operator to stop the old executor and settle provider I/O.
        acquired = guard.execute(text("SELECT pg_try_advisory_xact_lock(hashtextextended(:id, 741936))"), {"id": case_id}).scalar_one()
        if not acquired:
            raise RetentionError("Case đang được xử lý; không chạy đồng thời", status_code=409)
        case = get_case(db, case_id)
        if case["status"] == "DELETED":
            job = db.execute(text("""
                SELECT result_summary FROM app_private.deletion_jobs
                WHERE retention_case_id = :case_id AND status = 'COMPLETED'
                ORDER BY created_at DESC LIMIT 1
            """), {"case_id": case_id}).mappings().first()
            return {"retention_case_id": case_id,
                    "application_opaque_id": case.get("application_opaque_id"),
                    "status": "DELETED", "result_summary": job["result_summary"] if job else {}}
        case, position = _lock_case_and_position(db, case_id)
        case_snapshot = case
        # The case may have completed while the position lock was awaited.
        if case["status"] == "DELETED":
            job = db.execute(text("""
                SELECT result_summary FROM app_private.deletion_jobs
                WHERE retention_case_id=:case_id AND status='COMPLETED'
                ORDER BY created_at DESC LIMIT 1
            """), {"case_id": case_id}).mappings().first()
            return {"retention_case_id": case_id, "application_opaque_id": case.get("application_opaque_id"),
                    "status": "DELETED", "result_summary": job["result_summary"] if job else {}}
        if case["status"] != "SCHEDULED_FOR_DELETION" or not case.get("application_id"):
            raise RetentionError("Retention case chưa được xác nhận hoặc không còn application", status_code=409)
        if _as_utc(case["due_date"]) > _now():
            raise RetentionError("Retention case chưa đến hạn xóa", status_code=409)
        _require_original_closure(case, position)
        _require_no_active_processing(db, str(case["position_id"]))
        if db.execute(text("""
            SELECT 1 FROM app_private.deletion_jobs j
            JOIN app_private.application_retention_cases c ON c.retention_case_id=j.retention_case_id
            WHERE c.position_id=:position AND c.retention_case_id<>:case_id
              AND j.status='PROCESSING' LIMIT 1
        """), {"position": str(case["position_id"]), "case_id": case_id}).first():
            raise RetentionError("Vị trí có case xóa khác đang xử lý hoặc cần phục hồi", status_code=409)
        application_id = str(case["application_id"])
        params = {"application_id": application_id}
        _guard_share_level_text(db, application_id)
        latest_job = db.execute(text("""
            SELECT job_id, status FROM app_private.deletion_jobs
            WHERE retention_case_id=:case_id ORDER BY created_at DESC LIMIT 1
        """), {"case_id": case_id}).mappings().first()
        if latest_job and latest_job["status"] == "PROCESSING":
            if not recovery:
                raise RetentionError("Case cần đối soát phục hồi trước khi thử lại", status_code=409)
            job_id = str(latest_job["job_id"])
            _audit(db, actor_user_id=actor_user_id, action="RECOVER_RETENTION_DELETION", case=case,
                   outcome="RETRY", metadata={"application_opaque_id": case.get("application_opaque_id"),
                                               "policy_version": case.get("policy_version")})
        else:
            if recovery:
                raise RetentionError("Case không có job cần phục hồi", status_code=409)
            if latest_job and latest_job["status"] == "PENDING":
                job_id = str(latest_job["job_id"])
                db.execute(text("UPDATE app_private.deletion_jobs SET status='PROCESSING', error=NULL, completed_at=NULL WHERE job_id=:job_id"), {"job_id": job_id})
            else:
                job_id = str(db.execute(text("""
                    INSERT INTO app_private.deletion_jobs (retention_case_id, application_opaque_id, status)
                    VALUES (:case_id, :opaque_id, 'PROCESSING') RETURNING job_id
                """), {"case_id": case_id, "opaque_id": case.get("application_opaque_id")}).scalar_one())
        db.commit()
        fenced = True

        # Reacquire all row locks and repeat guards after the fence commit. No
        # storage access occurs before these checks and the durable fence.
        case, position = _lock_case_and_position(db, case_id)
        if case["status"] != "SCHEDULED_FOR_DELETION" or str(case.get("application_id")) != application_id:
            raise RetentionError("Retention case đã thay đổi trước khi xóa", status_code=409)
        _require_original_closure(case, position)
        _require_no_active_processing(db, str(case["position_id"]))
        _guard_share_level_text(db, application_id)
        originals = [dict(row) for row in db.execute(text("""
            SELECT bucket, storage_path FROM app_private.application_documents
            WHERE application_id = :application_id
        """), params).mappings().all()]
        extracted_paths = [row[0] for row in db.execute(text("""
            SELECT pr.extracted_text_storage_path
            FROM app_private.document_processing_runs pr
            JOIN app_private.application_documents d ON d.document_id = pr.document_id
            WHERE d.application_id = :application_id AND pr.extracted_text_storage_path IS NOT NULL
        """), params).all()]
        storage_summary = delete_storage_objects(originals, extracted_paths)
        counts = {
            "documents": _count(db, "SELECT COUNT(*) FROM app_private.application_documents WHERE application_id=:application_id", params),
            "document_processing_runs": _count(db, """
                SELECT COUNT(*) FROM app_private.document_processing_runs pr
                JOIN app_private.application_documents d ON d.document_id = pr.document_id
                WHERE d.application_id = :application_id
            """, params),
            "profile_versions": _count(db, "SELECT COUNT(*) FROM app_private.profile_versions WHERE application_id=:application_id", params),
            "profile_facts": _count(db, """
                SELECT COUNT(*) FROM app_private.profile_facts f
                JOIN app_private.profile_versions p ON p.profile_version_id = f.profile_version_id
                WHERE p.application_id = :application_id
            """, params),
            "assessment_runs": _count(db, "SELECT COUNT(*) FROM app_private.assessment_runs WHERE application_id=:application_id", params),
            "criterion_results": _count(db, """
                SELECT COUNT(*) FROM app_private.criterion_assessment_results r
                JOIN app_private.assessment_runs a ON a.assessment_id = r.assessment_id
                WHERE a.application_id = :application_id
            """, params),
            "evidence_items": _count(db, """
                SELECT COUNT(*) FROM app_private.evidence_items e
                JOIN app_private.criterion_assessment_results r ON r.result_id = e.criterion_result_id
                JOIN app_private.assessment_runs a ON a.assessment_id = r.assessment_id
                WHERE a.application_id = :application_id
            """, params),
            "ranking_items": _count(db, "SELECT COUNT(*) FROM app_private.ranking_items WHERE application_id=:application_id", params),
            "shortlist_share_items": _count(db, "SELECT COUNT(*) FROM app_private.shortlist_share_items WHERE application_id=:application_id", params),
            "shortlist_feedback": _count(db, "SELECT COUNT(*) FROM app_private.shortlist_feedback WHERE application_id=:application_id", params),
            "duplicate_signals": _count(db, "SELECT COUNT(*) FROM app_private.duplicate_signals WHERE application_id_1=:application_id OR application_id_2=:application_id", params),
            "cv_chunk_embeddings": _count(db, "SELECT COUNT(*) FROM app_private.cv_chunk_embeddings WHERE application_id=:application_id", params),
            "private_notes": _count(db, "SELECT COUNT(*) FROM app_private.application_private_notes WHERE application_id=:application_id", params),
            "identities": _count(db, "SELECT COUNT(*) FROM app_private.application_identities WHERE application_id=:application_id", params),
            "status_events": _count(db, "SELECT COUNT(*) FROM app_private.application_status_events WHERE application_id=:application_id", params),
            "batch_items_unlinked": _count(db, "SELECT COUNT(*) FROM app_private.cv_batch_items WHERE application_id=:application_id", params),
        }

        db.execute(text("DELETE FROM app_private.shortlist_feedback WHERE application_id=:application_id"), params)
        # Prevent new unscoped comments on a share whose historical membership
        # is no longer visible. Existing comments were checked before storage.
        db.execute(text("""
            UPDATE app_private.shortlist_shares SET share_level_feedback_blocked=TRUE
            WHERE share_id IN (SELECT share_id FROM app_private.shortlist_share_items WHERE application_id=:application_id)
        """), params)
        db.execute(text("DELETE FROM app_private.shortlist_share_items WHERE application_id=:application_id"), params)
        db.execute(text("DELETE FROM app_private.ranking_items WHERE application_id=:application_id"), params)
        db.execute(text("DELETE FROM app_private.duplicate_signals WHERE application_id_1=:application_id OR application_id_2=:application_id"), params)
        db.execute(text("DELETE FROM app_private.cv_chunk_embeddings WHERE application_id=:application_id"), params)
        db.execute(text("DELETE FROM app_private.assessment_runs WHERE application_id=:application_id"), params)
        db.execute(text("DELETE FROM app_private.profile_versions WHERE application_id=:application_id"), params)
        db.execute(text("DELETE FROM app_private.application_private_notes WHERE application_id=:application_id"), params)
        db.execute(text("DELETE FROM app_private.application_identities WHERE application_id=:application_id"), params)
        db.execute(text("DELETE FROM app_private.application_status_events WHERE application_id=:application_id"), params)
        db.execute(text("DELETE FROM app_private.application_documents WHERE application_id=:application_id"), params)
        db.execute(text("""
            UPDATE app_private.cv_batch_items
            SET application_id = NULL, original_filename = '[DELETED]'
            WHERE application_id = :application_id
        """), params)
        db.execute(text("DELETE FROM app_private.applications WHERE application_id=:application_id"), params)

        summary = {**counts, **storage_summary,
                   "application_opaque_id": case.get("application_opaque_id"),
                   "policy_version": case.get("policy_version")}
        db.execute(text("""
            UPDATE app_private.application_retention_cases
            SET status = 'DELETED'
            WHERE retention_case_id = :case_id
        """), {"case_id": case_id})
        db.execute(text("""
            UPDATE app_private.deletion_jobs
            SET status = 'COMPLETED', files_deleted = TRUE, data_deleted = TRUE,
                result_summary = CAST(:summary AS jsonb), error = NULL, completed_at = NOW()
            WHERE job_id = :job_id
        """), {"job_id": job_id, "summary": json.dumps(summary, ensure_ascii=False)})
        updated_event = db.execute(text("""
            UPDATE app_private.deletion_events
            SET completed_at = NOW(), result = 'COMPLETED'
            WHERE event_id = (
                SELECT event_id FROM app_private.deletion_events
                WHERE application_opaque_id = :opaque_id AND result = 'CONFIRMED'
                ORDER BY confirmed_at DESC LIMIT 1
            )
            RETURNING event_id
        """), {"opaque_id": case.get("application_opaque_id")}).scalar_one_or_none()
        if not updated_event:
            db.execute(text("""
                INSERT INTO app_private.deletion_events
                    (application_opaque_id, confirmed_by, policy_version, confirmed_at, completed_at, result)
                VALUES (:opaque_id, :actor, :policy_version, :confirmed_at, NOW(), 'COMPLETED')
            """), {"opaque_id": case.get("application_opaque_id"), "actor": actor_user_id,
                   "policy_version": case.get("policy_version"), "confirmed_at": case.get("confirmed_at")})
        _audit(db, actor_user_id=actor_user_id, action="EXECUTE_RETENTION_DELETION", case=case,
               outcome="DELETED", metadata=summary)
        db.commit()
        return {"retention_case_id": case_id,
                "application_opaque_id": case.get("application_opaque_id"),
                "status": "DELETED", "result_summary": summary}
    except Exception as exc:
        db.rollback()
        if fenced and case_snapshot is not None and job_id is not None:
            _mark_recovery_required(case_snapshot, job_id, actor_user_id, type(exc).__name__)
        if isinstance(exc, RetentionError):
            raise
        raise RetentionError("Không thể hoàn tất xóa dữ liệu ứng viên", status_code=500) from exc
    finally:
        db.close()
        guard.close()
