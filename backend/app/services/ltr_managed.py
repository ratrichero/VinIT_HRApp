"""Managed LTR: approved artifacts, pinned selections and fail-closed rollback."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.services.ltr import LTRError, LTRModel, artifact_sha256
from app.services.ai_runtime_controls import service_enabled


def current_selection(db, *, lock: bool = False) -> dict[str, Any] | None:
    row = db.execute(text("""
        SELECT selection_id::text AS selection_id, draft_config_id::text AS draft_config_id,
               mode, model_version, artifact_sha256
        FROM app_private.ltr_managed_selections WHERE current
    """ + (" FOR SHARE" if lock else ""))).mappings().first()
    return dict(row) if row else None


def approved_model(db, version: str, *, expected_hash: str | None = None, lock: bool = False) -> LTRModel:
    row = db.execute(text("""
        SELECT model_version, status, artifact, artifact_sha256
        FROM app_private.ltr_model_versions WHERE model_version=:version
    """ + (" FOR SHARE" if lock else "")), {"version": version}).mappings().first()
    if not row or row['status'] != 'APPROVED' or not row['artifact_sha256']:
        raise LTRError("Model LTR chưa được phê duyệt")
    artifact = row['artifact']
    if isinstance(artifact, str):
        artifact = json.loads(artifact)
    if not isinstance(artifact, dict):
        raise LTRError("Artifact LTR không hợp lệ")
    digest = artifact_sha256(artifact)
    if digest != row['artifact_sha256'] or (expected_hash and digest != expected_hash):
        raise LTRError("Artifact LTR không khớp hash được phê duyệt")
    model = LTRModel.from_artifact(artifact)
    if model.model_version != version or not model.passes_gates(
        min_ndcg=float(settings.LTR_MIN_NDCG_AT_10),
        min_pairwise=float(settings.LTR_MIN_PAIRWISE_ACCURACY),
        min_test_examples=int(settings.LTR_MIN_HOLDOUT_EXAMPLES),
        min_test_groups=int(settings.LTR_MIN_HOLDOUT_GROUPS),
    ):
        raise LTRError("Model LTR không khớp version hoặc chưa đạt quality gates")
    return model


def resolve_managed(db, pinned: dict[str, Any] | None) -> LTRModel | None:
    """Hold the control and selected model locks through ranking publication.

    OFF or a changed pin fails closed. An admin change waits for any ongoing
    publication; no completed OFF can be followed by the old publication.
    """
    if not isinstance(pinned, dict) or pinned.get('mode') not in ('SHADOW', 'ACTIVE'):
        return None
    if not service_enabled(db, "LTR", lock=True):
        return None
    current = current_selection(db, lock=True)
    if not current or current != pinned:
        return None
    return approved_model(db, current['model_version'], expected_hash=current['artifact_sha256'], lock=True)


def resolve_shadow(db, pinned: dict[str, Any] | None) -> LTRModel | None:
    """Compatibility helper for callers specifically requiring SHADOW."""
    if not isinstance(pinned, dict) or pinned.get('mode') != 'SHADOW':
        return None
    return resolve_managed(db, pinned)
