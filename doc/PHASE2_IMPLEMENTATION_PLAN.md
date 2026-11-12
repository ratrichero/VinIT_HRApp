# Plan triển khai chi tiết — Phase 2 Batch đầu: Workflow cốt lõi

> **Lưu ý đối chiếu sau lập plan:** migration `00013` đã được dùng cho direct criteria approval và `00014` đã được dành trong repo cho retention/shared feedback; không dùng lại các số này cho Workflow Core. Kiểm tra local/remote và chọn số trống tiếp theo nếu batch được duyệt. Luồng direct approval đã được người dùng xác nhận: nội dung D-04 và các câu mô tả chỉ dual approval bên dưới là đề xuất cũ, cần cập nhật khi chốt D-04 để bảo toàn cả hai luồng hiện hành. Plan và D-01…D-10 vẫn chưa được duyệt. Xem [`PHASE1_REMAINING_EXECUTION_PLAN.md`](PHASE1_REMAINING_EXECUTION_PLAN.md).

> Ngày lập plan: 2026-11-07  
> Branch: `arena/ea6e2570-vinit-hrapp`  
> Trạng thái: **PLAN CHI TIẾT BATCH ĐẦU — CHỜ DUYỆT ĐỂ TRIỂN KHAI**  
> Căn cứ: `audit/PHASE2_REVIEW_2026-11-07.md`  
> Phạm vi được người dùng chọn ưu tiên: **F2.01 Rubric Library + F2.02 Structured Collaborative Workflow HR–HM**.

## 1. Quyết định phạm vi đã chốt

| Hạng mục | Quyết định |
|---|---|
| Ưu tiên đầu tiên | Workflow cốt lõi: F2.01 + F2.02 |
| Mức plan hiện tại | Chỉ lập plan chi tiết cho batch đầu; các nhóm còn lại ở mức roadmap |
| F2.07 Retention automation | **Loại khỏi vòng triển khai này**; giữ nguyên retention thủ công an toàn của Phase 1 |
| Candidate Rediscovery | Để ở **cuối Phase 2**, không thuộc batch đầu |
| F2.08 SSO | **Tạm treo**, không thiết kế/triển khai |
| F2.03, F2.04, F2.05, F2.06, F2.09 | Chưa lập plan chi tiết ở vòng này |
| Phase 1 DEP-01…DEP-08 | Vẫn tạm dừng chờ Production; plan này không đóng hoặc thay thế các DEP đó |

Plan này chưa phải lệnh triển khai. Chỉ bắt đầu viết code sau khi người dùng duyệt plan và các quyết định ở Mục 3 được chốt.

## 2. Mục tiêu và kết quả mong đợi của batch đầu

### 2.1. Mục tiêu

1. Chuẩn hóa rubric theo job family để HR không phải tạo lại tiêu chí từ đầu cho các vị trí tương tự.
2. Cho phép áp dụng rubric mẫu vào một vị trí cụ thể nhưng vẫn giữ kiểm soát phê duyệt HR/HM hiện tại.
3. Biến shortlist feedback tự do thành scorecard có cấu trúc theo tiêu chí, có người phụ trách, hạn hoàn thành và trạng thái theo dõi.
4. Giữ ranh giới dữ liệu hiện tại: HM chỉ xem ứng viên được share; HR private notes không bao giờ lộ cho HM.

### 2.2. Kết quả đầu ra

- Một thư viện rubric có taxonomy job family, template version được quản trị và vòng đời xuất bản rõ ràng.
- HR có thể áp dụng template đã xuất bản thành criteria draft của position; bản nháp vẫn đi qua quy trình duyệt criteria hiện tại.
- Mỗi shortlist share mới tạo scorecard cho từng ứng viên/HM, gắn với đúng criteria version của assessment đã snapshot.
- HM lưu nháp, nộp scorecard; HR theo dõi tiến độ, yêu cầu mở lại khi cần và xem tổng hợp.
- Hệ thống hiển thị việc đến hạn/quá hạn trong ứng dụng. Email reminder chưa được coi là hoàn thành cho tới khi chốt nhà cung cấp/kênh gửi ở cổng riêng.

### 2.3. Ngoài phạm vi batch đầu

- SSO và thay đổi authentication.
- Retention scheduler, cảnh báo xóa, exception hold, OTP/chữ ký điện tử.
- Candidate Rediscovery.
- Analytics/override tracking nâng cao, QA inspection queue, cross-position duplicate, OCR ảnh và comparison/export.
- Tự động gộp/xóa hồ sơ ứng viên.
- Thay đổi thuật toán matching, BGE hoặc LTR.

## 3. Cổng quyết định trước khi viết code

Các điểm sau phải được duyệt ở đầu batch. Nếu chưa chốt, chỉ làm discovery/prototype giao diện, không chốt migration.

| ID | Quyết định | Đề xuất mặc định trong plan | Người chốt |
|---|---|---|---|
| D-01 | Danh sách job family ban đầu | Dùng 5 nhóm trong tài liệu: Academic/Faculty, Research, IT & Digital, Admin & Operations, Student Services; chỉ tạo taxonomy, chưa tự bịa nội dung rubric chuẩn | HR Lead/HR nghiệp vụ |
| D-02 | Chủ sở hữu template | HR Recruiter/HRBP tạo draft; HR Lead duyệt và publish; Admin hỗ trợ kỹ thuật nhưng không tự duyệt nội dung nghiệp vụ | HR Lead |
| D-03 | Vòng đời template | `DRAFT → PUBLISHED → ARCHIVED`; version đã publish bất biến, muốn sửa phải tạo version mới | HR Lead |
| D-04 | Áp dụng vào position | Template chỉ tạo criteria `DRAFT`; vẫn bắt buộc quy trình HR/HM approval hiện tại, không auto-approve | HR Lead + HM representative |
| D-05 | Level áp dụng | Template có `level_band` tùy chọn; danh sách level phải được chuẩn hóa trước khi khóa schema | HR Lead |
| D-06 | Thang scorecard | Mỗi criterion: 1–5 hoặc `INSUFFICIENT_EVIDENCE`; có overall recommendation bắt buộc khi submit | HR Lead + HM representative |
| D-07 | Điều kiện submit scorecard | Phải đánh giá mọi criterion hoặc đánh dấu thiếu bằng chứng; overall recommendation bắt buộc; strengths/concerns theo mẫu chốt ở D-06 | HR Lead + HM |
| D-08 | Deadline mặc định | 3 ngày làm việc kể từ lúc share, HR có thể đổi khi tạo share; lịch nghỉ lễ chưa tính ở vòng đầu | HR Lead |
| D-09 | Email reminder | Chưa cam kết trong batch đầu nếu chưa chọn SMTP/provider và mẫu email; in-app reminder là phạm vi chắc chắn | IT + HR Lead |
| D-10 | Ai xem scorecard | HM tác giả, HR phụ trách position, HR Lead/Admin theo quyền hiện tại; HM khác không xem được | HR Lead |

## 4. Thiết kế dữ liệu dự kiến

Migration tiếp theo dự kiến: `supabase/migrations/00013_phase2_workflow_core.sql`. Số migration chỉ được khóa khi bắt đầu triển khai và phải kiểm tra không trùng trên remote.

### 4.1. F2.01 — Rubric Library

#### Bảng `app_private.job_families`

Các trường chính:

- `job_family_id UUID PK`
- `code TEXT UNIQUE` — mã ổn định, viết hoa, không đổi sau khi đã dùng.
- `name TEXT`
- `description TEXT NULL`
- `status TEXT`: `ACTIVE` / `INACTIVE`
- `display_order INTEGER`
- `created_by`, `created_at`, `updated_at`

Không hard-delete family đã có template/position tham chiếu; chỉ deactivate.

#### Bảng `app_private.rubric_templates`

Đại diện cho một họ template logic, không chứa nội dung theo version:

- `template_id UUID PK`
- `job_family_id UUID FK`
- `title TEXT`
- `level_band TEXT NULL`
- `status TEXT`: `ACTIVE` / `ARCHIVED`
- `created_by`, `created_at`, `updated_at`

#### Bảng `app_private.rubric_template_versions`

- `template_version_id UUID PK`
- `template_id UUID FK`
- `version_number INTEGER`, unique theo template.
- `status TEXT`: `DRAFT` / `PUBLISHED` / `ARCHIVED`
- `mandatory_weight_total NUMERIC(5,2)`
- `nice_to_have_weight_total NUMERIC(5,2)`
- `change_note TEXT NULL`
- `created_by`, `published_by`, `published_at`, `created_at`, `updated_at`

Constraint chính:

- Hai nhóm trọng số cộng đúng 100.
- Chỉ một version `PUBLISHED` hiện hành cho mỗi template tại một thời điểm; khi publish version mới, version published cũ chuyển `ARCHIVED` trong cùng transaction.
- Version `PUBLISHED`/`ARCHIVED` không sửa item hoặc trọng số.

#### Bảng `app_private.rubric_template_items`

Tái sử dụng cấu trúc của `criteria_items`:

- `template_item_id UUID PK`
- `template_version_id UUID FK ON DELETE CASCADE`
- `name`, `description`
- `category`: `MUST_HAVE` / `NICE_TO_HAVE`
- `weight_in_group NUMERIC(5,2)`
- `expected_evidence_keywords JSONB`
- `requirement_spec JSONB NULL`
- `evidence_guidance TEXT NULL`
- `display_order INTEGER`
- timestamps cần thiết

Khi publish, validate:

- Ít nhất một `MUST_HAVE` có trọng số > 0.
- Tổng `weight_in_group` của mỗi category đang dùng bằng 100.
- `requirement_spec`, nếu có, hợp lệ theo schema dùng chung hiện tại.

#### Bảng `app_private.rubric_template_review_events`

Lưu quyết định publish/archive/return-to-draft nếu workflow cần bằng chứng:

- `event_id UUID PK`
- `template_version_id UUID FK`
- `reviewed_by UUID`
- `decision TEXT`: `PUBLISH` / `ARCHIVE` / `REQUEST_CHANGES`
- `comment TEXT NULL`
- `decided_at TIMESTAMPTZ`

Nếu HR chốt quy trình publish đơn giản hơn, bảng này vẫn hữu ích làm lịch sử quản trị; không thay thế `audit_events`.

#### Thay đổi trên criteria/positions

- Mở rộng `criteria_versions.origin` thêm `TEMPLATE_CLONE`.
- Thêm `source_template_version_id UUID NULL` vào `criteria_versions`.
- Thêm `source_template_item_id UUID NULL` vào `criteria_items` để truy vết và hỗ trợ diff sau này.
- Thêm `job_family_id UUID NULL` vào `positions`; giữ `job_family` text trong giai đoạn chuyển đổi để không phá dữ liệu/UI cũ.
- Backfill `job_family_id` chỉ khi text khớp chính xác với family code/name đã duyệt; không fuzzy backfill.
- Position mới/cập nhật sẽ chọn family từ danh sách `ACTIVE`; text hiển thị được đồng bộ từ family đã chọn trong giai đoạn chuyển đổi.

### 4.2. F2.02 — Structured scorecard

#### Bảng `app_private.shortlist_scorecards`

Một scorecard cho một `share_item` và một reviewer:

- `scorecard_id UUID PK`
- `share_id UUID FK`
- `share_item_id UUID FK UNIQUE`
- `position_id UUID FK`
- `application_id UUID FK`
- `assessment_id UUID NULL`
- `criteria_version_id UUID NULL`
- `reviewer_user_id UUID`
- `status TEXT`: `NOT_STARTED` / `IN_PROGRESS` / `SUBMITTED`
- `overall_recommendation TEXT NULL`: theo thang được chốt ở D-06.
- `strengths TEXT NULL`
- `concerns TEXT NULL`
- `interview_questions TEXT NULL` — chỉ giữ nếu HR/HM xác nhận cần.
- `due_at TIMESTAMPTZ NOT NULL`
- `submitted_at TIMESTAMPTZ NULL`
- `reopened_by`, `reopened_at`, `reopen_reason`
- `created_at`, `updated_at`

Quy tắc:

- Scorecard được tạo trong cùng transaction với share item khi share mới được tạo.
- `criteria_version_id` lấy từ `assessment_id` đã snapshot trong share item, không lấy criteria mới nhất tại thời điểm HM mở màn hình.
- Nếu chưa có assessment hợp lệ, scorecard ở trạng thái chờ dữ liệu và không cho submit cho tới khi HR chia sẻ snapshot assessment phù hợp.
- Khi share bị revoke, HM không sửa được nữa; HR vẫn đọc được lịch sử theo quyền.
- Sau submit, HM không tự sửa. HR phụ trách/HR Lead có thể reopen kèm lý do; hành vi được audit.

#### Bảng `app_private.shortlist_scorecard_criteria`

- `scorecard_criterion_id UUID PK`
- `scorecard_id UUID FK ON DELETE CASCADE`
- `criterion_id UUID FK` tới criteria item của version đã khóa.
- `rating SMALLINT NULL` — 1–5 nếu dùng thang đề xuất.
- `evidence_assessment TEXT NULL`: dùng cho `INSUFFICIENT_EVIDENCE` hoặc mã hóa lựa chọn tương đương.
- `comment TEXT NULL`
- `updated_at`

Unique `(scorecard_id, criterion_id)`.

#### Dữ liệu giữ nguyên

- `shortlist_feedback`: giữ làm kênh trao đổi tự do và tương thích dữ liệu cũ.
- `application_private_notes`: giữ HR-only, không liên kết hiển thị vào scorecard của HM.
- Share cũ trước migration không backfill scorecard bắt buộc; giao diện hiển thị là share legacy chỉ có feedback.

### 4.3. Quyền truy cập, RLS và audit

- Bảng mới đặt trong `app_private`, bật RLS, revoke quyền khỏi `PUBLIC`/`anon`/`authenticated`, grant cho `service_role` theo mẫu migration hiện tại.
- Backend tiếp tục kiểm tra quyền ở API; không dựa duy nhất vào RLS vì backend dùng service role.
- Rubric publish/apply và scorecard submit/reopen đều ghi `audit_events` với object ID, position ID nếu có, outcome và metadata không chứa nội dung ghi chú/CV.
- Không đưa nội dung scorecard, private note hoặc CV text vào log ứng dụng.

## 5. API dự kiến

### 5.1. Rubric Library

| Method | Endpoint | Quyền dự kiến | Mục đích |
|---|---|---|---|
| GET | `/v1/rubric-library/families` | HR/Admin theo phạm vi | Liệt kê family |
| POST | `/v1/rubric-library/families` | Admin/HR Lead | Tạo family |
| PATCH | `/v1/rubric-library/families/{id}` | Admin/HR Lead | Đổi tên/mô tả/trạng thái |
| GET | `/v1/rubric-library/templates` | HR được phân công/Admin/HR Lead | Tìm template theo family, level, trạng thái, từ khóa |
| POST | `/v1/rubric-library/templates` | HR Recruiter/HR Lead | Tạo template + version 1 draft |
| GET | `/v1/rubric-library/templates/{id}` | Theo quyền thư viện | Xem template và các version |
| POST | `/v1/rubric-library/templates/{id}/versions` | Người có quyền sửa | Tạo draft mới từ version nguồn |
| GET | `/v1/rubric-library/template-versions/{id}` | Theo quyền thư viện | Xem chi tiết version/items |
| PATCH | `/v1/rubric-library/template-versions/{id}` | Draft owner/HR Lead | Sửa metadata/trọng số draft |
| POST | `/v1/rubric-library/template-versions/{id}/items` | Draft owner/HR Lead | Thêm item |
| PATCH | `/v1/rubric-library/template-items/{id}` | Draft owner/HR Lead | Sửa item |
| DELETE | `/v1/rubric-library/template-items/{id}` | Draft owner/HR Lead | Xóa item khỏi draft |
| POST | `/v1/rubric-library/template-versions/{id}/publish` | HR Lead | Validate và publish |
| POST | `/v1/rubric-library/template-versions/{id}/archive` | HR Lead | Archive version |
| POST | `/v1/criteria/position/{position_id}/apply-template` | HR phụ trách position | Clone template published thành criteria draft |
| GET | `/v1/criteria/position/{position_id}/template-matches` | HR phụ trách position | Gợi ý template theo family/level của position |

`apply-template` phải trả `409` nếu position đang có criteria version chưa kết thúc cho JD hiện tại (`DRAFT`, `PENDING_HR_REVIEW`, `PENDING_HM_APPROVAL`) để tránh tạo hai luồng duyệt song song.

### 5.2. Scorecard và workflow

| Method | Endpoint | Quyền dự kiến | Mục đích |
|---|---|---|---|
| POST | `/v1/shortlist/share` | HR phụ trách | Mở rộng payload thêm `due_at` tùy chọn; tạo share + scorecards trong một transaction |
| GET | `/v1/shortlist/{share_id}` | HR/HM liên quan | Bổ sung scorecard summary và từng scorecard |
| GET | `/v1/shortlist/my-scorecards` | HM/HR | Inbox việc cần làm, lọc trạng thái/đến hạn |
| GET | `/v1/shortlist/scorecards/{scorecard_id}` | Tác giả/HR phụ trách/HR Lead/Admin | Xem chi tiết |
| PATCH | `/v1/shortlist/scorecards/{scorecard_id}` | HM tác giả | Lưu nháp ratings/comments/tổng quan |
| POST | `/v1/shortlist/scorecards/{scorecard_id}/submit` | HM tác giả | Validate đầy đủ và khóa scorecard |
| POST | `/v1/shortlist/scorecards/{scorecard_id}/reopen` | HR phụ trách/HR Lead | Mở lại kèm lý do |
| GET | `/v1/shortlist/{share_id}/scorecard-summary` | HR/HM liên quan | Tổng hợp tiến độ và recommendation, không lộ HR private notes |

Không tạo endpoint cho HM chuyển trạng thái application; quyền quyết định trạng thái vẫn thuộc HR như hiện tại.

## 6. Giao diện dự kiến

### 6.1. Rubric Library

- Thêm route `/rubric-library` và menu **Thư viện rubric** cho vai trò được phép.
- Màn hình danh sách: lọc job family, level, trạng thái, tìm theo tên; hiển thị version published hiện hành và version draft.
- Màn hình chi tiết: sửa draft, quản lý items/trọng số/requirement spec, xem lịch sử version và publish/archive.
- Không cho sửa version đã published; nút tạo version mới phải sao chép items và ghi change note.

### 6.2. Áp dụng template vào position

- Trong position detail, cạnh luồng tạo criteria bằng AI, thêm **Áp dụng từ thư viện**.
- Hiển thị template phù hợp theo job family/level trước, nhưng HR vẫn có thể chọn template published khác nếu có quyền.
- Trước khi áp dụng, hiển thị preview: nguồn template/version, số Must Have/Nice To Have, trọng số và cảnh báo nếu đang có criteria chưa duyệt.
- Sau clone, điều hướng HR vào criteria draft hiện tại để kiểm tra và gửi duyệt như quy trình cũ.

### 6.3. Scorecard trong shortlist

- Shortlist inbox hiển thị số scorecard chưa bắt đầu/đang làm/đã nộp/quá hạn.
- Khi mở share, mỗi ứng viên có panel scorecard riêng: AI summary hiện tại, ratings theo criterion, strengths/concerns, overall recommendation, due date và trạng thái.
- HM lưu nháp nhiều lần; nút nộp bị khóa cho tới khi đạt điều kiện D-07.
- HR xem tiến độ theo HM/ứng viên, scorecard đã nộp và yêu cầu reopen.
- Scorecard phải ghi rõ criteria version/assessment snapshot đang được đánh giá để tránh nhầm với assessment mới hơn.
- HR private notes vẫn nằm ở candidate detail HR-only; không render trong shortlist HM view.

### 6.4. Đa ngôn ngữ và truy cập

- Mọi nhãn mới đi qua hệ thống i18n Việt/Anh hiện tại.
- Form có label rõ ràng, lỗi validation đọc được bằng screen reader, trạng thái không chỉ dựa vào màu.
- Bảng/scorecard dùng được ở desktop và không làm vỡ layout mobile hiện tại.

## 7. Trình tự triển khai sau khi plan được duyệt

### Bước 0 — Chốt quyết định và nội dung mẫu

- Duyệt D-01…D-10.
- HR cung cấp taxonomy và ít nhất một rubric draft thật để kiểm thử nghiệp vụ; chưa cần đủ 5 template trước khi code nền tảng.
- Khóa thang scorecard và mẫu strengths/concerns/recommendation.

**Điểm dừng:** không viết migration nếu D-01, D-03, D-05, D-06 chưa chốt.

### Bước 1 — Migration và domain foundation

- Viết migration `00013_phase2_workflow_core.sql`.
- Thêm schema Pydantic dùng chung cho template item/scorecard.
- Thêm service/domain functions cho publish validation, template clone và scorecard completion.
- Viết unit test cho state transitions, weight validation và due-date calculation.

### Bước 2 — Rubric Library backend

- Implement family/template/version/item APIs.
- Implement publish/archive với transaction lock để không có hai published version cùng lúc.
- Implement template matches và apply-template.
- Bảo đảm criteria approval/materialization cũ không hồi quy.

### Bước 3 — Rubric Library frontend

- Thêm API client, route, menu và màn hình quản trị template.
- Tích hợp apply-template vào position detail.
- Thêm test/typecheck/build và kiểm tra quyền hiển thị theo role.

### Bước 4 — Scorecard backend

- Mở rộng create share để tạo scorecards theo snapshot assessment.
- Implement get/update/submit/reopen/summary APIs.
- Thêm audit events và kiểm tra revoke/reopen/assignment revoked.
- Không backfill scorecard cho share lịch sử.

### Bước 5 — Scorecard frontend

- Cập nhật shortlist inbox/detail và API client.
- Thêm scorecard form, progress, overdue indicator và HR summary.
- Kiểm tra HM không nhận HR private notes qua bất kỳ response nào.

### Bước 6 — Kiểm thử tích hợp và staging nội bộ

- Chạy backend unit/integration, frontend `tsc`, lint, build.
- Áp migration lên DB kiểm thử dùng một lần và staging đích theo quy trình Phase 1; không chạy integration suite trực tiếp lên project production-like đã kết nối.
- E2E bằng dữ liệu tổng hợp cho Admin/HR Lead/HR Recruiter/HM/Outsider.
- Cập nhật `Update_Excute_P2.md`, tài liệu API/vận hành và commit theo từng bước có thể rollback.

## 8. Kiểm thử bắt buộc

### 8.1. Unit tests

- Publish bị chặn khi thiếu Must Have, tổng trọng số category không bằng 100 hoặc hai nhóm không cộng 100.
- Version published không sửa được; tạo version mới sao chép đúng items/spec/order.
- Apply-template bị chặn khi có criteria đang chờ duyệt cho JD hiện tại.
- Scorecard completion: thiếu một criterion, thiếu overall recommendation hoặc dùng criterion ngoài version đã khóa đều bị chặn.
- Due date mặc định bỏ qua thứ Bảy/Chủ Nhật; ngày lễ chưa tính và phải được UI/API mô tả đúng.

### 8.2. Integration/API tests

- HR không phụ trách position không tạo/apply template vào position đó.
- HM không xem template draft ngoài phạm vi hoặc scorecard của HM khác.
- Template clone tạo criteria `DRAFT`, giữ `requirement_spec`, source IDs và vẫn cần HR/HM approve mới dùng để assessment.
- Publish version mới archive version published cũ trong cùng transaction.
- Share mới tạo đúng một scorecard cho mỗi share item; share bị revoke thì HM không đọc/sửa scorecard.
- Scorecard dùng criteria của assessment snapshot kể cả khi position có criteria approved mới hơn sau thời điểm share.
- Submit khóa chỉnh sửa; HR reopen có lý do và audit.
- Mọi response HM đều không chứa private note, email nội bộ ngoài phạm vi hoặc dữ liệu ứng viên không được share.

### 8.3. Frontend/E2E synthetic

- HR Lead tạo family/template, HR tạo draft, HR Lead publish.
- HR áp dụng template vào position, duyệt criteria và chạy luồng hiện tại không lỗi.
- HR share shortlist có due date; HM lưu nháp, nộp scorecard; HR xem summary và reopen.
- Outsider/HM không liên quan nhận 403 ở API và không thấy menu/action ở UI.
- Giao diện Việt/Anh không thiếu key; form báo lỗi rõ khi chưa hoàn thành scorecard.

## 9. Tiêu chí nghiệm thu batch đầu

Batch đầu chỉ được coi là hoàn thành khi:

1. Có ít nhất một job family và một template được HR Lead publish bằng workflow thật, không seed cứng nội dung chưa duyệt vào migration.
2. HR áp dụng được template thành criteria draft; criteria vẫn phải qua HR/HM approval trước khi assessment dùng.
3. Không thể sửa template đã published hoặc scorecard đã submitted nếu không qua hành động có quyền và có audit.
4. Shortlist mới tạo scorecard đúng snapshot; HM hoàn thành và nộp được; HR theo dõi/reopen được.
5. In-app hiển thị scorecard đến hạn/quá hạn; mọi tuyên bố về email reminder phải chờ cổng D-09 riêng.
6. Không có rò rỉ HR private notes hoặc dữ liệu ngoài share sang HM.
7. Backend tests, frontend typecheck/lint/build và E2E synthetic đạt; CI xanh.
8. `Update_Excute_P2.md` ghi đủ file/migration, lệnh test, kết quả, commit và blocker còn lại.

## 10. Rủi ro và cách giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| Job family text hiện tại không đồng nhất | Taxonomy có code ổn định; backfill exact-match; HR rà soát dữ liệu không khớp trước khi ép dùng |
| Template bị coi là auto-approved cho mọi position | Clone chỉ tạo draft; giữ nguyên HR/HM approval theo position |
| Scorecard dùng nhầm criteria mới sau khi share | Khóa `criteria_version_id` từ assessment snapshot tại thời điểm tạo share |
| Nhiều HM hoặc share lại gây trùng scorecard | Unique theo `share_item_id`; mỗi share có reviewer riêng và vòng đời riêng |
| HM thấy ghi chú nội bộ của HR | Giữ private notes ở API HR-only hiện tại; test response HM theo snapshot dữ liệu |
| Chưa có email provider nhưng nghiệp vụ kỳ vọng reminder tự động | In-app reminder là phạm vi batch đầu; email là cổng riêng D-09, không tuyên bố F2.02 hoàn tất toàn bộ nếu email là bắt buộc |
| Nội dung rubric chuẩn chưa sẵn sàng | Code hỗ trợ tạo/publish; HR sở hữu nội dung. Không hardcode rubric chưa duyệt |

## 11. Roadmap sau batch đầu — chỉ ở mức định hướng

Sau khi batch Workflow Core được duyệt và triển khai:

1. Lập plan chi tiết riêng cho nhóm tiếp theo theo quyết định ưu tiên mới.
2. Candidate Rediscovery chỉ được đưa vào cuối Phase 2 và phải chờ quyết định consent/retention/quyền tái sử dụng CV; việc F2.07 loại khỏi vòng này không có nghĩa rediscovery được phép bỏ qua các điều kiện pháp lý đó.
3. F2.07 vẫn giữ ngoài phạm vi cho tới khi có quyết định mới.
4. F2.08 SSO tiếp tục tạm treo cho tới khi người dùng mở lại.
