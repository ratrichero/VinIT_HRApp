# Kiểm thử backend Phase 1

Các integration test tạo dữ liệu giả và chạy trên PostgreSQL thật; LLM và Supabase Auth được giả lập. **Fixture sẽ `TRUNCATE app_private.positions CASCADE` và test tài khoản còn `TRUNCATE auth.users CASCADE`, xóa gần như toàn bộ dữ liệu trong database thử nghiệm.** Chỉ sử dụng cụm PostgreSQL cục bộ mới, dùng một lần, không chứa dữ liệu thật; không chạy song song với test/process khác trên cùng database. Tuyệt đối không trỏ vào Supabase cloud hay database phát triển đang sử dụng. `conftest.py` từ chối URL không có host cục bộ tường minh hoặc tên database không kết thúc bằng `_test`, nhưng kiểm tra này không thay thế việc tự xác nhận database là dùng một lần.

## Chuẩn bị database cục bộ rỗng

Ví dụ dưới đây giả định **một cụm PostgreSQL riêng, dùng một lần** đã chạy tại `127.0.0.1:55432`, có user quản trị `postgres`, các extension `uuid-ossp` và `pgcrypto`, và bộ công cụ `psql`/`createdb`. Không chạy phần tạo role trên cụm dùng chung. Schema `auth` dưới đây chỉ là stub cho test, không phải Supabase Auth thật.

```bash
psql 'postgresql://postgres@127.0.0.1:55432/postgres' -v ON_ERROR_STOP=1 <<'SQL'
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN BYPASSRLS;
SQL
createdb -h 127.0.0.1 -p 55432 -U postgres hra_phase1_test
psql 'postgresql://postgres@127.0.0.1:55432/hra_phase1_test' -v ON_ERROR_STOP=1 <<'SQL'
CREATE SCHEMA auth;
CREATE TABLE auth.users (id UUID PRIMARY KEY, email TEXT UNIQUE);
CREATE FUNCTION auth.uid() RETURNS UUID LANGUAGE sql STABLE AS $$ SELECT NULL::UUID $$;
SQL
for f in supabase/migrations/00001_initial_schema.sql \
         supabase/migrations/00002_audit_fixes_indexes_rls.sql \
         supabase/migrations/00003_phase1_operation_scope.sql \
         supabase/migrations/00004_recovery_and_privacy.sql \
         supabase/migrations/00005_account_administration.sql \
         supabase/migrations/00006_openai_compatible_provider_secrets.sql \
         supabase/migrations/00007_departments_and_position_codes.sql \
         supabase/migrations/00008_deterministic_assessment_foundation.sql \
         supabase/migrations/00009_structured_requirement_specs.sql \
         supabase/migrations/00010_pgvector_bge_ltr.sql \
         supabase/migrations/00011_ltr_model_governance.sql \
         supabase/migrations/00012_retention_audit_integrity.sql \
         supabase/migrations/00013_direct_criteria_approval.sql \
         supabase/migrations/00014_retention_shared_feedback_guard.sql; do
  psql 'postgresql://postgres@127.0.0.1:55432/hra_phase1_test' -v ON_ERROR_STOP=1 -f "$f"
done
```

Chạy từ gốc repository:

```bash
python -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade "pip>=26.2" "setuptools>=84.1.0"
backend/.venv/bin/pip install -e './backend[dev]'
TEST_DATABASE_URL='postgresql://postgres@127.0.0.1:55432/hra_phase1_test' \
  backend/.venv/bin/pytest -q backend/tests
```

Có thể dùng Unix socket qua tham số `host=/đường/dẫn/socket`; host phải được chỉ rõ. Không đặt `PGSERVICE`, `PGSERVICEFILE` hoặc `PGOPTIONS` khi chạy test.

Không đặt `TEST_DATABASE_URL` sẽ chỉ chạy unit test và bỏ qua integration test. Test không chứng minh việc triển khai Supabase Auth/Storage, OCR scan, mô hình AI thật, Docker hoặc chất lượng matching trên CV thật; các phần đó cần kiểm thử riêng trong môi trường được phê duyệt.

Integration test gồm bootstrap Admin một lần và tranh lock, tạo/sửa/khóa tài khoản, Auth giả lập và đổi mật khẩu tạm, các trạng thái lỗi/đối soát Auth–DB, chọn HM khác HR, dual approval, RBAC/ghi chú HR, ma trận role/position cho application/dashboard và các bề mặt Admin semantic/LTR/worker, version JD/profile, AI/allowlist, crash worker, phục hồi lô và metrics. Từ Batch 5, integration test còn bao phủ retention/deletion từng hồ sơ, audit hash chain/append-only, lỗi storage không purge DB và case đã hủy được tạo lại. Đây là test trên PostgreSQL cục bộ với dữ liệu tổng hợp; không dùng CV thật.

## Lưu ý retention và cảnh báo trùng

Các test retention mới cần PostgreSQL thật để xác nhận khóa và tranh chấp; unit test không thay thế integration test. Khi shortlist chứa ghi chú chung hoặc phản hồi không gắn application, purge bị chặn trước khi đụng storage; HR/Privacy cần quyết định cách xử lý, không tự xóa nội dung chung của các ứng viên khác. Cần kiểm tra riêng các shortlist đã purge trước khi có guard vì liên kết item cũ có thể đã mất. Văn bản tự do (kể cả phản hồi riêng của ứng viên khác hoặc phản hồi được thêm sau purge) vẫn có thể nhắc đến người đã xóa; guard không chứng minh đã loại bỏ mọi dữ liệu cá nhân trong văn bản.

Position/case/application/share được khóa trong suốt thao tác storage và transaction purge. Trước storage, job `PROCESSING` được commit làm fence bền vững, tiếp tục chặn mở lại/hủy sau lỗi; recovery chỉ được thực hiện thủ công sau đối soát. Storage không có transaction chung với PostgreSQL: nếu quá trình chết, kết nối DB mất, hoặc xóa storage một phần rồi lỗi, file có thể mất trong khi DB rollback. Xem `doc/RETENTION_RECOVERY_RUNBOOK.md` cho giới hạn, đặc biệt phải xác nhận executor/request cũ đã dừng trước khi retry. Không tự động chạy purge. API cặp duplicate chỉ đọc tín hiệu đã ghi nhận, không khẳng định trùng hay tự cập nhật dữ liệu.
