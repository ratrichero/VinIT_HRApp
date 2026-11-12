from datetime import datetime, timezone

import pytest

import app.db.supabase as supabase_module
from app.api.retention import RetentionActionRequest
from app.core.config import settings
from app.services.retention import (
    RetentionError,
    add_months,
    application_opaque_id,
    delete_storage_objects,
    extracted_storage_paths,
)


def test_retention_reason_is_deprecated_and_declared_never_stored():
    reason_schema = RetentionActionRequest.model_json_schema()["properties"]["reason"]

    assert reason_schema["deprecated"] is True
    assert "never stored" in reason_schema["description"]


def test_application_opaque_id_is_stable_and_not_the_application_id():
    application_id = "123e4567-e89b-12d3-a456-426614174000"

    opaque = application_opaque_id(application_id)

    assert opaque == application_opaque_id(application_id.upper())
    assert opaque != application_id
    assert len(opaque) == 64
    assert all(char in "0123456789abcdef" for char in opaque)


def test_add_months_handles_year_rollover_and_short_months():
    assert add_months(datetime(2025, 1, 31, tzinfo=timezone.utc), 1) == datetime(
        2025, 2, 28, tzinfo=timezone.utc
    )
    assert add_months(datetime(2025, 12, 15, tzinfo=timezone.utc), 12) == datetime(
        2026, 12, 15, tzinfo=timezone.utc
    )


def test_extracted_storage_paths_include_page_map_only_for_extracted_text():
    assert extracted_storage_paths("app/doc/token/extracted.txt") == [
        "app/doc/token/extracted.txt",
        "app/doc/token/pages.json",
    ]
    assert extracted_storage_paths("app/doc/token/other.txt") == [
        "app/doc/token/other.txt"
    ]
    assert extracted_storage_paths(None) == []


class _FakeBucket:
    def __init__(self, removed=None, error=None):
        self.removed = removed
        self.error = error
        self.calls = []

    def remove(self, paths):
        self.calls.append(list(paths))
        if self.error:
            raise self.error
        return self.removed


class _FakeStorage:
    def __init__(self, bucket):
        self.bucket = bucket

    def from_(self, _bucket):
        return self.bucket


class _FakeSupabaseClient:
    def __init__(self, bucket):
        self.storage = _FakeStorage(bucket)


def test_supabase_storage_deletion_counts_provider_confirmed_objects(monkeypatch):
    bucket = _FakeBucket(removed=[{"name": "folder/cv.docx"}])
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(supabase_module, "get_supabase_client", lambda: _FakeSupabaseClient(bucket))

    result = delete_storage_objects(
        [{"bucket": "cv-originals", "storage_path": "folder/cv.docx"},
         {"bucket": "cv-originals", "storage_path": "folder/missing.docx"}],
        [],
    )

    assert bucket.calls == [["folder/cv.docx", "folder/missing.docx"]]
    assert result == {"storage_objects_deleted": 1, "storage_objects_missing": 1}


def test_supabase_storage_errors_are_sanitised(monkeypatch):
    bucket = _FakeBucket(error=RuntimeError("provider detail with secret path"))
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(supabase_module, "get_supabase_client", lambda: _FakeSupabaseClient(bucket))

    with pytest.raises(RetentionError) as raised:
        delete_storage_objects(
            [{"bucket": "cv-originals", "storage_path": "folder/cv.docx"}], []
        )

    assert raised.value.status_code == 502
    assert "secret" not in raised.value.detail and "cv.docx" not in raised.value.detail


@pytest.mark.parametrize("status,closed", [
    ("OPEN", None),
    ("CLOSED", datetime(2024, 1, 2, tzinfo=timezone.utc)),
    ("CLOSED", None),
])
def test_original_closure_guard_rejects_changed_position(status, closed):
    from app.services.retention import _require_original_closure
    case = {"position_closed_at": datetime(2024, 1, 1, tzinfo=timezone.utc)}
    with pytest.raises(RetentionError) as exc:
        _require_original_closure(case, {"status": status, "closed_at": closed})
    assert exc.value.status_code == 409


def test_original_closure_guard_accepts_same_instant():
    from datetime import timedelta
    from app.services.retention import _require_original_closure
    original = datetime(2024, 1, 1, tzinfo=timezone.utc)
    _require_original_closure({"position_closed_at": original}, {"status": "CLOSED", "closed_at": original.astimezone(timezone(timedelta(hours=7)))})


def test_share_level_feedback_guard_blocks_before_purge():
    from app.services.retention import _guard_share_level_text
    class Result:
        def all(self): return []
        def scalar_one(self): return True
    class DB:
        queries = []
        def execute(self, statement, params):
            self.queries.append(str(statement))
            return Result()
    db = DB()
    with pytest.raises(RetentionError) as exc:
        _guard_share_level_text(db, "application-id")
    assert exc.value.status_code == 409
    assert "FOR UPDATE" in db.queries[0] and "FOR UPDATE OF s" in db.queries[1]
    assert "f.application_id IS NULL" in db.queries[2]
