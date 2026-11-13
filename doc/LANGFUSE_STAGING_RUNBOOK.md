# Runbook triển khai và kiểm thử Langfuse staging

> Trạng thái: tích hợp code chuẩn bị, mặc định OFF; chưa chọn/duyệt host, project, dữ liệu hoặc egress. Không bật hay chạy smoke gửi trace thật trước khi có phê duyệt riêng. Client yêu cầu `LANGFUSE_BASE_URL` hoặc `LANGFUSE_HOST` tường minh; không dùng mặc định cloud ngầm. Metadata, ID và hash vẫn có thể là dữ liệu cá nhân; lọc theo tên khóa không phải bảo đảm ẩn danh.

> Tài liệu vận hành cho LF-2/LF-3. Tài liệu này **không** mở gate môi trường; chỉ khi DEP-01 có quyết định ký duyệt thì staging mới được phép bật Langfuse.

## 1. Gate bắt buộc trước khi chạy

Không bắt đầu smoke staging nếu thiếu bất kỳ mục nào:

- [ ] `doc/PENDING_DEPLOYMENT.md` phần DEP-01 đã có environment mapping đã ký: backend, frontend, PostgreSQL, storage, Langfuse project và Langfuse host được đối chiếu cụ thể.
- [ ] Đã chọn Langfuse Cloud project riêng cho staging hoặc Langfuse self-host; không dùng project production.
- [ ] Đã phê duyệt privacy/egress: chỉ metadata tổng hợp, không CV/JD/prompt/output/quote/reasoning/secret. `LANGFUSE_CAPTURE_CONTENT` giữ `false`.
- [ ] Đã xác thực retention, RBAC, backup/restore của Langfuse staging; retention không mặc định là xóa.
- [ ] Chỉ dùng dữ liệu tổng hợp cho tới khi có phê duyệt riêng cho dữ liệu thật.
- [ ] Có người chịu trách nhiệm vận hành và kế hoạch rollback.

Nếu dùng Langfuse self-host: nó là hệ thống riêng gồm Langfuse web/worker và PostgreSQL, Redis/Valkey, ClickHouse, object storage/blob. Không nhúng Langfuse vào stack app đơn giản như một container phụ.

## 2. Biến môi trường staging

**Cảnh báo:** Nếu đã đặt `LANGFUSE_ENABLED=true` trong `.env`, sau khi API/worker
nạp cấu hình và có tác vụ, trace có thể được gửi tự động, không chỉ khi chạy smoke.
Giữ `LANGFUSE_ENABLED=false` ở cả API/worker cho đến khi đích Cloud và phạm vi
metadata/egress được duyệt; không restart/deploy vào môi trường đang có dữ liệu
thật chỉ để kiểm tra. Việc khai báo key không chứng minh các tiến trình đã nạp cấu
hình, và endpoint health chỉ phản ánh tiến trình API phục vụ request.


```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=<public-key-staging>
LANGFUSE_SECRET_KEY=<secret-key-staging>
# Host Cloud hoặc base URL self-host phê duyệt:
LANGFUSE_BASE_URL=https://<langfuse-staging-host>
LANGFUSE_ENVIRONMENT=staging
LANGFUSE_RELEASE=<commit-sha>
LANGFUSE_SAMPLE_RATE=1.0
LANGFUSE_CAPTURE_CONTENT=false
```

Quy tắc an toàn:

- Secret chỉ lấy từ secret manager của staging; không commit, không gửi qua chat, không ghi vào nhật ký.
- `LANGFUSE_CAPTURE_CONTENT=false` là mặc định bắt buộc; không đổi sang `true` trên Cloud. Nếu cần capture content cho debug có kiểm soát, chỉ self-host, dữ liệu tổng hợp, thời gian ngắn và có phê duyệt.

## 3. Kiểm tra không gửi

Trên backend staging, từ thư mục `backend`:

```bash
python scripts/langfuse_smoke.py
```

Kết quả mong đợi sau khi đã được duyệt bật: `enabled=true`, `configured=true`, `sdk_available=true`, environment `staging`, không lộ secret. Đây chỉ là trạng thái cấu hình của tiến trình script; không xác thực key, kết nối hay chứng minh API/worker đã nạp cùng cấu hình.

Kiểm tra API health (cần tài khoản Admin):

```text
GET /v1/admin/langfuse/health
```

Kết quả chỉ chứa trạng thái cấu hình an toàn, không chứa khóa.

## 4. Gửi trace tổng hợp kiểm thử

Chỉ khi gate mục 1 đã mở:

```bash
python scripts/langfuse_smoke.py --send
```

Sau đó kiểm tra trên Langfuse staging UI:

- Tìm trace `hra.langfuse.smoke`.
- `environment` là `staging`.
- Metadata smoke có `synthetic=true`, `smoke_test=true`.
- Observation `hra.langfuse.smoke` có input summary (hash/độ dài khi capture tắt) và output trạng thái tổng hợp; không có nội dung nhạy cảm.
- Score boolean `smoke_test=true` xuất hiện. Script fail-open và dòng báo gửi không chứng minh Langfuse đã nhận; phải kiểm tra UI.

## 5. Kiểm tra workflow tổng hợp một vòng

1. Tạo một vị trí và đơn ứng tuyển dùng CV/JD tổng hợp.
2. Chạy đường CV batch hoặc API hoàn chỉnh tùy theo deployment staging đã phê duyệt.
3. Kiểm tra Langfuse có các observation chính theo thứ tự:
   - `hra.worker.operation`
   - `hra.cv.document_extraction`
   - `hra.assessment`
   - các generation `hra.llm.*`
   - `hra.assessment.deterministic_matching`
   - `hra.assessment.semantic_retrieval` khi có tiêu chí chưa quyết định được bằng luật
   - `hra.embedding.bge` khi semantic fallback gọi BGE
   - `hra.assessment.evidence_verification`
   - `hra.assessment.scoring`
   - `hra.ranking.generate`
4. Đối chiếu `assessment_id`, `operation_id`, `assessment_fingerprint` với PostgreSQL. PostgreSQL vẫn là nguồn sự thật; Langfuse chỉ là tuyến quan sát.
5. Đối chiếu scores: `matching_score`, `evidence_coverage`, `needs_verification`, `rule_decided_count`, `llm_decided_count`, `evidence_verified_rate`.

## 6. Kiểm tra evaluation repeatability

Từ snapshot không chứa CV/quote:

```bash
python scripts/evaluate_matching.py snapshot.json
# Dry-run: chỉ tính report và liste scores dự kiến
python scripts/push_langfuse_evaluation.py snapshot.json --run-name <evaluation-label>
# Chỉ khi gate đã mở:
python scripts/push_langfuse_evaluation.py snapshot.json --run-name <evaluation-label> --send
```

Kiểm tra Langfuse có trace `hra.evaluation.repeatability`, scores `repeatability_*`, `criterion_flip_rate`, `fingerprint_reuse_rate`, `ranking_kendall_tau` và `repeatability_passed`. Không gửi snapshot thô hoặc danh sách application raw kèm theo.

## 7. Kiểm tra fail-open và latency

1. Tạm thời dùng Langfuse host không tới được trong môi trường kiểm thử có kiểm soát.
2. Chạy lại flow tổng hợp: nghiệp vụ không được fail vì Langfuse.
3. Đối chiếu application log và latency; nếu timeout/latency vượt ngân sách của staging, tắt sampling hoặc giảm `LANGFUSE_SAMPLE_RATE` trước, sau đó tắt hẳn nếu cần.

## 8. Rollback

Rollback ngay nếu có dữ liệu nhạy cảm trong Langfuse, hard failure do quan sát, hoặc latency vượt ngân sách:

1. Đặt `LANGFUSE_ENABLED=false`.
2. Restart/redeploy backend/worker staging.
3. Xác nhận `/v1/admin/langfuse/health` báo `enabled=false`.
4. Xem xét xóa trace đã gửi nhầm trong Langfuse staging theo chính sách đã phê duyệt.
5. Không cần rollback migration hoặc dữ liệu nghiệp vụ, vì Langfuse không giữ state nghiệp vụ.

## 9. Tiêu chí đóng LF-2/LF-3

- [ ] Smoke synthetic đã gửi và xem được trên staging.
- [ ] Một workflow tổng hợp đã có trace đầy đủ, không chứa nội dung nhạy cảm.
- [ ] Evaluation bridge đã đẩy score aggregate lên staging và đối chiếu được với report JSON.
- [ ] Kiểm chứng fail-open và rollback đã thực hiện.
- [ ] Kết quả, commit/release, dashboard/score names và bằng chứng được ghi vào `Update_Excute_P2.md`.


## Đối chiếu skill Langfuse và kiểm thử offline

Skill `langfuse` được cài trong `.agents/skills/langfuse`, pin theo `UPSTREAM.txt` (MIT). Code dùng SDK Python v4 (`langfuse>=4,<5`); không tự nâng major version chỉ vì skill đề xuất latest. SDK 4.18.0 đã được kiểm thử bằng exporter OpenTelemetry trong bộ nhớ, không gửi mạng. Một generation được tạo cho từng lần gọi/retry; usage an toàn được ghi ngay khi provider trả JSON, kể cả khi output JSON lỗi. Error chỉ ghi loại exception: wrapper không chuyển exception message/stack trace cho SDK. Tên keys và category/outcome do model trả về được giới hạn trước khi ghi summary.

Kiểm thử offline không chứng minh Cloud đã nhận trace hay privacy review đầy đủ: metadata vẫn chứa ID/hash liên kết ứng viên và model/provider do admin cấu hình; auto-instrumentation không được bật để tránh gửi nội dung ngoài ý muốn. Giá tính trên Langfuse theo model và bảng giá riêng có thể khác với ước tính pin theo route trong HRApp. Không bật capture nội dung, reasoning hay upload CV/JD theo gợi ý chung của skill. E2E tổng thể, gold và benchmark vẫn tạm hoãn.


## Bằng chứng smoke synthetic do operator cung cấp

Ảnh chụp UI Langfuse do operator cung cấp cho thấy trace `7fe40ec6a68d7ac94308067ba935503a` với observation `hra.langfuse.smoke`, score `smoke_test: True`, output `status=COMPLETED`, `synthetic=true`, và input summary `content_capture=disabled` cùng độ dài/hash. Trước đó operator báo script không gửi có `enabled=true`, `configured=true`, `sdk_available=true`, `environment=staging` và `capture_content=false`. Đây là bằng chứng UI cho một smoke tổng hợp đã tới một project Langfuse; ảnh không xác minh tên project/environment, commit đang chạy, cấu hình API/worker hay luồng nghiệp vụ. Chưa xác minh full workflow, fail-open với sự cố mạng, retention/RBAC hoặc privacy đối với dữ liệu thật. Không coi smoke là phê duyệt egress dữ liệu thật, benchmark hoặc E2E.
