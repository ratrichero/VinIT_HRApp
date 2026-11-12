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

### Kiểm kê sơ bộ từ repository và bằng chứng đã ghi — chưa xác minh runtime

- Backend `app/db/supabase.py` dùng `SUPABASE_SERVICE_ROLE_KEY` cho Supabase client phía server và `SUPABASE_ANON_KEY` cho client public; `app/api/auth.py` cũng dùng anon/publishable cho đăng nhập/đổi mật khẩu. Tên biến là tên lịch sử, không chứng minh key được cấu hình thuộc loại legacy hay mới; phải kiểm tra từng runtime và tính tương thích mà không in key.
- `app/core/security.py` xác minh token bất đối xứng bằng JWKS và còn nhánh HS256 qua `SUPABASE_JWT_SECRET`; cần kiểm tra loại token và mọi consumer trước khi revoke. Backend/worker dùng chung cấu hình trong topology PM2 được tài liệu mô tả.
- Các script test thủ công `retention_generate.py`, `retention_permissions_check.py`, `retention_lead_confirm.py`, `retention_execute_test.py`, `shortlist_e2e09_check.py` đọc `SUPABASE_ANON_KEY`; phải đưa vào danh sách consumer nếu còn sử dụng. Không chạy lại các script E2E đang treo.
- Frontend trong repo dùng `/v1` proxy; không tìm thấy consumer trực tiếp của các biến Supabase trong source frontend đã rà. Điều này không chứng minh không có consumer ngoài repo, browser cũ hay pipeline khác.
- Bằng chứng topology trước đó ghi PM2 `hra-backend`/worker cùng process và `hra-frontend`; VPS runbook khuyến nghị mỗi app một instance và backend một worker. Đây là bằng chứng lịch sử, **không phải trạng thái đo lại**. Cần xác nhận port/bind hiện tại; có khác biệt giữa runbook nội bộ và ghi nhận truy cập frontend qua public port.
- Chưa có bằng chứng backup/restore hay DR drill trong lần rà này. Không suy từ việc có schema/Supabase đang hoạt động rằng có backup đầy đủ, khôi phục được hoặc đã bao gồm Storage.

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
