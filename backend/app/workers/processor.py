"""
CV Processing Worker
Runs as a separate process/thread, polls the operations queue for pending tasks.
For Phase 1 MVP, implements simple polling-based task queue without requiring Celery/Redis.
"""
import time
import threading
import asyncio
import os
import json
import re
import hashlib
from collections import Counter
from contextlib import ExitStack
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.db.database import SessionLocal, engine
from app.core.config import settings
from app.core.logging import get_logger
from app.services import langfuse_observability as observability
from app.services.document_processor import document_processor
from app.services.llm_client import (
    llm_client, LLMError, normalize_profile_page_number, sanitize_profile_page_numbers,
)
from app.services.matching import matching_engine
from app.services.deterministic_matching import deterministic_matcher
from app.services.embedding import (
    chunk_text_sha256, parse_vector_literal,
    requirement_query_text, semantic_config_fingerprint, semantic_reuse_scope, vector_literal,
)
from app.services.semantic_diagnostics import record_semantic_run
from app.services.ltr import LTRModel, artifact_sha256, extract_ranking_features
from app.services.ltr_managed import current_selection, resolve_managed
from app.services.ai_runtime_controls import bge_pin_is_current, service_enabled
from app.services.semantic_retrieval import merge_candidate_chunks, retrieve_semantic_candidates
from app.services.redaction import redact_text
from app.services.ai_config import (
    get_active_runtime, runtime_context, runtime_snapshot,
)
from app.services.bge_routes import load_active_bge_chain, provider_for_pinned_route, route_index_version
from datetime import date

logger = get_logger(__name__)


def _database_error_metadata(exc: BaseException) -> dict:
    """Safe PostgreSQL diagnostics for logs: identifiers only, never values."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    metadata = {}
    for key, attr in (
        ("db_pgcode", "pgcode"),
        ("db_table", "table_name"),
        ("db_column", "column_name"),
        ("db_constraint", "constraint_name"),
    ):
        value = getattr(diag, attr, None) if diag is not None else None
        if value:
            metadata[key] = str(value)
    return metadata


# Processing queue polling interval (seconds)
POLL_INTERVAL_SECONDS = 5
HEARTBEAT_SECONDS = 20


class LostOwnership(RuntimeError):
    """The connection or fencing token for an operation was lost."""


class FencedSession(Session):
    """Keep all worker writes on the connection holding its advisory lock.

    A SQLAlchemy Connection can transparently reconnect after an invalidation.
    Before every commit, check both its backend PID and its attempt token so a
    reconnected or superseded worker cannot commit stale results.
    """
    def assert_ownership(self):
        owner = self.info.get("owner")
        if not owner:
            return
        try:
            row = self.execute(text("""
                SELECT pg_backend_pid() AS pid, worker_token::text AS token
                FROM app_private.operations WHERE operation_id = :operation_id
            """), {"operation_id": owner["operation_id"]}).mappings().first()
        except Exception as exc:
            raise LostOwnership("Cannot verify worker ownership") from exc
        if not row or row["pid"] != owner["pid"] or row["token"] != owner["token"]:
            raise LostOwnership("Worker no longer owns this operation")

    def commit(self):
        self.assert_ownership()
        return super().commit()


class ProcessingWorker:
    def __init__(self):
        self.running = False
        self.thread = None
        # Continue past a page of live advisory locks on the next poll. Without
        # this cursor, 100 long-running older jobs could starve newer jobs.
        self._queue_cursor = None
        self._ensure_storage_dirs()

    def _ensure_storage_dirs(self):
        """Create local storage directories if using local storage backend"""
        if settings.STORAGE_BACKEND == "local":
            os.makedirs(os.path.join(settings.LOCAL_STORAGE_PATH, "cv-originals"), exist_ok=True)
            os.makedirs(os.path.join(settings.LOCAL_STORAGE_PATH, "cv-extracted-text"), exist_ok=True)

    def start(self):
        """Start worker in background thread"""
        if self.running:
            logger.warning("Worker already running")
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Processing worker started")

    def stop(self):
        """Stop worker gracefully"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Processing worker stopped")

    def _run_loop(self):
        """Main worker loop - polls for pending operations"""
        logger.info("Worker entering run loop")
        while self.running:
            try:
                self._process_pending_operations()
            except Exception as e:
                logger.error("Error in worker loop", error_type=type(e).__name__)
            time.sleep(POLL_INTERVAL_SECONDS)

    def _heartbeat(self, operation_id: str, token: str, stop: threading.Event):
        """Health signal only, never a lease that can steal a live worker's job."""
        while not stop.wait(HEARTBEAT_SECONDS):
            db = SessionLocal()
            try:
                db.execute(text("""
                    UPDATE app_private.operations SET heartbeat_at = NOW()
                    WHERE operation_id = :id AND worker_token = :token AND status = 'PROCESSING'
                """), {"id": operation_id, "token": token})
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning("Worker heartbeat failed", operation_id=operation_id, error_type=type(exc).__name__)
            finally:
                db.close()

    def _process_pending_operations(self):
        """Claim one pending or abandoned operation without stealing live work.

        A session-level PostgreSQL advisory lock is held by the *same dedicated
        database connection* used for every handler transaction. PostgreSQL
        releases it when the worker process/connection dies. Heartbeat age alone
        never authorises a takeover. Existing pre-fencing workers must be drained
        before deploying this code.
        """
        connection = engine.connect()
        db = FencedSession(bind=connection, autoflush=False)
        operation_id = None
        lock_owned = False
        heartbeat_stop = threading.Event()
        heartbeat = None
        context_token = None
        observability_stack: ExitStack | None = None
        operation_observation = None
        try:
            cursor_filter = "" if self._queue_cursor is None else (
                "AND (created_at, operation_id) > (:cursor_time, CAST(:cursor_id AS uuid))"
            )
            cursor_params = {} if self._queue_cursor is None else {
                "cursor_time": self._queue_cursor[0], "cursor_id": str(self._queue_cursor[1])
            }
            rows = db.execute(text(f"""
                SELECT operation_id, capability, status, ai_config_id, ai_config_snapshot, created_at
                FROM app_private.operations
                WHERE status IN ('PENDING', 'PROCESSING')
                  AND capability IN ('CV_PROCESSING', 'ASSESSMENT', 'RANKING')
                  {cursor_filter}
                ORDER BY created_at, operation_id
                LIMIT 100 FOR UPDATE SKIP LOCKED
            """), cursor_params).mappings().all()
            chosen = None
            for row in rows:
                got_lock = db.execute(text("""
                    SELECT pg_try_advisory_lock(hashtextextended(:id, 418630021))
                """), {"id": str(row["operation_id"])}).scalar_one()
                if got_lock:
                    chosen = row
                    lock_owned = True
                    operation_id = str(row["operation_id"])
                    break
            if not chosen:
                self._queue_cursor = (rows[-1]["created_at"], rows[-1]["operation_id"]) if rows else None
                db.rollback()
                return
            self._queue_cursor = None

            capability, was_processing = chosen["capability"], chosen["status"] == "PROCESSING"
            token = str(uuid4())
            backend_pid = db.execute(text("SELECT pg_backend_pid()")).scalar_one()
            runtime = chosen["ai_config_snapshot"] or get_active_runtime(db)
            if not chosen["ai_config_snapshot"] and capability in {"CV_PROCESSING", "ASSESSMENT"}:
                try:
                    with db.begin_nested():
                        runtime["bge_chain"] = (load_active_bge_chain(db) if service_enabled(db, "BGE")
                                                else {"routes": [], "status": "OFF"})
                except Exception as exc:
                    logger.warning("Managed BGE unavailable; using lexical retrieval", error_type=type(exc).__name__)
                    runtime["bge_chain"] = {"routes": [], "status": "UNAVAILABLE"}
            if not chosen["ai_config_snapshot"] and capability in {"CV_PROCESSING", "ASSESSMENT", "RANKING"}:
                try:
                    with db.begin_nested():
                        runtime["ltr_selection"] = ((current_selection(db) or {"mode": "OFF"})
                                                    if service_enabled(db, "LTR") else {"mode": "OFF"})
                except Exception as exc:
                    logger.warning("Managed LTR unavailable; ranking unchanged", error_type=type(exc).__name__)
                    runtime["ltr_selection"] = {"mode": "OFF"}
            # Snapshots contain no secrets. Each route rehydrates its own key
            # only when attempted, so a broken primary key can fail over.
            snapshot = runtime_snapshot(runtime)
            db.execute(text("""
                UPDATE app_private.operations
                SET status = 'PROCESSING', started_at = COALESCE(started_at, NOW()),
                    attempt_started_at = NOW(), heartbeat_at = NOW(), worker_token = :token,
                    attempt_count = attempt_count + 1,
                    recovery_count = recovery_count + CASE WHEN :recovered THEN 1 ELSE 0 END,
                    ai_config_id = :config_id, ai_config_snapshot = CAST(:snapshot AS jsonb),
                    error_code = NULL, error_message = NULL
                WHERE operation_id = :operation_id
            """), {"operation_id": operation_id, "token": token, "recovered": was_processing,
                    "config_id": runtime.get("config_id"), "snapshot": json.dumps(snapshot)})
            if was_processing:
                db.execute(text("""
                    INSERT INTO app_private.operation_recovery_events(operation_id) VALUES (:operation_id)
                """), {"operation_id": operation_id})
            db.commit()
            context_token = runtime_context.set(runtime)
            db.info["owner"] = {"operation_id": operation_id, "pid": backend_pid, "token": token}
            logger.info("Worker claimed operation", operation_id=operation_id, capability=capability, recovered=was_processing)
            heartbeat = threading.Thread(target=self._heartbeat, args=(operation_id, token, heartbeat_stop), daemon=True)
            heartbeat.start()
            observability_stack = ExitStack()
            operation_observation = observability_stack.enter_context(observability.span(
                "hra.worker.operation",
                metadata={
                    "operation_id": operation_id,
                    "capability": capability,
                    "recovered": was_processing,
                    "ai_config_id": snapshot.get("config_id"),
                    "ai_provider": snapshot.get("provider"),
                    "ai_model": snapshot.get("model_name"),
                    "runtime_source": snapshot.get("source"),
                },
            ))

            try:
                if was_processing:
                    # Only this fenced owner may reset unfinished child work.
                    db.execute(text("""
                        UPDATE app_private.assessment_runs SET status = 'FAILED', completed_at = NOW()
                        WHERE operation_id = :operation_id AND status = 'PROCESSING'
                    """), {"operation_id": operation_id})
                    if capability == "CV_PROCESSING":
                        db.execute(text("""
                            UPDATE app_private.application_documents d
                            SET file_processing_status = 'RECEIVED', processing_error = NULL
                            FROM app_private.cv_batch_items bi
                            JOIN app_private.cv_batches b ON b.batch_id = bi.batch_id
                            WHERE b.operation_id = :operation_id AND d.application_id = bi.application_id
                              AND d.file_processing_status = 'PROCESSING'
                        """), {"operation_id": operation_id})
                    db.commit()

                if capability == "CV_PROCESSING":
                    self._process_cv_batch(UUID(operation_id), db)
                elif capability == "ASSESSMENT":
                    self._run_assessments(UUID(operation_id), db)
                else:
                    self._generate_ranking(UUID(operation_id), db)

                db.execute(text("""
                    UPDATE app_private.operations SET status = 'COMPLETED', completed_at = NOW(), heartbeat_at = NOW()
                    WHERE operation_id = :operation_id AND worker_token = :token
                """), {"operation_id": operation_id, "token": token})
                db.commit()
                if operation_observation is not None:
                    operation_observation.update(output={"status": "COMPLETED"})
                logger.info("Operation completed successfully", operation_id=operation_id)
            except LostOwnership:
                db.rollback()
                if operation_observation is not None:
                    operation_observation.update(
                        output={"status": "LOST_OWNERSHIP"}, level="WARNING", status_message="LostOwnership")
                logger.warning("Worker lost operation ownership; no further writes", operation_id=operation_id)
            except Exception as exc:
                if operation_observation is not None:
                    operation_observation.update(
                        output={"status": "FAILED"}, level="ERROR", status_message=type(exc).__name__)
                logger.error("Operation failed", operation_id=operation_id, error_type=type(exc).__name__)
                db.rollback()
                # A connection may have been replaced after the original error.
                # Refuse even the failure write when this worker is no longer owner.
                try:
                    db.assert_ownership()
                    if capability == "CV_PROCESSING":
                        db.execute(text("""
                            UPDATE app_private.application_documents d
                            SET file_processing_status = 'NEEDS_HR_REVIEW', processing_error = 'Lô xử lý thất bại'
                            FROM app_private.cv_batch_items bi JOIN app_private.cv_batches b ON b.batch_id = bi.batch_id
                            WHERE b.operation_id = :operation_id AND bi.application_id = d.application_id
                              AND d.file_processing_status IN ('RECEIVED', 'PROCESSING')
                        """), {"operation_id": operation_id})
                        db.execute(text("""
                            UPDATE app_private.cv_batches SET status = 'FAILED', completed_at = NOW()
                            WHERE operation_id = :operation_id AND status = 'PROCESSING'
                        """), {"operation_id": operation_id})
                    db.execute(text("""
                        UPDATE app_private.operations
                        SET status = 'FAILED', error_code = 'PROCESSING_ERROR',
                            error_message = 'Không thể xử lý tác vụ; vui lòng kiểm tra và thử lại.', completed_at = NOW()
                        WHERE operation_id = :operation_id AND worker_token = :token
                    """), {"operation_id": operation_id, "token": token})
                    db.commit()
                except LostOwnership:
                    db.rollback()
                    logger.warning("Worker could not record failure after losing ownership", operation_id=operation_id)
        finally:
            heartbeat_stop.set()
            if observability_stack is not None:
                observability_stack.close()
            if context_token is not None:
                runtime_context.reset(context_token)
            if heartbeat:
                heartbeat.join(timeout=2)
            db.info.pop("owner", None)
            db.close()  # rollback any unfinished transaction before unlocking
            if lock_owned:
                try:
                    connection.execute(text("SELECT pg_advisory_unlock(hashtextextended(:id, 418630021))"),
                                       {"id": operation_id})
                    connection.commit()
                except Exception:
                    # Never return a session with a possibly-held advisory lock
                    # to the pool. A broken connection is discarded instead.
                    connection.invalidate()
            connection.close()

    def _read_file_content(self, document) -> bytes:
        """Read file content from configured storage backend"""
        bucket = document["bucket"]
        storage_path = document["storage_path"]

        if settings.STORAGE_BACKEND == "local":
            full_path = os.path.join(settings.LOCAL_STORAGE_PATH, bucket, storage_path)
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"File not found at path: {full_path}")
            with open(full_path, "rb") as f:
                return f.read()
        elif settings.STORAGE_BACKEND == "supabase":
            from app.db.supabase import get_supabase_client
            supabase = get_supabase_client()
            if not supabase:
                raise RuntimeError("Supabase client is not configured")
            response = supabase.storage.from_(bucket).download(storage_path)
            return response
        else:
            raise ValueError(f"Unknown storage backend: {settings.STORAGE_BACKEND}")

    def _save_extracted_text(self, application_id: str, document_id: str, full_text: str, pages: list, attempt_token: str) -> str:
        """Persist extracted text in the configured backend so assessment can read it."""
        bucket = settings.SUPABASE_STORAGE_BUCKET_EXTRACTED
        application_id, document_id = str(application_id), str(document_id)
        relative_path = f"{application_id}/{document_id}/{attempt_token}/extracted.txt"
        pages_path = f"{application_id}/{document_id}/{attempt_token}/pages.json"
        if settings.STORAGE_BACKEND == "local":
            full_dir = os.path.join(settings.LOCAL_STORAGE_PATH, bucket, application_id, document_id, attempt_token)
            os.makedirs(full_dir, exist_ok=True)
            with open(os.path.join(settings.LOCAL_STORAGE_PATH, bucket, relative_path), "w", encoding="utf-8") as f:
                f.write(full_text)
            with open(os.path.join(settings.LOCAL_STORAGE_PATH, bucket, pages_path), "w", encoding="utf-8") as f:
                json.dump(pages, f, ensure_ascii=False)
        elif settings.STORAGE_BACKEND == "supabase":
            from app.db.supabase import get_supabase_client
            supabase = get_supabase_client()
            if not supabase:
                raise RuntimeError("Supabase storage is not configured")
            supabase.storage.from_(bucket).upload(relative_path, full_text.encode("utf-8"),
                                                   {"content-type": "text/plain; charset=utf-8", "upsert": "true"})
            supabase.storage.from_(bucket).upload(pages_path, json.dumps(pages, ensure_ascii=False).encode("utf-8"),
                                                   {"content-type": "application/json", "upsert": "true"})
        else:
            raise ValueError(f"Unknown storage backend: {settings.STORAGE_BACKEND}")
        return relative_path

    def _load_extracted_text(self, path: str) -> str:
        if not path:
            raise FileNotFoundError("No extracted text path is recorded")
        if settings.STORAGE_BACKEND == "local":
            with open(os.path.join(settings.LOCAL_STORAGE_PATH, settings.SUPABASE_STORAGE_BUCKET_EXTRACTED, path), encoding="utf-8") as f:
                return f.read()
        if settings.STORAGE_BACKEND == "supabase":
            from app.db.supabase import get_supabase_client
            supabase = get_supabase_client()
            if not supabase:
                raise RuntimeError("Supabase storage is not configured")
            return supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET_EXTRACTED).download(path).decode("utf-8")
        raise ValueError(f"Unknown storage backend: {settings.STORAGE_BACKEND}")

    def _process_cv_batch(self, operation_id: UUID, db):
        """Process all documents in a CV batch: extract text, extract profile, detect duplicates"""
        from sqlalchemy import text

        # Get batch ID for this operation
        batch_result = db.execute(text("""
            SELECT batch_id, position_id FROM app_private.cv_batches WHERE operation_id = :operation_id
        """), {"operation_id": str(operation_id)})
        batch_row = batch_result.fetchone()
        if not batch_row:
            raise Exception(f"No batch found for operation {operation_id}")

        batch_id, position_id = batch_row

        # Get all documents for applications in this batch (status RECEIVED)
        docs_result = db.execute(text("""
            SELECT d.document_id, d.application_id, d.bucket, d.storage_path,
                   d.original_filename, d.mime_type, d.size_bytes,
                   (SELECT run_id FROM app_private.document_processing_runs
                    WHERE document_id = d.document_id AND operation_id = :operation_id
                    ORDER BY created_at DESC LIMIT 1) AS processing_run_id,
                   a.created_by
            FROM app_private.application_documents d
            JOIN app_private.applications a ON d.application_id = a.application_id
            JOIN app_private.cv_batch_items bi ON bi.application_id = a.application_id
            WHERE bi.batch_id = :batch_id
              AND d.file_processing_status = 'RECEIVED'
        """), {"batch_id": str(batch_id), "operation_id": str(operation_id)})

        documents = [dict(zip(["document_id", "application_id", "bucket", "storage_path",
                               "original_filename", "mime_type", "size_bytes", "processing_run_id", "created_by"], row))
                     for row in docs_result.fetchall()]

        logger.info("Processing documents in batch", batch_id=batch_id, count=len(documents))

        processed_count = 0
        needs_review_count = 0
        extracted_texts = {}

        for doc in documents:
            document_id = doc["document_id"]
            application_id = doc["application_id"]
            loop = asyncio.new_event_loop()

            try:
                # Update document status to PROCESSING
                db.execute(text("""
                    UPDATE app_private.application_documents
                    SET file_processing_status = 'PROCESSING'
                    WHERE document_id = :document_id
                """), {"document_id": document_id})
                db.commit()

                # Read file
                content = self._read_file_content(doc)

                # Process document: extract text
                with observability.span(
                    "hra.cv.document_extraction",
                    metadata={
                        "operation_id": str(operation_id),
                        "batch_id": str(batch_id),
                        "position_id": str(position_id),
                        "document_id": document_id,
                        "application_id": application_id,
                        "mime_type": doc["mime_type"],
                        "size_bytes": doc["size_bytes"],
                    },
                ) as document_observation:
                    raw_text, raw_pages, doc_type = loop.run_until_complete(
                        document_processor.process_document(content, doc["original_filename"], doc["mime_type"])
                    )
                    document_observation.update(output={
                        "document_type": doc_type.value,
                        "raw_characters": len(raw_text or ""),
                        "page_count": len(raw_pages or []),
                    })
                # Identity is extracted locally, never sent to the model.  The
                # stored/model text and the evidence verifier use exactly the
                # same minimised text, including for later re-assessments.
                email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", raw_text)
                phone_match = re.search(r"(?<!\w)(?:\+?\d[\d .()\-]{7,}\d)(?!\w)", raw_text)
                full_text = redact_text(raw_text, detect_first_line_name=True)
                # Never persist OCR diagnostic fields, which can contain raw text.
                pages = [{"page_number": page.get("page_number"),
                          "content": redact_text(page.get("content") or "", detect_first_line_name=True)}
                         for page in raw_pages]

                # Save minimised extracted text
                db.assert_ownership()
                extracted_path = self._save_extracted_text(application_id, document_id, full_text, pages,
                                                           db.info["owner"]["token"])

                # Update document processing run
                run_filter = "run_id = :run_id" if doc.get("processing_run_id") else "document_id = :document_id"
                db.execute(text(f"""
                    UPDATE app_private.document_processing_runs
                    SET status = 'COMPLETED',
                        extraction_type = :extraction_type,
                        processor_version = 'v1.0',
                        error_code = NULL,
                        extracted_text_storage_path = :extracted_path
                    WHERE {run_filter}
                """), {
                    "document_id": document_id,
                    "run_id": doc.get("processing_run_id"),
                    "extraction_type": doc_type.value,
                    "extracted_path": extracted_path
                })

                # Update document status to COMPLETED
                db.execute(text("""
                    UPDATE app_private.application_documents
                    SET file_processing_status = 'COMPLETED'
                    WHERE document_id = :document_id
                """), {"document_id": document_id})
                # Extraction is durable on its own.  A later profile failure
                # must roll back only profile rows, not this completed run.
                db.commit()

                extracted_texts[application_id] = (full_text, pages, document_id)

                # Run profile extraction via LLM
                try:
                    candidate_profile = loop.run_until_complete(
                        llm_client.extract_candidate_profile(
                            cv_text=full_text,
                            candidate_identifier=str(application_id)
                        )
                    )

                    provider_metadata = candidate_profile.pop("_provider_metadata", {})
                    profile_prompt_version = candidate_profile.pop(
                        "_prompt_version", settings.PROFILE_PROMPT_VERSION)
                    candidate_profile = sanitize_profile_page_numbers(candidate_profile)
                    extraction_config = {
                        "prompt_version": profile_prompt_version,
                        "provider_metadata": provider_metadata,
                        "cv_text_sha256": hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
                        "extractor": "llm-profile",
                    }
                    # Create the next profile version.  Reprocessing a CV
                    # whose earlier attempt already produced a profile must
                    # not collide with the UNIQUE(application_id, version).
                    next_version = db.execute(text("""
                        SELECT COALESCE(MAX(version_number), 0) + 1
                        FROM app_private.profile_versions
                        WHERE application_id = :application_id
                    """), {"application_id": application_id}).scalar_one()
                    profile_ver_result = db.execute(text("""
                        INSERT INTO app_private.profile_versions
                        (application_id, source_document_id, version_number, extraction_config, status, created_at)
                        VALUES
                        (:application_id, :document_id, :version_number, CAST(:extraction_config AS jsonb), 'COMPLETED', NOW())
                        RETURNING profile_version_id
                    """), {"application_id": application_id, "document_id": document_id,
                            "version_number": int(next_version),
                            "extraction_config": json.dumps(extraction_config)})
                    profile_version_id = profile_ver_result.fetchone()[0]

                    # Extract basic contact signals locally; never infer a name from the
                    # opaque candidate_identifier returned by the model.
                    display_name = os.path.splitext(doc["original_filename"])[0]
                    email = email_match.group(0).lower() if email_match else None
                    phone = re.sub(r"\D", "", phone_match.group(0)) if phone_match else None

                    # Insert profile facts.  Model output is untrusted: only
                    # dict-shaped items are persisted, and the INTEGER page
                    # column always receives a coerced value or NULL.
                    facts = []
                    for edu in candidate_profile.get("education", []):
                        if not isinstance(edu, dict):
                            continue
                        facts.append({
                            "profile_version_id": profile_version_id,
                            "fact_type": "EDUCATION",
                            "fact_value": json.dumps(edu),
                            "source_page_number": normalize_profile_page_number(edu.get("page_number")),
                            "confidence": 0.9
                        })
                    for work in candidate_profile.get("work_history", []):
                        if not isinstance(work, dict):
                            continue
                        facts.append({
                            "profile_version_id": profile_version_id,
                            "fact_type": "WORK_EXPERIENCE",
                            "fact_value": json.dumps(work),
                            "source_page_number": normalize_profile_page_number(work.get("page_number")),
                            "confidence": 0.9
                        })
                    for skill in candidate_profile.get("skills", []):
                        if not isinstance(skill, str):
                            continue
                        facts.append({
                            "profile_version_id": profile_version_id,
                            "fact_type": "SKILL",
                            "fact_value": json.dumps({"name": skill}),
                            "source_page_number": None,
                            "confidence": 0.85
                        })
                    for cert in candidate_profile.get("certifications", []):
                        if not isinstance(cert, dict):
                            continue
                        facts.append({
                            "profile_version_id": profile_version_id,
                            "fact_type": "CERTIFICATION",
                            "fact_value": json.dumps(cert),
                            "source_page_number": normalize_profile_page_number(cert.get("page_number")),
                            "confidence": 0.85
                        })

                    for section, fact_type in (("languages", "LANGUAGE"), ("projects", "PROJECT")):
                        for item in candidate_profile.get(section, []):
                            value = {"name": item} if isinstance(item, str) else item
                            if not isinstance(value, dict):
                                continue
                            facts.append({
                                "profile_version_id": profile_version_id,
                                "fact_type": fact_type,
                                "fact_value": json.dumps(value),
                                "source_page_number": normalize_profile_page_number(value.get("page_number")),
                                "confidence": 0.85,
                            })

                    if facts:
                        for fact in facts:
                            db.execute(text("""
                                INSERT INTO app_private.profile_facts
                                (profile_version_id, fact_type, fact_value, source_page_number, confidence)
                                VALUES
                                (:profile_version_id, :fact_type, CAST(:fact_value AS jsonb), :source_page_number, :confidence)
                            """), fact)

                    # Update application identity
                    db.execute(text("""
                        UPDATE app_private.application_identities
                        SET display_name = :display_name, email = :email, phone = :phone, updated_at = NOW()
                        WHERE application_id = :application_id
                    """), {
                        "application_id": application_id,
                        "display_name": display_name, "email": email, "phone": phone
                    })

                    db.commit()

                except LLMError as e:
                    logger.error("Profile extraction failed, marking for HR review",
                                application_id=application_id, error_type=type(e).__name__)
                    db.rollback()
                    db.execute(text("""
                        UPDATE app_private.application_documents
                        SET file_processing_status = 'NEEDS_HR_REVIEW', processing_error = :error
                        WHERE document_id = :document_id
                    """), {"document_id": document_id, "error": "Không thể trích xuất hồ sơ; HR cần kiểm tra"})
                    run_filter = "run_id = :run_id" if doc.get("processing_run_id") else "document_id = :document_id"
                    db.execute(text(f"""
                        UPDATE app_private.document_processing_runs
                        SET error_code = 'PROFILE_EXTRACTION_FAILED'
                        WHERE {run_filter}
                    """), {"document_id": document_id, "run_id": doc.get("processing_run_id")})
                    needs_review_count += 1
                    db.execute(text("UPDATE app_private.cv_batches SET failed_files = failed_files + 1 WHERE batch_id = :batch_id"), {"batch_id": batch_id})
                    db.commit()
                    loop.close()
                    continue
                except LostOwnership:
                    db.rollback()
                    loop.close()
                    raise
                except Exception as e:
                    # Persistence and other non-LLM failures must not bubble
                    # into the extraction handler: extraction already
                    # committed, so only the profile attempt is rolled back.
                    logger.error("Profile persistence failed, marking for HR review",
                                 application_id=application_id, document_id=document_id,
                                 error_type=type(e).__name__, **_database_error_metadata(e))
                    db.rollback()
                    db.execute(text("""
                        UPDATE app_private.application_documents
                        SET file_processing_status = 'NEEDS_HR_REVIEW', processing_error = :error
                        WHERE document_id = :document_id
                    """), {"document_id": document_id, "error": "Không thể xử lý tài liệu; HR cần kiểm tra"})
                    run_filter = "run_id = :run_id" if doc.get("processing_run_id") else "document_id = :document_id"
                    db.execute(text(f"""
                        UPDATE app_private.document_processing_runs
                        SET error_code = :error_code
                        WHERE {run_filter}
                    """), {"document_id": document_id, "run_id": doc.get("processing_run_id"),
                            "error_code": "PROFILE_DATA_ERROR" if isinstance(e, SQLAlchemyError) else "PROFILE_PROCESSING_FAILED"})
                    needs_review_count += 1
                    db.execute(text("UPDATE app_private.cv_batches SET failed_files = failed_files + 1 WHERE batch_id = :batch_id"), {"batch_id": batch_id})
                    db.commit()
                    loop.close()
                    continue

                processed_count += 1
                db.execute(text("UPDATE app_private.cv_batches SET processed_files = processed_files + 1 WHERE batch_id = :batch_id"), {"batch_id": batch_id})
                db.commit()
                loop.close()

            except LostOwnership:
                db.rollback()
                loop.close()
                raise
            except Exception as e:
                logger.error("Document processing failed", document_id=document_id,
                             error_type=type(e).__name__, **_database_error_metadata(e))
                db.rollback()
                db.execute(text("""
                    UPDATE app_private.application_documents
                    SET file_processing_status = 'NEEDS_HR_REVIEW', processing_error = :error
                    WHERE document_id = :document_id
                """), {"document_id": document_id, "error": "Không thể xử lý tài liệu; HR cần kiểm tra"})
                run_filter = "run_id = :run_id" if doc.get("processing_run_id") else "document_id = :document_id"
                db.execute(text(f"""
                    UPDATE app_private.document_processing_runs
                    SET status = CASE WHEN status = 'COMPLETED' THEN 'COMPLETED' ELSE 'FAILED' END,
                        error_code = COALESCE(error_code, 'DOCUMENT_PROCESSING_FAILED')
                    WHERE {run_filter}
                """), {"document_id": document_id, "run_id": doc.get("processing_run_id")})
                needs_review_count += 1
                db.execute(text("UPDATE app_private.cv_batches SET failed_files = failed_files + 1 WHERE batch_id = :batch_id"), {"batch_id": batch_id})
                db.commit()
                loop.close()

        # Reconcile durable document and validation states after a crash. This
        # also resumes assessment if all documents completed in a prior attempt.
        counts = db.execute(text("""
            SELECT COUNT(*) FILTER (WHERE bi.validation_result = 'ACCEPTED' AND EXISTS (
                       SELECT 1 FROM app_private.application_documents d
                       WHERE d.application_id = bi.application_id AND d.file_processing_status = 'COMPLETED')) AS processed,
                   COUNT(*) FILTER (WHERE bi.validation_result = 'ERROR' OR EXISTS (
                       SELECT 1 FROM app_private.application_documents d WHERE d.application_id = bi.application_id
                         AND d.file_processing_status IN ('NEEDS_HR_REVIEW', 'ERROR_UNSUPPORTED'))) AS failed
            FROM app_private.cv_batch_items bi WHERE bi.batch_id = :batch_id
        """), {"batch_id": str(batch_id)}).mappings().one()
        processed_count, failed_count = int(counts["processed"]), int(counts["failed"])
        db.execute(text("""
            UPDATE app_private.cv_batches
            SET processed_files = :processed, failed_files = :failed,
                status = CASE WHEN :failed = 0 THEN 'COMPLETED' ELSE 'PARTIALLY_COMPLETED' END,
                completed_at = NOW()
            WHERE batch_id = :batch_id
        """), {"batch_id": str(batch_id), "processed": processed_count, "failed": failed_count})
        db.commit()
        logger.info("Batch processing complete", batch_id=batch_id, processed=processed_count, needs_review=failed_count)

        if processed_count:
            criteria_result = db.execute(text("""
                SELECT 1 FROM app_private.criteria_versions
                WHERE position_id = :position_id AND status = 'APPROVED' LIMIT 1
            """), {"position_id": str(position_id)})
            if criteria_result.first():
                # Finish both steps before completing the same operation; polling
                # callers therefore cannot mistake an extraction-only result for a ranking.
                self._run_assessments(operation_id, db)

    def _operation_position(self, operation_id: UUID, db) -> str:
        position_id = db.execute(text("SELECT position_id FROM app_private.operations WHERE operation_id = :operation_id"),
                                 {"operation_id": str(operation_id)}).scalar_one_or_none()
        if not position_id:
            raise RuntimeError("Operation has no associated position; cannot process safely")
        return str(position_id)

    def _semantic_fallback_chunks(self, db, loop, *, application_id: str, document_id: str,
                                  deterministic_result: dict, unresolved_criteria: list[dict]) -> dict:
        """Add BGE/pgvector candidates to the lexical fallback chunks.

        Any embedding or pgvector failure keeps the lexical chunks; semantic
        retrieval must never fail an assessment.
        """
        fallback = {
            criterion_id: list(chunks)
            for criterion_id, chunks in (deterministic_result.get("fallback_chunks") or {}).items()
        }
        if not unresolved_criteria:
            return fallback
        chunks = [chunk for chunk in deterministic_result.get("chunks", []) if isinstance(chunk, dict)]
        if not chunks:
            return fallback
        chain = (runtime_context.get() or {}).get("bge_chain")
        # Old/unavailable snapshots never fall through to the legacy endpoint.
        try:
            with db.begin_nested():
                allowed = bge_pin_is_current(db, chain)
        except Exception as exc:
            logger.warning("BGE control unavailable; using lexical retrieval", error_type=type(exc).__name__)
            allowed = False
        if not allowed:
            deterministic_result["_semantic_route_used"] = {"status": "LEXICAL_FALLBACK"}
            return fallback
        routes = chain.get("routes", []) if isinstance(chain, dict) else []
        for index, route in enumerate(routes):
            try:
                if not isinstance(route, dict):
                    continue
                provider = provider_for_pinned_route(db, route)
                config = route.get("config", {}) if route else {}
                result = self._semantic_fallback_one(
                    db, loop, application_id=application_id, document_id=document_id,
                    deterministic_result=deterministic_result, unresolved_criteria=unresolved_criteria,
                    provider=provider, index_version=route_index_version(route) if route else settings.EMBEDDING_INDEX_VERSION,
                    top_k=int(config.get("top_k", settings.SEMANTIC_TOP_K)),
                    min_similarity=float(config.get("min_similarity", settings.SEMANTIC_MIN_SIMILARITY)),
                )
                if result is not None:
                    deterministic_result["_semantic_route_used"] = {
                        "route_set_id": chain.get("route_set_id") if chain else None,
                        "route_config_id": route.get("config_id") if route else None,
                        "model": provider.model, "fallback_index": index,
                    }
                    return result
            except Exception as exc:
                logger.warning("BGE route failed", fallback_index=index, error_type=type(exc).__name__)
        deterministic_result["_semantic_route_used"] = {"status": "LEXICAL_FALLBACK"}
        return fallback

    def _semantic_fallback_one(self, db, loop, *, application_id: str, document_id: str,
                               deterministic_result: dict, unresolved_criteria: list[dict],
                               provider, index_version: str, top_k: int, min_similarity: float) -> dict | None:
        """One route owns all query/document vectors and an isolated cache namespace."""
        fallback = {criterion_id: list(chunks) for criterion_id, chunks in
                    (deterministic_result.get("fallback_chunks") or {}).items()}
        chunks = [chunk for chunk in deterministic_result.get("chunks", []) if isinstance(chunk, dict)]
        embedding_model = str(getattr(provider, "model", settings.EMBEDDING_MODEL))
        embedding_dimension = int(getattr(provider, "dimension", settings.EMBEDDING_DIMENSION))
        specs = deterministic_result.get("requirement_specs") or {}
        queries = {
            str(criterion.get("criterion_id")): requirement_query_text(
                specs.get(str(criterion.get("criterion_id"))) or criterion)
            for criterion in unresolved_criteria
        }
        chunk_hashes = [chunk_text_sha256(str(chunk.get("text") or "")) for chunk in chunks]

        # Reuse vectors already stored for this exact document chunk text,
        # model and index version.  Only missing chunks are sent to the
        # embedding provider; this avoids repeating cost and CV egress when
        # a new rubric/policy causes another assessment of the same document.
        pg_available = True
        cached_vectors: dict[tuple[str, str], list[float]] = {}
        try:
            with db.begin_nested():
                cached_rows = db.execute(text("""
                    SELECT chunk_id, chunk_text_sha256, embedding::text AS embedding_text
                    FROM app_private.cv_chunk_embeddings
                    WHERE document_id = :document_id AND embedding_model = :model
                      AND index_version = :index_version
                      AND chunk_text_sha256 = ANY(CAST(:chunk_hashes AS text[]))
                """), {
                    "document_id": document_id, "model": embedding_model,
                    "index_version": index_version,
                    "chunk_hashes": chunk_hashes,
                }).mappings().all()
            for row in cached_rows:
                try:
                    cached_vectors[(str(row["chunk_id"]), str(row["chunk_text_sha256"]))] = (
                        parse_vector_literal(row["embedding_text"]))
                except Exception:
                    continue
        except Exception as exc:
            pg_available = False
            logger.warning("pgvector embedding cache unavailable; embedding all chunks",
                           error_type=type(exc).__name__)

        chunk_vectors: list[list[float] | None] = [
            cached_vectors.get((str(chunk.get("chunk_id")), chunk_hashes[index]))
            for index, chunk in enumerate(chunks)
        ]
        missing_indices = [index for index, vector in enumerate(chunk_vectors) if vector is None]
        cache_hits = len(chunks) - len(missing_indices)
        try:
            if missing_indices:
                missing_vectors = loop.run_until_complete(provider.embed(
                    [str(chunks[index].get("text") or "") for index in missing_indices],
                    kind="document"))
                for index, vector in zip(missing_indices, missing_vectors, strict=True):
                    chunk_vectors[index] = vector
            query_vectors = loop.run_until_complete(
                provider.embed(list(queries.values()), kind="query"))
        except Exception as exc:  # provider outage must not fail assessment
            record_semantic_run(
                cache_hits=cache_hits, cache_misses=len(missing_indices),
                pgvector_status="AVAILABLE" if pg_available else "UNAVAILABLE",
                outcome="PROVIDER_FALLBACK", error_type=type(exc).__name__)
            logger.warning("Semantic embedding unavailable; using lexical fallback",
                           error_type=type(exc).__name__)
            return None
        resolved_chunk_vectors: list[list[float]] = [
            vector for vector in chunk_vectors if vector is not None
        ]
        if len(resolved_chunk_vectors) != len(chunks):
            record_semantic_run(
                cache_hits=cache_hits, cache_misses=len(missing_indices),
                pgvector_status="AVAILABLE" if pg_available else "UNAVAILABLE",
                outcome="PROVIDER_FALLBACK", error_type="EmbeddingError")
            logger.warning("Semantic embedding unavailable; using lexical fallback",
                           error_type="EmbeddingError")
            return None
        chunk_vectors = resolved_chunk_vectors

        # Persist only newly embedded vectors.  A missing extension/table
        # only disables pgvector for this run; in-memory cosine below still
        # works.
        try:
            with db.begin_nested():
                for index in missing_indices:
                    chunk, vector = chunks[index], chunk_vectors[index]
                    db.execute(text("""
                        INSERT INTO app_private.cv_chunk_embeddings
                            (application_id, document_id, chunk_id, chunk_text_sha256, section,
                             page_number, char_start, char_end, embedding, embedding_model,
                             embedding_dimension, index_version)
                        VALUES (:application_id, :document_id, :chunk_id, :chunk_hash, :section,
                                :page_number, :char_start, :char_end, CAST(:embedding AS vector),
                                :model, :dimension, :index_version)
                        ON CONFLICT (document_id, chunk_id, chunk_text_sha256, embedding_model, index_version)
                        DO NOTHING
                    """), {
                        "application_id": application_id, "document_id": document_id,
                        "chunk_id": chunk.get("chunk_id"),
                        "chunk_hash": chunk_text_sha256(str(chunk.get("text") or "")),
                        "section": chunk.get("section"), "page_number": chunk.get("page_number"),
                        "char_start": chunk.get("char_start"), "char_end": chunk.get("char_end"),
                        "embedding": vector_literal(vector), "model": embedding_model,
                        "dimension": embedding_dimension,
                        "index_version": index_version,
                    })
        except Exception as exc:
            pg_available = False
            logger.warning("pgvector persistence unavailable; using in-memory semantic retrieval",
                           error_type=type(exc).__name__)

        chunk_by_id = {str(chunk.get("chunk_id")): chunk for chunk in chunks}
        for (criterion_id, _query), query_vector in zip(queries.items(), query_vectors, strict=True):
            semantic_chunks: list[dict] = []
            if pg_available:
                try:
                    with db.begin_nested():
                        rows = db.execute(text("""
                            SELECT chunk_id, chunk_text_sha256, 1 - (embedding <=> CAST(:query_vector AS vector)) AS similarity
                            FROM app_private.cv_chunk_embeddings
                            WHERE document_id = :document_id AND embedding_model = :model
                              AND index_version = :index_version
                              AND (chunk_id, chunk_text_sha256) IN (
                                  SELECT * FROM unnest(CAST(:chunk_ids AS text[]), CAST(:chunk_hashes AS text[]))
                              )
                            ORDER BY embedding <=> CAST(:query_vector AS vector)
                            LIMIT :top_k
                        """), {
                            "document_id": document_id, "model": embedding_model,
                            "index_version": index_version,
                            "chunk_ids": [str(chunk.get("chunk_id")) for chunk in chunks],
                            "chunk_hashes": chunk_hashes,
                            "query_vector": vector_literal(query_vector),
                            "top_k": top_k,
                        }).mappings().all()
                    for row in rows:
                        similarity = float(row["similarity"])
                        chunk = chunk_by_id.get(str(row["chunk_id"]))
                        if (chunk and row.get("chunk_text_sha256") == chunk_text_sha256(str(chunk.get("text") or ""))
                                and similarity >= min_similarity):
                            semantic_chunks.append({
                                **chunk, "semantic_similarity": round(similarity, 6),
                                "retrieval_source": "SEMANTIC",
                            })
                except Exception as exc:
                    pg_available = False
                    logger.warning("pgvector query unavailable; using in-memory semantic retrieval",
                                   error_type=type(exc).__name__)
            if not semantic_chunks:
                semantic_chunks = retrieve_semantic_candidates(
                    query_vector, chunks, chunk_vectors,
                    min_similarity=min_similarity,
                    top_k=top_k,
                )
            fallback[criterion_id] = merge_candidate_chunks(
                fallback.get(criterion_id, []), semantic_chunks,
                limit=5,
            )
        record_semantic_run(
            cache_hits=cache_hits, cache_misses=len(missing_indices),
            document_chunks_embedded=len(missing_indices),
            query_texts_embedded=len(queries),
            pgvector_status="AVAILABLE" if pg_available else "UNAVAILABLE",
            outcome="SEMANTIC_SUCCESS")
        return fallback

    def _load_ltr_model(self, db=None) -> LTRModel | None:
        mode = (settings.LTR_MODE or "OFF").upper()
        if mode not in {"SHADOW", "ACTIVE"}:
            return None
        try:
            model: LTRModel | None = None
            if settings.LTR_MODEL_VERSION:
                if db is None:
                    logger.warning("LTR_MODEL_VERSION is configured but no database session is available")
                    return None
                row = db.execute(text("""
                    SELECT artifact, status, artifact_sha256
                    FROM app_private.ltr_model_versions
                    WHERE model_version = :model_version
                """), {"model_version": settings.LTR_MODEL_VERSION}).mappings().first()
                if not row:
                    logger.warning("Configured LTR model version was not found; ranking unchanged")
                    return None
                status = str(row["status"] or "").upper()
                if status == "REJECTED" or (mode == "ACTIVE" and status != "APPROVED"):
                    logger.warning("LTR model version is not approved for this mode; ranking unchanged")
                    return None
                artifact = row["artifact"]
                if isinstance(artifact, str):
                    artifact = json.loads(artifact)
                stored_hash = row.get("artifact_sha256") if hasattr(row, "get") else None
                stored_hash_normalized = str(stored_hash).strip().lower() if stored_hash else ""
                if not stored_hash_normalized:
                    if mode == "ACTIVE":
                        logger.warning(
                            "LTR registry artifact is missing artifact_sha256; ranking unchanged")
                        return None
                elif stored_hash_normalized != artifact_sha256(artifact):
                    logger.warning("LTR artifact hash does not match registry; ranking unchanged")
                    return None
                model = LTRModel.from_artifact(artifact)
            elif settings.LTR_MODEL_PATH:
                if mode == "ACTIVE" and (settings.APP_ENV or "").strip().lower() == "production":
                    logger.warning(
                        "LTR file artifacts are not allowed for ACTIVE in production; "
                        "use an APPROVED registry artifact")
                    return None
                model = LTRModel.load(settings.LTR_MODEL_PATH)
            else:
                return None
            if not model.passes_gates(
                min_ndcg=float(settings.LTR_MIN_NDCG_AT_10),
                min_pairwise=float(settings.LTR_MIN_PAIRWISE_ACCURACY),
                min_test_examples=int(settings.LTR_MIN_HOLDOUT_EXAMPLES),
                min_test_groups=int(settings.LTR_MIN_HOLDOUT_GROUPS),
            ):
                logger.warning("LTR artifact did not pass quality gates; ranking unchanged")
                return None
            return model
        except Exception as exc:  # LTR is optional; never fail ranking for it
            logger.warning("LTR artifact unavailable; ranking unchanged",
                           error_type=type(exc).__name__)
            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    pass
            return None

    def _run_assessments(self, operation_id: UUID, db):
        """Assess only the position explicitly associated with this operation."""
        position_id = self._operation_position(operation_id, db)
        cv = db.execute(text("""
            SELECT criteria_version_id, jd_version_id, mandatory_weight_total, nice_to_have_weight_total
            FROM app_private.criteria_versions WHERE position_id = :position_id AND status = 'APPROVED'
              AND jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions WHERE position_id = :position_id ORDER BY version_number DESC LIMIT 1)
            ORDER BY version_number DESC LIMIT 1
        """), {"position_id": position_id}).mappings().first()
        if not cv:
            raise RuntimeError("Không có bộ tiêu chí đã duyệt cho vị trí này")
        criteria_version_id = str(cv["criteria_version_id"])
        criteria_rows = db.execute(text("""
            SELECT criterion_id, name, description, category, weight_in_group, expected_evidence_keywords,
                   requirement_spec
            FROM app_private.criteria_items WHERE criteria_version_id = :criteria_version_id ORDER BY display_order
        """), {"criteria_version_id": criteria_version_id}).mappings().all()
        criteria_items = []
        for row in criteria_rows:
            item = {**dict(row), "criterion_id": str(row["criterion_id"]),
                    "weight_in_group": float(row["weight_in_group"])}
            spec = item.get("requirement_spec")
            if isinstance(spec, str):
                try:
                    item["requirement_spec"] = json.loads(spec)
                except (TypeError, ValueError):
                    item["requirement_spec"] = None
            criteria_items.append(item)
        if not criteria_items:
            raise RuntimeError("Bộ tiêu chí đã duyệt không có tiêu chí nào")

        applications = db.execute(text("""
            SELECT DISTINCT ON (a.application_id) a.application_id, d.document_id,
                   processing.extracted_text_storage_path, profile.profile_version_id
            FROM app_private.applications a
            JOIN app_private.application_documents d ON d.application_id = a.application_id
            LEFT JOIN LATERAL (
                SELECT extracted_text_storage_path FROM app_private.document_processing_runs
                WHERE document_id = d.document_id AND status = 'COMPLETED'
                ORDER BY created_at DESC LIMIT 1
            ) processing ON TRUE
            LEFT JOIN LATERAL (
                SELECT profile_version_id FROM app_private.profile_versions
                WHERE application_id = a.application_id AND status = 'COMPLETED'
                ORDER BY version_number DESC LIMIT 1
            ) profile ON TRUE
            WHERE a.position_id = :position_id AND d.document_type = 'CV'
              AND d.file_processing_status = 'COMPLETED'
              AND a.application_status IN ('NEW', 'IN_REVIEW', 'SHORTLIST')
            ORDER BY a.application_id, d.created_at DESC
        """), {"position_id": position_id, "criteria_version_id": criteria_version_id}).mappings().all()
        failed_count = 0
        loop = asyncio.new_event_loop()
        try:
            for app in applications:
                application_id, document_id = str(app["application_id"]), str(app["document_id"])
                assessment_id = None
                assessment_stack: ExitStack | None = None
                assessment_observation = None
                verification_stack: ExitStack | None = None
                verification_observation = None
                try:
                    assessment_stack = ExitStack()
                    assessment_observation = assessment_stack.enter_context(observability.span(
                        "hra.assessment",
                        metadata={
                            "operation_id": str(operation_id),
                            "position_id": position_id,
                            "application_id": application_id,
                            "document_id": document_id,
                            "profile_version_id": str(app["profile_version_id"]) if app["profile_version_id"] else None,
                            "criteria_version_id": criteria_version_id,
                            "jd_version_id": str(cv["jd_version_id"]),
                            "matching_policy_version": matching_engine.POLICY_VERSION,
                            "deterministic_rules_version": settings.DETERMINISTIC_RULES_VERSION,
                            "prompt_version": settings.MATCHING_PROMPT_VERSION,
                        },
                    ))
                    if not app["profile_version_id"] or not app["extracted_text_storage_path"]:
                        raise RuntimeError("Thiếu hồ sơ trích xuất hoặc văn bản CV")
                    # Old extracted files may predate minimisation. Redact again
                    # before both the AI call and exact-quote verification.
                    cv_text = redact_text(self._load_extracted_text(app["extracted_text_storage_path"]),
                                          detect_first_line_name=True)
                    facts = db.execute(text("""
                        SELECT fact_type, fact_value FROM app_private.profile_facts
                        WHERE profile_version_id = :profile_version_id
                    """), {"profile_version_id": str(app["profile_version_id"])}).mappings().all()
                    candidate_profile = {
                        "candidate_identifier": application_id,
                        "total_years_experience": 0,
                        "education": [f["fact_value"] for f in facts if f["fact_type"] == "EDUCATION"],
                        "work_history": [f["fact_value"] for f in facts if f["fact_type"] == "WORK_EXPERIENCE"],
                        "skills": [f["fact_value"].get("name") for f in facts if f["fact_type"] == "SKILL"],
                        "certifications": [f["fact_value"] for f in facts if f["fact_type"] == "CERTIFICATION"],
                        "languages": [f["fact_value"] for f in facts if f["fact_type"] == "LANGUAGE"],
                        "projects": [f["fact_value"] for f in facts if f["fact_type"] == "PROJECT"],
                    }
                    runtime_public = runtime_snapshot(runtime_context.get() or {})
                    group_weights = {"MUST_HAVE": float(cv["mandatory_weight_total"]) / 100,
                                     "NICE_TO_HAVE": float(cv["nice_to_have_weight_total"]) / 100}
                    fingerprint_payload = {
                        "version": "assessment-fingerprint-v1",
                        "application_id": application_id,
                        "position_id": position_id,
                        "jd_version_id": str(cv["jd_version_id"]),
                        "criteria_version_id": criteria_version_id,
                        "rubric": criteria_items,
                        "profile_version_id": str(app["profile_version_id"]),
                        "profile_facts": sorted(
                            ({"fact_type": f["fact_type"], "fact_value": f["fact_value"]} for f in facts),
                            key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, default=str),
                        ),
                        "cv_text_sha256": hashlib.sha256(cv_text.encode("utf-8")).hexdigest(),
                        # LTR affects ranking, not this assessment. Keep its pinned
                        # selection in operation provenance, not the assessment key.
                        "ai_runtime": {key: value for key, value in runtime_public.items() if key != "ltr_selection"},
                        "llm_seed": settings.LLM_SEED,
                        "prompt_version": settings.MATCHING_PROMPT_VERSION,
                        "matching_policy_version": matching_engine.POLICY_VERSION,
                        "deterministic_rules_version": settings.DETERMINISTIC_RULES_VERSION,
                        "ranking_policy_version": settings.RANKING_POLICY_VERSION,
                        # Hash the effective scoring parameters themselves, not
                        # only a human-bumped version string, and pin the
                        # evaluation date used for "present" date intervals.
                        "evaluation_date": date.today().isoformat(),
                        "scoring_parameters": {
                            "score_map": {
                                "STRONG_MATCH": settings.STRONG_MATCH_SCORE,
                                "MATCH": settings.MATCH_SCORE,
                                "NO_MATCH": settings.NO_MATCH_SCORE,
                                "UNCLEAR": None,
                            },
                            "min_evidence_coverage": settings.MIN_EVIDENCE_COVERAGE,
                            "min_evidence_strength": matching_engine.MIN_EVIDENCE_STRENGTH,
                            "group_weights": group_weights,
                            "mandatory_weight_default": settings.MANDATORY_CRITERIA_WEIGHT_DEFAULT,
                            "nice_to_have_weight_default": settings.NICE_TO_HAVE_WEIGHT_DEFAULT,
                            "llm_strict_json_schema": settings.LLM_STRICT_JSON_SCHEMA,
                        },
                        "semantic_retrieval": semantic_config_fingerprint(),
                    }
                    reuse_scope = semantic_reuse_scope(str(operation_id), fingerprint_payload["semantic_retrieval"])
                    if reuse_scope:
                        fingerprint_payload["semantic_reuse_scope"] = reuse_scope
                    assessment_fingerprint = hashlib.sha256(json.dumps(
                        fingerprint_payload, sort_keys=True, ensure_ascii=False, default=str
                    ).encode("utf-8")).hexdigest()
                    if assessment_observation is not None:
                        assessment_observation.update(metadata={
                            "assessment_fingerprint": assessment_fingerprint,
                            "cv_text_sha256": fingerprint_payload["cv_text_sha256"],
                            "profile_fact_count": len(facts),
                            "criterion_count": len(criteria_items),
                        })
                    existing_assessment = db.execute(text("""
                        SELECT assessment_id FROM app_private.assessment_runs
                        WHERE assessment_fingerprint = :fingerprint AND status = 'COMPLETED'
                        LIMIT 1
                    """), {"fingerprint": assessment_fingerprint}).scalar_one_or_none()
                    if existing_assessment:
                        continue
                    provider_snapshot = {
                        "runtime": runtime_public,
                        "provider_returned_model": None,
                        "system_fingerprint": None,
                    }
                    assessment_id = db.execute(text("""
                        INSERT INTO app_private.assessment_runs
                            (position_id, application_id, jd_version_id, criteria_version_id, profile_version_id,
                             policy_version, operation_id, ai_config_id, status, assessment_fingerprint,
                             matching_policy_version, prompt_version, provider_model_snapshot)
                        VALUES (:position_id, :application_id, :jd_version_id, :criteria_version_id,
                                :profile_version_id, :policy_version, :operation_id, :ai_config_id, 'PROCESSING',
                                :fingerprint, :matching_policy_version, :prompt_version,
                                CAST(:provider_snapshot AS jsonb))
                        RETURNING assessment_id
                    """), {"position_id": position_id, "application_id": application_id,
                            "jd_version_id": str(cv["jd_version_id"]), "criteria_version_id": criteria_version_id,
                            "profile_version_id": str(app["profile_version_id"]),
                            "policy_version": settings.ASSESSMENT_POLICY_VERSION,
                            "operation_id": str(operation_id),
                            "ai_config_id": (runtime_context.get() or {}).get("config_id"),
                            "fingerprint": assessment_fingerprint,
                            "matching_policy_version": matching_engine.POLICY_VERSION,
                            "prompt_version": settings.MATCHING_PROMPT_VERSION,
                            "provider_snapshot": json.dumps(provider_snapshot)}).scalar_one()
                    db.commit()
                    if assessment_observation is not None:
                        assessment_observation.update(metadata={"assessment_id": str(assessment_id)})
                    # Deterministic rules decide measurable criteria first.
                    # The LLM is only a fallback for criteria the rules cannot
                    # decide, and it receives just that unresolved sub-rubric.
                    with observability.span(
                        "hra.assessment.deterministic_matching",
                        metadata={
                            "assessment_id": str(assessment_id),
                            "assessment_fingerprint": assessment_fingerprint,
                            "criterion_count": len(criteria_items),
                            "deterministic_rules_version": settings.DETERMINISTIC_RULES_VERSION,
                        },
                    ) as deterministic_observation:
                        deterministic_result = deterministic_matcher.evaluate_criteria(
                            cv_text, criteria_items, candidate_profile)
                        deterministic_observation.update(output={
                            "rule_finding_count": len(deterministic_result.get("findings", [])),
                            "unresolved_criterion_count": len(deterministic_result.get("unresolved_criterion_ids", [])),
                            "chunk_count": len(deterministic_result.get("chunks", [])),
                            "candidate_years_experience_present": deterministic_result.get("candidate_years_experience") is not None,
                        })
                    if deterministic_result.get("candidate_years_experience"):
                        candidate_profile["total_years_experience"] = deterministic_result[
                            "candidate_years_experience"]
                    raw_findings = list(deterministic_result.get("findings", []))
                    unresolved_ids = set(deterministic_result.get("unresolved_criterion_ids", []))
                    unresolved_criteria = [
                        criterion for criterion in criteria_items
                        if str(criterion.get("criterion_id")) in unresolved_ids
                    ]
                    provider_metadata: dict = {}
                    prompt_version = settings.MATCHING_PROMPT_VERSION
                    fallback_chunks = deterministic_result.get("fallback_chunks", {})
                    if unresolved_criteria:
                        with observability.span(
                            "hra.assessment.semantic_retrieval",
                            metadata={
                                "assessment_id": str(assessment_id),
                                "assessment_fingerprint": assessment_fingerprint,
                                "unresolved_criterion_count": len(unresolved_criteria),
                                "semantic_routes_pinned": len((runtime_context.get() or {}).get("bge_chain", {}).get("routes", [])),
                            },
                        ) as semantic_observation:
                            fallback_chunks = self._semantic_fallback_chunks(
                                db, loop, application_id=application_id, document_id=document_id,
                                deterministic_result=deterministic_result,
                                unresolved_criteria=unresolved_criteria)
                            semantic_observation.update(output={
                                "fallback_criterion_count": len(fallback_chunks or {}),
                                "fallback_chunk_count": sum(
                                    len(chunks) for chunks in (fallback_chunks or {}).values()
                                    if isinstance(chunks, list)
                                ),
                            })
                    if unresolved_criteria:
                        findings = loop.run_until_complete(llm_client.match_criterion_evidence(
                            cv_text=cv_text, candidate_profile=candidate_profile,
                            rubric=unresolved_criteria,
                            candidate_identifier=application_id,
                            rubric_version=criteria_version_id,
                            candidate_chunks=fallback_chunks))
                        if isinstance(findings, dict):
                            provider_metadata = findings.pop("_provider_metadata", {}) or {}
                            prompt_version = findings.pop(
                                "_prompt_version", settings.MATCHING_PROMPT_VERSION)
                            raw_findings.extend(findings.get("findings", []))
                    provider_snapshot.update(provider_metadata)
                    if deterministic_result.get("_semantic_route_used"):
                        provider_snapshot["semantic_route"] = deterministic_result["_semantic_route_used"]
                    chunk_by_id = {
                        str(chunk.get("chunk_id")): chunk
                        for chunk in deterministic_result.get("chunks", [])
                        if isinstance(chunk, dict) and chunk.get("chunk_id")
                    }
                    verification_stack = ExitStack()
                    verification_observation = verification_stack.enter_context(observability.span(
                        "hra.assessment.evidence_verification",
                        metadata={
                            "assessment_id": str(assessment_id),
                            "assessment_fingerprint": assessment_fingerprint,
                            "raw_finding_count": len(raw_findings),
                            "criterion_count": len(criteria_items),
                        },
                    ))
                    validated = []
                    for finding in matching_engine.canonicalize_findings(
                            criteria_items, raw_findings):
                        evidence = finding.get("evidence") or {}
                        quote = evidence.get("verbatim_quote") or ""
                        chunk_id = (evidence.get("chunk_id") or evidence.get("evidence_chunk_id")
                                    or finding.get("evidence_chunk_id"))
                        chunk = chunk_by_id.get(str(chunk_id)) if chunk_id else None
                        if chunk is not None:
                            finding["evidence_chunk_id"] = str(chunk_id)
                            evidence["chunk_id"] = str(chunk_id)
                            if not quote:
                                # The model selected a chunk without quoting it;
                                # the chunk text itself is the verifiable quote.
                                quote = str(chunk.get("text") or "")
                        preferred_start = evidence.get("char_start")
                        preferred_end = evidence.get("char_end")
                        if chunk is not None:
                            preferred_start = chunk.get("char_start", preferred_start)
                            preferred_end = chunk.get("char_end", preferred_end)
                        span = matching_engine.find_quote_span(
                            quote, cv_text,
                            preferred_page=evidence.get("page_number"),
                            preferred_start=preferred_start,
                            preferred_end=preferred_end,
                        )
                        verified = span is not None
                        finding["evidence_verified"] = verified
                        if verified:
                            quote = cv_text[span[0]:span[1]]
                            evidence["verbatim_quote"] = quote
                            evidence["position_in_text"] = span[0]
                        # Page numbers are verified against extracted page text;
                        # DOCX has no reliable page boundaries and remains unpaged.
                        pages = matching_engine.quote_pages(quote, cv_text, span) if verified else []
                        suggested_page = evidence.get("page_number")
                        evidence["page_number"] = suggested_page if suggested_page in pages else (pages[0] if pages else None)
                        finding["evidence"] = evidence
                        if not verified and finding.get("outcome") != "UNCLEAR":
                            finding["outcome"] = "UNCLEAR"
                            finding["requires_verification"] = True
                        validated.append(finding)
                    with observability.span(
                        "hra.assessment.scoring",
                        metadata={
                            "assessment_id": str(assessment_id),
                            "assessment_fingerprint": assessment_fingerprint,
                            "validated_finding_count": len(validated),
                            "matching_policy_version": matching_engine.POLICY_VERSION,
                        },
                    ) as scoring_observation:
                        score, coverage, match_status, results, needs_verification = matching_engine.calculate_assessment_scores(
                            criteria_items, validated, group_weights=group_weights)
                        scoring_observation.update(output={
                            "matching_status": match_status,
                            "evidence_coverage": coverage,
                            "needs_verification": needs_verification,
                            "result_count": len(results),
                        })
                    if verification_observation is not None:
                        verification_observation.update(output={
                            "validated_finding_count": len(validated),
                            "evidence_verified_count": sum(
                                1 for finding in validated if finding.get("evidence_verified")),
                            "downgraded_to_unclear_count": sum(
                                1 for finding in validated
                                if finding.get("outcome") == "UNCLEAR" and finding.get("requires_verification")),
                        })
                    if verification_stack is not None:
                        verification_stack.close()
                        verification_stack = None
                        verification_observation = None
                    if assessment_observation is not None:
                        outcome_counts = Counter(str(result.get("outcome") or "UNCLEAR") for result in results)
                        source_counts = Counter(str(result.get("decision_source") or "LLM") for result in results)
                        verified_count = sum(1 for result in results if result.get("evidence_verified"))
                        score_metadata = {
                            "assessment_id": str(assessment_id),
                            "assessment_fingerprint": assessment_fingerprint,
                            "matching_status": match_status,
                        }
                        assessment_observation.update(
                            output={
                                "status": "COMPLETED",
                                "matching_status": match_status,
                                "criterion_count": len(results),
                                "outcome_counts": dict(outcome_counts),
                                "decision_source_counts": dict(source_counts),
                                "evidence_verified_count": verified_count,
                            },
                            metadata=score_metadata,
                        )
                        if score is not None:
                            assessment_observation.score(
                                name="matching_score", value=float(score), data_type="NUMERIC", metadata=score_metadata)
                        assessment_observation.score(
                            name="evidence_coverage", value=float(coverage), data_type="NUMERIC", metadata=score_metadata)
                        assessment_observation.score(
                            name="needs_verification", value=bool(needs_verification), data_type="BOOLEAN", metadata=score_metadata)
                        assessment_observation.score(
                            name="unclear_criterion_count", value=int(outcome_counts.get("UNCLEAR", 0)),
                            data_type="NUMERIC", metadata=score_metadata)
                        assessment_observation.score(
                            name="rule_decided_count", value=int(source_counts.get("RULE", 0)),
                            data_type="NUMERIC", metadata=score_metadata)
                        assessment_observation.score(
                            name="llm_decided_count", value=int(source_counts.get("LLM", 0)),
                            data_type="NUMERIC", metadata=score_metadata)
                        assessment_observation.score(
                            name="evidence_verified_rate",
                            value=(verified_count / len(results) if results else 0.0),
                            data_type="NUMERIC", metadata=score_metadata)
                    db.execute(text("""
                        UPDATE app_private.assessment_runs
                        SET status = 'COMPLETED', matching_status = :matching_status, matching_score = :score,
                            evidence_coverage = :coverage, completed_at = NOW(),
                            prompt_version = :prompt_version,
                            provider_model_snapshot = CAST(:provider_snapshot AS jsonb)
                        WHERE assessment_id = :assessment_id
                    """), {"assessment_id": assessment_id, "matching_status": match_status,
                            "score": score, "coverage": coverage, "prompt_version": prompt_version,
                            "provider_snapshot": json.dumps(provider_snapshot)})
                    for result in results:
                        result_id = db.execute(text("""
                            INSERT INTO app_private.criterion_assessment_results
                                (assessment_id, criterion_id, outcome, score, confidence, confidence_band,
                                 requires_hr_verification, reasoning, decision_source, evidence_strength,
                                 evidence_chunk_id, rule_version)
                            VALUES (:assessment_id, :criterion_id, :outcome, :score, :confidence, :confidence_band,
                                    :requires_verification, :reasoning, :decision_source, :evidence_strength,
                                    :evidence_chunk_id, :rule_version) RETURNING result_id
                        """), {"assessment_id": assessment_id, "criterion_id": result["criterion_id"],
                                "outcome": result["outcome"],
                                "score": result.get("score"),
                                "confidence": result.get("confidence", 0),
                                "confidence_band": result.get("confidence_band", "LOW"),
                                "requires_verification": result.get("requires_verification", result["outcome"] == "UNCLEAR"),
                                "reasoning": result.get("reasoning"),
                                "decision_source": result.get("decision_source") or "LLM",
                                "evidence_strength": result.get("evidence_strength"),
                                "evidence_chunk_id": result.get("evidence_chunk_id"),
                                "rule_version": result.get("rule_version")}).scalar_one()
                        evidence = result.get("evidence") or {}
                        if evidence.get("verbatim_quote"):
                            db.execute(text("""
                                INSERT INTO app_private.evidence_items
                                    (criterion_result_id, source_document_id, verbatim_quote, page_number,
                                     position_in_text, verification_status)
                                VALUES (:result_id, :document_id, :quote, :page_number, :position_in_text,
                                        :verification_status)
                            """), {"result_id": result_id, "document_id": document_id,
                                    "quote": evidence["verbatim_quote"], "page_number": evidence.get("page_number"),
                                    "position_in_text": evidence.get("position_in_text"),
                                    "verification_status": "VERIFIED" if result.get("evidence_verified") else "FAILED"})
                    db.commit()
                except LostOwnership:
                    if assessment_observation is not None:
                        assessment_observation.update(
                            output={"status": "LOST_OWNERSHIP"}, level="WARNING", status_message="LostOwnership")
                    db.rollback()
                    raise
                except Exception as e:
                    if assessment_observation is not None:
                        assessment_observation.update(
                            output={"status": "FAILED"}, level="ERROR", status_message=type(e).__name__)
                    db.rollback()
                    failed_count += 1
                    logger.error("Assessment failed for application", application_id=application_id, error_type=type(e).__name__)
                    if assessment_id:
                        db.execute(text("""
                            UPDATE app_private.assessment_runs SET status = 'FAILED', completed_at = NOW()
                            WHERE assessment_id = :assessment_id
                        """), {"assessment_id": assessment_id})
                        db.commit()
                finally:
                    if verification_stack is not None:
                        verification_stack.close()
                    if assessment_stack is not None:
                        assessment_stack.close()
        finally:
            loop.close()
        if failed_count:
            raise RuntimeError(f"Không thể đánh giá {failed_count} hồ sơ. Vui lòng kiểm tra kết nối AI và thử lại.")
        # Use the same operation id: completion now guarantees ranking is ready.
        with observability.span(
            "hra.ranking.generate",
            metadata={
                "operation_id": str(operation_id),
                "position_id": position_id,
                "criteria_version_id": criteria_version_id,
                "ranking_policy_version": settings.RANKING_POLICY_VERSION,
                "ltr_mode_pinned": (runtime_context.get() or {}).get("ltr_selection", {}).get("mode", "OFF"),
            },
        ):
            self._generate_ranking(operation_id, db, criteria_version_id=criteria_version_id)

    def _generate_ranking(self, operation_id: UUID, db, criteria_version_id: Optional[str] = None):
        """Generate a snapshot for one position and one approved rubric version."""
        position_id = self._operation_position(operation_id, db)
        if criteria_version_id is None:
            criteria_version_id = db.execute(text("""
                SELECT criteria_version_id FROM app_private.criteria_versions
                WHERE position_id = :position_id AND status = 'APPROVED'
                  AND jd_version_id = (SELECT jd_version_id FROM app_private.jd_versions WHERE position_id = :position_id ORDER BY version_number DESC LIMIT 1)
                ORDER BY version_number DESC LIMIT 1
            """), {"position_id": position_id}).scalar_one_or_none()
        if not criteria_version_id:
            raise RuntimeError("Không có bộ tiêu chí đã duyệt để xếp hạng")
        already_published = db.execute(text("""
            SELECT 1 FROM app_private.ranking_runs r
            WHERE r.operation_id = :operation_id AND r.status = 'COMPLETED'
              AND NOT EXISTS (SELECT 1 FROM app_private.assessment_runs a
                  WHERE a.operation_id = :operation_id AND a.status = 'COMPLETED' AND a.completed_at > r.created_at)
            LIMIT 1
        """), {"operation_id": str(operation_id)}).first()
        if already_published:
            return
        rows = db.execute(text("""
            SELECT DISTINCT ON (a.application_id) a.application_id, i.display_name, ar.assessment_id,
                   ar.matching_status, ar.matching_score, ar.evidence_coverage
            FROM app_private.applications a
            LEFT JOIN app_private.application_identities i ON i.application_id = a.application_id
            JOIN app_private.assessment_runs ar ON ar.application_id = a.application_id
            WHERE a.position_id = :position_id AND a.application_status IN ('NEW', 'IN_REVIEW', 'SHORTLIST')
              AND ar.status = 'COMPLETED' AND ar.criteria_version_id = :criteria_version_id
              AND ar.profile_version_id = (SELECT profile_version_id FROM app_private.profile_versions
                    WHERE application_id = a.application_id AND status = 'COMPLETED' ORDER BY version_number DESC LIMIT 1)
            ORDER BY a.application_id, ar.created_at DESC, ar.assessment_id DESC
        """), {"position_id": position_id, "criteria_version_id": str(criteria_version_id)}).mappings().all()
        applications = [{"application_id": row["application_id"], "display_name": row["display_name"],
                         "latest_assessment": {"assessment_id": row["assessment_id"],
                             "matching_status": row["matching_status"], "matching_score": row["matching_score"],
                             "evidence_coverage": row["evidence_coverage"]}} for row in rows]
        pinned_ltr = (runtime_context.get() or {}).get("ltr_selection")
        try:
            with db.begin_nested():
                ltr_model = resolve_managed(db, pinned_ltr)
        except Exception as exc:
            logger.warning("Managed LTR unavailable; ranking unchanged", error_type=type(exc).__name__)
            ltr_model = None
        ltr_mode = pinned_ltr['mode'] if ltr_model else "OFF"
        ltr_scores: dict[str, float] = {}
        if ltr_model:
            try:
                with db.begin_nested():
                    assessment_ids = [str(item["latest_assessment"]["assessment_id"]) for item in applications]
                    if assessment_ids:
                        feature_rows = db.execute(text("""
                            SELECT cr.assessment_id::text AS assessment_id, cr.outcome, cr.decision_source,
                                   cr.evidence_strength, ci.category
                            FROM app_private.criterion_assessment_results cr
                            JOIN app_private.criteria_items ci ON ci.criterion_id = cr.criterion_id
                            WHERE cr.assessment_id = ANY(CAST(:assessment_ids AS uuid[]))
                        """), {"assessment_ids": assessment_ids}).mappings().all()
                        results_by_assessment: dict[str, list[dict]] = {}
                        for row in feature_rows:
                            results_by_assessment.setdefault(str(row["assessment_id"]), []).append(dict(row))
                        for item in applications:
                            assessment = item["latest_assessment"]
                            features = extract_ranking_features(
                                assessment, results_by_assessment.get(str(assessment["assessment_id"]), []))
                            ltr_scores[str(item["application_id"])] = ltr_model.score(features)
            except Exception as exc:
                logger.warning("Managed LTR scoring failed; ranking unchanged", error_type=type(exc).__name__)
                ltr_model, ltr_mode, ltr_scores = None, "OFF", {}
        ranked = matching_engine.rank_applications(
            applications, [], ltr_scores=ltr_scores, ltr_mode=ltr_mode)
        ranking_run_id = db.execute(text("""
            INSERT INTO app_private.ranking_runs
                (position_id, criteria_version_id, policy_version, operation_id, ai_config_id, status, completed_at,
                 ltr_model_version, ltr_mode, ltr_selection_id)
            VALUES (:position_id, :criteria_version_id, :ranking_policy_version, :operation_id, :ai_config_id, 'COMPLETED', NOW(),
                    :ltr_model_version, :ltr_mode, :ltr_selection_id)
            RETURNING ranking_run_id
        """), {"position_id": position_id, "criteria_version_id": str(criteria_version_id),
                "ranking_policy_version": settings.RANKING_POLICY_VERSION,
                "operation_id": str(operation_id), "ai_config_id": (runtime_context.get() or {}).get("config_id"),
                "ltr_model_version": ltr_model.model_version if ltr_model else None,
                "ltr_mode": ltr_mode,
                "ltr_selection_id": pinned_ltr.get("selection_id") if ltr_model else None}).scalar_one()
        for item in ranked:
            assessment = item["latest_assessment"]
            db.execute(text("""
                INSERT INTO app_private.ranking_items
                    (ranking_run_id, position_id, application_id, assessment_id, rank_number,
                     ranking_status, matching_score, evidence_coverage, ltr_score)
                VALUES (:ranking_run_id, :position_id, :application_id, :assessment_id, :rank_number,
                        :ranking_status, :matching_score, :coverage, :ltr_score)
            """), {"ranking_run_id": ranking_run_id, "position_id": position_id,
                    "application_id": item["application_id"], "assessment_id": assessment["assessment_id"],
                    "rank_number": item["rank_number"], "ranking_status": assessment["matching_status"],
                    "matching_score": assessment["matching_score"], "coverage": assessment["evidence_coverage"],
                    "ltr_score": item.get("ltr_score")})
        identity_rows = db.execute(text("""
            SELECT a.application_id, i.email, i.phone FROM app_private.applications a
            LEFT JOIN app_private.application_identities i ON i.application_id = a.application_id
            WHERE a.position_id = :position_id
        """), {"position_id": position_id}).mappings().all()
        identities = [{"application_id": row["application_id"], "identity": {"email": row["email"], "phone": row["phone"]}}
                      for row in identity_rows]
        for first, second, confidence, signal_type in matching_engine.detect_duplicates(identities):
            db.execute(text("""
                INSERT INTO app_private.duplicate_signals
                    (position_id, application_id_1, application_id_2, signal_type, confidence, detector_version)
                SELECT :position_id, :first, :second, :signal_type, :confidence, 'v1.0'
                WHERE NOT EXISTS (
                    SELECT 1 FROM app_private.duplicate_signals WHERE position_id = :position_id
                      AND signal_type = :signal_type
                      AND NOT (review_status = 'DISMISSED' AND COALESCE(detector_version, '') = 'identity-changed')
                      AND ((application_id_1 = :first AND application_id_2 = :second)
                           OR (application_id_1 = :second AND application_id_2 = :first))
                )
            """), {"position_id": position_id, "first": first, "second": second,
                    "signal_type": signal_type, "confidence": confidence})
        db.commit()
        logger.info("Ranking generated", position_id=position_id, ranking_run_id=ranking_run_id, count=len(ranked))


# Singleton worker instance
worker = ProcessingWorker()
