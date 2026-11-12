# Chuẩn bị song song: vận hành và quyết định Phase 1

> Chỉ là checklist để phân công; chưa có mục nào được xác nhận, chưa cấp quyền thao tác hay chạy E2E. Không đưa mật khẩu, token, key, CV, prompt hay PII vào tài liệu. Không ghi giá trị secret; chỉ ghi loại key, nguồn cấu hình, owner và trạng thái đã xác minh.

## 1. DevOps/IT — DEP-03, DEP-04, DEP-08

| Mục | Owner | Trạng thái / bằng chứng cần điền |
|---|---|---|
| Inventory môi trường, phân loại test/production, URL và project ref | DevOps/Release | CHỜ — xác nhận mapping và mốc giờ, không suy từ tên `APP_ENV` |
| Backend, frontend, worker: host, process, phiên bản/commit, số instance, ai bật worker | DevOps | CHỜ — đối chiếu lúc release; xác minh session PostgreSQL cho advisory lock |
| Migration và rollback: phiên bản thực tế; thử migration trên DB dùng một lần | DevOps/DBA | CHỜ — `00014` mới chỉ ở repo/local CI; không tự áp project kết nối. Rà backfill/lịch sử và release tương thích; backup trước thay đổi |
| Supabase API key/JWT consumers: backend, worker, deploy, tác vụ định kỳ, integration, client khác | IT Security + chủ project | CHỜ — ghi từng consumer/version, loại key, chuyển sang key/JWKS mới, restart và test; không ghi giá trị key |
| Disable legacy key/revoke JWT secret | Chủ project | BLOCKED — chỉ thao tác thủ công sau khi mọi consumer đã kiểm chứng và có phương án rollback; không tự disable |
| Backup DB và storage, retention backup, mã hóa, phân quyền và restore | DevOps/DBA | CHỜ — lịch, owner, RPO/RTO được phê duyệt, bằng chứng restore isolated; test phải được cấp phép |
| DR, monitoring, alerting, log/PII và bảo vệ branch | DevOps/Security | CHỜ — drill đã phê duyệt; alert lỗi retention/worker/storage, kiểm tra quyền repo; API protection trước đó 403 không chứng minh trạng thái |
| Runbook phục hồi retention | DevOps + HR Lead/Admin | CHỜ REVIEW — xem `doc/RETENTION_RECOVERY_RUNBOOK.md`; phân vai dừng executor, xác nhận provider I/O đã ổn định, quyết định tiếp tục xóa |

## 2. HR/Privacy/Legal — feedback và retention

| Quyết định | Người chốt | Đầu ra cần có |
|---|---|---|
| Ghi chú/feedback chung trong shortlist có nhiều ứng viên | HR Lead + Privacy/Legal | Quy tắc xác định thông tin cá nhân, trách nhiệm review/redact/xóa, phê duyệt và audit; không mặc định xóa nội dung của người khác |
| Shares đã purge trước guard và feedback về sau | Privacy/Legal + IT | Phương án kiểm kê an toàn, phạm vi lịch sử và cách xử lý; không suy ra đã sạch vì item đã mất liên kết |
| Retention 12 tháng, phạm vi đã tuyển, legal hold/ngoại lệ | Legal/Privacy + HR | Chính sách chính thức và quy trình giải quyết ngoại lệ. Không tự bật scheduler/automation |
| Phê duyệt egress và provider/model/storage | IT Security + Legal + HR | Kiểm kê hồi cứu, vùng xử lý, retention/training/xóa, hợp đồng và phê duyệt; redaction best-effort không phải ẩn danh tuyệt đối |

## 3. HR/HM/PO — tiêu chí đánh giá

| Việc | Người chốt | Đầu ra cần có |
|---|---|---|
| Policy điểm, mandatory và định nghĩa `UNCLEAR` | HR Lead + HM | Quy tắc chấm có ký duyệt; giữ Python tối thiểu 4 năm và partial 2 năm `UNCLEAR` chờ xác minh, không sửa manifest tự ý |
| Duplicate theo nội dung file | PO + HR | Quyết định có thuộc Phase 1 hay chấp nhận giới hạn hiện tại; không thêm cross-position/merge tự động |
| Tập pilot được phép | HR/HM + Privacy | Nguồn dữ liệu, mục đích/consent, người dán nhãn/phân xử, bao phủ nhóm IT, phân chia holdout và data handling; không sao chép CV thật vào Git |
| Metric/evaluation contract | HR/HM + kỹ thuật | Định nghĩa denominator, threshold, cách đo extraction/matching/mandatory false negative/quote/NDCG@5 và cách công bố theo nhóm |
| Workflow Core D-01…D-10 | HR/HM/IT | Quyết định riêng khi muốn mở Phase 2; direct approval hiện hữu không bị vô tình loại bỏ |

Không thu thập hoặc gửi dữ liệu thật, chạy E2E, deploy, thay key hay áp migration chỉ vì checklist này đã được tạo.
