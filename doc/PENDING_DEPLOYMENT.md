# Tài liệu chờ triển khai — Phase 1

> **Đối chiếu mới:** xem [`PHASE1_PRODUCTION_DEFERRED_REPORT.md`](PHASE1_PRODUCTION_DEFERRED_REPORT.md) cho quyết định A1–A6 và phần B tạm treo; xem [`PHASE1_REMAINING_EXECUTION_PLAN.md`](PHASE1_REMAINING_EXECUTION_PLAN.md) cho trạng thái tổng hợp, các việc đang dở và mâu thuẫn thời gian cần xác minh. Các mô tả môi trường/commit ở dưới là snapshot lịch sử, không thay thế kiểm tra thực tế trước triển khai. E2E hiện vẫn tạm treo theo quyết định người dùng; E2E-09 đã có PASS bổ sung trong checklist, không còn là kịch bản chưa kiểm chứng.

> Trạng thái tại ngày 2026-11-07: các nâng cấp Batch 1–5 đã có code, test, CI và migration tương ứng; Batch 5.1 đã chuẩn bị bộ dữ liệu/checklist staging. Tài liệu này lưu riêng những phần **đã sẵn sàng ở repository nhưng chưa được triển khai hoặc chưa được nghiệm thu trên môi trường đích**. Không mục nào trong tài liệu này được coi là đã hoàn thành chỉ vì đã có code, checklist hoặc migration.
>
> Quyết định ngày 2026-11-07: các gate Phase 1 còn lại **tạm dừng, chờ triển khai Production**. Rà soát Phase 2 được thực hiện ở mức tài liệu/code nhưng không đóng bất kỳ DEP nào trong tài liệu này.

- Branch: `arena/ea6e2570-vinit-hrapp`
- Mốc code/tài liệu được audit: `dc9d020`
- Project Supabase đã kết nối: `myrymlqdbyqmpynesiwk`
- Migration remote mới nhất đã xác nhận: `20261107142027 retention_audit_integrity`
- Báo cáo audit chi tiết: [`audit/UPGRADE_AUDIT_2026-11-07.md`](../audit/UPGRADE_AUDIT_2026-11-07.md)
- Checklist chạy staging: [`doc/E2E_STAGING_EXECUTION_CHECKLIST.md`](E2E_STAGING_EXECUTION_CHECKLIST.md)

### Mapping môi trường bắt buộc trước DEP-01/DEP-03

Không được mặc định project Supabase đã kết nối là staging. Trước khi deploy hoặc
chạy E2E, DevOps/Release owner phải điền và ký xác nhận bảng sau; các ô chưa có
bằng chứng là blocker thực thi, không phải chi tiết có thể bổ sung sau.

| Thành phần | Staging cho DEP-01/DEP-02 | Môi trường phục vụ project đã kết nối cho DEP-03 |
|---|---|---|
| Mục đích môi trường | Dùng chính stack hiện tại sau khi purge CV và reclassify cho test code; chưa ký nghiệm thu cho tới khi có bằng chứng purge | Môi trường test code; giữ nguyên stack và tài khoản hiện tại để tiếp tục các bước tiếp theo. Dữ liệu CV/kết quả thử nghiệm hiện tại không cần bảo tồn lâu dài |
| Backend URL/process | VPS HRA, PM2 `hra-backend`, Uvicorn nội bộ `127.0.0.1:8005` | VPS HRA, PM2 `hra-backend`, Uvicorn nội bộ `127.0.0.1:8005`; health `ready`, database `connected`, health vẫn báo `environment=production` theo cấu hình hiện tại |
| Frontend URL/process | VPS HRA, PM2 `hra-frontend`, Next chạy trực tiếp cổng `3005` | VPS HRA, PM2 `hra-frontend`, Next chạy trực tiếp cổng `3005`; HTTP nội bộ trả `200`; hiện truy cập qua IP public `:3005` |
| Supabase project ref | `myrymlqdbyqmpynesiwk` | `myrymlqdbyqmpynesiwk` |
| Migration cao nhất đã xác nhận | `20261107142027 retention_audit_integrity` | `20261107142027 retention_audit_integrity` |
| Backend commit đang chạy | `8c94fa8` | `8c94fa8` |
| Frontend commit đang chạy | `8c94fa8` | `8c94fa8` |
| Worker topology/số instance | PM2 có 1 `hra-backend` với worker trong cùng process và 1 `hra-frontend`; đã `pm2 save` sau purge/restart | PM2 có 1 `hra-backend` với worker trong cùng process và 1 `hra-frontend`; dùng chung PM2/user với NarrativeHealth; đã `pm2 save` sau purge/restart |
| Loại dữ liệu được phép | Chỉ nạp dữ liệu cho vòng test code mới; dữ liệu thật đã từng tồn tại không được gọi ngược là synthetic | Đã purge toàn bộ CV cũ và đối chiếu độc lập: applications/documents/profiles/assessments/rankings/embeddings đều bằng 0; hai bucket `cv-originals` và `cv-extracted-text` đều bằng 0. Giữ nguyên 4 Auth users, 4 user profiles, 2 positions, 2 JD versions, 3 criteria versions và 2 AI configuration versions |
| Provider/mode được phép | Provider test hiện tại chỉ sau khi xác nhận payload qua redaction và cấu hình egress; `LTR_MODE=OFF`; semantic `OFF` hoặc `hash` non-BGE cho smoke | Cấu hình AI ACTIVE dạng OpenAI-compatible qua host `tokenharbor.ai`, model `deepseek-v4.1-flash:free`. Kiểm kê hồi cứu DEP-05 vẫn phải xác nhận quan hệ gateway/provider DeepSeek, retention/training và thời gian sử dụng thực tế |

Kết luận Gate 0 sau quyết định mới nhất: stack VPS + Supabase hiện tại đã purge toàn bộ CV cũ và được phân loại là **môi trường test code sẵn sàng cho vòng dữ liệu mới**. Giữ nguyên stack và các tài khoản đã tạo; HR Lead/Hiring Manager cho E2E dùng tài khoản hiện tại hoặc tạo mới nếu cần. Việc purge không biến dữ liệu thật trong quá khứ thành dữ liệu synthetic và không dùng kết quả thử nghiệm cũ để chứng minh độ chính xác OCR/BGE/LTR. DEP-01 chưa ký PASS cho tới khi có mapping commit đang chạy trên VPS, xác nhận vai trò tài khoản E2E và checklist E2E có bằng chứng.

### Audit PII tại biên LLM — code hiện tại

Phạm vi audit là code tại HEAD hiện tại, không phải bằng chứng hồi tố cho mọi phiên bản code/cấu hình từng chạy trên VPS.

| Đường gửi | Dữ liệu trước HTTP request | Kết luận |
|---|---|---|
| Tạo criteria từ JD | `extract_criteria_from_jd` chạy `redact_text` cho job title và toàn bộ JD trước `_call_llm` | Không gửi JD raw qua đường này |
| Trích xuất profile CV | Worker redact text gốc trước khi lưu extracted text và trước khi gọi; `extract_candidate_profile` redact lại với `detect_first_line_name=True`. Email/phone/display name được trích xuất cục bộ để lưu identity, còn định danh gửi model là application UUID | Không gửi CV raw; model nhận toàn bộ nội dung nghề nghiệp còn lại sau redaction |
| Matching fallback | Worker redact lại extracted text; profile qua `redact_professional_profile`, rubric qua `redact_payload`/`redact_text`, từng chunk qua `redact_text`, tối đa 5 chunks cho mỗi criterion | Đường worker không gửi toàn bộ CV. Direct caller không truyền chunks vẫn dùng legacy prompt chứa toàn bộ CV đã redact |
| Test provider | Chỉ gửi prompt connectivity tối thiểu, không có CV/JD/profile | Không phát sinh egress dữ liệu ứng viên |
| Embedding/semantic | Chỉ chạy khi semantic được bật. Worker tạo chunks từ CV text đã redact rồi mới embed; `BGEHttpEmbeddingProvider` tự nó không redact thêm | Phải giữ nguyên thứ tự redact-trước-embed và kiểm kê endpoint riêng ở DEP-05/DEP-06 |

`redact_text` che các dòng có nhãn tên/email/phone/ngày sinh/địa chỉ/lương/hộ chiếu/CMND-CCCD và một số thuộc tính nhạy cảm, đồng thời che email, URL và dãy số dài; `redact_payload` loại các key định danh đã biết. Test biên bằng fake HTTP client xác nhận tên/email/phone synthetic không xuất hiện trong payload và nội dung nghề nghiệp vẫn được giữ.

Giới hạn bắt buộc phải ghi đúng: đây là **data minimisation best-effort, không phải bảo đảm ẩn danh tuyệt đối**. Redaction có thể sót tên không có nhãn hoặc không khớp heuristic, địa chỉ nằm trong câu, ngày sinh không nhãn, biến thể OCR và thông tin nhận dạng gián tiếp từ trường học/công ty/dự án. `_call_llm` không tự redact ở transport layer; hiện ba method nghiệp vụ criteria/profile/matching là các caller duy nhất và đều redact trước, nhưng mọi caller tương lai phải giữ cùng kỷ luật hoặc bổ sung guard tại transport. Trước khi đổi nhãn `APP_ENV` khỏi `production`, phải xác nhận `LANGFUSE_CAPTURE_CONTENT=false`; nếu bật capture ngoài production, Langfuse có thể nhận prompt/output đã redact chứ không chỉ metadata.

### Checklist purge toàn bộ CV nhưng giữ tài khoản — ĐÃ THỰC THI VÀ KIỂM CHỨNG

1. Dừng/drain `hra-backend` và tạm dừng upload/assessment để không phát sinh CV mới trong lúc purge; đếm lại aggregate ngay trước khi xóa, không dùng số tại thời điểm audit làm số cuối cùng.
2. Phạm vi giữ: `auth.users`, `app_private.user_profiles`, role/position assignments của người dùng, AI configuration và — trừ khi có quyết định riêng — positions/JD/criteria hiện có. HR Lead/HM dùng tài khoản hiện tại hoặc tạo mới.
3. Phạm vi xóa theo từng application: file gốc trong bucket CV, extracted text và `pages.json`, `applications`, `application_identities`, `application_documents`, `document_processing_runs`, `profile_versions`/`profile_facts`, `assessment_runs` và results/evidence phái sinh, `ranking_items`, shortlist shares/feedback, `duplicate_signals`, `cv_chunk_embeddings`, private notes và status events. `cv_batch_items` phải unlink application và thay filename bằng `[DELETED]` như retention hiện tại.
4. Ưu tiên chạy retention execute cho từng application nếu đủ điều kiện nghiệp vụ; nếu dùng reset test hàng loạt, phải dùng một thao tác có kiểm soát với danh sách application ID, transaction cho DB, đối soát storage trước/sau và audit evidence chỉ chứa opaque ID/counts. Không xóa tay rời rạc từng bảng và không đụng audit hash chain.
5. Kiểm chứng sau purge: applications/documents/profile versions/assessment runs/embeddings bằng 0; không còn object CV/extracted text thuộc các application đã xóa; số Auth users/user profiles không đổi; đăng nhập và phân quyền HR Lead/HM vẫn hoạt động.
6. Purge trong HRA không xóa log/retention phía DeepSeek/gateway. DEP-05 phải yêu cầu xác nhận chính sách lưu trữ/training và khả năng xóa dữ liệu phía provider riêng.

Script thực thi đã chuẩn bị tại `backend/scripts/purge_test_cv_data.py`: mặc định dry-run, chỉ in counts; khi execute phải có `--confirm PURGE_ALL_CV_KEEP_ACCOUNTS`, từ chối nếu còn operation `PENDING`/`PROCESSING`, xóa storage trước rồi xóa DB trong transaction. Đây là reset môi trường test, không phải bằng chứng DEP-02 retention. Trên VPS chạy:

```bash
cd /home/ubuntu/hra
git uphra
pm2 stop hra-backend
cd /home/ubuntu/hra/backend
.venv/bin/python scripts/purge_test_cv_data.py --dry-run
.venv/bin/python scripts/purge_test_cv_data.py --execute --confirm PURGE_ALL_CV_KEEP_ACCOUNTS
pm2 restart hra-backend
pm2 status
```

Chỉ execute khi dry-run có `active_operations: 0`. Gửi lại JSON output của script (chỉ gồm counts) để đối chiếu độc lập qua Supabase: DB targets bằng 0, `storage.objects` trong `cv-originals`/`cv-extracted-text` bằng 0 và số tài khoản không đổi. Nếu đối chiếu thấy object mồ côi do attempt trích xuất cũ, dừng lại `hra-backend` và chạy lại cùng lệnh execute với `--include-storage-orphans` để script liệt kê/xóa qua Storage API rồi kiểm tra lại bucket.

Bằng chứng purge hoàn tất: script trên VPS báo `storage_orphans.cv-extracted-text.objects_found=2`, `storage_objects_deleted=2`, `objects_remaining=0`; đối chiếu độc lập qua Supabase sau đó xác nhận applications, identities, documents, processing runs, profile versions/facts, assessment runs, criterion results, evidence items, ranking runs/items, shortlist items, duplicate signals, embeddings và linked batch items đều bằng 0; `storage.objects` trong cả hai bucket đều bằng 0. Preserved counts không đổi: 4 Auth users, 4 user profiles, 2 positions, 2 JD versions, 3 criteria versions, 2 AI configuration versions. PM2 sau restart có `hra-backend` và `hra-frontend` online.

## 1. Danh sách chờ triển khai/thực thi

| ID | Hạng mục chờ | Trạng thái chờ | Phụ thuộc | Chủ trì | Bằng chứng đóng hạng mục |
|---|---|---|---|---|---|
| DEP-01 | Deploy backend/frontend chứa Batch 1–5 lên môi trường test đã reclassify và chạy E2E cho vòng dữ liệu mới | `CLOSED_SCOPED 2026-11-11` | Đóng ở phạm vi rút gọn theo quyết định người vận hành/điều phối 11/11/2026: VPS đã chạy tới commit `40e5e21` (rules v1.4), health/HTTP đạt; checklist PASS cho E2E-01, E2E-05, E2E-06, E2E-07, E2E-08 và xác nhận bổ sung Mục 5.3. Phạm vi loại khỏi vòng này: E2E-02…E2E-04, E2E-09 chuyển vòng kiểm chứng tiếp theo; E2E-10…E2E-13 thuộc DEP-02; E2E-14…E2E-16 `CONDITIONAL` ngoài phạm vi. HR Lead/Hiring Manager ký bổ sung sau | DevOps/IT + HR/HM | Checklist E2E-01…E2E-16 đã điền PASS/FAIL/N/A hợp lệ, commit SHA, migration versions, log/screenshot đã che secret, ký duyệt |
| DEP-02 | Kiểm chứng retention/audit qua backend môi trường test đã deploy | `IN_EXECUTION — PURGE_PARTIALLY_VERIFIED` | E2E-10…E2E-12 PASS. E2E-13 đã execute IT-0005: case `DELETED`, job `COMPLETED`, 3 object đã xóa và storage target còn 0; DB purge/unlink đối chiếu, IT-0006 còn nguyên; SQL hash-chain sau xóa 73 events, 0 broken. Tuy nhiên shortlist, embeddings và notes có count 0 trước xóa nên chưa chứng minh purge khi chúng tồn tại; cần fixture bổ sung hoặc quyết định phạm vi rõ ràng trước ký đóng. Không dùng thao tác purge reset làm bằng chứng retention | DevOps + HR Lead/Admin | `GET /v1/admin/audit/verify` trả `valid=true`; retention due/not-due/confirm/execute có case/job/audit evidence |
| DEP-03 | Triển khai code tương ứng với schema `00011`/`00012` lên môi trường phục vụ project đã kết nối, nếu môi trường đó đang chạy code cũ | `BLOCKED_ENVIRONMENT_IDENTIFICATION` | Điền cột môi trường đã kết nối trong bảng mapping, xác nhận topology/process đang chạy, cửa sổ deploy, drain worker, kế hoạch rollback | DevOps/Release owner | Phiên bản deploy thực tế, health checks, smoke test Admin/LTR/retention, xác nhận không chạy mixed-version worker |
| DEP-04 | Đóng legacy Supabase API keys và revoke legacy JWT signing secret | `BLOCKED_MANUAL_OPS` | Kiểm kê 11/11/2026 qua Management API: project còn đủ legacy anon + legacy service_role key song song với publishable/secret key mới → chưa disable được cho tới khi xác nhận backend/worker trên VPS chỉ dùng key mới (`sb_secret_…`) và restart đồng nhất; thao tác disable/revoke làm thủ công trên Dashboard, không ghi giá trị key vào tài liệu | Chủ project Supabase | Dashboard/Management API xác nhận legacy disabled, legacy JWT secret revoked, login/JWKS mới hoạt động |
| DEP-05 | Kiểm kê hồi cứu DeepSeek/gateway và phê duyệt privacy/egress cho LLM/BGE/OCR dùng dữ liệu thật | `RETROSPECTIVE_INVENTORY_AND_APPROVAL_REQUIRED` | Provider/gateway/model/API base, thời gian dùng, loại payload sau redaction, `ALLOW_EXTERNAL_API`, retention/training phía provider, DLP/redaction | IT Security/Legal/HR | Văn bản phê duyệt hoặc ticket bảo mật đã ký; cấu hình endpoint đúng phạm vi phê duyệt; xác nhận retention/deletion phía provider |
| DEP-06 | BGE pilot bằng endpoint thật và golden set HR | `WAITING_ENDPOINT_AND_DATA` | DEP-05, endpoint BGE-M3 1024 chiều có token/quota, HR golden set | IT + HR | Báo cáo Recall@5, false MATCH/NO_MATCH, unresolved rate, latency; quyết định bật/tắt semantic |
| DEP-07 | LTR SHADOW rồi mới xét ACTIVE | `WAITING_HR_GOLD_DATASET` | DEP-05 nếu dùng dữ liệu thật, HR gold dataset đủ lớn/đại diện, artifact đạt gates và được Admin approve | HR/HM + kỹ thuật | Dataset/labeling report, training gates, review event/artifact hash, SHADOW comparison chứng minh không vi phạm mandatory/coverage |
| DEP-08 | Production readiness: branch protection, monitoring/alerting, topology worker, backup/restore/DR drill | `WAITING_OPS_DECISION` | Quy trình phát hành và hạ tầng đích | DevOps/IT | Cấu hình branch protection nếu áp dụng, dashboard/alert test, quyết định worker topology, biên bản restore/DR drill |

## 2. Phần Batch 5.1 đã chuẩn bị nhưng chưa thực thi

Đã lưu trong repository:

- `staging/synthetic/manifest.json`
- `staging/synthetic/candidates/*.txt`
- `backend/scripts/generate_staging_fixtures.py`
- `backend/tests/test_staging_fixtures.py`
- `doc/E2E_STAGING_EXECUTION_CHECKLIST.md`

Cách sinh DOCX upload staging:

```bash
backend/.venv/bin/python backend/scripts/generate_staging_fixtures.py --check
backend/.venv/bin/python backend/scripts/generate_staging_fixtures.py
```

Giới hạn bắt buộc:

- Chỉ dùng dữ liệu tổng hợp `@example.test`; không thay bằng CV thật khi chưa đóng DEP-04/DEP-05 theo phạm vi áp dụng.
- Bộ fixture là dữ liệu smoke/E2E, **không** phải HR golden set để đo matching/BGE/LTR accuracy.
- File `ocr_simulated.txt` chỉ là nội dung để tạo scan ngoài Git; không tự chứng minh chất lượng OCR.
- DOCX sinh ra trong `staging/generated/` bị ignore; không commit file sinh ra chứa dữ liệu staging.

## 3. Thứ tự triển khai khuyến nghị

### Gate A — Test-environment readiness: DEP-01

Chưa bắt đầu cho tới khi purge toàn bộ CV cũ đã thực thi/kiểm chứng, bảng mapping
môi trường được DevOps/Release owner điền và ký xác nhận. Vòng E2E tiếp theo dùng
chính stack hiện tại đã reclassify, giữ tài khoản người dùng, `LTR_MODE=OFF`;
semantic chỉ dùng `OFF` hoặc provider `hash` non-BGE cho smoke plumbing nếu chưa
đóng DEP-06.

### Gate B — Data lifecycle acceptance: DEP-02

Kiểm chứng sâu retention, storage purge và audit verify qua backend môi trường
test đã deploy. DEP-02 dùng cùng stack của Gate A nhưng ký đóng riêng; thao tác
purge reset ban đầu không tự động thay thế bằng chứng workflow retention.

### Gate C — Deployment alignment & security: DEP-03, sau đó DEP-04

Đồng bộ code với schema `00011`/`00012` trên môi trường đã kết nối sau khi đã
xác định rõ môi trường đó. Việc kiểm kê client/deployment cho DEP-04 có thể
chuẩn bị song song, nhưng chỉ đóng legacy keys/JWT secret sau khi mọi runtime
đã chuyển sang key/JWKS mới.

### Gate D — AI privacy & quality: DEP-05 → DEP-06 → DEP-07

DEP-05 gồm kiểm kê hồi cứu các lần thử DeepSeek/gateway trước đây và phê duyệt
cho mọi lần gửi dữ liệu thật trong tương lai. BGE pilot và LTR SHADOW/ACTIVE là
các gate độc lập; không suy chất lượng từ fixture tổng hợp.

### Gate E — Production readiness: DEP-08

Branch protection, monitoring/alerting, worker topology, backup/restore và DR
drill. Việc chuẩn bị backup/monitoring có thể bắt đầu trước DEP-03; chỉ đóng
Gate E khi có bằng chứng vận hành đầy đủ.

### Thứ tự chi tiết

1. Thực thi checklist purge toàn bộ CV, giữ tài khoản; kiểm chứng DB/Storage và reclassify stack thành môi trường test code.
2. Điền bảng mapping môi trường, chốt commit sẽ deploy và cửa sổ triển khai; xác nhận không có worker/API phiên bản cũ đang xử lý job.
3. Deploy môi trường test theo DEP-01; ghi commit SHA, cấu hình provider ở mức không lộ secret và migration versions.
4. Chạy checklist E2E cho vòng dữ liệu mới; hoàn thành DEP-02 cho audit/retention bằng đúng workflow retention.
5. Nếu môi trường phục vụ project đã kết nối còn code cũ, lên lịch DEP-03 sau khi môi trường test đạt; không để mixed-version worker.
6. Chủ project thực hiện DEP-04 sau khi mọi deployment đã dùng key/JWKS mới.
7. Hoàn tất kiểm kê hồi cứu và xin DEP-05 trước khi gửi thêm dữ liệu thật tới LLM/BGE/OCR.
8. Chạy DEP-06 cho BGE; xây HR gold dataset và chạy DEP-07 ở `SHADOW`; chỉ xét `ACTIVE` sau SHADOW report đạt gate.
9. Hoàn thiện DEP-08 trước khi tuyên bố production readiness.

## 4. Lưu ý rollback và an toàn schema

- Migration `00011`/`00012` là thay đổi cộng thêm; rollback mặc định là rollback code, giữ schema để tránh mất governance/evidence. Không drop cột, bảng, trigger hoặc audit hash chain nếu chưa có kế hoạch rollback đã phê duyệt và backup đã kiểm chứng.
- Sau `00012`, audit events được trigger gán hash ngay cả khi backend cũ ghi audit. Nếu `GET /v1/admin/audit/verify` hoặc postflight SQL báo `valid=false`, dừng rollout retention và điều tra; không sửa tay audit row để làm xanh.
- Nếu backend cũ chưa có API retention/LTR governance, không coi các workflow đó là đã triển khai chỉ vì schema đã có.
- Giữ `LTR_MODE=OFF` và semantic ở cấu hình an toàn cho tới khi DEP-06/DEP-07 có bằng chứng riêng.
- Trước khi xét LTR `ACTIVE`, xử lý finding F-01 trong báo cáo audit: worker phải fail-closed khi registry artifact thiếu `artifact_sha256`, hoặc artifact phải được re-register/re-approve để luôn gắn với hash đã duyệt.

## 5. Mẫu ký nhận chờ triển khai

| ID | Người phụ trách | Ngày dự kiến | Kết quả thực tế | Liên kết bằng chứng |
|---|---|---|---|---|
| DEP-01 | Người vận hành/Điều phối môi trường test | Đóng 11/11/2026 | PASS ở phạm vi rút gọn (E2E-01, E2E-05…E2E-08); HR Lead/HM ký bổ sung sau | `doc/E2E_STAGING_EXECUTION_CHECKLIST.md` Mục 5, 5.2, 5.3, 7 |
| DEP-02 |  |  |  |  |
| DEP-03 |  |  |  |  |
| DEP-04 |  |  |  |  |
| DEP-05 |  |  |  |  |
| DEP-06 |  |  |  |  |
| DEP-07 |  |  |  |  |
| DEP-08 |  |  |  |  |
