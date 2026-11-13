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

```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=<public-key-staging>
LANGFUSE_SECRET_KEY=<secret-key-staging>
# Host Cloud hoặc base URL self-host phê duyệt:
LANGFUSE_BASE_URL=https://<langfuse-staging-host>
LANGFUSE_ENVIRONMENT=staging
LANGFUSE_RELEASE=<commit-sha>
LANGFUSE_TRACE_SAMPLE_RATE=1.0
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

Kết quả mong đợi: `enabled=true`, `configured=true`, SDK `available=true`, environment `staging`, không lộ secret và hàm không báo lỗi.

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
- Metadata chỉ có `synthetic=true`, `check=ok_count`, `release`.
- Observation `hra.smoke.echo` chỉ có `input_characters` và `output_characters` dạng count; không có nội dung nhạy cảm giả lập.
- Score `smoke_check_passed=1` xuất hiện.

## 5. Kiểm tra workflow tổng hợp một vòng

1. Tạo một vị trí và đơn ứng tuyển dùng CV/JD tổng hợp.
2. Chạy đường CV batch hoặc API hoàn chỉnh tùy theo deployment staging đã phê duyệt.
3. Kiểm tra Langfuse có các observation chính theo thứ tự:
   - `hra.cv.operation.process`
   - `hra.cv.document_extraction`
   - `hra.assessment.run`
   - các generation `hra.llm.*`
   - `hra.assessment.deterministic_matching`
   - `hra.assessment.semantic_retrieval` khi có tiêu chí chưa quyết định được bằng luật
   - `hra.embedding.generate` khi semantic fallback gọi BGE
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
3. Đối chiếu application log và latency; nếu timeout/latency vượt ngân sách của staging, tắt sampling hoặc giảm `LANGFUSE_TRACE_SAMPLE_RATE` trước, sau đó tắt hẳn nếu cần.

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
