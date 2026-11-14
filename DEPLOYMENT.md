# Triển khai và vận hành VinUni HRApp

> Mã này **chưa sẵn sàng production**. Các test dùng PostgreSQL cục bộ dùng một lần, dữ liệu tổng hợp và AI HTTP mock; chưa chứng minh Supabase Auth/Storage, model thật, OCR scan hay Docker trong môi trường đích. Không dùng CV thật trong preview hoặc kiểm thử chưa được phê duyệt.

## Lịch sử project đã kết nối

Trên project `myrymlqdbyqmpynesiwk`, sau xác nhận của người dùng, đã áp `00003_phase1_operation_scope.sql`, `00004_recovery_and_privacy.sql` (05/11/2026 15:28 UTC), `00005_account_administration.sql` (05/11/2026 16:36 UTC), `00006_openai_compatible_provider_secrets.sql` (06/11/2026), `00007_departments_and_position_codes.sql` (06/11/2026), `00008_deterministic_assessment_foundation.sql`, `00009_structured_requirement_specs.sql`, `00010_pgvector_bge_ltr.sql`, `00011_ltr_model_governance.sql` và `00012_retention_audit_integrity.sql` (07/11/2026). Lịch sử remote:

| File trong repository | Version/name trên Supabase |
|---|---|
| `00001_initial_schema.sql` | `20261105081853 initial_schema` |
| `00002_audit_fixes_indexes_rls.sql` | `20261105082127 audit_fixes_indexes_rls_grants` |
| `00003_phase1_operation_scope.sql` | `20261105131736 phase1_operation_scope` |
| `00004_recovery_and_privacy.sql` | `20261105152817 recovery_and_privacy` |
| `00005_account_administration.sql` | `20261105163626 account_administration` |
| `00006_openai_compatible_provider_secrets.sql` | `20261106042158 openai_compatible_provider_secrets` |
| `00007_departments_and_position_codes.sql` | `20261106050756 departments_and_position_codes` |
| `00008_deterministic_assessment_foundation.sql` | `20261107012433 deterministic_assessment_foundation` |
| `00009_structured_requirement_specs.sql` | `20261107021622 structured_requirement_specs` |
| `00010_pgvector_bge_ltr.sql` | `20261107022845 pgvector_bge_ltr` |
| `00011_ltr_model_governance.sql` | `20261107133211 ltr_model_governance` |
| `00012_retention_audit_integrity.sql` | `20261107142027 retention_audit_integrity` |

Preflight trước 00005 (05/11/2026 16:36 UTC): DB/Auth/REST/Storage khỏe, không có vị trí, hồ sơ, tác vụ đang xử lý, auth user hoặc profile; một cấu hình AI ACTIVE endpoint loopback. Sau áp 00005: bảng `app_private.account_initialization` (1 row, `initialized_at` NULL → bootstrap đang mở vì chưa từng có ADMIN), hai cột `user_profiles.must_change_password` (`boolean NOT NULL DEFAULT FALSE`) và `tokens_valid_after` (`timestamptz`), function `app_private.mark_admin_initialized()` và trigger `mark_admin_initialized` trên `user_role_assignments`, RLS `ENABLE` trên `account_initialization` chỉ `service_role` được `SELECT,UPDATE`. Backfill HM không tạo thêm row do không có `position_assignments` đang hiệu lực tại thời điểm áp. Postflight xác nhận `has_table=true`, `has_must_change=true`, `has_tokens_valid=true`, `has_func=true`, `has_trigger=true`. Endpoint của cấu hình AI ACTIVE hiện tại vẫn là **loopback** (`localhost` trong container backend không phải VPS/model bên ngoài); phải chọn và kích hoạt endpoint hợp lệ từ Admin trước khi dùng AI. Tại thời điểm kiểm tra chưa có ADMIN/auth user. Chưa xác minh backup/restore, rotate key hay E2E dịch vụ thật; không thể suy ra mọi worker bên ngoài đã dừng chỉ từ snapshot này.

Mã backend hiện tại **phụ thuộc 00005** (kiểm tra trạng thái tài khoản, `must_change_password`, `tokens_valid_after` và bootstrap một lần). Đã áp xong lên project kết nối sau khi preflight không có dữ liệu xung đột; với môi trường khác phải đối chiếu schema/grants và user/role hiện có, backup/restore, thử staging và lập kế hoạch rollback riêng trước khi áp. 00005 ghi dấu bootstrap một lần (kể cả assignment ADMIN đã thu hồi cũng đóng bootstrap), không khôi phục role HM đã thu hồi và không backfill `HR_LEAD` từ position.

Preflight trước 00006 (06/11/2026): project đang ở 5 migration, `ai_configuration_versions` chưa có `provider_name`/`api_key_ciphertext`/`api_key_hint`, có một cấu hình `local` ACTIVE và không có tác vụ `PENDING`/`PROCESSING`. Lần áp đầu bị PostgreSQL từ chối và rollback vì `CREATE OR REPLACE VIEW` không thể chèn cột mới vào giữa thứ tự cột hiện hữu; file migration đã đổi sang `DROP VIEW`/`CREATE VIEW` với danh sách cột tường minh rồi áp thành công ở version `20261106042158`. Postflight xác nhận ba cột mới tồn tại trong `app_private.ai_configuration_versions`; view `public.ai_configuration_versions` chỉ phơi `provider_name`, `api_key_configured`, `api_key_hint` và **không** có `api_key_ciphertext`, grant không cấp cho `anon`/`authenticated`. Backend mới phụ thuộc 00006 cho Quản trị AI; cấu hình `local` ACTIVE hiện hữu không bị thay đổi.

Preflight trước 00007 (06/11/2026): project đang ở 6 migration, chưa có bảng `app_private.departments` hoặc cột `positions.department_id`, có 0 vị trí và không có tác vụ `PENDING`/`PROCESSING`. Lần áp đầu bị PostgreSQL từ chối và rollback vì dùng `COMMENT ON TABLE` cho view `public.departments`; file migration đã đổi sang `COMMENT ON VIEW` rồi áp thành công ở version `20261106050756`. Postflight xác nhận bảng phòng ban có 8 cột, `positions` có `department_id`/`department_sequence`, các view `public.departments`/`public.positions` phơi đúng cột mới và hiện có 0 phòng ban. Backend mới phụ thuộc 00007 để Admin quản lý phòng ban và để HR tạo vị trí với mã tự sinh theo `code_format` của phòng ban; Admin phải tạo ít nhất một phòng ban đang hoạt động trước khi HR tạo vị trí.

Preflight trước 00008 (07/11/2026): project đang ở 7 migration, chưa có `assessment_fingerprint` hoặc policy `assessment-v2.0`, không có tác vụ `PENDING`/`PROCESSING` và có 4 assessment đã hoàn tất. Đã áp thành công ở version `20261107012433`. Postflight xác nhận `assessment_runs` có 4 cột fingerprint/policy/prompt/provider snapshot, `criterion_assessment_results` có 4 cột decision/evidence, policy `assessment-v2.0` tồn tại. Backend matching mới phụ thuộc 00008; quy trình đo độ ổn định và golden set nằm ở [doc/MATCHING_STABILITY.md](doc/MATCHING_STABILITY.md).

Preflight trước 00009 (07/11/2026): project đang ở 8 migration và `app_private.criteria_items` chưa có `requirement_spec`. Đã áp thành công ở version `20261107021622`; postflight xác nhận cột `requirement_spec` có kiểu `jsonb`. Backend hiện tại đọc cột này trong worker/API tiêu chí, vì vậy không deploy code sau 00009 lên database chưa có migration này.

Preflight trước 00010 (07/11/2026): project đang ở 9 migration, chưa có extension `vector`, bảng `cv_chunk_embeddings`/`ltr_model_versions` hoặc các cột LTR trên ranking. Đã áp thành công ở version `20261107022845`; postflight xác nhận extension `vector`, cột `cv_chunk_embeddings.embedding` kiểu `vector`, HNSW cosine index, RLS trên hai bảng mới, `ranking_runs.ltr_model_version`, `ranking_runs.ltr_mode` và `ranking_items.ltr_score`. Backend hiện tại ghi/đọc các cột LTR khi tạo và đọc ranking, kể cả khi LTR tắt, nên database đích phải có 00010 trước khi rollout code này.

Preflight trước 00011 (07/11/2026): registry LTR chưa có artifact hash hoặc review history. Đã áp thành công ở version `20261107133211`; postflight xác nhận `ltr_model_versions` có `artifact_sha256`, `registered_by`, `reviewed_by`, `reviewed_at`, `review_reason`, bảng `app_private.ltr_model_review_events` tồn tại và RLS đang bật trên cả hai bảng. Backend/API phê duyệt LTR mới phụ thuộc 00011; không rollout API admin LTR lên database chưa có migration này.

Preflight trước 00012 (07/11/2026): project đang ở 11 migration, có 21 audit events, 0 retention/deletion rows, 0 operation `PENDING`/`PROCESSING`, đã có `pgcrypto` và chưa có cột/trigger của `00012`. Đã áp thành công ở version `20261107142027`; postflight xác nhận đủ 3 cột hash audit, 2 cột retention mới, 2 trigger audit, RLS bật trên 4 bảng liên quan, 21/21 audit events có hash và 0 broken event. Không rollout API `/v1/retention` hoặc endpoint `/v1/admin/audit/verify` lên database chưa có `00012`. Quy trình áp dụng và vận hành nằm ở mục “Retention và audit integrity (migration 00012)” bên dưới.

Schema ban đầu trên project này có một số cột AI đã tồn tại trước 00004; không giả định nội dung mọi version remote byte-for-byte giống file local. Không chạy `supabase db push`/reset mù quáng: version remote là timestamp, khác tiền tố file local. Với project/môi trường khác, đối chiếu migration thực tế, xin phê duyệt và làm staging/drain riêng theo checklist dưới đây. Hướng dẫn dựng VPS Ubuntu với Docker Compose, Nginx, TLS và vận hành: [doc/VPS_DEPLOYMENT.md](doc/VPS_DEPLOYMENT.md).

## Checklist khi áp 00004 vào môi trường khác hoặc triển khai worker mới

1. **Thu hồi/rotate service-role key từng xuất hiện trong lịch sử Git — trạng thái 05/11/2026:** key legacy `service_role` JWT từng commit trong `backend/.env.example` vẫn còn là **legacy key đang bật** trên project `myrymlqdbyqmpynesiwk` (cùng với `anon` JWT). Project đã có sẵn cặp key mới `sb_publishable_*`/`sb_secret_*` (type `publishable`/`secret`, prefix `sb_publishable_z2Ynu`/`sb_secret_rLbWw`) nhưng **chưa deactivate legacy** và **chưa revoke legacy JWT secret**. Tạo secret mới riêng lẻ không tự thu hồi legacy; nếu bật lại legacy, key lộ sẽ sống lại. Thu hồi trọn vẹn theo docs Supabase cần: (a) tạo/đổi sang dùng `sb_publishable_`/`sb_secret_` ở mọi client/backend/worker/pipeline/mobile đã lưu key cũ, (b) deactivate legacy `anon`+`service_role` cùng lúc (Dashboard **Settings → API Keys → Legacy API keys → Deactivate**, hoặc Management API `PUT /v1/projects/{ref}/api-keys/legacy?enabled=false`), (c) migrate JWT signing keys sang asymmetric và **revoke legacy JWT secret** (Dashboard **Auth → Signing Keys** hoặc Management API) — legacy JWT vẫn còn hiệu lực nếu chỉ tắt API key mà chưa revoke secret. Backend hiện tại verify token theo `alg`: asymmetric/JWKS (ví dụ `ES256`) qua `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, đồng thời còn hỗ trợ `HS256` bằng `SUPABASE_JWT_SECRET` cho token legacy trong thời gian chuyển đổi. Mọi backend phải được nâng cấp/restart đồng nhất trước khi revoke legacy JWT secret; backend bản cũ chỉ biết `HS256` sẽ không verify được token asymmetric. Chặn token cũ đã đăng nhập dựa trên `tokens_valid_after`/`iat` chỉ có tác dụng trong API app, không thay thế việc revoke ở Supabase. Không gửi key vào frontend, Git hay chat; đổi secret trong secret manager, rà soát log/client/phạm vi phơi lộ và drain worker cũ trước khi deactivate. Connector hiện tại không có thao tác disable legacy, nên bước deactivate/revoke phải làm thủ công trên Dashboard/Management API và được kiểm chứng qua `GET /v1/projects/{ref}/api-keys/legacy` hoặc `list_api_keys`.
2. Sao lưu, thử restore, thử migration và kịch bản crash/recovery trên staging có schema và storage tương đương; rà soát ứng dụng dùng view/grant trực tiếp. Kiểm tra lịch sử migration thực tế và lập phương án rollback đã phê duyệt. 00004 thêm cột operations/config/profile, view, bảng ghi chú HR và sự kiện recovery, RLS/grant cùng unique index cho cấu hình AI ACTIVE; dữ liệu cũ có nhiều ACTIVE cần được xử lý theo kế hoạch được duyệt **trước** khi tạo index.
3. Tạm ngừng nhận job mới tại gateway/UI, cho công việc đang chạy hoàn thành nếu có thể, sau đó dừng/drain **tất cả** API/worker phiên bản cũ. Worker được nhúng trong mỗi process API; bản cũ không dùng advisory lock và có thể ghi đồng thời với worker mới. Không chạy mixed-version workers trong/ sau migration.
4. Kết nối PostgreSQL có **session thực được giữ liên tục** trong suốt một attempt; khuyến nghị direct connection. Không dùng PgBouncer transaction/statement pooling: backend PID hoặc advisory session lock có thể đổi sau mỗi transaction. Nếu dùng pooler session mode, chỉ dùng sau khi đã xác minh độc lập khả năng pin cùng backend PID và lock trong suốt attempt, failover và timeout. Kiểm soát TLS và network ở môi trường cloud.
5. Sau phê duyệt, áp migration qua quy trình versioning của môi trường. Xác nhận bảng/cột/index/grant, cấu hình AI hợp lệ, access riêng tư của notes, backend health và staging smoke HR/HM với dữ liệu tổng hợp. Chỉ sau đó khởi động đồng nhất API/worker phiên bản mới, theo dõi queue rồi mở nhận job. Nếu cần rollback, dừng/drain worker mới trước và làm theo kế hoạch đã thử; không để worker cũ chạy trên job đang do worker mới xử lý.

Ví dụ preflight chỉ đọc (không tự sửa dữ liệu):

```sql
SELECT status, count(*) FROM app_private.ai_configuration_versions GROUP BY status;
SELECT capability, status, count(*) FROM app_private.operations GROUP BY capability, status;
SELECT has_schema_privilege('authenticated', 'app_private', 'USAGE') AS authenticated_private_usage,
       has_table_privilege('authenticated', 'public.applications', 'SELECT') AS authenticated_applications_select,
       has_schema_privilege('service_role', 'app_private', 'USAGE') AS service_private_usage;
-- Sau 00003 kỳ vọng: false, false, true. Đối chiếu mọi bảng/view cần dùng, không chỉ ví dụ.
```

## Storage và privacy

- Giữ `cv-originals` và `cv-extracted-text` **private**; upload/download đi qua backend kiểm tra quyền. Không cấp policy trực tiếp cho HM chỉ dựa trên assignment: có thể bỏ qua `allow_cv_view=false`. Kiểm tra và xử lý policy cũ theo phạm vi được phê duyệt. Code hiện tại chỉ cấp nội dung CV qua endpoint backend có xác thực và audit, không phát signed URL mới. Các link do phiên bản cũ đã cấp vẫn có thể hoạt động tới hết TTL (10 phút), kể cả sau deploy/thu hồi; chỉ tính sau khi đã drain mọi backend cũ. File/preview đã tải về không thể thu hồi.
- CV gốc vẫn được lưu để người có quyền xem. Trước mỗi cuộc gọi AI, code che theo regex các identifier/thuộc tính nhạy cảm phổ biến, hạn chế profile có cấu trúc và thêm system guardrails; extracted text mới cũng lưu bản đã che. Đây là **best effort, không phải ẩn danh hoặc bảo đảm không rò rỉ**: tên không nhãn, địa chỉ, dữ liệu nhạy cảm viết tự do, OCR và biến thể ngôn ngữ có thể bị bỏ sót; che nhầm cũng có thể làm mất bằng chứng. Prompt không bảo đảm loại bỏ prompt injection hoặc bias.
- Cần đánh giá DLP/NER, chính sách retention, hợp đồng xử lý dữ liệu, kiểm thử bảo mật/bias và kiểm soát mạng độc lập trước khi xử lý hồ sơ thật. Chỉ gửi dữ liệu tới dịch vụ/model đã được phê duyệt; ưu tiên local. Ghi chú riêng HR không được truyền vào profile/prompt, nhưng không thay thế chính sách truy cập/log của toàn hệ thống.
- SQLAlchemy ẩn bound parameters, worker tránh ghi CV/prompt/exception raw, nhưng hệ điều hành, proxy, model provider, OCR và dịch vụ khác vẫn cần được rà soát logging, quyền, mã hóa và backup. Từ Batch 5, code đã có workflow retention/xác nhận xóa và audit hash chain/append-only trigger; migration `00012` đã áp/postflight đạt trên project đã kết nối, nhưng workflow chỉ được coi là đang vận hành khi backend chứa code Batch 5 được deploy và smoke test qua Supabase Auth/Storage.

## Cấu hình AI và egress

- Backend/worker đọc `LLM_PROVIDER`, `LLM_PROVIDER_NAME`, `LLM_MODEL_NAME`, `LLM_API_BASE`, `LLM_API_KEY`, `LLM_TEMPERATURE_DEFAULT`, `LLM_SEED` (tùy chọn, chỉ khi provider hỗ trợ), `LLM_ALLOWED_MODELS`, `LLM_ALLOWED_API_BASES`, `ALLOW_EXTERNAL_API` và `AI_CONFIG_ENCRYPTION_KEY` từ environment khi khởi động. Hai allowlist là **JSON arrays**; model/endpoint mặc định cũng được tự đưa vào allowlist. Cấu hình, secret và chính sách phải nhất quán giữa tất cả process API/worker; thay env/secret cần rollout/restart theo quy trình.
- Với các lựa chọn `local`, `openai`, `azure`, Admin vẫn chỉ tạo/kích hoạt version nằm trong allowlist môi trường. Riêng nhà cung cấp **OpenAI Compatible** (`provider=compatible`), Admin nhập **tên nhà cung cấp** (`provider_name`), **Base URL**, **API Key** và **Model** tự do; backend chuẩn hóa Base URL, kiểm tra chính sách egress, mã hóa API key bằng Fernet trước khi lưu vào `api_key_ciphertext`, và chỉ trả về `api_key_configured` cùng hint 4 ký tự cuối. API key không xuất hiện trong response danh sách/chi tiết, audit, log hoặc `ai_config_snapshot`; snapshot tác vụ chỉ chứa cấu hình công khai và worker nạp lại ciphertext theo `config_id` trong bộ nhớ khi chạy/phục hồi. Nếu đổi chỉ tên/model/temperature tại **cùng Base URL**, backend tái sử dụng ciphertext của cấu hình ACTIVE; không sao chép key sang Base URL khác.
- `AI_CONFIG_ENCRYPTION_KEY` là khóa Fernet chỉ nằm trong môi trường backend. Chưa đặt khóa này thì giao diện vẫn mở nhưng backend từ chối lưu API key mới bằng lỗi 503. Việc rotate khóa làm các API key đã lưu không giải mã được; khi đó phải tạo phiên bản OpenAI Compatible mới và nhập lại key. Không commit, log hoặc gửi khóa mã hóa/API key qua chat.
- Trước khi tạo/kích hoạt, Admin bấm **Test kết nối** để backend gửi một prompt kiểm tra tối thiểu tới Base URL/model đang nhập. Test không lưu cấu hình, không dùng dữ liệu ứng viên, không ghi API key và trả về trạng thái HTTP, latency, model nhà cung cấp trả về nếu có; lỗi 401/403 thường là sai API key/quyền, 404 thường là sai Base URL/model, timeout/connection error thường là backend không tới được endpoint hoặc `ALLOW_EXTERNAL_API` chưa bật với endpoint public.
- Admin tạo và kích hoạt version qua API kiểm tra role/account và policy, kích hoạt atomic, ghi audit không chứa secret. Job ghim snapshot cấu hình công khai ở attempt đầu và dùng lại khi phục hồi; tác vụ mới dùng version active. Assessment tái sử dụng kết quả `COMPLETED` có cùng fingerprint (CV/profile/rubric/runtime/prompt/policy); đổi model không tự đánh giá lại, nhưng lần chạy HR yêu cầu sau đó sẽ dùng fingerprint mới nếu runtime đã đổi. Cấu hình built-in bị loại khỏi allowlist sẽ fail closed; cấu hình OpenAI Compatible tùy chỉnh không bị khóa bởi allowlist model/endpoint nhưng vẫn fail closed theo chính sách mạng. Giao diện health chỉ cho biết policy của process trả lời, không chứng minh model hoạt động.
- Tất cả nhãn `local`, `compatible`, `openai`, `azure` dùng **cùng** endpoint OpenAI-compatible `POST /chat/completions`, JSON và `Authorization: Bearer` khi có key. Runtime ưu tiên API key đã lưu của chính phiên bản cấu hình; `LLM_API_KEY` của môi trường chỉ dùng cho runtime môi trường hoặc cấu hình DB trỏ đúng endpoint mặc định của môi trường, không tự gửi sang Base URL tùy chỉnh khác. Không hỗ trợ trực tiếp Azure API native `api-key`/`api-version`, deployment path hoặc xác thực riêng; chỉ dùng Azure qua gateway tương thích đã phê duyệt.
- `ALLOW_EXTERNAL_API=false` mặc định chỉ cho endpoint phân giải thành địa chỉ private/loopback. Khi cho phép endpoint public, HTTP client yêu cầu HTTPS; URL không được chứa credential/query/fragment, client không dùng proxy từ environment. Muốn dùng Base URL public như `https://api.openai.com/v1` qua OpenAI Compatible, người vận hành phải chủ động đặt `ALLOW_EXTERNAL_API=true` và phê duyệt egress. Kiểm tra DNS trước request **không pin DNS** và allowlist không thay thế firewall/egress proxy, TLS nội bộ, DLP, phê duyệt và giám sát. Không bật external chỉ để demo.

## Semantic retrieval, BGE và Learning-to-Rank

**Sau migration `00019`, database là công tắc BGE/LTR của worker mới**, mặc định OFF. Các biến `SEMANTIC_RETRIEVAL_ENABLED`, `ALLOW_MANAGED_BGE_ROUTING`, `ALLOW_MANAGED_LTR_ROUTING`, `LTR_MODE` không còn tắt/bật worker mới; không dựa vào chúng để rollback. Dừng/drain toàn bộ HRA API/worker cũ, không mixed-version, backup/restore và theo [AI_ADMIN_ROUTING_STATUS.md](doc/AI_ADMIN_ROUTING_STATUS.md) trước rollout/rollback. Migration `00019` đã áp project test `myrymlqdbyqmpynesiwk` dưới version `20261112081935`; người dùng báo code `5f5c529` đã deploy trên VPS test, hai process HRA restart, readiness và smoke tests pass. Chưa xác minh E2E, provider hoặc CV thật.

- Admin bật/tắt chuỗi BGE đã duyệt; `ALLOW_EXTERNAL_API` và policy egress vẫn được áp dụng độc lập trên API và từng worker. Endpoint public yêu cầu HTTPS. Key write-only được mã hóa. BGE 1024 chiều; các route có cache riêng, lỗi về lexical. OFF không hủy các lượt semantic đã qua kiểm tra và đang chạy.
- LTR OFF/SHADOW/ACTIVE quản trị từ database. ACTIVE cần model đã approve/gates/hash, một ranking SHADOW có điểm với đúng artifact, lý do và xác nhận chất lượng thực tế/rollback. Các điều kiện kỹ thuật tối thiểu không chứng minh HR gold hoặc phê duyệt pilot. OFF chờ publication đang giữ khóa; ranking đã xuất bản không đổi.
- Status UI là database intent, không phải liveness hoặc xác minh từng worker/provider. Đồng bộ policy, ngưỡng model và khóa mã hóa; thử bằng dữ liệu tổng hợp đã phê duyệt trước. Không dùng dữ liệu thật, không bật chỉ để demo.
- Các hướng dẫn env legacy ở tài liệu lịch sử không áp dụng cho worker mới; nếu rollback code cũ, drain và chặn egress trước, đặt env legacy an toàn cho mọi process, rồi mới cho chạy lại code cũ.

## Retention và audit integrity (migration 00012)

### Trước khi áp migration

1. Xác nhận môi trường đích đã có các migration tới `00011`, extension `pgcrypto` khả dụng và không có operation `PENDING`/`PROCESSING` cần drain theo checklist migration chung.
2. Sao lưu database và thử restore trên staging; ghi lại số lượng `app_private.audit_events`, retention cases, deletion jobs/events hiện có. Migration sẽ backfill hash chain cho audit events hiện hữu theo `created_at, event_id`, vì vậy cần cửa sổ bảo trì và thời gian tỉ lệ với số audit rows.
3. Không dùng dữ liệu/CV thật để smoke test nếu EXT-1/EXT-2 chưa đóng. Chuẩn bị dữ liệu tổng hợp: một position đã đóng quá hạn, một application có CV/extracted text/profile/assessment, một Admin và một HR Lead/HR có grant `CONFIRM_DELETION`.

### Sau khi áp migration

1. Đối chiếu lịch sử migration của môi trường và xác nhận các cột `chain_sequence`, `previous_event_hash`, `event_hash` trên `app_private.audit_events`; các cột `position_id`, `application_opaque_id` trên retention/deletion tables; trigger `audit_events_set_hash`, `audit_events_append_only`; RLS/grant chỉ cấp cho `service_role` qua public views.
2. Gọi `GET /v1/admin/audit/verify` bằng tài khoản Admin. Kỳ vọng `valid=true`; endpoint chỉ trả số lượng và mã sự kiện lỗi đầu tiên, không trả metadata audit. Nếu `valid=false`, dừng rollout retention, giữ nguyên hiện trạng và điều tra bằng quyền DBA; không sửa tay audit row để “làm xanh”.
3. Smoke test retention bằng dữ liệu tổng hợp theo thứ tự: tạo case cho position đã đóng quá hạn → xác nhận bởi người có quyền → execute một case → kiểm tra file gốc, `extracted.txt`, `pages.json`, profile/assessment/evidence/ranking/shortlist/embeddings/notes đã bị xóa hoặc unlink; retention case/deletion job/event còn lại chỉ chứa opaque ID và counts.
4. Kiểm tra các trường hợp âm tính: hồ sơ chưa đến hạn không xác nhận được; người chỉ có quyền xem không xác nhận/execute được; storage lỗi thì job `FAILED` và database chưa bị purge; update một audit row qua application/service role bị trigger chặn.

### Vận hành hằng ngày

- Không có job tự động xóa hàng loạt. HR tạo case khi position đã qua hạn; người có thẩm quyền xác nhận và thực thi từng case. Case đã hủy có thể được tạo lại khi chạy generate lần nữa; case đang mở hoặc đã xóa không tạo trùng.
- Audit hash chain là cơ chế **tamper-evidence**, không phải bằng chứng chống DB superuser: người có quyền hạ tầng vẫn có thể disable trigger, truncate hoặc restore backup cũ. Bù lại bằng phân quyền DBA tối thiểu, backup/WORM log ngoài hệ thống nếu pháp chế yêu cầu và kiểm tra `audit/verify` định kỳ.
- Nếu storage đã xóa nhưng DB purge lỗi, job được đánh dấu `FAILED`; retry coi file thiếu là đã vắng. Không sửa trực tiếp DB để đánh dấu hoàn tất; khảo sát lỗi, bảo đảm case vẫn `SCHEDULED_FOR_DELETION`, rồi execute lại qua API.

## Phục hồi worker và giám sát

Mỗi attempt giữ PostgreSQL session-level advisory lock, backend PID và token; worker xác minh fencing trước commit. Heartbeat chỉ là tín hiệu, **không phải lease** cho phép worker khác cướp job. Worker mới tự nhận job `PROCESSING` nếu lock cũ được giải phóng; cột `attempt_count`/`recovery_count`, heartbeat và event recovery được cập nhật. Hàng đợi quét theo trang để không bị kẹt sau 100 lock sống. Test cục bộ đã mô phỏng process crash, hai worker, mất DB connection, khôi phục lô và kiểm tra metric; vẫn cần diễn tập staging với topology thực.

1. Theo dõi `/v1/admin/worker/health` (chỉ ADMIN): pending, processing, heartbeat quá 2 phút, chạy quá 30 phút, thất bại/khôi phục 24 giờ và pending lâu nhất. `recoveries_24h` đếm **sự kiện còn lưu** được ghi từ khi có 00004; không backfill được lịch sử cũ, và xóa operation cũng xóa event. Thiết lập cảnh báo và liveness/monitoring bên ngoài: endpoint này **không chứng minh worker còn sống**.
2. Khi heartbeat cũ hoặc hàng đợi không tiến triển, xác minh log, process, DB connection và job với on-call; không tự reset `PROCESSING`, không dựa riêng vào thời gian. Session DB còn sống có thể giữ lock ngay cả khi worker treo hoặc mạng partition, do đó recovery có thể chậm đến khi PostgreSQL phát hiện session chết.
3. Nếu cần can thiệp, dừng worker/process đã xác minh theo quy trình, đánh giá ảnh hưởng các job khác; DBA chỉ kết thúc session PostgreSQL đã xác minh chính xác sau phê duyệt, không kill hàng loạt. Khi lock được giải phóng, worker mới nhận lại job và cập nhật attempt/event. Theo dõi tới trạng thái cuối, đối chiếu batch, assessment/ranking và phản hồi HR. Không dùng công cụ SQL để chiếm thử advisory lock trên hệ thống đang chạy nếu không hiểu và giải phóng lock.
4. Recovery là **at-least-once**, không exactly-once: cuộc gọi model có thể bị lặp và tính phí/lưu log nhiều lần. Kết quả DB được fencing/reconcile, nhưng storage có thể còn object orphan ở các attempt khác nhau. Với `cv-extracted-text`, `extracted.txt` và `pages.json` nằm trong thư mục token attempt; tham chiếu hiện hành nằm ở `document_processing_runs.extracted_text_storage_path`. Chỉ đối soát/thu gom sau thời gian chờ an toàn, backup, xác minh cả object cặp, mọi tham chiếu và job còn sống; dry-run, review thủ công, không xóa mù. CV gốc cũng cần đối soát `application_documents.storage_path` riêng.
5. Với job thất bại thực sự, khảo sát nguyên nhân (storage, model, quyền, network), khôi phục dịch vụ và dùng quy trình nghiệp vụ được phê duyệt để chạy lại. Không sửa trực tiếp DB hoặc tự coi kết quả AI là quyết định tuyển dụng.

## Khởi chạy phát triển

- `DATABASE_URL` chỉ backend/worker, có quyền SQL cần thiết trên `app_private` và SELECT các cột `id`, `email` của `auth.users` để quản lý tài khoản; không cấp cho browser. `SUPABASE_URL`, `SUPABASE_ANON_KEY` dùng cho Supabase Auth backend. API kiểm tra audience `authenticated` và tự chọn cách verify theo `alg`: JWKS/issuer suy ra từ `SUPABASE_URL` cho token bất đối xứng, hoặc `SUPABASE_JWT_SECRET` cho token HS256 legacy. `SUPABASE_SERVICE_ROLE_KEY` chỉ backend/worker và bắt buộc khi tạo tài khoản và dùng Storage Supabase.
- `ADMIN_BOOTSTRAP_TOKEN` mặc định rỗng. Chỉ đặt token ngẫu nhiên đủ mạnh trong thời gian ngắn để khởi tạo Admin đầu tiên qua HTTPS/mạng hạn chế, sau đó xóa khỏi mọi backend và restart. Cơ chế one-time vẫn đóng sau khi Admin bị xóa/khóa; xem runbook ở [hướng dẫn VPS](doc/VPS_DEPLOYMENT.md#7-bootstrap-người-dùng-và-smoke-test). Không gửi secret/password trong chat hoặc log.
- Frontend gọi `/v1` cùng origin và Next proxy tới `API_INTERNAL_URL` phía server; không đưa địa chỉ backend localhost vào mã browser. Compose dùng `http://backend:8000`. Local Storage chỉ cho phát triển, cần backup/bảo vệ volume.

```bash
# Sau khi chuẩn bị DB, các migration được phê duyệt và backend/.env an toàn:
cd backend
python -m venv .venv
.venv/bin/python -m pip install --upgrade "pip>=26.2" "setuptools>=84.1.0"
.venv/bin/pip install -e .
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
cd frontend
cp .env.local.example .env.local # API_INTERNAL_URL đến backend
npm ci
npm run dev
```

`/health` là liveness, `/health/ready` chỉ kiểm tra database, không chứng minh Storage/AI. Đăng nhập cần user Supabase active và role/assignment. Compose (`cp .env.example .env`, điền secret an toàn, `docker compose up --build`) không tạo PostgreSQL/Supabase/LLM; worker chạy trong API. Docker/Compose chưa kiểm thử ở đây.

## Việc còn chặn production

Hoàn thành kiểm thử staging/e2e Auth/Storage/LLM/OCR với dữ liệu được phép; đánh giá chất lượng và bias, egress/DLP, retention/xóa, audit bất biến, bảo vệ session/XSS (`localStorage` đang chứa access token), DR/monitoring và phê duyệt pháp lý/bảo mật. Python dependencies chưa lock; cần quản lý chuỗi cung ứng và quét image định kỳ. Ngày 05/11/2026, `npm audit --omit=dev` báo 0 lỗ hổng; audit đầy đủ báo 6 moderate trong chuỗi dev-only `@typescript-eslint`/`minimatch`, cần theo dõi bản vá tương thích. Kết quả audit dependencies chỉ phản ánh thời điểm quét, không chứng minh image triển khai an toàn.

Riêng semantic/LTR: chưa có BGE endpoint thật, chưa đo chất lượng embedding trên golden set HR và chưa có HR labelled dataset đủ lớn. Đây là các điều kiện chặn trước khi bật BGE hoặc LTR ACTIVE bằng database/UI trong môi trường dùng dữ liệu thật.

**Cloudflare evidence reranker:** migration `00020_reranker_controls.sql` is required before deploying the reranker code; it defaults OFF. It was applied to test project `myrymlqdbyqmpynesiwk` as Supabase migration `20261112094826`, with operator approval and without a separate backup. Reranker remains OFF; the new code has not yet been verified on the VPS. For any other database, obtain explicit migration/backup approval. Drain HRA processes, avoid mixed worker versions, and follow [CLOUDFLARE_EVIDENCE_RERANKER.md](doc/CLOUDFLARE_EVIDENCE_RERANKER.md). This is separate from BGE embedding and LTR. Never enable or send real CV/JD data without the appropriate destination and privacy approval.

**LLM pricing and redesigned administration:** migration `00021_llm_prices_and_usage.sql` is required before deploying this code. It was applied to test project `myrymlqdbyqmpynesiwk` as Supabase migration `20261113031442`; no separate backup was created or independently verified for this application. It adds nullable versioned prices and best-effort usage estimates; it does not change the active provider or backfill costs. The new code has not yet been verified on the VPS. For other databases follow their authorization and backup/restore requirements; drain HRA processes before rollout. See [LLM_ADMIN_COSTS.md](doc/LLM_ADMIN_COSTS.md) for limits and retention considerations.

The operator reports deploying the reranker on the test VPS and a successful deploy smoke test; the deployed commit and worker behavior remain unverified. The operator subsequently reported a single synthetic Cloudflare reranker request PASS (3 contexts; 3159 ms); it did not change runtime controls and is not a quality or end-to-end benchmark. See [CLOUDFLARE_EVIDENCE_RERANKER.md](doc/CLOUDFLARE_EVIDENCE_RERANKER.md) for the separately authorized synthetic-only provider check and [MATCHING_BENCHMARK_AND_PRIVACY.md](doc/MATCHING_BENCHMARK_AND_PRIVACY.md) for gold-data and approval prerequisites.
