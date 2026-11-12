# Update Execute — Phase 1 (P1)

> File này là nhật ký thực thi cho các dev khác theo dõi các thay đổi/nâng cấp Phase 1: hạng mục đã làm, đang làm, còn chờ, bằng chứng kiểm thử và các blocker ngoài code. Mỗi batch nâng cấp từ thời điểm này phải cập nhật file này trước khi coi là hoàn tất.
>
> Branch: `arena/ea6e2570-vinit-hrapp`  
> Ngày bắt đầu vòng nâng cấp: 2026-11-07  
> Nguồn yêu cầu: review lần 2 của GPT đối với code Phase 1 tại commit nền `1326acd`, phần đánh giá/phản biện và plan nâng cấp đã thống nhất với người dùng.

## 1. Nguyên tắc thực thi

1. Làm lần lượt theo gate: sửa đúng scoring → an toàn dữ liệu → semantic vận hành → LTR governance → RBAC/CI/E2E → retention/audit → đánh giá model/dữ liệu thật.
2. Không bật BGE/LTR production chỉ vì code đã có. BGE cần endpoint thật + golden set; LTR cần HR gold dataset + phê duyệt + SHADOW.
3. Không tự ý vô hiệu hóa Supabase legacy keys/JWT secret khi chưa xác nhận mọi deployment đã chuyển sang key/JWKS mới; đây là thao tác Dashboard/Management API của chủ project.
4. Mỗi batch phải có test hoặc bằng chứng kiểm chứng tương ứng, cập nhật tài liệu liên quan và commit riêng để dev khác review được.

## 2. Tổng quan trạng thái

| Batch | Hạng mục | Trạng thái | Commit/Bằng chứng |
|---:|---|---|---|
| 0 | Đánh giá/phản biện review GPT và lập plan nâng cấp | ĐÃ LÀM | Kết luận: đồng ý phần lớn; chưa đóng Phase 1 |
| 1 | Sửa công thức matching score cho UNCLEAR; khóa LTR file artifact ở production; tạo Phase 1 Closure Review | ĐÃ LÀM | Commit `57b9072`, `1386f7e`; targeted tests đạt |
| 2 | Embedding cache + semantic diagnostics | ĐÃ LÀM | Commit `ccd9141`; semantic/LTR tests đạt |
| 3 | LTR governance: artifact hash, review events, Admin approve/reject API | ĐÃ LÀM ở code + project Supabase đã kết nối | Commit `eb674d7`; migration `00011` remote version `20261107133211` |
| 4 | RBAC test matrix + CI độc lập + khung E2E staging | ĐÃ LÀM ở code/CI — CHƯA CHẠY E2E THẬT | Commit `3d68ba2`, sửa harness `3105045`; GitHub Actions run `42379643837` đạt cả 3 job |
| 5 | Retention/deletion workflow + audit integrity | ĐÃ LÀM ở code + CI + project Supabase đã kết nối — CHƯA CÓ STAGING EVIDENCE | Commit `cce75b5`; GitHub Actions run `42380974685` đạt cả 3 job; migration `00012` remote version `20261107142027` |
| 5.1 | Chuẩn bị thực thi gate staging: bộ dữ liệu tổng hợp + checklist E2E chi tiết | ĐÃ CHUẨN BỊ — CHƯA CHẠY E2E THẬT | Commit `90dd4b2`; GitHub Actions run `42382329761` đạt cả 3 job; chờ DevOps/HR chạy trên staging |
| 5.2 | Lưu tài liệu chờ triển khai + review/audit toàn bộ nâng cấp Batch 1–5.1 | ĐÃ AUDIT — CHƯA ĐÓNG GATE TRIỂN KHÁI | Commit `5f5ab66`; GitHub Actions run `42383228867` đạt cả 3 job; full backend local **160 passed**; audit remote 0 broken |
| 5.3 | Post-audit hardening theo đánh giá GPT: F-01 LTR fail-closed, F-03 retention contract, mapping DEP-01/DEP-03 và tiêu chí PASS E2E | ĐÃ LÀM Ở CODE/TÀI LIỆU — CHƯA DEPLOY/CHƯA ĐÓNG DEP | Commit `c862700`; GitHub Actions run `42385930996` đạt cả 3 job; DEP-01 đang bị chặn bởi mapping môi trường staging |
| 5.4 | Chẩn đoán thông báo CI cũ và giảm nhiễu cho thay đổi chỉ gồm Markdown | ĐÃ XỬ LÝ | Run lỗi `42379094324` thuộc commit cũ `479e391`; nguyên nhân đã sửa ở `3105045`; CI tại HEAD `072c7e2` đạt cả 3 job |
| OPS-1 | Smart deploy `git uphra` cho VPS PM2/no-Docker | ĐÃ LÀM Ở SCRIPT/TÀI LIỆU — CHỜ ÁP DỤNG ĐÚNG TRÊN VPS | Commit `605aed0`, `82df2c0`, `b177a66`, `b88aa2b`, `9aa2fe4`, `11fbaf4`; GitHub Actions run `42760182499`, `42761053413`, `42761695196`, `42777309240`, `42780615879`, `42780920898` đạt cả 3 job; HRA dùng alias riêng `uphra` và frontend chuyển sang `next start` trực tiếp như NarrativeHealth |
| 6 | BGE pilot bằng golden set HR; HR gold dataset cho LTR; LTR SHADOW report | CHƯA LÀM | Cần dữ liệu/HR/nguồn lực ngoài code |
| EXT-1 | Đóng legacy Supabase API keys và revoke legacy JWT secret | BLOCKED — MANUAL OPS | Connector không có thao tác deactivate/revoke; cần chủ project thao tác Dashboard/Management API |

## 3. Batch 1 — Scoring UNCLEAR + khóa LTR file production + Closure Review

### Đã thay đổi

- `backend/app/services/matching.py`
  - Từ `matching-v2.1`, `matching_score` là trung bình có trọng số chỉ trên các tiêu chí đã đủ bằng chứng để tính điểm.
  - `UNCLEAR` bị loại khỏi cả tử số và mẫu số; không còn bị tính như 0.
  - `evidence_coverage` vẫn đo phần trọng số rubric đã có bằng chứng; mandatory/coverage gate không đổi.
- `backend/app/core/config.py`
  - Tăng `MATCHING_POLICY_VERSION` từ `matching-v2.0` lên `matching-v2.1`.
- `backend/tests/test_phase1_unit.py`
  - Cập nhật kỳ vọng điểm theo công thức mới.
  - Thêm regression tests: STRONG_MATCH + UNCLEAR, không có tiêu chí được chấm, NO_MATCH đã có bằng chứng.
- `backend/app/workers/processor.py`
  - Khi `APP_ENV=production` và `LTR_MODE=ACTIVE`, chặn nạp LTR bằng `LTR_MODEL_PATH`; production ACTIVE phải dùng registry artifact đã APPROVED.
- `backend/tests/test_semantic_ltr.py`
  - Thêm test chặn file artifact ở production và cho phép ở staging.
- Tài liệu/UI:
  - `doc/MATCHING_STABILITY.md` bổ sung mục công thức điểm từ `matching-v2.1`.
  - `doc/BGE_LTR.md` đồng bộ ý nghĩa feature `matching_score` và giới hạn file artifact.
  - Nhãn chi tiết ứng viên đổi thành “Điểm trên tiêu chí đã có bằng chứng”; bổ sung bản dịch EN.
- `audit/PHASE1_REVIEW_2026-11-07.md`
  - Tạo khung Phase 1 Closure Review đối chiếu F1.01–F1.13 theo PASS/PARTIAL/BLOCKED/NOT TESTED.

### Kiểm chứng

- Targeted tests `test_phase1_unit.py` + `test_semantic_ltr.py`: đạt tại thời điểm batch 1.
- Lưu ý tương thích: artifact LTR đã train bằng `matching_score` theo policy cũ không được coi là tương thích với `matching-v2.1` cho tới khi train/đánh giá lại.

## 4. Batch 2–3 — Semantic cache/diagnostics và LTR governance

### Batch 2: Embedding cache + semantic diagnostics — ĐÃ LÀM

- `backend/app/services/embedding.py`
  - Bổ sung `parse_vector_literal` để đọc vector từ pgvector text.
- `backend/app/workers/processor.py`
  - Trước khi gọi provider, worker tra cứu vector đã lưu theo `document_id + chunk_id + chunk_text_sha256 + embedding_model + index_version`.
  - Chỉ embed các chunk còn thiếu; chỉ insert các vector mới.
  - Ghi diagnostics cho provider fallback, cache hit/miss, số chunk/query đã embed và trạng thái pgvector.
- `backend/app/services/semantic_diagnostics.py`
  - Cung cấp trạng thái cấu hình/runtime: `DISABLED`, `MISCONFIGURED`, `READY_UNVERIFIED`, `OPERATIONAL`, `OPERATIONAL_IN_MEMORY_PGVECTOR_UNAVAILABLE`, `DEGRADED_FALLBACK`.
- `backend/app/api/admin.py`
  - Thêm `GET /v1/admin/semantic/health` cho Admin; không gọi provider và không trả endpoint/API key.
- Tests/docs:
  - Test lượt semantic đầu embed toàn bộ, lượt sau dùng cache và không gọi document embedding lại.
  - Cập nhật `doc/BGE_LTR.md`, `audit/PHASE1_REVIEW_2026-11-07.md`.

### Batch 3: LTR governance — ĐÃ LÀM ở code + project đã kết nối

- `supabase/migrations/00011_ltr_model_governance.sql`
  - Thêm `artifact_sha256`, `registered_by`, `reviewed_by`, `reviewed_at`, `review_reason` vào `ltr_model_versions`.
  - Tạo bảng append-only `ltr_model_review_events` cho REGISTERED/APPROVED/REJECTED.
  - Đã áp lên Supabase project `myrymlqdbyqmpynesiwk` với version `20261107133211`; đã kiểm chứng cột/bảng/RLS.
- `backend/app/services/ltr.py`
  - Thêm `artifact_sha256` dùng canonical JSON để phê duyệt gắn với đúng nội dung artifact.
- `backend/scripts/register_ltr_model.py`
  - Đăng ký DRAFT kèm artifact hash + sự kiện REGISTERED.
  - Từ chối ghi đè cùng `model_version` bằng artifact khác.
- `backend/app/workers/processor.py`
  - Khi nạp registry artifact, kiểm tra artifact hash; hash không khớp thì không dùng model.
- `backend/app/api/admin.py`
  - Thêm `GET /v1/admin/ltr/models`.
  - Thêm `POST /v1/admin/ltr/models/{model_version}/approve` và `/reject` với lý do bắt buộc, kiểm tra DRAFT/gates/hash, ghi review event + audit event.
- Tài liệu:
  - Cập nhật `DEPLOYMENT.md` với migration `00011`.
  - Cập nhật `doc/BGE_LTR.md`: phê duyệt qua Admin API thay vì sửa SQL trực tiếp.
  - Cập nhật `audit/PHASE1_REVIEW_2026-11-07.md`.

### Kiểm chứng

- Semantic/LTR targeted tests đạt sau batch 3.
- Migration `00011` đã kiểm chứng trên project đã kết nối; môi trường đích khác vẫn phải áp/kiểm chứng riêng.

## 5. Batch 4 — RBAC matrix + CI + E2E staging

### Trạng thái: ĐÃ LÀM ở code — CHƯA CHẠY E2E THẬT

### Đã thay đổi

- `backend/tests/test_phase1_integration.py`
  - Thêm `test_rbac_matrix_position_scope_and_admin_surfaces` chạy trên PostgreSQL dùng một lần.
  - Ma trận kiểm tra: HR Lead/HR Recruiter/Hiring Manager/người không được gán theo position được phép và không được phép.
  - Kiểm tra danh sách/chi tiết application bị giới hạn theo position, dashboard chỉ trả position được phép, và người dùng không có assignment không nhận dashboard rows.
  - Kiểm tra `/v1/admin/semantic/health`, `/v1/admin/ltr/models` và `/v1/admin/worker/health` là ADMIN-only; người không phải Admin bị 403.
- `.github/workflows/ci.yml`
  - Job `backend-unit`: cài backend, chạy toàn bộ pytest không có integration database và Ruff trên các bề mặt đã nâng cấp.
  - Job `frontend`: `npm ci`, i18n tests, type-check, lint và production build.
  - Job `backend-integration`: dùng service `pgvector/pgvector:pg17`, tạo database dùng một lần, tạo auth/role stubs tối thiểu, áp toàn bộ migration theo thứ tự và chạy backend tests với `TEST_DATABASE_URL`.
  - CI không dùng Supabase project thật làm database tự động.
- `backend/tests/README.md`
  - Bổ sung migration `00010_pgvector_bge_ltr.sql` và `00011_ltr_model_governance.sql` vào danh sách áp thủ công cho test database.
  - Ghi rõ integration suite đã bao phủ thêm ma trận RBAC position/application/dashboard và các endpoint Admin semantic/LTR/worker.
- `doc/E2E_STAGING.md`
  - Thêm runbook E2E staging: điều kiện an toàn dữ liệu, chuẩn bị môi trường, kịch bản bắt buộc cho auth/RBAC, JD/criteria, upload/OCR, profile/matching/ranking, semantic, LTR governance, shortlist và worker recovery.
  - Ghi rõ bằng chứng phải lưu và điều kiện đạt; việc có runbook không đồng nghĩa E2E thật đã đạt.
- `audit/PHASE1_REVIEW_2026-11-07.md`
  - Cập nhật trạng thái CI từ chưa có workflow sang đã có workflow nhưng vẫn `PARTIAL` cho tới khi checks xanh trên GitHub và branch protection được cấu hình.
  - Cập nhật F1.10/F1.13 theo test RBAC mới; F1.10 vẫn `BLOCKED` do retention/audit integrity và legacy keys.

### Kiểm chứng

- Local không có `TEST_DATABASE_URL`: full backend đạt **90 passed, 59 skipped**; test RBAC mới sẽ được thực thi trong job CI integration dùng PostgreSQL/pgvector dùng một lần.
- Ruff phạm vi các bề mặt đã nâng cấp đạt.
- YAML của `.github/workflows/ci.yml` đã parse thành công.
- Các lần chạy GitHub Actions đầu tiên cho thấy backend-unit và frontend đạt, nhưng backend-integration thất bại ở 6 test worker. Truy vết bằng JUnit/annotations và tái hiện cục bộ cho thấy nguyên nhân không phải RBAC mới: `backend/tests/test_accounts.py::reset_disposable_database()` truncate `auth.users CASCADE`, làm mất policy `assessment-v2.0` do migration `00008` seed, nhưng chỉ khôi phục policy cũ `v1.0`. Khi worker ghi `assessment_runs.policy_version='assessment-v2.0'`, PostgreSQL trả FK violation.
- Đã sửa harness test để reset khôi phục cả `assessment-v2.0` đúng nội dung migration `00008`.
- Sau sửa, chạy full backend trên PostgreSQL dùng một lần tại local đạt **149 passed**.
- GitHub Actions run `42379643837` tại commit `3105045` đã đạt cả ba job: Backend unit tests, Frontend checks và Backend integration (disposable PostgreSQL + pgvector). URL: https://github.com/ratrichero/VinIT_HRApp/actions/runs/42379643837

### Còn lại sau Batch 4

- Chạy E2E thật trên staging tách biệt với Supabase Auth/Storage, OCR scan, LLM thật và BGE endpoint thật bằng dữ liệu tổng hợp/được phép; ghi bằng chứng theo `doc/E2E_STAGING.md`.
- Cấu hình branch protection yêu cầu các job CI chính nếu repo/production process cần.
- Không dùng CV thật cho E2E cho tới khi EXT-1/EXT-2 được đóng hoặc có phê duyệt riêng.

## 6. Batch 5 — Retention/deletion + audit integrity

### Trạng thái: ĐÃ LÀM ở code + CI + project Supabase đã kết nối — CHƯA CÓ BẰNG CHỨNG STAGING

### Phạm vi đã chốt cho Phase 1

- Chỉ tạo retention case cho vị trí `CLOSED` khi đã qua thời hạn lưu trữ theo policy đã phê duyệt (`v1.0-12month`: 12 tháng kể từ `positions.closed_at`).
- Không xóa tự động hàng loạt. HR có quyền xem tạo danh sách case; Admin/HR Lead toàn cục, HR Lead được gán vị trí hoặc người có grant `CONFIRM_DELETION`/`RETENTION_CONFIRM` mới được xác nhận/hủy/thực thi từng case.
- Không triển khai trong Phase 1 các yêu cầu thuộc Phase 2 F2.07 như phê duyệt Legal, OTP/chữ ký điện tử hoặc retention exception hold. “Hủy case” chỉ hủy case hiện tại; khi HR chạy tạo case lại, hồ sơ chưa bị xóa có thể được tạo case mới, còn case đang mở/`DELETED` không bị tạo trùng.

### Đã thay đổi

- `supabase/migrations/00012_retention_audit_integrity.sql`
  - Bổ sung `position_id`, `application_opaque_id` cho `application_retention_cases`; đổi FK application sang `ON DELETE SET NULL` để case còn lại dưới dạng bằng chứng ẩn danh sau purge.
  - Bổ sung opaque ID cho `deletion_jobs`, partial unique index cho case đang mở, index theo position/status/due date và refresh các public view/grant chỉ cho `service_role`.
  - Audit: thêm sequence-backed `chain_sequence`, `previous_event_hash`, `event_hash`; backfill SHA-256 hash chain; trigger BEFORE INSERT dùng advisory transaction lock để hạn chế fork; trigger BEFORE UPDATE/DELETE chặn sửa/xóa `audit_events`.
  - Giới hạn trung thực: đây là tamper-evidence ở mức ứng dụng/DB row. Không có BEFORE TRUNCATE vì harness test dùng `TRUNCATE ... CASCADE`; không tuyên bố chống được DB superuser cố ý vô hiệu hóa trigger/hạ tầng.
- `backend/app/services/retention.py`
  - Sinh opaque ID bằng SHA-256 có domain separator; tính due date bằng cộng tháng lịch từ ngày đóng vị trí.
  - Workflow generate/list/confirm/cancel/execute từng case; confirm và execute đều chặn case chưa đến hạn.
  - Execute xóa storage trước (local hoặc Supabase, gồm cả extracted `pages.json` cùng thư mục), sau đó mới purge DB theo thứ tự FK: shortlist feedback/items, ranking items, duplicate signals, embeddings, assessments (cascade results/evidence), profiles/facts, private notes, identity, status events, documents/processing runs.
  - `cv_batch_items` được unlink và đổi tên file thành `[DELETED]`; retention case/deletion job/event/audit chỉ giữ opaque ID + counts, không ghi tên/email/tên file/quote/CV text vào summary hoặc audit metadata.
  - Nếu storage lỗi, không purge DB; deletion job ghi `FAILED` với mã lỗi đã làm sạch. Với Supabase Storage, số object đã xóa được đếm theo danh sách provider xác nhận.
- `backend/app/api/retention.py` + `backend/app/api/__init__.py`
  - Thêm router `/v1/retention`: list/generate case theo position và confirm/cancel/execute theo case.
  - Quyền xem: Admin/HR Lead toàn cục hoặc assignment HR_RECRUITER/HR_LEAD. Quyền confirm/cancel/execute chặt hơn: Admin/HR Lead toàn cục, assignment HR_LEAD hoặc grant xác nhận xóa.
- `backend/app/services/audit_integrity.py` + `backend/app/api/admin.py`
  - Thêm `GET /v1/admin/audit/verify` cho Admin; đối chiếu linkage và tính lại hash, chỉ trả trạng thái tổng hợp, không lộ metadata audit.
- `.github/workflows/ci.yml`
  - Bổ sung `retention.py`, `audit_integrity.py`, `api/retention.py` vào Ruff scope của job backend-unit.
- Tests:
  - `backend/tests/test_retention_audit.py`: opaque ID ổn định/không bằng application ID, cộng tháng qua năm/tháng ngắn, extracted paths, Supabase remove counts và sanitised provider errors.
  - `backend/tests/test_phase1_integration.py`: purge đầu-cuối trên PostgreSQL thật (file local, documents, profiles/facts, assessments/results/evidence, ranking, shortlist/feedback, embeddings, notes, batch items), RBAC confirm/execute, chưa đến hạn không confirm được, storage lỗi không xóa DB, audit append-only + phát hiện tamper khi bypass trigger, case đã hủy được tạo lại và case đang mở không bị tạo trùng.

### Kiểm chứng

- Ruff phạm vi Batch 5: đạt.
- Targeted Batch 5 trên PostgreSQL local: **9 passed** (5 unit + 4 integration).
- Full backend trên PostgreSQL dùng một lần tại local: **158 passed**.
- Dựng database local mới và áp migration theo thứ tự `00001`–`00012`: đạt; targeted Batch 5 trên database mới: **9 passed**. PostgreSQL nhúng local thiếu `digest()` của pgcrypto nên chỉ tạo wrapper trong database local; Supabase/CI dùng pgcrypto thật.
- GitHub Actions run `42379810795` cho commit tài liệu `9cf1d43` của Batch 4 đã hoàn tất `success` ở cả 3 job.
- Commit Batch 5 `cce75b5` đã push; GitHub Actions run `42380974685` đạt cả Backend unit tests, Frontend checks và Backend integration (disposable PostgreSQL + pgvector). URL: https://github.com/ratrichero/VinIT_HRApp/actions/runs/42380974685
- Preflight Supabase `myrymlqdbyqmpynesiwk`: project `ACTIVE_HEALTHY`, migration mới nhất trước Batch 5 là `20261107133211`, có 21 audit events, 0 retention/deletion rows, 0 operation `PENDING`/`PROCESSING`, đã có `pgcrypto`, chưa có cột/trigger của `00012`.
- Đã áp migration `00012_retention_audit_integrity` lên project đã kết nối; remote version `20261107142027`. Postflight: đủ 3 cột hash audit, 2 cột retention mới, 2 trigger audit, RLS bật trên 4 bảng liên quan, 21/21 audit events có hash và 0 broken event theo cùng thuật toán của `verify_audit_chain`, 0 operation đang chạy.

### Còn lại sau Batch 5

- Chạy retention workflow trên staging thật với Supabase Auth/Storage và backend đã deploy code Batch 5; chưa dùng CV thật.
- Kiểm chứng `GET /v1/admin/audit/verify` qua backend staging (postflight SQL trên project đã kết nối hiện đạt 0 broken event, nhưng chưa thay thế smoke test qua API đã deploy).
- F1.10 chưa đóng hoàn toàn cho tới khi có staging evidence; EXT-1 legacy keys vẫn `BLOCKED – manual ops`.

### Batch 5.1 — Chuẩn bị thực thi gate staging

#### Trạng thái: ĐÃ CHUẨN BỊ — CHƯA CHẠY E2E THẬT

#### Đã thay đổi

- `staging/synthetic/manifest.json` + `staging/synthetic/candidates/*.txt`
  - Bộ dữ liệu tổng hợp `phase1-staging-synthetic-v1`: 5 user theo vai trò, department/position mẫu, criteria Python/PostgreSQL/Docker, 8 candidate cho matching/duplicate/retention và 1 fixture text phục vụ tạo scan OCR ngoài Git.
  - Mọi identity dùng `@example.test` và số điện thoại tổng hợp chứa `000`; không chứa CV/dữ liệu thật.
- `backend/scripts/generate_staging_fixtures.py`
  - Validate manifest chỉ cho phép dữ liệu `SYNTHETIC_ONLY`, kiểm tra source files/expected outcomes, sinh DOCX vào `staging/generated/` để upload staging.
- `backend/tests/test_staging_fixtures.py`
  - Kiểm tra manifest hoàn chỉnh, chỉ dùng email tổng hợp và DOCX sinh ra đọc lại được bằng `python-docx`.
- `doc/E2E_STAGING_EXECUTION_CHECKLIST.md`
  - Checklist thực thi từng bước cho DevOps/Admin/HR/HM: preflight, chuẩn bị dữ liệu, 16 kịch bản E2E-01…E2E-16, mẫu bằng chứng, điều kiện ký duyệt và dọn dẹp.
  - Ghi rõ fixture này là smoke/E2E data, không phải HR golden set cho matching/BGE/LTR.
- `doc/E2E_STAGING.md`
  - Liên kết runbook tổng quát tới checklist thực thi và bộ fixture.
- `.gitignore`
  - Ignore `staging/generated/`; source pack tổng hợp vẫn được review trong Git.

#### Kiểm chứng

- `generate_staging_fixtures.py --check`: đạt; sinh thử 8 DOCX vào thư mục tạm thành công.
- Targeted `test_staging_fixtures.py` + `test_retention_audit.py`: **7 passed**.
- Backend unit không có integration database: **97 passed, 63 skipped**.
- Ruff cho script/test mới: đạt.
- Commit `90dd4b2` đã push; GitHub Actions run `42382329761` đạt cả Backend unit tests, Frontend checks và Backend integration. URL: https://github.com/ratrichero/VinIT_HRApp/actions/runs/42382329761

#### Còn phụ thuộc bên ngoài

- DevOps/IT dựng staging và deploy commit chứa Batch 5; HR/HM/Admin chạy checklist bằng tài khoản staging.
- Nếu dùng LLM/BGE/OCR thật phải có phê duyệt privacy/egress; chưa có phê duyệt thì chỉ dùng local/mock hoặc dữ liệu tổng hợp trong staging tách biệt.
- Sau khi chạy thật, mới cập nhật Closure Review bằng bằng chứng PASS/FAIL; không coi Batch 5.1 là E2E đã đạt.

### Batch 5.2 — Tài liệu chờ triển khai + review/audit toàn bộ nâng cấp

#### Trạng thái: ĐÃ AUDIT — CÁC GATE TRIỂN KHÁI/VẬN HÀNH VẪN CHƯA ĐÓNG

#### Đã thay đổi

- `doc/PENDING_DEPLOYMENT.md`
  - Lưu riêng toàn bộ phần đã sẵn sàng trong repository nhưng chưa triển khai/chưa nghiệm thu: DEP-01 deploy staging + E2E, DEP-02 retention/audit qua backend staging, DEP-03 deploy code tương ứng schema lên môi trường phục vụ project đã kết nối, DEP-04 legacy keys, DEP-05 privacy/egress, DEP-06 BGE pilot, DEP-07 LTR SHADOW/ACTIVE, DEP-08 production readiness.
  - Mỗi hạng mục có trạng thái chờ, phụ thuộc, chủ trì, bằng chứng đóng và mẫu ký nhận.
- `audit/UPGRADE_AUDIT_2026-11-07.md`
  - Audit độc lập toàn bộ nâng cấp từ `1326acd` tới `dc9d020` theo Batch 1, 2, 3, 4, 5 và 5.1.
  - Kết luận: code/CI/remote schema đạt trong phạm vi đã nâng cấp; triển khai/vận hành và dữ liệu/model thật vẫn `PARTIAL/BLOCKED`.
- Liên kết truy vết:
  - `audit/PHASE1_REVIEW_2026-11-07.md` trỏ tới báo cáo audit nâng cấp và tài liệu chờ triển khai.
  - `doc/E2E_STAGING_EXECUTION_CHECKLIST.md` trỏ tới tài liệu chờ triển khai.

#### Kiểm chứng phục vụ audit

- Full backend trên PostgreSQL dùng một lần tại local: **160 passed**.
- Ruff phạm vi CI cho các bề mặt nâng cấp: đạt.
- `generate_staging_fixtures.py --check`: đạt.
- Supabase connector postflight: project `ACTIVE_HEALTHY`; migration tới `20261107142027`; audit events 21, broken 0, missing hash 0; operations đang chạy 0; approved LTR models 0.
- Commit `5f5ab66` đã push; GitHub Actions run `42383228867` đạt cả Backend unit tests, Frontend checks và Backend integration. URL: https://github.com/ratrichero/VinIT_HRApp/actions/runs/42383228867

#### Finding còn mở được chuyển vào tài liệu chờ triển khai

- F-01: Trước LTR ACTIVE, cần fail-closed hoặc re-register/re-approve nếu registry artifact thiếu `artifact_sha256`.
- F-02: Audit hash chain là tamper-evidence, không chống DB superuser; cần kiểm soát DBA và kiểm tra định kỳ.
- F-03: Retention API không lưu free-text reason để tránh PII; nếu governance yêu cầu lý do, dùng reason code có cấu trúc.
- F-04/F-05: Chưa có bằng chứng deploy backend đích, E2E staging thật, phê duyệt privacy/egress, BGE golden set hoặc HR gold dataset cho LTR.

### Batch 5.3 — Post-audit hardening theo đánh giá GPT

#### Trạng thái: ĐÃ LÀM Ở CODE/TÀI LIỆU — CHƯA DEPLOY, CHƯA ĐÓNG DEP-01…DEP-08

#### Đã thay đổi

- `backend/app/workers/processor.py`
  - F-01: ở `LTR_MODE=ACTIVE`, worker từ chối registry artifact thiếu/rỗng `artifact_sha256`; hash không khớp vẫn bị từ chối ở mọi mode dùng registry.
- `backend/tests/test_semantic_ltr.py`
  - Bổ sung bao phủ hash hợp lệ, hash không khớp và hash thiếu/rỗng cho registry artifact.
- `backend/app/api/retention.py` và `backend/tests/test_retention_audit.py`
  - F-03: trường `reason` được đánh dấu deprecated trong schema, ghi rõ chỉ để tương thích, được chấp nhận nhưng cố ý bỏ qua và không bao giờ lưu; chưa áp dụng `reason_code` khi Legal/HR chưa duyệt.
- `doc/PENDING_DEPLOYMENT.md`
  - Bổ sung bảng mapping môi trường bắt buộc cho DEP-01/DEP-03 và thứ tự Gate A–E.
  - DEP-01 đổi trạng thái thành `READY_CODE — BLOCKED_ENVIRONMENT_MAPPING`; DEP-03 thành `BLOCKED_ENVIRONMENT_IDENTIFICATION`.
- `doc/E2E_STAGING_EXECUTION_CHECKLIST.md`
  - Bổ sung phân loại `CRITICAL`/`CORE_FUNCTIONAL`/`CONDITIONAL`, quy tắc dùng `N/A` và yêu cầu defect ID/severity/owner cho mọi FAIL.
- `audit/UPGRADE_AUDIT_2026-11-07.md`
  - Cập nhật trạng thái sau audit của F-01 và F-03.

#### Kiểm chứng

- Targeted LTR tests: **2 passed**.
- Retention tests: **6 passed**.
- Full backend local ở cấu hình mặc định: **98 passed, 63 skipped**; các test integration bị skip vì local không cấu hình `TEST_DATABASE_URL`, chờ GitHub CI chạy với PostgreSQL dùng một lần.
- Ruff `--select F` đúng phạm vi CI cho các bề mặt LTR/retention/worker/test đã sửa: đạt.
- `git diff --check`: đạt.
- Commit `c862700` đã push; GitHub Actions run `42385930996` đạt cả Backend unit tests, Frontend checks và Backend integration. URL: https://github.com/ratrichero/VinIT_HRApp/actions/runs/42385930996

#### Blocker còn lại

- **BLOCKER DEP-01/DEP-03:** chưa có thông tin staging/connected runtime gồm URL, Supabase project của staging, backend/frontend commit đang chạy, worker topology, chủ trì và cửa sổ triển khai. Không được mặc định project đã kết nối là staging.
- Chưa thực thi DEP-01/DEP-02 trên staging; do đó Phase 1 vẫn chưa đóng và Phase 2 vẫn chỉ ở mức plan, chưa triển khai code.

### Batch 5.4 — Chẩn đoán thông báo CI cũ và giảm nhiễu CI

#### Trạng thái: ĐÃ XỬ LÝ — LỖI TRONG EMAIL LÀ RUN CŨ, KHÔNG PHẢI HEAD HIỆN TẠI

- Email báo run `42379094324` thất bại thuộc commit cũ `479e391` (`ci: trích đoạn chẩn đoán lỗi worker`, 2026-11-07 13:54 UTC), trước commit sửa lỗi.
- Job Backend integration thất bại ở 6 test worker. Annotations cho thấy `IntegrityError` khi worker ghi assessment; nguyên nhân gốc là test harness reset database làm mất policy `assessment-v2.0` nhưng chỉ khôi phục policy cũ `v1.0`.
- Đã sửa ở commit `3105045` (`test: khôi phục assessment policy sau reset database`). GitHub Actions run `42379643837` tại commit sửa lỗi đã đạt cả 3 job.
- Các run từ `9cf1d43` về sau đều đạt; tại HEAD `072c7e2`, GitHub Actions run `42386051678` đạt cả Backend unit tests, Frontend checks và Backend integration.
- Nguyên nhân cảm giác “báo lỗi liên tục”: nhiều commit chẩn đoán được push liên tiếp trong khoảng 13:43–13:54 UTC trước khi sửa, mỗi run lỗi tạo một thông báo riêng; một số email đến/trưng bày sau khi code đã được sửa.
- `.github/workflows/ci.yml` đã bổ sung `paths-ignore: ["**.md"]` cho push/pull request để thay đổi chỉ gồm tài liệu Markdown không chạy toàn bộ CI. Push hỗn hợp có code/migration/frontend/staging vẫn chạy CI như trước.
- Commit `e49c346` đã push; GitHub Actions run `42454397160` đạt cả Backend unit tests, Frontend checks và Backend integration. URL: https://github.com/ratrichero/VinIT_HRApp/actions/runs/42454397160

### OPS-1 — Smart deploy `git uphra` cho VPS PM2/no-Docker

#### Trạng thái: ĐÃ LÀM Ở SCRIPT/TÀI LIỆU — CHƯA CHẠY TRÊN VPS TRONG PHIÊN NÀY

#### Bối cảnh

- Sau khi người dùng deploy code mới nhất lên VPS PM2, hệ thống gặp hai hiện tượng đã xử lý thủ công: backend PM2 giữ cấu hình/process cũ khiến login 401 cho tới khi restart `hra-backend`; frontend Next standalone thiếu copy `.next/static` và `public` khiến logo mất và trang login quay vòng do JS không chạy đúng.
- Người dùng cung cấp script smart deploy của project khác (NarrativeHealth) làm tham chiếu; script được chỉnh lại theo đúng cấu trúc VinIT HRApp thay vì sao chép nguyên trạng.

#### Đã thay đổi

- Tạo `scripts/deploy.sh` cho VPS PM2/no-Docker:
  - Pull theo branch hiện tại hoặc `--branch`/`DEPLOY_BRANCH`; từ chối deploy khi worktree bẩn hoặc local có commit chưa push.
  - Chỉ cài Node deps khi `frontend/package.json`/`package-lock.json` đổi; dùng `npm ci`.
  - Chỉ cài Python deps khi `backend/pyproject.toml` đổi; dùng `backend/.venv/bin/python -m pip install .`.
  - Chỉ build frontend khi source/config/deps đổi; sau build luôn sync `.next/static` và `public` vào `.next/standalone`. Nếu standalone thiếu assets nhưng build cũ còn dùng được, script tự sync và restart frontend.
  - Chỉ restart `hra-backend` khi `backend/app` hoặc Python deps đổi; chỉ restart `hra-frontend` khi build/assets đổi; có stale-guard retry restart lỗi ở lần chạy sau.
  - Không tự áp Supabase migrations: nếu `supabase/migrations` đổi, script dừng và yêu cầu chạy lại với `--migrations-verified` sau khi migration đã được áp/kiểm chứng qua quy trình Supabase đã duyệt.
  - Sau restart có smoke test backend health, frontend root, logo và API proxy bootstrap-status.
- Cập nhật `.gitignore` để ignore `.deploy-state/` do script tạo trên VPS.
- Cập nhật `doc/VPS_DEPLOYMENT_NO_DOCKER.md` mục 12.1.1: alias riêng `git config --global alias.uphra '!bash /home/ubuntu/hra/scripts/deploy.sh'`, cách dùng `--force`, `--migrations-verified`, `--branch` và lưu ý lần chạy đầu.

#### Kiểm chứng

- Đã kiểm tra cú pháp script bằng `bash -n scripts/deploy.sh` và `scripts/deploy.sh --help` ở local.
- Người vận hành chạy thử `git up` trên VPS nhưng output vẫn là script cũ của NarrativeHealth (`branch: main`, PM2 `nextjs-dashboard`/`fastapi-backend`), chứng tỏ VPS chưa gọi đúng script/alias của VinIT HRApp hoặc chưa checkout đúng branch chứa script.
- Đã bổ sung hỗ trợ branch dạng positional để `git uphra arena/ea6e2570-vinit-hrapp` hoạt động tương đương `--branch arena/ea6e2570-vinit-hrapp`, đồng thời bổ sung lưu ý chẩn đoán nhầm script/alias trong tài liệu VPS.
- Người dùng xác định đúng nguyên nhân chồng lấn: NarrativeHealth và VinIT HRApp cùng chạy trên một VPS/PM2 và cùng muốn dùng `git up`; alias đặt bằng `git config --global` là alias theo OS user, không theo thư mục project. Quyết định: HRA dùng tên riêng `git uphra`, NarrativeHealth giữ `git up` hoặc đổi sang tên riêng khác; không để hai project cùng chiếm một global alias.
- PM2 dùng chung không phải lỗi tự thân nếu tên process, cwd, cổng và env tách riêng; script HRA chỉ restart `hra-backend`/`hra-frontend` và từ nay in rõ repo root, branch và PM2 targets ở dòng log đầu tiên.
- Sau khi alias `uphra` được tạo, script đã chạy đúng repo HRA nhưng dừng an toàn vì worktree có hai untracked path: `backend/build/` và `ecosystem.config.cjs`. Đây là lỗi bootstrap của bộ deploy: tài liệu yêu cầu tạo ecosystem ngoài Git nhưng `.gitignore` chưa ignore file này, còn `backend/build/` là artifact do pip/setuptools sinh ra.
- Đã bổ sung ignore cho `/ecosystem.config.cjs` và `backend/build/`; script mới cũng bỏ qua đúng hai untracked path đã biết này ở lần bootstrap trước khi pull được `.gitignore`, trong khi vẫn dừng với mọi tracked modification hoặc untracked path khác.
- Người dùng chốt chuyển frontend VPS sang hướng đơn giản như NarrativeHealth: PM2 chạy `next start` trực tiếp từ thư mục `frontend`, bỏ bước copy `.next/static`/`public` vào standalone. `frontend/next.config.js` chỉ bật standalone khi `NEXT_OUTPUT_STANDALONE=1`; Dockerfile đặt biến này để giữ đường Docker hiện tại.
- Script deploy bỏ logic sync standalone, kiểm tra `.next/BUILD_ID` khi tái dùng build cũ, dùng `npm ci --no-audit --no-fund`, và ở lần bootstrap chưa có marker sẽ chấp nhận `node_modules` sẵn có nếu `npm ls --depth=0` kiểm chứng đạt. Script cũng dừng nếu PM2 `hra-frontend` vẫn trỏ vào `.next/standalone` để tránh restart runtime cũ sau khi build trực tiếp.
- Chưa xác nhận smart deploy VinIT chạy thành công trên VPS; người vận hành cần sao lưu/sửa ecosystem sang direct mode, pull thủ công một lần để lấy bản sửa, rồi chạy lại `git uphra`.

#### Commit/CI

- Commit triển khai: `605aed0` (`ops: thêm smart deploy git up cho VPS`), đã push lên `arena/ea6e2570-vinit-hrapp`.
- GitHub Actions run `42760182499` cho commit trên: **success** cả Frontend checks, Backend unit tests và Backend integration (disposable PostgreSQL + pgvector).
- Sau phản hồi chạy thử nhầm script cũ trên VPS, commit `82df2c0` bổ sung hỗ trợ `git up <branch>` dạng positional và lưu ý chẩn đoán alias/script. GitHub Actions run `42761053413` cho commit này: **success** cả 3 job.
- Chuẩn lệnh riêng `git uphra` cho VPS dùng chung: commit `b177a66`; GitHub Actions run `42761695196`: **success** cả 3 job.
- Sửa bootstrap untracked `backend/build/` và `ecosystem.config.cjs`: commit `b88aa2b`; GitHub Actions run `42777309240`: **success** cả 3 job.
- Chuyển frontend VPS sang `next start` trực tiếp và đơn giản hóa dependency/bootstrap: commit `9aa2fe4`; GitHub Actions run `42780615879`: **success** cả 3 job; build frontend local ở chế độ direct cũng đạt trước khi push. Commit `11fbaf4` sửa thao tác chuyển PM2 sang xóa/tạo lại riêng `hra-frontend` để chắc chắn nhận `cwd`/`script` mới; GitHub Actions run `42780920898`: **success** cả 3 job.

## 7. Batch 6 — Đánh giá model và dữ liệu thật

### Trạng thái: CHƯA LÀM

### Điều kiện tiên quyết

- BGE: endpoint thật đã được phê duyệt privacy/egress; golden set HR cho semantic retrieval; đo Recall@5, false MATCH/NO_MATCH, unresolved rate, latency.
- LTR: HR gold dataset đủ lớn; train đạt gates; artifact APPROVED; SHADOW report không có vi phạm mandatory/coverage gate.
- Không dùng weak label từ trạng thái ứng tuyển để bật LTR ACTIVE.

## 8. Quyết định tạm dừng gate Phase 1

- Ngày 2026-11-07, người dùng quyết định: các gate còn lại của Phase 1 **tạm dừng tại đây, chờ triển khai Production**. Các hạng mục DEP-01…DEP-08 trong `doc/PENDING_DEPLOYMENT.md` giữ nguyên trạng thái chờ; không mục nào được coi là đã nghiệm thu chỉ vì code/CI/migration đã sẵn sàng.
- Phase 1 chưa đóng. Việc chuyển sang rà soát Phase 2 không thay thế E2E staging/production, không đóng legacy keys, không phê duyệt privacy/egress và không cho phép dùng CV thật ngoài phạm vi đã được phê duyệt.
- Khi Production được triển khai, quay lại `doc/PENDING_DEPLOYMENT.md` để thực hiện và ký bằng chứng theo từng DEP.

### Tiến triển Gate 0 — Phân loại môi trường hiện tại

- Người vận hành xác nhận VPS HRA được cấu hình `APP_ENV=production` có chủ đích, đồng thời có thể coi VPS là server test. Supabase project `myrymlqdbyqmpynesiwk` đã có tài khoản HR/CV phục vụ thử nghiệm mô hình LLM; dữ liệu được cho biết có thể reset.
- Đã kiểm tra qua Supabase connector: project ở region `ap-southeast-1`, trạng thái `ACTIVE_HEALTHY`; Auth/DB/REST/Storage đều healthy; migration cao nhất là `20261107142027 retention_audit_integrity`. Không truy vấn nội dung HR/CV.
- Kết luận tạm thời cho gate: stack hiện tại là pilot cấu hình production có dữ liệu HR/CV thật dùng thử, không phải staging synthetic sạch cho DEP-01/DEP-02. DEP-01 vẫn bị chặn cho tới khi tạo staging tách biệt hoặc có quyết định reset/reclassify chính thức kèm bằng chứng xóa/kiểm chứng dữ liệu.
- Việc đã dùng HR/CV cho thử nghiệm LLM phải được kiểm kê ở DEP-05: provider nào đã nhận dữ liệu, loại dữ liệu đã gửi, region/lưu trữ và phê duyệt áp dụng; không suy ngược rằng thử nghiệm đã có phê duyệt privacy/egress.
- Quyết định mới nhất của người vận hành: toàn bộ hệ thống hiện tại và các bước sắp triển khai chỉ phục vụ test code. Giữ nguyên stack và các tài khoản đã tạo để tiếp tục kiểm thử; HR Lead/Hiring Manager chạy E2E dùng tài khoản hiện tại hoặc tạo mới nếu cần. CV và kết quả thử nghiệm hiện tại không cần bảo tồn lâu dài; toàn bộ CV đã nhập được phép xóa để thử nghiệm luồng dữ liệu mới. Chưa thực thi purge trong bước audit này.
- Đối chiếu aggregate qua Supabase: 4 Auth users, 4 user profiles, 2 positions, 5 applications, 5 documents và 4 assessment runs. Cấu hình AI ACTIVE là OpenAI-compatible qua host `tokenharbor.ai`, model `deepseek-v4.1-flash:free`; DEP-05 cần kiểm kê hồi cứu quan hệ gateway/DeepSeek, thời gian dùng, payload, retention/training và `ALLOW_EXTERNAL_API` trên runtime thực tế.
- Audit code PII: worker redact CV trước khi lưu extracted text/gọi model, `extract_candidate_profile` redact lại; matching redact profile/rubric/chunks và worker chỉ gửi tối đa 5 chunks mỗi criterion; criteria redact job title/JD; provider test không gửi dữ liệu ứng viên. Kết luận đúng là **không gửi CV raw qua các đường nghiệp vụ hiện tại, nhưng chỉ bảo đảm minimisation best-effort sau redaction**, không phải ẩn danh tuyệt đối. `_call_llm` không tự redact, nên caller tương lai phải giữ kỷ luật này. Test mục tiêu redaction/LLM boundary/matching/semantic: `30 passed`.
- Checklist purge CV giữ tài khoản và tiêu chí kiểm chứng sau purge đã ghi tại `doc/PENDING_DEPLOYMENT.md`. Sau purge phải xác nhận applications/documents/profile/assessments/embeddings bằng 0, storage không còn object CV/extracted text của các application đã xóa, số tài khoản không đổi và login/phân quyền vẫn hoạt động trước khi reclassify stack cho DEP-01.
- Người vận hành đã xác nhận thực thi ngay. Đã chuẩn bị `backend/scripts/purge_test_cv_data.py` với dry-run mặc định, mã xác nhận bắt buộc, chặn khi còn operation đang chạy, xóa storage trước và xóa DB trong transaction; test script/retention đạt `10 passed`. Trước khi chạy script, đối chiếu aggregate: 4 Auth users, 4 user profiles, 2 positions, 5 applications/documents, 4 profile versions, 97 profile facts, 4 assessment runs, 6 ranking items, 1 duplicate signal, 0 embeddings; storage có 5 object `cv-originals` và 10 object `cv-extracted-text`; không có operation `PENDING`/`PROCESSING`. Sau execute, đối chiếu độc lập qua Supabase xác nhận toàn bộ DB target đã bằng 0 và preserved counts không đổi; storage bucket `cv-originals` đã sạch nhưng còn 2 object mồ côi trong `cv-extracted-text`, nên đã bổ sung `--include-storage-orphans` để xóa qua Storage API và phải đối chiếu lại trước khi tuyên bố purge hoàn tất.
- Purge đã hoàn tất: orphan sweep báo xóa 2/2 object còn lại trong `cv-extracted-text`; đối chiếu độc lập cuối cùng qua Supabase xác nhận mọi DB target về CV và cả hai bucket storage đều bằng 0, preserved counts vẫn là 4 Auth users, 4 user profiles, 2 positions, 2 JD versions, 3 criteria versions, 2 AI configuration versions. PM2 `hra-backend`/`hra-frontend` online sau restart. Gate 0 được reclassify sang môi trường test code sẵn sàng vòng dữ liệu mới; DEP-01 còn chờ mapping commit đang chạy, xác nhận tài khoản vai trò E2E và checklist E2E có bằng chứng.
- Đã nhận bằng chứng runtime VPS cho DEP-01: `git rev-parse --short HEAD` là `8c94fa8`, worktree sạch; PM2 có `hra-backend` và `hra-frontend` online cùng các process NarrativeHealth; backend health trả `ready/database connected`, frontend nội bộ HTTP `200`, và người vận hành đã chạy `pm2 save`. Health vẫn báo `environment=production`; đây là nhãn cấu hình hiện tại, còn phân loại vận hành theo quyết định là môi trường test code. DEP-01 còn chờ xác nhận/tạo Outsider, kiểm tra đăng nhập các vai trò và chạy E2E.

### Bổ sung quản lý mật khẩu cho vòng E2E

- Đã mở rộng `POST /v1/auth/change-password`: mọi tài khoản `ACTIVE` đều tự đổi được mật khẩu sau khi tái xác thực bằng mật khẩu hiện tại; luồng bắt buộc đổi mật khẩu tạm thời vẫn giữ và được ghi audit riêng (`CHANGE_TEMPORARY_PASSWORD` so với `CHANGE_OWN_PASSWORD`). Sau khi đổi, token cũ bị từ chối qua `tokens_valid_after`.
- Đã thêm `POST /v1/admin/users/{user_id}/reset-password` cho Admin: đặt mật khẩu tạm thời qua Supabase Auth Admin API, bật `must_change_password=true`, thu hồi token cũ và ghi audit `RESET_USER_PASSWORD` không chứa credential. Giao diện Admin → Tài khoản có hành động “Đặt lại mật khẩu”; menu tài khoản có lối vào “Đổi mật khẩu”.
- Kiểm thử: commit `91539bc`; cục bộ backend unit `117 passed, 65 skipped` (integration DB không chạy khi thiếu `TEST_DATABASE_URL`), frontend i18n/type-check/lint/build đều đạt; GitHub Actions run `42808084883` đạt cả 3 job Backend unit, Frontend checks và Backend integration. Chưa deploy lên VPS và chưa coi là bằng chứng E2E/DEP-01 cho tới khi cập nhật runtime và kiểm thử đăng nhập thực tế trên môi trường test.

### Sửa luồng rà soát tiêu chí AI và trọng số

- Người vận hành phát hiện AI có thể tách một yêu cầu thành tiêu chí chồng lấp, ví dụ thêm `Backend API Development` bên cạnh `Python Programming`; bản nháp cũ chưa cho HR thêm/xóa/chuyển nhóm tiêu chí và hiển thị `Docker=30%` dù là tiêu chí duy nhất của nhóm Ưu tiên.
- Đã sửa prompt tiêu chí (`criteria-prompt-v2.1`) để yêu cầu weight trong từng nhóm cộng 100% và tránh tách tiêu chí chồng lấp; backend chuẩn hoá kết quả AI theo từng nhóm trước khi lưu, ví dụ Docker duy nhất trong NICE_TO_HAVE được lưu/hiển thị 100% trong nhóm và tương ứng 30% tổng điểm khi nhóm Ưu tiên chiếm 30%.
- HR phụ trách nay có thể thêm, sửa tên/mô tả/loại yêu cầu/từ khóa bằng chứng, chuyển tiêu chí giữa Bắt buộc/Ưu tiên và xóa tiêu chí khỏi bản nháp. Đã thêm màn hình “Điều chỉnh trọng số tiêu chí” với tổng từng nhóm, chia đều, chuẩn hoá theo tỉ lệ hiện tại và lưu nguyên tử; backend chặn HR/HM duyệt nếu một nhóm hiện có không cộng đúng 100% hoặc thiếu tiêu chí Bắt buộc.
- Kiểm thử: commit `4dce013`; cục bộ backend `117 passed, 66 skipped` (test integration mới chờ CI PostgreSQL), frontend i18n/type-check/lint/build đều đạt; GitHub Actions run `42842019405` đạt cả 3 job Backend unit, Frontend checks và Backend integration. Chưa deploy lên VPS; bản nháp hiện hữu phải được HR xóa tiêu chí thừa và bấm chuẩn hoá trọng số sau khi cập nhật, hoặc tạo phiên bản tiêu chí mới.

## 9. Blocker ngoài code

| Mã | Hạng mục | Người/điều kiện cần | Trạng thái |
|---|---|---|---|
| EXT-1 | Deactivate legacy Supabase anon/service_role keys và revoke legacy JWT secret | Chủ project thao tác Dashboard/Management API sau khi mọi deployment dùng key/JWKS mới | BLOCKED |
| EXT-2 | Phê duyệt privacy/egress cho LLM/BGE/OCR endpoints | IT Security/Legal/HR | CHƯA CÓ BẰNG CHỨNG |
| EXT-3 | Golden set HR cho matching/BGE và HR gold dataset cho LTR | HR/HM cung cấp/chấm nhãn | CHƯA CÓ |
| EXT-4 | E2E trên môi trường staging đích | DevOps/IT chuẩn bị staging tương đương | CHƯA CÓ BẰNG CHỨNG |

## 10. Quy ước cập nhật file này

Sau mỗi batch, dev thực hiện phải bổ sung:

1. Trạng thái mới trong bảng tổng quan.
2. File/code/migration đã thay đổi.
3. Lệnh test đã chạy và kết quả.
4. Commit hash sau khi push.
5. Blocker còn lại và người/điều kiện cần để mở khóa.

## 11. Hardening retention/shortlist và xem duplicate cùng vị trí

- Theo yêu cầu tiếp tục ba mục ưu tiên: confirm/execute kiểm tra position vẫn `CLOSED` và `closed_at` bằng snapshot; lock position trước case; cancel/reopen và xử lý đồng thời tuân theo fence. Chặn xóa nếu còn operation/tài liệu đang xử lý.
- Trước thao tác storage, commit `deletion_jobs.PROCESSING` làm hàng rào bền vững. Không tự retry khi kết quả chưa chắc chắn; recovery thủ công yêu cầu xác nhận executor cũ đã dừng và storage I/O đã ổn định, có RBAC và audit. `doc/RETENTION_RECOVERY_RUNBOOK.md` nêu điều kiện dừng, đối soát, giới hạn storage không atomic, quy trình không tiếp tục xóa, và yêu cầu drain phiên bản cũ. Không coi cờ/lock là chứng minh request provider đã dừng.
- Không purge khi share đang liên kết chứa note/feedback chung; không tự xóa nội dung chung. Migration mới `00014_retention_shared_feedback_guard.sql` (chỉ repo/local test, chưa áp project kết nối) thêm cờ không định danh ngăn feedback chung mới vào share sau purge; UI báo yêu cầu HR tạo share mới. Văn bản tự do và lịch sử đã purge trước guard vẫn cần HR/Privacy quyết định/kiểm kê.
- API/UI chỉ xem các tín hiệu duplicate có sẵn cùng position; HR phụ trách, HR Lead/Admin được phép, HM/outsider bị từ chối; không thêm cross-position, merge/xóa hoặc xác nhận/bác bỏ. Tín hiệu có thể cũ.
- Local PostgreSQL 16 + pgvector dùng một lần: migrations `00001`–`00014`, full backend **246 passed**. Package `pgserver` cục bộ chỉ có stub `pgcrypto`/`uuid-ossp`, nên test tạo hàm `digest(text,'sha256')` dùng SHA-256 built-in của PostgreSQL và stub UUID; kết quả không chứng minh extension pgcrypto thực. CI PostgreSQL/pgvector riêng sẽ xác nhận lại với extension thật. Test có mô phỏng xóa một phần, mất kết nối DB thật bằng terminate backend, crash process, retry có xác nhận, tranh chấp lock, shared feedback và RBAC.
- Backend unit không DB trước bổ sung test cuối: **162 passed, 80 skipped**; Ruff phạm vi CI đạt. Frontend type-check, lint, unit 3/3, i18n 3/3 và production build đạt.
- Chuẩn bị song song: `doc/PHASE1_OPERATIONS_DECISION_CHECKLIST.md` liệt kê owner/đầu ra DevOps, HR/Privacy/Legal, HR/HM; tất cả còn chờ xác nhận thực tế. Không chạy E2E, không thay dữ liệu VPS/Supabase, không bật AI/automation, không đổi manifest/rules. DEP-02 vẫn partial và Phase 1 chưa đóng. CI sẽ theo commit sau khi push branch làm việc; chỉ ghi PASS sau khi có kết quả thật.
