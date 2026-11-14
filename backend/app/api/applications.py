from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import Response
from typing import List, Optional
from uuid import UUID, uuid4
from app.core.security import ensure_token_is_current, get_current_user
from app.core.permissions import (
    application_access, can_update_application_status, check_position_access, is_system_admin,
)
from app.services.ai_config import sanitize_provider_snapshot
from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import (
    FileValidationError,
    InvalidStatusTransitionError,
    NotFoundError
)
from app.schemas.applications import (
    Application,
    ApplicationWithAssessment,
    ApplicationStatus,
    ApplicationStatusUpdate,
)
from app.schemas.common import OperationResponse
from app.db.supabase import get_supabase_client
from app.db.database import SessionLocal
from sqlalchemy import text
from app.services.document_processor import document_processor
import os
import json
import aiofiles
from urllib.parse import quote

router = APIRouter()
logger = get_logger(__name__)

# Valid status transitions per business rules
VALID_TRANSITIONS = {
    ApplicationStatus.NEW: [ApplicationStatus.IN_REVIEW, ApplicationStatus.REJECTED_SCREENING],
    ApplicationStatus.IN_REVIEW: [ApplicationStatus.SHORTLIST, ApplicationStatus.REJECTED_SCREENING],
    ApplicationStatus.SHORTLIST: [ApplicationStatus.IN_REVIEW, ApplicationStatus.INTERVIEW, ApplicationStatus.REJECTED_SCREENING],
    ApplicationStatus.INTERVIEW: [ApplicationStatus.REJECTED_INTERVIEW, ApplicationStatus.OFFERED],
    ApplicationStatus.OFFERED: [ApplicationStatus.ACCEPTED],
    ApplicationStatus.REJECTED_SCREENING: [],  # Terminal; reopen requires special permission
    ApplicationStatus.REJECTED_INTERVIEW: [],  # Terminal
    ApplicationStatus.ACCEPTED: [],
}


@router.post("/upload-batch/{position_id}", response_model=OperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_cv_batch(position_id: UUID, files: List[UploadFile] = File(...),
                          current_user: dict = Depends(get_current_user)):
    """Save the batch transactionally; the worker cannot see it until commit."""
    user_id, position_id_str = current_user["user_id"], str(position_id)
    await check_position_access(position_id, current_user, required_roles=["HR_RECRUITER"])
    if not files or len(files) > settings.MAX_FILES_PER_BATCH:
        raise HTTPException(status_code=400, detail=f"Vui lòng chọn từ 1 đến {settings.MAX_FILES_PER_BATCH} tệp")
    sizes = []
    for file in files:
        file.file.seek(0, os.SEEK_END); sizes.append(file.file.tell()); file.file.seek(0)
    total_size = sum(sizes)
    if total_size > settings.MAX_BATCH_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Tổng dung lượng lô CV vượt giới hạn 250 MB")
    if settings.STORAGE_BACKEND not in ("local", "supabase"):
        raise HTTPException(status_code=500, detail="Storage backend is not configured")
    storage = get_supabase_client() if settings.STORAGE_BACKEND == "supabase" else None
    if settings.STORAGE_BACKEND == "supabase" and not storage:
        raise HTTPException(status_code=503, detail="Supabase storage is not configured")

    db = SessionLocal()
    saved_paths = []
    accepted = failed = 0
    try:
        pos = db.execute(text("SELECT status FROM app_private.positions WHERE position_id = :id FOR UPDATE"), {"id": position_id_str}).scalar_one_or_none()
        if pos is None:
            raise NotFoundError("Position")
        if pos != "OPEN":
            raise HTTPException(status_code=400, detail="Không thể tải CV cho vị trí đã đóng hoặc tạm dừng")
        approved = db.execute(text("""SELECT 1 FROM app_private.criteria_versions WHERE position_id = :id AND status = 'APPROVED'
            AND jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions WHERE position_id = :id ORDER BY version_number DESC LIMIT 1) LIMIT 1"""), {"id": position_id_str}).first()
        if not approved:
            raise HTTPException(status_code=400, detail="Tiêu chí cần được HR và Hiring Manager duyệt trước khi tải CV")
        active = db.execute(text("""
            SELECT 1 FROM app_private.operations WHERE position_id = :id
              AND capability IN ('CV_PROCESSING', 'ASSESSMENT', 'RANKING') AND status IN ('PENDING', 'PROCESSING') LIMIT 1
        """), {"id": position_id_str}).first()
        if active:
            raise HTTPException(status_code=409, detail="Vị trí đang có tác vụ xử lý. Vui lòng đợi tác vụ hoàn tất trước khi tải thêm CV.")
        operation_id = db.execute(text("""
            INSERT INTO app_private.operations (position_id, capability, status, requested_by)
            VALUES (:position_id, 'CV_PROCESSING', 'PENDING', :user_id) RETURNING operation_id
        """), {"position_id": position_id_str, "user_id": user_id}).scalar_one()
        batch_id = db.execute(text("""
            INSERT INTO app_private.cv_batches (position_id, uploaded_by, operation_id, status, total_files, total_size_bytes)
            VALUES (:position_id, :user_id, :operation_id, 'PROCESSING', :total, :size) RETURNING batch_id
        """), {"position_id": position_id_str, "user_id": user_id, "operation_id": operation_id,
                "total": len(files), "size": total_size}).scalar_one()
        for file, size in zip(files, sizes):
            filename = os.path.basename(file.filename or 'unnamed')
            error = None
            detected_mime = None
            if size > settings.MAX_FILE_SIZE_BYTES:
                error = "FILE_TOO_LARGE"
            else:
                content = await file.read()
                try:
                    detected_mime = await document_processor.validate_file(content, filename, file.content_type)
                except FileValidationError as exc:
                    error = str(exc)
            app_id = None
            if error:
                failed += 1
            else:
                app_id = db.execute(text("""
                    INSERT INTO app_private.applications (position_id, created_by)
                    VALUES (:position_id, :user_id) RETURNING application_id
                """), {"position_id": position_id_str, "user_id": user_id}).scalar_one()
                extension = '.pdf' if detected_mime == 'application/pdf' else '.docx'
                storage_path = f"{position_id_str}/{app_id}/{uuid4()}{extension}"
                # Track before I/O so even a partially written file or an
                # upload that errors after writing is eligible for cleanup.
                saved_paths.append(storage_path)
                if settings.STORAGE_BACKEND == "local":
                    full_path = os.path.join(settings.LOCAL_STORAGE_PATH, settings.SUPABASE_STORAGE_BUCKET_CV, storage_path)
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    async with aiofiles.open(full_path, "wb") as out:
                        await out.write(content)
                else:
                    storage.storage.from_(settings.SUPABASE_STORAGE_BUCKET_CV).upload(
                        path=storage_path, file=content, file_options={"content-type": detected_mime})
                document_id = db.execute(text("""
                    INSERT INTO app_private.application_documents (application_id, document_type, bucket, storage_path,
                        original_filename, mime_type, size_bytes, file_processing_status)
                    VALUES (:app_id, 'CV', :bucket, :storage_path, :filename, :mime, :size, 'RECEIVED') RETURNING document_id
                """), {"app_id": app_id, "bucket": settings.SUPABASE_STORAGE_BUCKET_CV, "storage_path": storage_path,
                        "filename": filename, "mime": detected_mime, "size": size}).scalar_one()
                db.execute(text("INSERT INTO app_private.application_identities (application_id) VALUES (:id)"), {"id": app_id})
                db.execute(text("""
                    INSERT INTO app_private.document_processing_runs (document_id, operation_id, extraction_type, status)
                    VALUES (:document_id, :operation_id, 'INITIAL_EXTRACTION', 'PENDING')
                """), {"document_id": document_id, "operation_id": operation_id})
                accepted += 1
            db.execute(text("""
                INSERT INTO app_private.cv_batch_items (batch_id, original_filename, declared_mime_type, detected_mime_type,
                    size_bytes, validation_result, error_code, application_id)
                VALUES (:batch_id, :filename, :declared, :detected, :size, :result, :error, :app_id)
            """), {"batch_id": batch_id, "filename": filename, "declared": file.content_type, "detected": detected_mime,
                    "size": size, "result": 'ERROR' if error else 'ACCEPTED', "error": error, "app_id": app_id})
        db.execute(text("UPDATE app_private.cv_batches SET failed_files = :failed WHERE batch_id = :id"), {"failed": failed, "id": batch_id})
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, position_id, outcome, metadata)
            VALUES (:user_id, 'UPLOAD_CV_BATCH', 'CV_BATCH', :batch_id, :position_id, 'SUCCESS', CAST(:metadata AS jsonb))
        """), {"user_id": user_id, "batch_id": batch_id, "position_id": position_id_str,
                "metadata": json.dumps({"total_files": len(files), "accepted": accepted, "failed": failed})})
        db.commit()
        return OperationResponse(operation_id=operation_id, status="pending",
                                 message=f"Đã nhận {accepted} tệp hợp lệ, {failed} tệp lỗi.")
    except Exception:
        db.rollback()
        # Database rollback must not leave candidate documents in storage.
        for path in saved_paths:
            try:
                if settings.STORAGE_BACKEND == "local":
                    full_path = os.path.join(settings.LOCAL_STORAGE_PATH, settings.SUPABASE_STORAGE_BUCKET_CV, path)
                    if os.path.exists(full_path):
                        os.remove(full_path)
                else:
                    storage.storage.from_(settings.SUPABASE_STORAGE_BUCKET_CV).remove([path])
            except Exception as exc:
                logger.error("Could not remove orphaned upload", error_type=type(exc).__name__)
        raise
    finally:
        db.close()


@router.post("/{application_id}/reprocess", response_model=OperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def reprocess_application_cv(application_id: UUID, current_user: dict = Depends(get_current_user)):
    """Queue one failed CV document for extraction/profile/assessment again.

    A new operation and one-item batch are created for traceability; the
    original upload batch remains unchanged as historical evidence.
    """
    user_id, app_id = current_user["user_id"], str(application_id)
    db = SessionLocal()
    try:
        app = db.execute(text("""
            SELECT application_id, position_id FROM app_private.applications
            WHERE application_id = :app_id FOR UPDATE
        """), {"app_id": app_id}).mappings().first()
        if not app:
            raise NotFoundError("Application")
        position_id = str(app["position_id"])
        if not can_update_application_status(user_id, position_id):
            raise HTTPException(status_code=403, detail="Chỉ HR phụ trách mới được xử lý lại CV")

        position_status = db.execute(text("""
            SELECT status FROM app_private.positions WHERE position_id = :id FOR UPDATE
        """), {"id": position_id}).scalar_one_or_none()
        if position_status is None:
            raise NotFoundError("Position")
        if position_status != "OPEN":
            raise HTTPException(status_code=400, detail="Không thể xử lý lại CV cho vị trí đã đóng hoặc tạm dừng")
        approved = db.execute(text("""
            SELECT 1 FROM app_private.criteria_versions WHERE position_id = :id AND status = 'APPROVED'
              AND jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions
                                   WHERE position_id = :id ORDER BY version_number DESC LIMIT 1) LIMIT 1
        """), {"id": position_id}).first()
        if not approved:
            raise HTTPException(status_code=400, detail="Tiêu chí cần được HR và Hiring Manager duyệt trước khi tải CV")
        active = db.execute(text("""
            SELECT 1 FROM app_private.operations WHERE position_id = :id
              AND capability IN ('CV_PROCESSING', 'ASSESSMENT', 'RANKING')
              AND status IN ('PENDING', 'PROCESSING') LIMIT 1
        """), {"id": position_id}).first()
        if active:
            raise HTTPException(status_code=409, detail="Vị trí đang có tác vụ xử lý. Vui lòng đợi tác vụ hoàn tất trước khi xử lý lại CV.")

        doc = db.execute(text("""
            SELECT * FROM app_private.application_documents
            WHERE application_id = :app_id AND document_type = 'CV'
            ORDER BY created_at DESC, document_id DESC LIMIT 1 FOR UPDATE
        """), {"app_id": app_id}).mappings().first()
        if not doc:
            raise NotFoundError("CV document")
        if doc["file_processing_status"] not in ("NEEDS_HR_REVIEW", "ERROR_UNSUPPORTED"):
            raise HTTPException(status_code=409, detail="Hồ sơ không ở trạng thái cần xử lý lại")

        operation_id = db.execute(text("""
            INSERT INTO app_private.operations (position_id, capability, status, requested_by)
            VALUES (:position_id, 'CV_PROCESSING', 'PENDING', :user_id) RETURNING operation_id
        """), {"position_id": position_id, "user_id": user_id}).scalar_one()
        batch_id = db.execute(text("""
            INSERT INTO app_private.cv_batches
                (position_id, uploaded_by, operation_id, status, total_files, total_size_bytes)
            VALUES (:position_id, :user_id, :operation_id, 'PROCESSING', 1, :size) RETURNING batch_id
        """), {"position_id": position_id, "user_id": user_id, "operation_id": operation_id,
                "size": doc["size_bytes"]}).scalar_one()
        db.execute(text("""
            INSERT INTO app_private.cv_batch_items
                (batch_id, original_filename, declared_mime_type, detected_mime_type,
                 size_bytes, validation_result, application_id)
            VALUES (:batch_id, :filename, :mime, :mime, :size, 'ACCEPTED', :app_id)
        """), {"batch_id": batch_id, "filename": doc["original_filename"], "mime": doc["mime_type"],
                "size": doc["size_bytes"], "app_id": app_id})
        db.execute(text("""
            INSERT INTO app_private.application_identities (application_id) VALUES (:id)
            ON CONFLICT (application_id) DO NOTHING
        """), {"id": app_id})
        db.execute(text("""
            UPDATE app_private.application_documents
            SET file_processing_status = 'RECEIVED', processing_error = NULL
            WHERE document_id = :document_id
        """), {"document_id": doc["document_id"]})
        db.execute(text("""
            INSERT INTO app_private.document_processing_runs (document_id, operation_id, extraction_type, status)
            VALUES (:document_id, :operation_id, 'INITIAL_EXTRACTION', 'PENDING')
        """), {"document_id": doc["document_id"], "operation_id": operation_id})
        db.execute(text("""
            INSERT INTO app_private.audit_events
                (actor_user_id, action_type, object_type, object_id, position_id, outcome, metadata)
            VALUES (:user_id, 'REPROCESS_CV_DOCUMENT', 'APPLICATION', :app_id, :position_id, 'SUCCESS',
                    CAST(:metadata AS jsonb))
        """), {"user_id": user_id, "app_id": app_id, "position_id": position_id,
                "metadata": json.dumps({"document_id": str(doc["document_id"]), "batch_id": str(batch_id)})})
        db.commit()
        return OperationResponse(operation_id=operation_id, status="pending",
                                 message="Đã đưa CV vào hàng đợi xử lý lại.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _enrich_file_status(app: dict) -> None:
    docs = app.get("documents") or []
    if not docs:
        app["file_processing_status"] = "UNKNOWN"
        return
    errors = [d for d in docs if d.get("file_processing_status") in ("ERROR_UNSUPPORTED", "NEEDS_HR_REVIEW") or d.get("processing_error")]
    if errors:
        app["file_processing_status"] = "NEEDS_HR_REVIEW"
        app["file_error"] = errors[0].get("processing_error")
    elif any(d.get("file_processing_status") in ("RECEIVED", "PROCESSING") for d in docs):
        app["file_processing_status"] = "PROCESSING"
    else:
        app["file_processing_status"] = "COMPLETED"


def _normalize_application(app: dict) -> None:
    identity = app.get("identity")
    if isinstance(identity, list):
        app["identity"] = identity[0] if identity else None
    _enrich_file_status(app)


@router.get("", response_model=List[ApplicationWithAssessment])
async def list_applications(
    position_id: UUID = Query(...),
    status_filter: Optional[ApplicationStatus] = Query(None, alias="status"),
    matching_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """List applications only for HR assigned to the position."""
    await check_position_access(position_id, current_user, required_roles=["HR_RECRUITER"])
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT a.*, row_to_json(i) AS identity, COALESCE(d.documents, '[]'::jsonb) AS documents,
                   row_to_json(latest) AS latest_assessment,
                   EXISTS (SELECT 1 FROM app_private.duplicate_signals ds
                           WHERE ds.position_id = a.position_id AND ds.review_status = 'PENDING'
                             AND (ds.application_id_1 = a.application_id OR ds.application_id_2 = a.application_id)) AS has_duplicate_warning
            FROM app_private.applications a
            LEFT JOIN app_private.application_identities i ON i.application_id = a.application_id
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(to_jsonb(ad) ORDER BY ad.created_at DESC) AS documents
                FROM app_private.application_documents ad WHERE ad.application_id = a.application_id
            ) d ON TRUE
            LEFT JOIN LATERAL (
                SELECT ar.* FROM app_private.assessment_runs ar
                WHERE ar.application_id = a.application_id AND ar.status = 'COMPLETED'
                  AND ar.profile_version_id = (SELECT profile_version_id FROM app_private.profile_versions
                      WHERE application_id = a.application_id AND status = 'COMPLETED' ORDER BY version_number DESC LIMIT 1)
                  AND ar.criteria_version_id = (SELECT c.criteria_version_id FROM app_private.criteria_versions c
                      WHERE c.position_id = a.position_id AND c.status = 'APPROVED'
                        AND c.jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions
                            WHERE position_id = a.position_id ORDER BY version_number DESC LIMIT 1)
                      ORDER BY c.version_number DESC LIMIT 1)
                ORDER BY ar.created_at DESC, ar.assessment_id DESC LIMIT 1
            ) latest ON TRUE
            WHERE a.position_id = :position_id
              AND (CAST(:status_filter AS text) IS NULL OR a.application_status = :status_filter)
              AND (CAST(:matching_status AS text) IS NULL OR COALESCE(latest.matching_status, 'NOT_ASSESSED') = :matching_status)
            ORDER BY a.created_at DESC, a.application_id DESC LIMIT :page_size OFFSET :offset
        """), {"position_id": str(position_id), "status_filter": status_filter.value if status_filter else None,
                "matching_status": matching_status, "page_size": page_size, "offset": (page - 1) * page_size}).mappings().all()
        applications = [dict(row) for row in rows]
        for item in applications:
            if isinstance(item.get("latest_assessment"), dict):
                item["latest_assessment"]["provider_model_snapshot"] = sanitize_provider_snapshot(
                    item["latest_assessment"].get("provider_model_snapshot"))
            _normalize_application(item)
            item.update({"can_view_cv": True, "can_view_assessment_evidence": bool(item["latest_assessment"]), "can_update_status": True})
        return applications
    finally:
        db.close()


@router.get("/{application_id}", response_model=ApplicationWithAssessment)
async def get_application(application_id: UUID, current_user: dict = Depends(get_current_user)):
    """Get a visible application's latest completed assessment and authorized evidence."""
    app_id = str(application_id)
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT a.*, row_to_json(i) AS identity FROM app_private.applications a
            LEFT JOIN app_private.application_identities i ON i.application_id = a.application_id
            WHERE a.application_id = :id
        """), {"id": app_id}).mappings().first()
        if not row:
            raise NotFoundError("Application")
        access = application_access(current_user["user_id"], str(row["position_id"]), app_id)
        app = dict(row)
        app.update(access)
        documents = db.execute(text("SELECT * FROM app_private.application_documents WHERE application_id = :id ORDER BY created_at DESC"), {"id": app_id}).mappings().all()
        app["documents"] = [dict(d) for d in documents]
        _normalize_application(app)
        app["has_duplicate_warning"] = bool(access["can_update_status"] and db.execute(text("""
            SELECT EXISTS(SELECT 1 FROM app_private.duplicate_signals WHERE position_id = :position_id
                AND review_status = 'PENDING' AND (application_id_1 = :id OR application_id_2 = :id))
        """), {"id": app_id, "position_id": str(row["position_id"])}).scalar_one())
        assessment = db.execute(text("""
            SELECT ar.* FROM app_private.assessment_runs ar
            JOIN app_private.applications a ON a.application_id = ar.application_id
            WHERE ar.application_id = :id AND ar.status = 'COMPLETED'
                  AND ar.profile_version_id = (SELECT profile_version_id FROM app_private.profile_versions
                      WHERE application_id = a.application_id AND status = 'COMPLETED' ORDER BY version_number DESC LIMIT 1)
                  AND ar.criteria_version_id = (SELECT c.criteria_version_id FROM app_private.criteria_versions c
                      WHERE c.position_id = a.position_id AND c.status = 'APPROVED'
                        AND c.jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions
                            WHERE position_id = a.position_id ORDER BY version_number DESC LIMIT 1)
                      ORDER BY c.version_number DESC LIMIT 1)
                  AND (:hr_access OR EXISTS (
                      SELECT 1 FROM app_private.shortlist_share_items si
                      JOIN app_private.shortlist_shares s ON s.share_id = si.share_id
                      JOIN app_private.position_assignments hm ON hm.position_id = s.position_id
                          AND hm.user_id = s.shared_with AND hm.position_role = 'HIRING_MANAGER' AND hm.revoked_at IS NULL
                      WHERE s.shared_with = :user_id AND s.status = 'ACTIVE'
                        AND si.application_id = a.application_id AND si.assessment_id = ar.assessment_id
                  ))
            ORDER BY ar.created_at DESC, ar.assessment_id DESC LIMIT 1
        """), {"id": app_id, "hr_access": access["can_update_status"], "user_id": current_user["user_id"]}).mappings().first()
        latest = dict(assessment) if assessment else None
        if latest:
            latest["provider_model_snapshot"] = sanitize_provider_snapshot(
                latest.get("provider_model_snapshot"),
                operations_access=is_system_admin(current_user["user_id"]),
            )
        app["can_view_assessment_evidence"] = False
        if latest:
            latest["criterion_results"] = []
            # A separate summary-only share must not gain evidence just because
            # another active share grants access to an older CV snapshot.
            can_view_evidence = access["can_update_status"] or bool(access["can_view_cv"] and db.execute(text("""
                SELECT 1 FROM app_private.shortlist_share_items si
                JOIN app_private.shortlist_shares s ON s.share_id = si.share_id
                JOIN app_private.position_assignments hm ON hm.position_id = s.position_id
                    AND hm.user_id = s.shared_with AND hm.position_role = 'HIRING_MANAGER' AND hm.revoked_at IS NULL
                WHERE s.shared_with = :user_id AND s.status = 'ACTIVE' AND s.allow_cv_view
                  AND si.application_id = :application_id AND si.assessment_id = :assessment_id
            """), {"user_id": current_user["user_id"], "application_id": app_id,
                    "assessment_id": latest["assessment_id"]}).first())
            app["can_view_assessment_evidence"] = can_view_evidence
            if can_view_evidence:
                results = db.execute(text("""
                    SELECT car.*, ci.name AS criterion_name, ci.category,
                           car.requires_hr_verification AS requires_verification
                    FROM app_private.criterion_assessment_results car
                    JOIN app_private.criteria_items ci ON ci.criterion_id = car.criterion_id
                    WHERE car.assessment_id = :assessment_id ORDER BY ci.display_order, ci.criterion_id
                """), {"assessment_id": str(latest["assessment_id"])}).mappings().all()
                for item in results:
                    criterion_result = dict(item)
                    evidence = db.execute(text("""
                        SELECT evidence_id, verbatim_quote, page_number, verification_status
                        FROM app_private.evidence_items WHERE criterion_result_id = :result_id ORDER BY created_at
                    """), {"result_id": str(item["result_id"])}).mappings().all()
                    criterion_result["evidence"] = [dict(e) for e in evidence]
                    latest["criterion_results"].append(criterion_result)
        app["latest_assessment"] = latest
        if not access["can_view_cv"]:
            # Summary-only sharing includes the display name, not contact
            # details, original documents or processing diagnostics.
            if app.get("identity"):
                app["identity"] = {"display_name": app["identity"].get("display_name")}
            app["documents"] = []
            app["file_processing_status"] = "UNKNOWN"
            app["file_error"] = None
        return app
    finally:
        db.close()


@router.get("/{application_id}/status-events")
async def list_application_status_events(application_id: UUID, current_user: dict = Depends(get_current_user)):
    """Recruiter-only decision history, including reasons and notes."""
    db = SessionLocal()
    try:
        position_id = db.execute(text("SELECT position_id FROM app_private.applications WHERE application_id = :id"),
                                 {"id": str(application_id)}).scalar_one_or_none()
        if not position_id:
            raise NotFoundError("Application")
        if not can_update_application_status(current_user["user_id"], str(position_id)):
            raise HTTPException(status_code=403, detail="Chỉ HR phụ trách được xem lịch sử quyết định")
        rows = db.execute(text("""
            SELECT e.event_id, e.previous_status, e.new_status, e.reason_code AS reason, e.note,
                   e.changed_at, p.display_name AS changed_by_name
            FROM app_private.application_status_events e
            LEFT JOIN app_private.user_profiles p ON p.user_id = e.changed_by
            WHERE e.application_id = :id ORDER BY e.changed_at DESC, e.event_id DESC
        """), {"id": str(application_id)}).mappings().all()
        return [dict(row) for row in rows]
    finally:
        db.close()


@router.patch("/{application_id}/status", response_model=Application)
async def update_application_status(
    application_id: UUID,
    update: ApplicationStatusUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Record an HR decision and its reason together with the audit event."""
    user_id = current_user["user_id"]
    app_id = str(application_id)
    db = SessionLocal()
    try:
        app = db.execute(text("SELECT * FROM app_private.applications WHERE application_id = :app_id FOR UPDATE"),
                         {"app_id": app_id}).mappings().first()
        if not app:
            raise NotFoundError("Application")
        if not can_update_application_status(user_id, str(app["position_id"])):
            raise HTTPException(status_code=403, detail="Chỉ HR phụ trách mới được cập nhật trạng thái hồ sơ")
        current_status = ApplicationStatus(app["application_status"])
        new_status = update.new_status
        if new_status not in VALID_TRANSITIONS.get(current_status, []):
            raise InvalidStatusTransitionError(current_status.value, new_status.value)
        reason = (update.reason or "").strip() or None
        note = (update.note or "").strip() or None
        if new_status in (ApplicationStatus.REJECTED_SCREENING, ApplicationStatus.REJECTED_INTERVIEW) and not reason:
            raise HTTPException(status_code=400, detail="Vui lòng nhập lý do loại hồ sơ")
        changed = db.execute(text("""
            UPDATE app_private.applications SET application_status = :new_status, updated_at = NOW()
            WHERE application_id = :app_id RETURNING *
        """), {"new_status": new_status.value, "app_id": app_id}).mappings().one()
        db.execute(text("""
            INSERT INTO app_private.application_status_events
                (application_id, previous_status, new_status, changed_by, reason_code, note)
            VALUES (:app_id, :previous, :new_status, :user_id, :reason, :note)
        """), {"app_id": app_id, "previous": current_status.value, "new_status": new_status.value,
                "user_id": user_id, "reason": reason, "note": note})
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id, action_type, object_type, object_id, position_id, outcome)
            VALUES (:user_id, 'UPDATE_APPLICATION_STATUS', 'APPLICATION', :app_id, :position_id, :outcome)
        """), {"user_id": user_id, "app_id": app_id, "position_id": str(app["position_id"]), "outcome": new_status.value})
        db.commit()
        return dict(changed)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _authorized_cv_document(application_id: UUID, user_id: str) -> dict:
    """Initial authorization and metadata lookup; not sufficient to release bytes."""
    app_id = str(application_id)
    db = SessionLocal()
    try:
        app = db.execute(text("SELECT position_id FROM app_private.applications WHERE application_id = :id"), {"id": app_id}).mappings().first()
        if not app:
            raise NotFoundError("Application")
        if not application_access(user_id, str(app["position_id"]), app_id, db=db)["can_view_cv"]:
            raise HTTPException(status_code=403, detail="Shortlist này không cho phép xem CV gốc")
        doc = db.execute(text("""
            SELECT * FROM app_private.application_documents WHERE application_id = :id AND document_type = 'CV'
            ORDER BY created_at DESC, document_id DESC LIMIT 1
        """), {"id": app_id}).mappings().first()
        if not doc:
            raise NotFoundError("CV document")
        return {**dict(doc), "position_id": str(app["position_id"])}
    finally:
        db.close()


@router.get("/{application_id}/cv-download-url")
def get_cv_signed_url(application_id: UUID, response: Response, current_user: dict = Depends(get_current_user)):
    """Legacy discovery endpoint. Never issues a storage bearer URL.

    `source=local` is retained for older frontends and means the authenticated
    backend path, not where the object is stored. It is not itself access to CV bytes.
    """
    doc = _authorized_cv_document(application_id, current_user["user_id"])
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    return {"file_url": f"{settings.API_V1_PREFIX}/applications/{application_id}/cv-file",
            "filename": doc["original_filename"], "source": "local"}


@router.get("/{application_id}/cv-file")
def serve_cv_file(application_id: UUID, current_user: dict = Depends(get_current_user)):
    """Fetch privately, reauthorize under the position lock, then audit before release.

    A successful audit records authorization to serve bytes, not proof that a
    browser actually received or viewed them. Bytes already released cannot be
    retracted. Storage I/O happens before acquiring the position lock.
    """
    user_id, app_id = str(current_user["user_id"]), str(application_id)
    doc = _authorized_cv_document(application_id, user_id)
    if doc["bucket"] != settings.SUPABASE_STORAGE_BUCKET_CV:
        raise HTTPException(status_code=400, detail="Invalid file location")
    if doc["size_bytes"] > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="CV file exceeds size limit")
    if settings.STORAGE_BACKEND == "local":
        base = os.path.realpath(os.path.join(settings.LOCAL_STORAGE_PATH, settings.SUPABASE_STORAGE_BUCKET_CV))
        path = os.path.realpath(os.path.join(base, doc["storage_path"]))
        if not path.startswith(base + os.sep):
            raise HTTPException(status_code=400, detail="Invalid file path")
        try:
            with open(path, "rb") as stream:
                content = stream.read(settings.MAX_FILE_SIZE_BYTES + 1)
        except FileNotFoundError:
            raise NotFoundError("CV file") from None
        except OSError as exc:
            logger.error("Could not read CV file", error_type=type(exc).__name__)
            raise HTTPException(status_code=502, detail="Could not retrieve CV file") from None
    elif settings.STORAGE_BACKEND == "supabase":
        storage = get_supabase_client()
        if not storage:
            raise HTTPException(status_code=503, detail="Supabase storage is not configured")
        try:
            content = storage.storage.from_(doc["bucket"]).download(doc["storage_path"])
        except Exception as exc:
            logger.error("Could not retrieve CV file", error_type=type(exc).__name__)
            raise HTTPException(status_code=502, detail="Could not retrieve CV file") from None
    else:
        raise HTTPException(status_code=500, detail="Storage backend is not configured")
    if not isinstance(content, bytes) or len(content) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=502, detail="Invalid CV file response")

    db = SessionLocal()
    try:
        from app.services.retention import position_has_inflight_purge
        if not db.execute(text("SELECT 1 FROM app_private.positions WHERE position_id=:id FOR UPDATE"), {"id": doc["position_id"]}).first():
            raise NotFoundError("Position")
        account = db.execute(text("""
            SELECT account_status, must_change_password, tokens_valid_after FROM app_private.user_profiles
            WHERE user_id=:id FOR SHARE
        """), {"id": user_id}).mappings().first()
        if not account or account["account_status"] != "ACTIVE" or account["must_change_password"]:
            raise HTTPException(status_code=403, detail="Tài khoản chưa được kích hoạt hoặc đã bị khóa")
        if current_user.get("token_payload") is not None:
            ensure_token_is_current(current_user["token_payload"], account["tokens_valid_after"])
        if position_has_inflight_purge(db, doc["position_id"]):
            raise HTTPException(status_code=409, detail="Vị trí có case xóa đang xử lý hoặc cần phục hồi")
        latest = db.execute(text("""
            SELECT document_id FROM app_private.application_documents
            WHERE application_id=:app_id AND document_type='CV'
            ORDER BY created_at DESC, document_id DESC LIMIT 1
        """), {"app_id": app_id}).scalar_one_or_none()
        if str(latest) != str(doc["document_id"]):
            raise HTTPException(status_code=409, detail="CV đã thay đổi. Vui lòng tải lại.")
        if not application_access(user_id, doc["position_id"], app_id, db=db)["can_view_cv"]:
            raise HTTPException(status_code=403, detail="Shortlist này không cho phép xem CV gốc")
        db.execute(text("""
            INSERT INTO app_private.audit_events (actor_user_id,action_type,object_type,object_id,position_id,outcome)
            VALUES (:actor,'CV_FILE_ACCESS_GRANTED','APPLICATION',:app_id,:position,'SUCCESS')
        """), {"actor": user_id, "app_id": app_id, "position": doc["position_id"]})
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    filename = os.path.basename(doc["original_filename"] or "cv")
    return Response(content=content, media_type=doc["mime_type"], headers={
        "Content-Disposition": "inline; filename*=UTF-8''" + quote(filename, safe=""),
        "Cache-Control": "private, no-store, max-age=0", "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
    })
