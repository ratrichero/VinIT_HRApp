# Nhật ký thay đổi — công việc UI/UX tuyển dụng

Mỗi mục ghi lại một tính năng đã hoàn tất: vấn đề, thay đổi, phạm vi giữ nguyên,
kiểm thử đã chạy và phần chưa kiểm. Mục mới nhất nằm trên cùng.

**Quy trình.** Sau khi một tính năng UI/UX code xong và kiểm thử liên quan đã
chạy: (1) thêm mục nhật ký vào file này, (2) commit cùng phần code và test của
nhánh đang làm, (3) push lên nhánh đó. Nhánh chung duy nhất của dự án:
`freebuff/1434fda45407dc1a68600843` (nhánh `feature/ux-finish-application` đã được
bỏ; nội dung của nó nằm trọn trong nhánh chung).

## 2026-11-27 — Từ điển i18n: 78 khoá trả về tiếng Việt, 30 giá trị trùng, và hai test chặn

**Vấn đề.** `test:i18n` chỉ kiểm *có entry*, không kiểm entry nói gì, nên hai lỗi
im lặng cùng tồn tại:

1. **78 khoá** có giá trị y nguyên khoá tiếng Việt → giao diện tiếng Anh vẫn hiện
tiếng Việt. Con số thật lớn hơn con số đã báo trước đó (69): regex dùng bộ ký tự
thiếu (thiếu `ộ`, `ẽ`, `ậ`…) nên bỏ sót 9 khoá; test mới dùng bộ ký tự đầy đủ của
bộ test hiện có và lộ ra.
2. **30 nhóm giá trị tiếng Anh trùng** giữa các khoá → `translate` dựng bảng nghịch
Anh → Việt nên hai khoá cùng một bản dịch làm dịch ngược chọn sai khoá.

**Hai test mới** (`tests/i18n.test.cjs`, tổng 6 test):

| Test | Bắt gì |
| --- | --- |
| `không có khoá nào trả về y nguyên tiếng Việt…` | value === key và khoá có dấu tiếng Việt |
| `giá trị tiếng Anh là duy nhất…` | hai khoá cùng một bản dịch |
| `dịch ngược trả lại đúng khoá…` | chốt chặn: dịch vòng tròn 40 mẫu phải về đúng khoá gốc |

Hai danh sách miễn trừ có sẵn nhưng **để trống**: mỗi dòng thêm vào là một chỗ
người dùng tiếng Anh vẫn đọc tiếng Việt, hoặc một chỗ dịch ngược nhập nhằng —
phải kèm lý do cụ thể (tên riêng/mã).

**Sửa.** 2090 → **2081 entry**:

- **78 dòng dịch thật** (không phải `"X": "X"`), gồm cả các câu dài về rubric mẫu,
tiêu chí AI, nhóm vị trí, loại việc làm, cảnh báo tệp chưa quét virus.
- **30 nhóm trùng** được tách bằng bản dịch khác nghĩa: `Đang chờ`/`Chờ xử lý` →
`Pending`/`Queued`, `Điểm`/`Chấm điểm` → `Score`/`Grading`, `Sửa`/`Chỉnh sửa` →
`Edit`/`Modify`, `Vị trí tuyển dụng`/`Danh sách vị trí tuyển dụng` → `Recruitment
positions`/`Recruitment positions list`, …
- **9 khoá bị bỏ**: 2 khoá rác có khoảng trắng đầu (`"                      Đã xử
lý"`), 2 khoá chết (`Từ khóa bằng chứng`, `Shortlist chia sẻ`), và 5 khoá gộp về
một lối viết trong mã: `Huỷ`→`Hủy`, `Xoá tiêu chí`→`Xóa tiêu chí`, `Thêm vào
Shortlist`→`Thêm vào shortlist`, `Xem chi tiết & phản hồi`→`Xem chi tiết và phản
hồi`, `Giờ`→`Thời gian`. Gộp chứ không dịch khác nhau: cùng một từ mà hai lối
viết thì bản dịch phải giống nhau, nếu không bảng nghịch không thể vừa ý cả hai.

**Kiểm ngược.** Chèn thử một khoá chưa dịch và một khoá trùng giá trị → đúng **2
test đỏ** (hai test mới), 4 test còn xanh; phục hồi thì xanh lại.

**Đã chạy.** `test:i18n` **6 pass**; `test:unit` **234 pass**; `tsc` exit 0;
`next build` exit 0. Đo trực tiếp trên từ điển: `leak 0, dup 0, 2081 entry`.

**Chưa kiểm.** Chưa mở giao diện tiếng Anh để đọc bằng mắt. Bản dịch do mình
viết; vài chỗ phải chọn từ khác nghĩa để phá trùng (`Chấm điểm`→`Grading`,
`Chỉnh sửa`→`Modify`, `Mở`/`Đang mở`→`Open`/`Currently open`) — đúng nghĩa gần
nhất nhưng **nên có người duyệt nội dung** trước khi coi là bản dịch cuối.

## 2026-11-27 — Chuỗi lỗi "bằng cấp": cờ `threshold_pending` phải tắt được, và script đếm dữ liệu cũ

**Trạng thái khi bắt đầu.** Arena đã sửa hai phần trong `eb48521`: bỏ
`required_degree_level or 3` (giờ trả `unresolved`), và giữ spec DEGREE trong
response kèm cờ `threshold_pending` thay vì bỏ hẳn spec. Dead code
`required_degree = None` cũng đã biến mất. Hướng được chọn: **schema giữ chặt**,
cờ "cần xem lại" nằm ở response — không nới schema.

**Lỗi còn lại, đo được bằng cách đọc mã.** Cờ đó chỉ được máy chủ tính lại khi tải
trang. `patchSpec`, `changeKind` và `resync` trong `RubricItemEditor.tsx` chỉ gửi
`requirement_spec`, không đụng `threshold_pending` trong state. Nên: HR chọn xong
bậc bằng → `missingThreshold()` vẫn thấy `items[i].threshold_pending === true` →
vẫn chặn lưu với câu "chưa có ngưỡng"; tải lại trang thì máy chủ đọc ngưỡng cũ
trong DB nên vẫn đánh cờ. **Ngõ cụt: không lưu được, cũng không thoát ra được.**

**Sửa.** Thêm `pendingAfterEdit(spec)` vào `lib/requirementSpec.ts` — tính cờ từ
chính spec vừa sửa, đúng hai loại có ngưỡng bắt buộc (`YEARS`, `DEGREE`, khớp
`_PENDING_FILL` của máy chủ). Ba đường sửa spec trong editor đều truyền cờ đã
tính lại. Chốt chặn ở trang rubric giữ nguyên: item chưa ai sửa thì cờ vẫn đúng.

**Test mới.** `frontend/tests/requirement-spec-pending.test.cjs` (4 test, đã khai
trong `test:unit`): xét đúng hai ngưỡng, và cả ba đường sửa spec đều truyền cờ.

**Kiểm ngược (cả hai đầu chuỗi).**

| Gỡ dòng sửa | Kết quả |
| --- | --- |
| trả `patchSpec` về `onChange({ requirement_spec: next })` | đúng 1 test đỏ (`patchSpec tính lại cờ…`), 3 test còn xanh |
| trả `_evaluate_degree` về `spec.required_degree_level or 3` | đúng 1 test đỏ (`test_degree_without_a_level_never_decides_anything`), 7 test còn xanh |

Cả hai đã phục hồi mã.

**Script chỉ đọc.** `backend/scripts/audit_degree_specs.py` đếm tiêu chí DEGREE
đang thiếu bậc trong DB đã có, phân theo trạng thái bộ tiêu chí và theo vị trí;
có `--json`. Chỉ chạy `SELECT`, không tạo migration. Đo thật trên DB cục bộ:

```
DB trắng : DEGREE 0, thiếu bậc 0
Sau khi chèn 2 tiêu chí DEGREE (1 thiếu bậc, 1 có bậc 3):
  DEGREE 2, thiếu bậc 1 — DRAFT 1/2 — PROBE-DEGREE 1
Sau khi dọn: về 0
```

Tức script đếm đúng cả hai chiều, không đếm nhầm tiêu chí đã có bậc.

**Đã chạy.** `tsc` sạch; `test:unit` **234 pass** (230 + 4 test mới); `test:i18n`
pass; `next build` exit 0; `pytest backend/tests` trên PostgreSQL cục bộ **918
passed, 0 skipped**; ruff đúng phạm vi CI (`--select F` trên danh sách file trong
`ci.yml`) — All checks passed.

**Chưa kiểm.** Chưa mở giao diện bấm thử luồng "HR điền bậc rồi Lưu": sửa này
kiểm bằng test cấu trúc + đọc mã, không phải bằng thao tác thật. Ruff ngoài phạm
vi CI còn 2 lỗi F401 có sẵn trong `backend/app/api/notifications.py` (file của
arena, `datetime` và `HTTPAuthorizationCredentials` không dùng) — chưa sửa.

## 2026-11-27 — Quyền `GET /interviews`: test mức DB, và một lỗi 500 lộ ra theo

**Vấn đề.** Audit `doc/AUDIT_2026-11-27_NANG_CAP_GAN_DAY.md` mục 1 tìm ra `GET
/interviews` không tham số trả lịch của **mọi** vị trí kèm tên ứng viên. Arena đã vá
trong `eb48521` (403 khi không có `position_id`/`application_id`/`mine`; thêm đường
`application_id`; `InterviewPanel` gọi theo hồ sơ). Nhưng bộ test đi kèm dùng DB giả
nên chỉ kiểm **quyết định**, và không có test nào chứng minh `mine=true` trả đúng
buổi của mình.

**Sửa.** Thêm `backend/tests/test_interviews_list_permissions_db.py` — 5 test chạy
trên PostgreSQL thật, tự dựng hai buổi của hai người phỏng vấn khác nhau:

| Test | Khoá điều gì |
| --- | --- |
| `test_bare_list_is_forbidden_for_an_interviewer` | người phỏng vấn gọi không tham số → 403, thân lỗi không có tên ứng viên |
| `test_mine_true_returns_only_my_own_sessions` | `mine=true` → 200, đúng 1 buổi của mình, không có buổi của người kia |
| `test_hr_still_sees_the_whole_position_calendar` | đối chứng: HR của vị trí thấy cả hai buổi (để 403 trên không phải vì chặn tất cả) |
| `test_application_scoped_list_returns_only_that_application` | lọc theo hồ sơ trả đúng buổi của hồ sơ đó |
| `test_application_scoped_list_is_forbidden_for_an_interviewer` | người phỏng vấn không phải HR của vị trí → 403 |

**Lỗi thật lộ ra khi viết test.** `_INTERVIEW_SELECT` và hai câu khác trong
`backend/app/api/interviews.py` đọc `a.status`, nhưng `app_private.applications` chỉ
có `a.application_status` (từ commit arena `f835e5a`). Trên DB thật, **mọi** đường
đọc lịch phỏng vấn — list, chi tiết một buổi, và màn scorecard — ném
`UndefinedColumn` → 500. Không test nào bắt được vì tất cả dùng DB giả; đường 403
còn che mất lỗi vì nó chặn trước câu SELECT. Sửa cả ba chỗ thành
`a.application_status`.

**Kiểm ngược.** Đổi chốt 403 thành `if False and ...` rồi chạy lại: đúng 1 test đỏ
(`test_bare_list_is_forbidden_for_an_interviewer`), 4 test còn lại vẫn xanh — tức
phép kiểm bám đúng chốt chặn, không xanh nhờ may. Đã phục hồi mã.

**Đo lại `profile-transition-requests`** (server 3000, mock API, build hiện tại):

| Lần chuyển | `totalGet` | `paths` |
| --- | --- | --- |
| 1 | 2 | `/v1/interviews` 1, `/v1/applications/app-2` 1 |
| 2 | 2 | `/v1/interviews` 1, `/v1/applications/app-8` 1 |
| 3 | 1 | `/v1/interviews` 1 |

URL thật ghi được: `?application_id=app-5` khi mở hồ sơ, `?application_id=app-0` sau
khi bấm `n`. Nói thẳng: **số request không giảm** (vẫn 1 `GET /v1/interviews` mỗi lần
chuyển, như trước khi vá) — cái đổi là **phạm vi**: trước là `list({})` kéo tới 200
buổi của mọi vị trí rồi lọc ở client, nay máy chủ lọc theo hồ sơ và trả vài dòng. Hai
request `/v1/applications/app-N` còn lại là tải trước hồ sơ **sau nữa** trong hàng đợi
(script cho phép, và nó không phải chi tiết của hồ sơ đích).

**Đã chạy.** `pytest backend/tests -q` trên PostgreSQL cục bộ dựng lại từ
`scripts/test-db.sh`: **918 passed, 0 skipped** (913 trước + 5 test mới). 5 file test
liên quan phỏng vấn: 83 passed. Đo `profile-transition-requests`: pass toàn bộ
assertion.

**Chưa kiểm.** Chưa chạy e2e nào khác ngoài script đo trên; chưa thử ba endpoint vừa
sửa cột bằng tay trên giao diện (mới kiểm qua test HTTP + DB thật). PostgreSQL dùng
để đo là bản 16.2 của bundle `pgserver`, CI dùng 17.

## 2026-11-27 — Vá mock của 5 test arena làm đỏ: 18 → 13 test đỏ

**Vấn đề.** Mục trước đo được 5 test pass trước merge mà đỏ sau merge, tất cả vì mock **riêng của
mỗi test** thiếu route mới của arena. Fixture chung `fixtures/hr-screens.cjs` đã được vá ở commit
`df9a63c`, nhưng năm test này tự viết handler `context.route('**/v1/**')` nên không hưởng được.

**Sửa.** Thêm vào mock riêng của từng test, trả dữ liệu rỗng, không đổi assert nào:

| Test | Route thêm | Kiểu trả |
| --- | --- | --- |
| `account-ui` | `GET /v1/notifications` | `{items: [], unread_count: 0}` |
| `position-open-partial-failure` | `GET /v1/notifications` | `{items: [], unread_count: 0}` |
| `workflow-create-mock` | `GET /v1/notifications` | `{items: [], unread_count: 0}` |
| `deadline-work-queue-mock` | `GET /v1/notifications` | `{items: [], unread_count: 0}` |
| `ranking-context-mock` | `GET /v1/notifications` + `GET /v1/interviews` | `{items: [], unread_count: 0}` + `[]` |

`deadline-work-queue-mock` là ca đáng chú ý: mock của nó trả **500** cho mọi path lạ (để bắt request
chưa khai báo), nên thiếu route không hiện ra như "request lạ" mà như "máy chủ hỏng".

**Đo.** Trước: cả 5 đỏ (`account-ui` — `Unmocked API request: GET /v1/notifications`;
`position-open-partial-failure` — `Unexpected GET /v1/notifications`; `workflow-create-mock` — như trên;
`deadline-work-queue-mock` — `500 Internal Server Error`; `ranking-context-mock` — thêm cả
`GET /v1/interviews`). Sau: cả 5 pass, in đúng dòng "OK; all /v1 intercepted". Đối chứng: chính là
lần chạy trước khi vá (đỏ ở 5 dòng assert trên) và lần chạy trên cây `8fc5f0b` (pass) — không phải
suy luận.

**Đã chạy.** 5 test trên. **Chưa kiểm.** Chưa chạy lại toàn bộ 45 file sau khi vá (chỉ 5 file bị
sửa); 13 test đỏ còn lại (10 đã đỏ từ trước merge + 3 bị chặn cờ môi trường) giữ nguyên, chưa sửa.

## 2026-11-27 — Quét toàn bộ e2e: 18 test đỏ, trong đó 5 là nợ của arena

**Việc làm.** Chạy tuần tự cả **45** file `frontend/tests/*.e2e.cjs` trên cây hiện tại (HEAD
`df9a63c`, server 3000, mock API): **27 pass, 18 fail**. Để biết cái nào là nợ của arena chứ không
phải lỗi có sẵn, dựng thêm worktree tại `8fc5f0b` (HEAD trước khi merge arena), build và chạy lại
đúng 18 file đỏ trên cổng 3001 — **cùng file test**, vì merge không sửa file e2e nào (chỉ thêm unit
test và sửa `fixtures/hr-screens.cjs` + `mock-api-server.cjs`). Worktree và server 3001 đã dọn sau
khi đo.

**Arena làm đỏ — 5 test (pass trước merge, fail nay):**

| Test | Lỗi | Nguồn |
| --- | --- | --- |
| `account-ui` | `Unmocked API request: GET /v1/notifications` | `NotificationBell` (arena) |
| `position-open-partial-failure` | `Unexpected GET /v1/notifications` | `NotificationBell` |
| `workflow-create-mock` | `Unexpected GET /v1/notifications` | `NotificationBell` |
| `ranking-context-mock` | `Unexpected GET /v1/notifications` + `GET /v1/interviews` | `NotificationBell` + `InterviewPanel` |
| `deadline-work-queue-mock` | `500 Internal Server Error` | mock của test trả 500 cho mọi path lạ; probe in ra `UNMOCKED /v1/notifications` |

Tất cả đều là **mock riêng của từng test thiếu route mới**, không phải trang hỏng: hai component
mới của arena (`NotificationBell`, `InterviewPanel`) gọi endpoint mà 45 bộ mock rải rác trong
`tests/` chưa biết. Sửa `fixtures/hr-screens.cjs` (commit trước) chỉ chữa được nhóm dùng fixture
chung.

**Đã đỏ từ trước merge — 10 test (cùng lỗi, cùng dòng, trước và sau):** `a11y-mock`,
`applicants-large-list-mock`, `draft-back-guard-mock`, `retention-ui`, `shortlist-filter-mock`,
`shortlist-workspace-mock` (đều là `/v1/dashboard/work-queue` — và `/v1/positions/p1/duplicate-signals`
ở `applicants-large-list-mock` — bị tính là request lạ), `careers-public` (heading "Vị trí đang
tuyển dụng" không hiện trong 30 giây), `test-data-purge-mock` (không thấy tab "Dọn dữ liệu test"),
`ux-metrics` (thiếu sự kiện `PROFILE_CLOSED` khi rời hồ sơ), `ux04-sticky-viewer` (heading CV ở
118px, cần ≥ 143px). Sáu test đầu nay **có thêm** `/v1/notifications` trong danh sách lạ — sửa mock
của chúng thì phải thêm route đó, nếu không vẫn đỏ.

**Không chạy được trong phiên này — 3 test:** `careers-demo`, `intake-ui`, `synthetic-ui` tự chặn
khi thiếu cờ `HRA_E2E_SYNTHETIC=1` (kèm `HRA_E2E_HEALTH_URL`, `HRA_E2E_FIXTURE` cho `synthetic-ui`).
Đỏ y như trước merge, không liên quan arena.

**Chưa kiểm.** Ba test bị chặn cờ ở trên chưa chạy với cờ đầy đủ (cần backend + DB dùng-một-lần),
nên chưa biết chúng xanh hay đỏ. Chưa sửa 15 test còn lại — mục này chỉ đo và phân loại.

## 2026-11-27 — Sau khi đồng bộ arena: mock thiếu hai route mới, và badge không được hỏi lại khi đổi hồ sơ

**Vấn đề.** Đồng bộ nhánh arena (46 commit) làm ba e2e `finish-direct-advance`,
`sticky-review-actions`, `profile-transition-requests` đỏ ở assert "không có request lạ". Nguyên
nhân không nằm ở code trang: hai thành phần mới của arena gọi endpoint mà
`tests/fixtures/hr-screens.cjs` chưa mock — `InterviewPanel` gọi `GET /v1/interviews` ngay khi
mở hồ sơ, `NotificationBell` gọi `GET /v1/notifications` khi mount (và mỗi 60 giây). Mock trả
`{}` cho đường dẫn lạ, nên đây là lỗi của fixture, không phải của trang.

**Sửa.** Thêm hai route vào mock: `/v1/interviews` trả `[]`, `/v1/notifications` trả
`{items: [], unread_count: 0}`. Danh sách rỗng là đúng ý: ba e2e này không kiểm lịch phỏng vấn
lẫn hộp thư, và dữ liệu rỗng không đổi bố cục trang nên số đo cũ vẫn so sánh được.

**Lỗi thứ hai lộ ra sau khi mock đủ.** `profile-transition-requests` đi tiếp được và đỏ ở dòng
244: ở lại một hồ sơ 32 giây rồi bấm `n`, trang tải lại badge việc-cần-làm
(`/v1/dashboard/work-queue`). Thủ phạm là thay đổi của arena trong `AppLayout`: thêm `pathname`
vào deps của effect badge (sửa lỗi thật — trước đó badge chỉ cập nhật lúc đăng nhập). Nhưng
`pathname` đổi cả khi chỉ đổi mã hồ sơ, nên sau 30 giây chốt giãn cách, mỗi lần bấm `n` lại tốn
một request. Hai bên không thể cùng đúng: test unit mới của arena đòi `pathname` trong deps, e2e
đòi không hỏi lại badge khi đổi hồ sơ trong cùng vị trí.

**Sửa (2).** Giữ `pathname` trong deps, thêm chốt `badgeScreenRef`: bỏ mã hồ sơ ở cuối đường dẫn
(`/positions/p1/applicants/app-2` → `/positions/p1/applicants`) rồi mới so. Đổi màn hình thật
(dashboard → vị trí → lịch) vẫn cập nhật badge; đổi hồ sơ trong cùng danh sách thì không.

**Đo** (ba e2e, 1440×900, mock, `app-2` còn 2 tiêu chí chờ):

| Test | Trước khi sửa mock | Sau |
| --- | --- | --- |
| `finish-direct-advance` | đỏ: `['GET /v1/interviews']` (dòng 181) | pass: `{clean:{clicks:1, reviewPostsAtFinish:0, statusPatches:0}}` |
| `sticky-review-actions` | đỏ: `['GET /v1/interviews']` (dòng 159) | pass: `OK` (390/768/1024/1440px) |
| `profile-transition-requests` | đỏ: `['GET /v1/interviews']` (dòng 142) | pass |

Sau khi thêm route `/v1/interviews` nhưng **chưa** thêm `/v1/notifications`, cả ba vẫn đỏ với
`['GET /v1/notifications']` — đối chứng cho thấy mỗi route là một khoảng trống riêng, không phải
một lỗi chung. Sau khi mock đủ, `profile-transition-requests` đỏ tiếp ở dòng 244 với
`["/v1/applications/app-0","/v1/interviews","/v1/dashboard/work-queue","/v1/applications/app-2"]`;
thêm chốt `badgeScreenRef` thì nhánh đó còn
`{auth: 0, paths: ["/v1/applications/app-0", "/v1/interviews", "/v1/applications/app-2"]}` — mất
đúng một request badge, không mất request nào khác.

**Đã chạy.** Ba e2e trên (pass), `review-loop-metrics.cjs` (pass, `keyboardProfile` giữ nguyên
`{keysPressed:4, deadKeys:0, finishByKey:true, clicksDuringFinish:0, shortcutsHelpOpened:true}`),
`test:unit` **188 pass / 0 fail**, `test:i18n` 3 pass, `tsc --noEmit` sạch, `eslint` trên
`AppLayout.tsx` sạch, `next build` exit 0.

**Chưa kiểm.** Chưa chạy lại toàn bộ bộ e2e (chỉ ba test bị ảnh hưởng và script đo). Chưa nhìn
tận mắt việc badge có cập nhật khi đi giữa các màn hình — đó là suy luận từ nhánh `badgeScreen`
khác nhau, không phải phép đo. Hệ quả đã biết của chốt mới: đi từ danh sách ứng viên vào một hồ
sơ trong **cùng** vị trí không làm mới badge nữa (trước đó có, sau thay đổi của arena); badge chỉ
mới lại khi đổi màn hình hoặc sau 30 giây ở màn hình khác. Nếu muốn badge mới cả trong trường hợp
này thì phải nới assert của `profile-transition-requests` — chưa làm vì yêu cầu là giữ nguyên assert.

## 2026-11-25 — Bàn phím đi trọn một hồ sơ: `f` hoàn tất, `?` mở bảng phím tắt

**Vấn đề.** Bàn phím dừng ở tiêu chí cuối. Xác nhận hết tiêu chí bằng `1` xong, muốn bấm
"Đã xử lý xong" phải rời bàn phím sang chuột — cử chỉ duy nhất còn lại của cả vòng duyệt. Còn
dòng gợi ý phím tắt ở đầu trang thì dài, chỉ nằm ở một chỗ nên HR không nhớ hết.

**Sửa.** `f` → `finish`, gọi đúng `startFinish()` mà nút "Đã xử lý xong" đang gọi (cùng một cửa,
không sinh đường hoàn tất thứ hai); `canFinish` false thì phím không làm gì. `?` mở hộp thoại
"Phím tắt khi duyệt hồ sơ" liệt kê 8 phím đang có hiệu lực, đóng bằng `Esc` hoặc nút Đóng.
Dòng gợi ý thêm "f hoàn tất hồ sơ · ? xem bảng phím tắt". Cả hai phím mới nằm trong
`reviewKeyboard.ts` và chịu chung điều kiện chặn: đang gõ chữ, có Ctrl/Cmd/Alt, hay sự kiện đã
bị xử lý thì không chen vào. Khoá i18n mới đã thêm vào `en.json`.

**Đo** (`tests/review-loop-metrics.cjs` mục 6, 1440×900, mock API, hồ sơ `app-2` còn 2 tiêu chí
chờ; đếm cú bấm chuột thật bằng listener `click` pha capture):

| Chỉ số | Trước (HEAD `8cae15c`) | Sau |
| --- | --- | --- |
| Phím cho một hồ sơ | 4 lần bấm, **2 lần vô ích** (`?`, `f`) | 4 lần bấm, **0 vô ích** |
| Hoàn tất bằng bàn phím | **không** (`finishByKey: false`) | **có** (mở hộp thoại hoàn tất) |
| Cú bấm chuột để hoàn tất | **1** | **0** |
| `?` mở bảng phím tắt | không | có, 8 dòng, `Esc` đóng được |

Số xác nhận tiêu chí không đổi (2 phím cho 2 tiêu chí, 1 request mỗi lần xác nhận) — thay đổi này
không đụng vào vòng xác nhận, chỉ nối thêm chặng cuối.

**Assert mới** (không nới assert cũ): `?` phải mở bảng, bảng phải có dòng về `f`, `Esc` phải đóng,
`f` phải hoàn tất được hồ sơ, và hoàn tất không được cần cú bấm chuột nào. Đối chứng: build lại
HEAD rồi chạy cùng script → fail ngay "`?` phải mở bảng phím tắt" với
`{deadKeys: 2, finishByKey: false, clicksDuringFinish: 1}`; khôi phục bản sửa → pass với
`{deadKeys: 0, finishByKey: true, clicksDuringFinish: 0}`.

**Đã chạy.** `review-keyboard.test.cjs` (11 test, gồm 1 test mới cho `f`/`?`), `i18n.test.cjs` (3),
`tsc --noEmit`, `next build`, và ba e2e liên quan: `finish-direct-advance`, `sticky-review-actions`,
`profile-transition-requests` — tất cả pass.

**Chưa kiểm.** Chưa nhìn bảng phím tắt bằng mắt (chỉ đọc text trong DOM ở 1440px) và chưa xem ở
390px. Chưa chạy nhánh `f` trên hồ sơ "sạch" (đi thẳng sang hồ sơ kế, không hộp thoại) — nhánh đó
dùng chung `startFinish()` đã có test `finish-direct-advance` cho nút. Chưa thử `?` khi một hộp
thoại khác đang mở: handler thoát sớm nên không mở chồng, nhưng đó là suy luận từ code, không
phải phép đo.

## 2026-11-25 — Thanh dính ở 390px: ba hàng 152px → hai hàng 110px

**Vấn đề.** Ở 390px thanh dính chiếm ba hàng (ngữ cảnh + bộ đếm / tiêu chí + hai quyết định /
hoàn tất + điều hướng): **152px**, 18% màn hình 844px. Hai nút điều hướng "Trước"/"Tiếp" tốn
82px + 71px cho hai từ mà không mang thông tin gì thêm ngoài mũi tên.

**Sửa.** Dưới 600px điều hướng chỉ còn **icon** (40px, `aria-label` đầy đủ "Hồ sơ trước" / "Hồ sơ tiếp theo"),
và thanh gộp còn **hai hàng**: hàng 1 = ngữ cảnh + bộ đếm + "Hoàn tất" + hai icon; hàng 2 = tiêu chí đang chọn +
**Xác nhận** + **Đánh dấu sai** với nhãn đầy đủ. Cách làm: ở màn hẹp các Box nhóm chuyển `display: contents`
và con của chúng xếp bằng `order` (0 ngữ cảnh → 1 bộ đếm → 2 hoàn tất → 3,4 điều hướng → 5 tiêu chí → 6,7
quyết định); từ 600px trở lên trả lại ba nhóm như cũ. Chip bộ đếm ở màn hẹp viết gọn "2/2" (nhãn đầy đủ vẫn
là `aria-label`), và `StickyActionBar` bớt đệm dọc 10px → 6px ở màn hẹp.

**Đo** (`tests/sticky-bar-height.e2e.cjs`, Chromium headless, mock API):

| Khổ | Trước | Sau |
| --- | --- | --- |
| **390×844** | **152px, 3 hàng, 18% màn hình** | **110px, 2 hàng, 13% màn hình** |
| 768×1024 | 120px, 2 hàng | 120px, 2 hàng |
| 1024×768 | 120px, 2 hàng | 120px, 2 hàng |
| 1440×900 | 120px, 2 hàng | 120px, 2 hàng |

Không tràn ngang ở cả bốn khổ; Xác nhận và Đánh dấu sai cùng một hàng ở cả bốn khổ.

**Assert.** Trước đây test chỉ in số ở 390px (trần phải bật bằng biến môi trường); nay chốt thẳng: **≤ 116px và
≤ 2 hàng** ở 390px — trần đặt trên số đo 110px và dưới bản cũ 152px. `sticky-review-actions` nay khẳng định nhãn
bộ đếm **theo từng khổ** ("2/2" / "Còn 2/2 tiêu chí chờ") *và* `aria-label` đầy đủ ở màn hẹp, thay vì một chuỗi
cho mọi khổ — không nới, thêm một phép kiểm a11y. Nhãn hai nút quyết định vẫn được khẳng định đầy đủ
("Xác nhận" / "Đánh dấu sai") ở cả bốn khổ.

**Đối chứng.** Build lại HEAD khi chưa sửa: test **fail** — "390: thanh dính phải ≤ 116px (đang 152px, bản ba hàng
152px)". Khôi phục bản sửa, build lại: pass (`390: 110px, 2 hàng`).

**Kiểm thử đã chạy.** `sticky-bar-height` (4 khổ, exit 0), `sticky-review-actions` (4 khổ), `finish-direct-advance`
(1/1/1 cú bấm), `profile-lazy-panels`, `ranking-context-mock` (link "Hồ sơ tiếp theo" vẫn tìm được theo tên),
`npx tsc --noEmit`, `npx next build` — đều pass.

**Chưa kiểm.** Chưa xem ảnh chụp và chưa thử bằng mắt trên máy thật; mới đo DOM trong Chromium headless ở
390×844 (chưa thử 360px hay 320px). Vùng chạm của hai nút icon là 40×43px — trên ngưỡng 40px nhưng chưa đo bằng
ngón tay thật. Chip "2/2" không còn chữ "tiêu chí" trên màn hình, chỉ còn trong `aria-label`.

## 2026-11-25 — Ý #6: lần chuyển đã không GET chi tiết hồ sơ đích, nay có phép kiểm

**Điều cần.** Bấm `n` sang hồ sơ kế không được phát sinh `GET /v1/applications/{id}` cho **chính hồ sơ đích**
— đó là request làm trang mới phải quay spinner.

**Hiện trạng khi kiểm.** Việc “tải trước hồ sơ kế sớm hơn” đã có từ trước: `PrefetchProfile` gọi
`prefetchApplication(nextId)` khi trình duyệt rảnh (tối đa 1500 ms), và `takePrefetchedApplication()` trả bản
vừa xong trong `PREFETCH_REUSE_MS = 5 giây` với `fresh: true`, nên trang đích vẽ bằng bản đó mà không đọc lại
API. Vì vậy con số “1 `GET`” trong cửa sổ mỗi lần chuyển **không phải** của hồ sơ đích mà là tải trước **hồ sơ
sau nữa** (đi app-5 → app-0 thì cửa sổ có `app-2`): chi phí bị đẩy lên trước, không lặp lại.

**Thay đổi.** Chỉ thêm phép kiểm, không sửa code sản phẩm: `tests/profile-transition-requests.cjs` nay khẳng
định mỗi lần chuyển có **0** request cho đường dẫn `/v1/applications/{toId}` của hồ sơ vừa mở (trước đây chỉ
in ra trong `paths`, không ai kiểm).

**Đo** (`profile-transition-requests`, 3 lần chuyển liên tiếp trong cùng vị trí):

| Bản | `GET` chi tiết của hồ sơ đích | Đường dẫn trong cửa sổ chuyển | Assert mới |
| --- | --- | --- | --- |
| Hiện tại (tải trước khi rảnh) | 0 / 0 / 0 | `app-2`, `app-8`, — | **pass** |
| Đối chứng: bỏ hẳn `prefetchApplication` | 1 ở lần chuyển đầu | `app-0` (đúng hồ sơ đích) | **fail**: "lần chuyển 1 không được GET chi tiết hồ sơ đích (app-0), thấy {\"/v1/applications/app-0\":1}" |

Tổng `GET` mỗi cửa sổ chuyển vẫn là 1 / 1 / 0 như trước — không tăng, không giảm; cái được khoá lại là
**hồ sơ đích không tự gọi lại**.

**Đã thử và bỏ.** Đổi tải trước sang chạy ngay khi hồ sơ hiện tại có dữ liệu (thay vì đợi rảnh) để “sớm hơn”:
build lại và đo — `paths` y hệt (`app-2`, `app-8`, —), `detail` 1 / 1 / 0, không có khác biệt nào đo được,
nên đã trả code về như cũ. Bản tải trước hiện tại đã kịp xong trong nhịp 0,2–0,4 giây mỗi hồ sơ của test.

**Chưa kiểm.** Chỉ mock API + Chromium headless trên máy ảo. Tải trước vẫn đợi rảnh tối đa 1500 ms: nếu máy/mạng
chậm tới mức 1500 ms mới rảnh thì bản tải trước có thể chưa xong lúc bấm `n`, trang đích sẽ `GET` lại — chưa đo
kịch bản đó, cũng chưa đo trên mạng thật.

## 2026-11-25 — Cửa sổ dừng 600 ms có đáng? Đo độ trễ chip số ghi chú

**Câu hỏi.** Cửa sổ dừng 600 ms (nạp ghi chú khi HR ở lại hồ sơ) đổi lấy điều gì? Đo thời gian từ lúc hồ sơ
hiện ra (`verification-progress` dựng xong) tới lúc chip "N ghi chú riêng tư" xuất hiện, trên CPU bình thường
và khi CPU bị bóp chậm 6 lần, kèm chi phí request của từng phương án.

**Cách đo.** Script mới `frontend/tests/notes-chip-latency.cjs`: mở danh sách → mở hồ sơ (mock trả sẵn 2 ghi
chú) → đo tới khi chip có mặt, rồi bấm `n` sang hồ sơ kế và đo lần hai; chạy hai lượt, lượt sau bóp CPU bằng
CDP `Emulation.setCPUThrottlingRate: 6`. Mỗi phương án là một bản build của trang hồ sơ, chỉ khác
`NOTES_SETTLE_MS` (600 / 250 / 0) hoặc bản hiện tại (không cửa sổ). Chi phí request lấy từ
`tests/profile-transition-requests.cjs` (lướt 3 hồ sơ cách 250 ms rồi dừng, panel đóng).

**Kết quả** (chip: ms sau khi hồ sơ hiện ra, hai lần đo; request: cho 3 lần lướt + 1 lần dừng):

| Phương án | Chip trên CPU 1x | Chip trên CPU 6x | Request ghi chú (3 lướt) | Ghi chú khi chuyển |
| --- | --- | --- | --- | --- |
| Không cửa sổ (hiện tại) | không hiện | không hiện | **0** | 0 |
| Cửa sổ 600 ms | 792 / 788 | 835 / 370 | 1 (của hồ sơ dừng lại) | 0 / 3 |
| Cửa sổ 250 ms | **289 / 294** | 422 / 191 | 1 (của hồ sơ dừng lại) | **2 / 3** |
| Cửa sổ 0 ms (nạp ngay) | **68 / 43** | 340 / 169 | **4** (cả 3 hồ sơ lướt qua) | **3 / 3** |

Hồ sơ hiện ra mất 150–260 ms trên 1x và 700–1600 ms trên 6x, nên bóp CPU có tác dụng thật. Trên 6x, một phần
cửa sổ dừng đã trôi qua trước khi khung hồ sơ vẽ xong, nên có mẫu chip chỉ còn 370–191 ms.

**Đọc số.** Cửa sổ dừng làm chip hiện muộn đúng bằng phần cửa sổ còn lại: 600 ms → ~790 ms; 250 ms → ~290 ms;
nạp ngay → 40–70 ms. Về phía request, cả ba phương án đều tối đa **một** request cho mỗi hồ sơ — khác biệt
chỉ là hồ sơ nào bị hỏi: 600 ms bỏ qua hồ sơ sống dưới 600 ms, 250 ms bỏ qua dưới 250 ms, nạp ngay thì hồ sơ
nào cũng hỏi. Với nhịp lướt 250 ms/hồ sơ đang đo, 600 ms tiết kiệm 2 request trên 3 lần chuyển so với 250 ms.

**Đề xuất.**
- Nếu chip trước khi mở panel **không cần**: giữ như hiện tại (0 cửa sổ, chỉ tải khi mở panel) — 0 request, chip
  và số ghi chú hiện khi panel mở; tiêu đề panel đã có "(2)". Cửa sổ 600 ms khi đó chỉ tốn thêm request.
- Nếu cần chip: dùng **250 ms** thay cho 600 ms — chip sớm hơn ~500 ms (≈2,7 lần), vẫn không hỏi gì cho hồ sơ
  lướt dưới 250 ms; cái mất là 2 request/3 lần chuyển trong nhịp lướt 250 ms.
- Giữ 600 ms chỉ đáng khi biết nhịp lướt thật của HR rơi vào khoảng 250–600 ms/hồ sơ. Hiện **không có dữ liệu
  thật** cho khoảng này (chỉ có `PROFILE_OPENED`/`PROFILE_CLOSED` trong localStorage của máy HR, chưa thu thập).

**Chưa kiểm.** Toàn bộ là mock API + Chromium headless trên máy ảo; số tuyệt đối phụ thuộc máy, chỉ nên so
tương đối giữa các phương án. Chưa đo trên mạng thật (request ghi chú đi qua mạng công ty) và chưa có phân bố
thời gian HR thật ở lại một hồ sơ. Lượt này không đổi code sản phẩm, chỉ thêm script đo và mục nhật ký này.

## 2026-11-25 — Mở panel ghi chú là có dữ liệu ngay, không chờ cửa sổ dừng

**Vấn đề.** Với cửa sổ dừng 600 ms (nạp ghi chú khi HR ở lại hồ sơ), nếu HR mở panel "Ghi chú nội bộ HR"
ngay khi vào hồ sơ thì panel phải chờ hết cửa sổ mới có dữ liệu — đo trên bản đó: **526 ms** và **579 ms**
từ cú bấm mở panel tới lúc request ghi chú đi (hai lần đo ở hai hồ sơ).

**Sửa.** Không thêm đường tải thứ hai: mở panel chỉ bật cờ `notesRequested`, và request vẫn do đúng effect cũ
phát ra, với `AbortController` + cờ `cancelled` cũ (đổi hồ sơ là cắt request đang bay). Mỗi hồ sơ mở panel
một lần = đúng một `GET .../private-notes`; đóng/mở lại không hỏi lại; hồ sơ kế không tự nạp.

**Đo** (nhánh `immediate` trong `tests/profile-transition-requests.cjs`: mở hồ sơ từ danh sách, bấm mở panel
ngay khi nút vừa có mặt, đo từ cú bấm tới sự kiện request; lặp lại ở hồ sơ kế và lấy số nhỏ hơn để một lần
máy chậm không làm fail oan):

| | Trước (`e0e7e07^`, còn cửa sổ dừng) | Sau |
| --- | --- | --- |
| Mở panel ngay khi vào hồ sơ → có request ghi chú | 526 / 579 ms | **125 / 104 ms** |
| Request ghi chú cho hồ sơ đó mỗi lần mở panel | 1, nhưng do hẹn giờ chứ không do cú bấm | **1**, do cú bấm |
| Đóng rồi mở lại panel | 0 thêm | 0 thêm |
| Hồ sơ kế khi panel đóng | 0 (trong cửa sổ test) | 0 |

**Assert.** `elapsedMs` = số nhỏ hơn của hai lần mở, phải **< 400 ms** (trần đặt giữa ~100 ms đo được và
~520–565 ms của bản phải chờ cửa sổ); cộng ba assert cấu trúc: `requestsAfterOpen` đúng
`['/v1/applications/app-5/private-notes']`, đóng/mở lại vẫn 1 request, `otherProfiles` rỗng.

**Đối chứng.** Build lại `e0e7e07^`: `elapsedFirstMs 526`, `elapsedSecondMs 579` → fail; bản hiện tại
`elapsedFirstMs 125`, `elapsedSecondMs 104` → pass cả script (`profile-transition-requests` exit 0). Bản cũ
cũng fail sớm hơn ở assert "mở/chuyển hồ sơ không được tải ghi chú".

**Đã thử và bỏ.** Đóng băng đồng hồ trang (`page.clock.install` + `pauseAt`) để assert không phụ thuộc tốc độ
máy: kiểm tra riêng cho thấy `setTimeout` tạo trước lúc cài đồng hồ vẫn chạy thật, nên cách này không phân
biệt được, đã bỏ khỏi test thay vì giữ một assert không đo đúng thứ mình tưởng.

**Chưa kiểm.** Chạy với mock API trong trình duyệt headless trên máy ảo, không phải backend/mạng thật; con số
~100 ms là của môi trường này. Không đo cảm giác chờ của HR trên mạng chậm.

## 2026-11-24 — Ghi chú chỉ tải khi mở panel: hồ sơ nào cũng 0 request

**Vấn đề.** Sau khi bỏ request cho hồ sơ đã rời, hồ sơ HR **dừng lại** vẫn tốn một
`GET /v1/applications/{id}/private-notes` sau 600 ms. Nhưng ghi chú nằm trong accordion ở cuối trang và
chỉ để đọc khi cần: phần lớn lần mở hồ sơ không ai mở panel đó, nên request vẫn là thừa.

**Sửa.** Bỏ hẳn `NOTES_SETTLE_MS` và effect tự tải. Thêm cờ `notesRequested`, chỉ bật khi `HRNotesPanel`
báo **mở panel lần đầu** (prop `onOpen`, gọi trong `onChange` của Accordion). Mở lại/đóng panel không hỏi
lại vì effect chỉ phụ thuộc cờ đó. `change-password` và các chỗ khác không đụng tới.

**Đo** (`tests/profile-transition-requests.cjs`: mở danh sách → mở hồ sơ → bấm `n` ba lần cách 250 ms →
dừng lại 1,5 s, rồi mở panel ghi chú của hồ sơ đang xem). Cửa sổ đo mỗi lần chuyển chỉ chờ mạng xong
(+200 ms), ngắn hơn mốc `NOTES_SETTLE_MS = 600` cũ, nên số "trước" cho một hồ sơ đứng yên lấy từ nhánh
lướt-rồi-dừng (1,5 s), không từ cửa sổ chuyển:

| | Trước | Sau |
| --- | --- | --- |
| Ghi chú tải khi lướt 3 hồ sơ **rồi dừng lại** ở hồ sơ cuối | 1 (của hồ sơ dừng lại) | **0** |
| Ghi chú tải khi mở panel của hồ sơ đang xem | 0 (đã tải sẵn) | **1** (đúng hồ sơ đó) |
| Ghi chú tải cho hồ sơ đã rời | 0 | 0 |
| `auth/me`, rubric, badge mỗi lần chuyển | 0 | 0 (không đổi) |

**Assert của nhánh lướt.** Nhánh "Lướt nhanh" chỉ khẳng định điều thật sự cần: **không request nào cho
hồ sơ HR đã rời** (`leftBehind`), và request nào có cũng chỉ cho hồ sơ **đang hiển thị** (`offProfile`). Số
request của hồ sơ đang xem chỉ được in ra, không đếm cứng: máy chạy chậm làm mỗi hồ sơ sống lâu hơn và một
request có thể tới muộn mà vẫn đúng — đó không phải lỗi để bắt. Chốt chặn để con số 0 không phải vì "không
có gì chạy": mở panel phải hỏi ghi chú của chính hồ sơ đang xem.

**Đối chứng.** Dựng lại bản trước thay đổi (`git show e0e7e07^:...page.tsx`, còn `NOTES_SETTLE_MS`), build
lại: dòng `TRANSITIONS` in `skim.beforeOpen: [{askedFor: app-8}]` (hồ sơ dừng lại vẫn bị hỏi ghi chú), rồi
test **fail** — "mở/chuyển hồ sơ không được tải ghi chú: [\"/v1/applications/app-8/private-notes\"]".
Khôi phục bản sửa, build lại: pass, `skim.beforeOpen: []`, `skim.afterOpen: [app-8]`.

**Hệ quả đã cân nhắc.** Không tải thì không biết số, nên chip "N ghi chú riêng tư" cạnh trạng thái và số
ghi chú theo tiêu chí chỉ hiện **sau khi mở panel** (trước đây hiện sau 600 ms). Panel "Ghi chú nội bộ HR"
là lối vào duy nhất và vẫn nằm cuối trang; đây là đánh đổi có chủ ý để đổi lấy 0 request.

**Kiểm thử đã chạy.** `profile-transition-requests` pass toàn bộ (chuyển hồ sơ, ở lại 32 giây, huỷ request
khi rời, đóng/mở panel, ghi chú không mang sang hồ sơ kế — nhánh này nay mở panel để tải ghi chú), chạy lại
lần nữa sau khi sửa assert của nhánh lướt: vẫn pass; `profile-lazy-panels` pass, `npx tsc --noEmit` pass,
`npx next build` pass.

**Chưa kiểm.** Chưa chạy trên backend thật (mọi `/v1/` đều mock); chưa đo lại trong 375/768px (panel vẫn là
accordion như cũ); chưa đo chi phí khi HR **mở panel** rồi chuyển hồ sơ rồi quay lại — mỗi lần mở hồ sơ
state reset nên panel tải lại (cố ý: ghi chú có thể vừa được thêm bởi HR khác).

## 2026-11-24 — Quản lý tài khoản và chi tiết vị trí: 2 lần `auth/me` còn 1

**Vấn đề.** Hai trang đã được chuyển sang `getCurrentUser()` ở mục dưới, nhưng chưa có số đo riêng:
chúng chỉ được kiểm gián tiếp qua luồng mở hồ sơ. Mở **thẳng** mỗi trang vẫn có hai nơi cùng hỏi
`GET /v1/auth/me` — khung trang (`AppLayout`, kiểm quyền) và chính trang (`admin/users` để biết dòng
nào là "Tài khoản của bạn", `positions/[id]` để biết vai trò theo vị trí) — cùng một câu trả lời,
gửi hai lần.

**Sửa.** Không thêm gì: hai trang đã đọc bản dùng chung (`lib/meCache.ts`, 30 giây, gắn token) từ mục
trước. Mục này chỉ thêm phép đo để xác nhận.

**Đo** (`tests/page-auth-me-requests.cjs`, mở thẳng URL trong tab mới, đếm `GET /v1/auth/me` từ lúc
điều hướng tới khi nội dung thật của trang hiện ra — dòng `Trần Minh HM` ở bảng tài khoản, tiêu đề
vị trí ở trang chi tiết — rồi đợi thêm 800 ms cho request thứ hai kịp bay; 2 lần mỗi trang):

| Trang | `auth/me` trước | `auth/me` sau | Tổng `GET` trước → sau |
| --- | --- | --- | --- |
| Quản lý tài khoản (`/admin/users`) | 2 | **1** | 4 → 3 |
| Chi tiết vị trí (`/positions/p1`) | 2 | **1** | 9 → 8 |

**Đối chứng.** Đưa `admin/users/page.tsx` và `positions/[id]/page.tsx` về `5543abc` (bản còn
`authApi.me()`), build lại: test **fail** — "quan-ly-tai-khoan lần 1: mở trang chỉ được hỏi auth/me
đúng một lần, thấy 2", và dòng `PAGE_AUTH_ME` cho cả hai trang đều `authMe: 2` ở cả 2 lần chạy.
Khôi phục bản sửa, build lại: pass, `authMe: 1` ở cả 4 lần chạy.

**Chốt chặn trong test.** Ngoài số đếm, test còn chờ nội dung thật của trang hiện ra (không thì con số
1 chỉ là do danh tính chưa từng được tải), và fail nếu có request `/v1/` nào ngoài danh sách đã mock
— để phép đo không bỏ sót đường tải mới.

**Kiểm thử đã chạy.** `node tests/page-auth-me-requests.cjs` pass; `npx next build` pass.

**Chưa kiểm.** Chưa chạy trên backend thật (mọi `/v1/` đều được mock); mới đo với một tài khoản
`ADMIN` + `HR_RECRUITER`; chưa đo `auth/me` cho trang danh sách vị trí và dashboard bằng script riêng
(số của chúng đã nằm trong nhánh "mở hồ sơ từ danh sách" của `profile-transition-requests`).

## 2026-11-23 — Mở hồ sơ từ danh sách: 2 lần `auth/me` còn 1

**Vấn đề.** `lib/meCache.ts` mới chỉ gom hai chỗ: khung trang (`AppLayout`) và trang hồ sơ. Các trang
khác vẫn gọi `authApi.me` trực tiếp, nên mở hồ sơ từ danh sách ứng viên tốn **2** `GET /v1/auth/me`
(danh sách tự hỏi để có bộ lọc "Của tôi" + khung trang hỏi để kiểm quyền) — cùng một câu trả lời.

**Sửa.** Chuyển 5 chỗ sang `getCurrentUser()` (bản dùng chung, 30 giây, gắn token): danh sách ứng
viên, dashboard, danh sách vị trí, chi tiết vị trí, và quản lý tài khoản (`admin/users`, cùng lỗi).
Chỗ dùng đổi từ `response.data` sang chính object. `change-password` giữ `authApi.me` trực tiếp vì
trang đó nằm ngoài khung trang — chỉ một lời gọi, không trùng.

**Đo** (`tests/profile-transition-requests.cjs`, nhánh "Mở hồ sơ từ danh sách", đếm `GET /v1/auth/me`
từ lúc mở danh sách tới khi hồ sơ dùng được):

| | Trước | Sau |
| --- | --- | --- |
| `auth/me` trước khi bấm vào hồ sơ | 2 | **1** |
| `auth/me` cho cả luồng mở hồ sơ | 2 | **1** |
| `auth/me` mỗi lần chuyển hồ sơ sau đó | 0 | 0 (không đổi) |

**Đối chứng.** Đưa 5 file về `HEAD` (gọi `authApi.me` trực tiếp), build lại: test **fail** với "mở hồ
sơ từ danh sách chỉ được hỏi auth/me tối đa một lần, thấy 2". Khôi phục bản sửa, build lại: pass.

**Kiểm thử đã chạy.** `profile-transition-requests` (nhánh mới + toàn bộ assert cũ),
`ux03-dashboard`, `dashboard-metrics`, `list-to-profile-requests`, `profile-lazy-panels` đều pass;
`npx next build` pass.

**Chưa kiểm.** Chưa đếm `auth/me` cho trang chi tiết vị trí và `admin/users` bằng số (chỉ sửa cùng
cách, các test hiện có của hai trang vẫn pass); chưa thử backend thật.

## 2026-11-23 — Ghi chú: không còn request cho hồ sơ HR đã rời (ý #2, lần hai)

**Vấn đề.** Mỗi lần bấm `n` vẫn còn một `GET /v1/applications/{hồ sơ cũ}/private-notes`. Lần sửa
trước (`4bc87f1`) chỉ cắt request đang bay khi rời hồ sơ — tức request **vẫn được gửi**, chỉ không
dùng kết quả. Trên mạng, đó vẫn là một request cho hồ sơ đã rời.

**Nguyên nhân thật.** Ghi chú được nạp bằng `runWhenIdle` ngay sau khi hồ sơ hiện ra (~180 ms). Nhịp
lướt hồ sơ của HR (`n` liền tay) chậm hơn thế, nên **hồ sơ nào cũng kịp gửi request trước khi bị
rời**; cleanup chỉ huỷ nó. Đo bằng cách lướt 3 hồ sơ cách nhau 250 ms: **3** request ghi chú
(app-0, app-2, app-8), trong đó **2** của hồ sơ đã rời. Chip số ghi chú và panel là thông tin phụ —
không đáng một request cho mỗi hồ sơ chỉ liếc qua.

**Sửa.** Ghi chú chỉ nạp khi HR **dừng lại** ở hồ sơ: `NOTES_SETTLE_MS = 600` (dài hơn nhịp lướt
250 ms, ngắn hơn một nhịp đọc tiêu đề). Rời trước mốc đó thì `clearTimeout` — không có request nào.
Thêm chốt kiểm URL ngay trước khi gọi API, vì đổi URL xảy ra trước khi React kịp dọn effect.

**Đo lại** (`tests/profile-transition-requests.cjs`, nhánh "Lướt nhanh"):

| | Trước (HEAD) | Sau |
| --- | --- | --- |
| Request ghi chú khi lướt 3 hồ sơ (250 ms/hồ sơ) | **3** (app-0, app-2, app-8) | **1** (app-8 — nơi HR dừng lại) |
| Request cho hồ sơ **đã rời** | **2** | **0** |
| Ghi chú mỗi lần chuyển (dừng lại đọc) | 1, của hồ sơ đang mở | 1, của hồ sơ đang mở (không đổi) |
| Tổng `GET /v1/` mỗi lần chuyển | 2 / 2 / 1 | 2 / 2 / 1 (không đổi) |

**Đối chứng.** Build lại `page.tsx` từ `HEAD` (không có cửa sổ dừng): test **fail** với "lướt 3 hồ sơ
chỉ được 1 request ghi chú… thấy app-0, app-2, app-8" (3 ≠ 1). Khôi phục bản sửa, build lại: pass.
Vòng đo chuyển hồ sơ nay chờ request ghi chú bằng cách **đọc danh sách request đã ghi nhận** thay vì
`waitForRequest`, để không lỡ request tới trước lúc đăng ký (đúng lỗi gặp ở lần chạy đối chứng đầu).

**Kiểm thử đã chạy.** `profile-transition-requests` (nhánh lướt nhanh + toàn bộ assert cũ: `auth/me`
= 0, `work-queue` = 0, ghi chú không mang sang hồ sơ kế), `profile-lazy-panels`,
`finish-direct-advance`, `sticky-review-actions`, `by-criterion-confirm-all` đều pass; `npx next build`
pass.

**Chưa kiểm.** Chưa đo cảm nhận độ trễ của chip ghi chú (nay hiện sau ~600 ms) trên máy chậm; 600 ms
là lựa chọn sản phẩm, không phải số đo tối ưu. Chưa thử trên backend thật.

## 2026-11-23 — Ghi chú không mang sang hồ sơ kế: nay có phép kiểm

**Vấn đề.** Phần xoá `notes` khi đổi hồ sơ không có test nào chứng minh: mock luôn trả mảng rỗng,
nên "không mang ghi chú sang" và "mang nhưng rỗng" cho ra cùng một màn hình.

**Phép kiểm mới** (trong `tests/profile-transition-requests.cjs`, nhánh "Ghi chú không mang sang hồ
sơ kế"). Mock trả ghi chú **riêng cho từng hồ sơ** — app-5 có 2 (1 chung + 1 cho tiêu chí `c2`),
app-0 có 1 (cũng cho `c2`, nên chỉ nội dung phân biệt được) — và **giữ** câu trả lời của app-0 trên
một cổng cho tới khi test mở. Trong cửa sổ đó:

| Điều kiện | Kỳ vọng |
| --- | --- |
| Trước khi chuyển (app-5, ghi chú đã về) | chip `2 ghi chú riêng tư`; chữ ghi chú của app-5 nằm cạnh tiêu chí `c2` |
| Sau khi bấm `n`, ghi chú app-0 **chưa** về | không còn chip số ghi chú; chữ của app-5 không còn trong `#criterion-c2` |
| Mở cổng (ghi chú app-0 về) | chip `1 ghi chú riêng tư` (không phải 2, không phải 3) và đúng chữ của app-0 |

**Ba lần đối chứng, để biết dòng nào thật sự giữ cho ghi chú không mang sang.**

1. Bỏ `setNotes([])` ở nhánh chính → test **vẫn pass**. Vì trang được gắn lại theo `applicantId`
   (Next đổi tham số động là dựng lại nhánh trang), `useState([])` tự đặt lại state.
2. Thêm "state sống qua lần gắn lại" (biến module giữ `notes`, `useState` đọc từ đó) + bỏ
   `setNotes([])` → **vẫn pass**. Vì nhánh `if (!mayManageNotes) { setNotes([]); ... }` cũng xoá
   ngay khi trang mount (lúc đó `application` chưa có nên quyền ghi chú là false).
3. Bỏ **cả hai** chỗ xoá + state sống qua lần gắn lại → **fail** đúng thông điệp "số ghi chú của hồ
   sơ cũ không được mang sang hồ sơ kế khi ghi chú mới chưa về". Tức phép kiểm bắt đúng lỗi, và hai
   chỗ xoá kia là hai lớp bảo vệ độc lập.

**Kiểm thử đã chạy.** `profile-transition-requests` pass trên bản build sạch (nhánh mới + các assert
cũ: `auth/me` = 0, `work-queue` = 0, ghi chú chỉ của hồ sơ đang mở); `npx next build` pass.

**Chưa kiểm.** Chỉ Chromium headless với mock; chưa thử với ghi chú thật từ backend (nhiều tác giả,
thời điểm khác nhau) — phép kiểm chỉ quan tâm số lượng và nội dung.

## 2026-11-23 — Nguyên nhân thật của hai request còn thừa mỗi lần chuyển hồ sơ

**Vấn đề nêu ra.** Mỗi lần chuyển hồ sơ còn 2 request thừa: `GET /v1/auth/me` hai lần và
`private-notes` của hồ sơ vừa rời.

**Đo trước khi sửa** (`tests/profile-transition-requests.cjs`, bản production, mock API):

| Lần chuyển | `auth/me` | `work-queue` | `private-notes` | Tổng `GET /v1/` |
| --- | --- | --- | --- | --- |
| Chuyển nhanh, 3 lần liên tiếp | 0 / 0 / 0 | 0 | của hồ sơ **đang mở** (app-0, app-2, app-8) | 2 / 2 / 1 |
| Ở lại hồ sơ 32 giây rồi chuyển | **1** | **1** | của hồ sơ đang mở | **5** |

Vậy "hai request thừa" là `auth/me` + `dashboard/work-queue`, không phải hai lần `auth/me`. Chúng
chỉ hiện khi HR ở lại một hồ sơ lâu hơn 30 giây — đúng nhịp làm việc thật, nên lần đo nhanh trước
đây (0/0/0) đã che mất.

**Nguyên nhân thật, từng cái.**

1. `auth/me`: `AppLayout` kiểm tra lại danh tính theo `pathname`, mà `pathname` có cả mã hồ sơ
   (`/positions/p1/applicants/app-5` → `app-0`). Mỗi lần bấm `n` là một "đổi trang" theo nghĩa đó.
   Trong 30 giây đầu, `lib/meCache.ts` che được lần hỏi này; quá 30 giây thì nó thành request thật.
   Thêm vào đó trang hồ sơ được gắn lại theo `applicantId` và tự gọi `getCurrentUser()` khi trình
   duyệt rảnh — cùng một câu hỏi, chỉ khác chỗ hỏi. Trước khi có `meCache`, hai chỗ này là hai
   request cách nhau 40–60 ms; sau khi có, chúng chỉ còn lộ ra khi bản dùng chung đã hết hạn.
2. `work-queue`: cùng effect đó (có giãn cách 30 giây) nên cũng chạy lại mỗi lần đổi `pathname`.
   Badge số việc không đổi khi chỉ chuyển giữa các hồ sơ của một vị trí.
3. `private-notes` của hồ sơ vừa rời: **không tái hiện được** trên nhánh này. Ở bốn mốc bấm `n`
   liền nhau (cách 0 / 10 / 30 / 70 ms), request ghi chú luôn mang id hồ sơ **đang hiển thị**
   (app-0 hoặc app-2), không có id hồ sơ đã rời; request đang bay thì đã bị huỷ (`ERR_ABORTED`,
   sửa ở `4bc87f1`). Còn một đường hở thật: ghi chú đang `POST` dở mà HR bấm sang hồ sơ khác thì
   bước tải lại sau `POST` hỏi ghi chú của hồ sơ vừa rời.

**Sửa.**

- `AppLayout`: khoá xác thực là **phạm vi** `/positions/{id}` (bỏ phần sau), không phải cả
  `pathname`. Đổi vị trí vẫn kiểm tra lại (vai trò gắn theo vị trí); chuyển hồ sơ trong cùng vị trí
  thì không. Badge `work-queue` dùng cùng khoá.
- `page.tsx`: bỏ lần tự gọi `auth/me`; đọc danh tính khung trang đã tải qua `getCachedUser()` /
  `subscribeCurrentUser()` (mới trong `lib/meCache.ts`), nên mở hồ sơ nào cũng không hỏi lại.
- `page.tsx`: nhịp rảnh nạp ghi chú thoát ngay nếu đã rời hồ sơ hoặc signal đã huỷ (không mở
  request để rồi huỷ), và `addNote` không tải lại ghi chú nếu URL đã sang hồ sơ khác.

**Đo sau khi sửa** (cùng script, cùng kịch bản):

| Lần chuyển | `auth/me` | `work-queue` | Tổng `GET /v1/` |
| --- | --- | --- | --- |
| Chuyển nhanh, 3 lần liên tiếp | 0 / 0 / 0 | 0 | 2 / 2 / 1 (không đổi) |
| Ở lại hồ sơ 32 giây rồi chuyển | **0** | **0** | **3** (`app-0`, tải trước `app-2`, ghi chú `app-0`) |
| Bấm `n` liền hai lần (0–70 ms) | 0 | 0 | ghi chú chỉ của hồ sơ đang hiển thị |

Tức mỗi lần chuyển bớt 2 request (5 → 3 khi ở lại lâu; 0 → 0 khi chuyển nhanh), và `auth/me` giờ
chỉ còn một lần cho mỗi lần đổi vị trí.

**Phép kiểm huỷ request nay chờ theo sự kiện, không ngủ.** Kịch bản cũ có ba con số cố định: route
mock ngủ 1.500 ms trước khi trả lời, rồi test ngủ 1.900 ms sau khi rời hồ sơ và 1.200 ms sau khi lùi
hồ sơ. Trên máy chậm, 1.900 ms có thể ngắn hơn thời gian trình duyệt kịp báo huỷ (flaky), còn trên
máy nhanh thì luôn thừa. Nay: route **giữ** mọi request ghi chú trên một cổng, test bấm `n` lần hai
rồi mới mở cổng, và chờ đúng một trong hai sự kiện — `requestfailed` (đã huỷ) hoặc `response` (vẫn
được trả lời) — cái nào tới trước; trần chờ **10.000 ms**, chỉ để báo lỗi rõ khi môi trường treo.
Trạng thái "không còn ghi chú đang bay" cũng chờ theo tập request đang bay, trần **5.000 ms**. Đo
lại cả script: **46,6 s → 43,5 s** (32 s trong đó là phép đo dwell 32 giây). Đối chứng bỏ
`controller.abort()`: test fail ngay với thông báo "…nhưng nó vẫn được trả lời (200)" — không phải
chờ hết trần.

**Kiểm thử đã chạy.** `profile-transition-requests` (thêm 2 phép đo + 3 assert mới: `auth/me` = 0
sau 32 giây, `work-queue` = 0, không có ghi chú ngoài hồ sơ đang xem) pass; `profile-lazy-panels`,
`list-to-profile-requests`, `finish-direct-advance`, `review-loop-metrics`, `review-double-confirm`
pass; `npx next build` pass.

**Chưa kiểm.** Chưa đo riêng trước/sau cho đường `POST` ghi chú chậm rồi rời hồ sơ (chỉ thêm chốt
chặn, chưa có số "trước"); chưa thử trên backend thật; `auth/me` vẫn được hỏi lại khi đổi vị trí
theo thiết kế.

## 2026-11-23 — "Đã xử lý xong hồ sơ này" đi thẳng khi không còn gì để ghi

**Vấn đề.** Hộp thoại hoàn tất luôn mở, kể cả khi hồ sơ đã xác minh đủ tiêu chí bị gắn cờ và trạng
thái không đổi. Ở trường hợp đó hộp thoại chỉ để chọn sẵn "giữ nguyên trạng thái" rồi bấm xác nhận:
hai cú bấm cho một việc đã xong, và một lần dừng không cần thiết trên mỗi hồ sơ.

**Sửa.** Nút `Đã xử lý xong hồ sơ này` gọi `startFinish`: nếu (a) không còn tiêu chí chờ
(`pendingResults.length === 0`), (b) không có bước trạng thái nào để ghi (không có quyền đổi trạng
thái, hoặc gợi ý rỗng, hoặc gợi ý bằng đúng trạng thái hiện tại), và (c) có hồ sơ kế trong hàng đợi,
thì ghi `VERIFICATION_COMPLETED` rồi `router.push(withCompletedFlag(keepContext(nextApplicantId)))`
— hồ sơ kế nhận cờ `completed=1` nên hiện dòng "Đã xử lý xong hồ sơ trước. Đang xem hồ sơ tiếp
theo." như khi đi qua hộp thoại, rồi cờ được bỏ khỏi URL. Ngược lại vẫn mở hộp thoại như cũ.

**Phạm vi giữ nguyên.** Còn tiêu chí chờ → hộp thoại (còn việc để ghi). Có đề xuất đổi trạng thái →
hộp thoại (ở đó mới có lựa chọn trạng thái và lý do). Là hồ sơ cuối hàng đợi → hộp thoại, để HR thấy
mình đang kết thúc ở đâu. Không tự động hoá quyết định nào: đường tắt chỉ bỏ bước xác nhận cho việc
không ghi gì.

**Đo** (`tests/finish-direct-advance.e2e.cjs`, bản production, hồ sơ đã xác minh đủ và trạng thái
`INTERVIEW` — không có gợi ý chuyển tiếp):

| Nhánh | Cú bấm (trước) | Cú bấm (sau) | Ghi dữ liệu | Điều hướng |
| --- | --- | --- | --- | --- |
| Không còn gì để ghi | **2** (mở hộp thoại + xác nhận) | **1** | 0 POST, 0 PATCH | sang hồ sơ kế, có dòng xác nhận |
| Còn 2 tiêu chí chờ | 1 (mở hộp thoại) | 1 | 0 | không đổi |
| Hết chờ, có đề xuất Shortlist | 1 (mở hộp thoại) | 1 | 0 | không đổi |

Số cú bấm đếm bằng listener `click` pha capture trên `window`, tức cú bấm thật.

**Đối chứng.** Build lại `page.tsx` từ `HEAD` (không có `startFinish`), chạy đúng kịch bản nhánh đầu:
`OLD_FINISH {"clicksAfterOpen":1,"clicksTotal":2,"advancedTo":"/positions/p1/applicants/app-0",
"patches":0,"posts":0}` — 2 cú bấm. Test mới trên bản đó **fail** (sau 1 cú bấm hộp thoại mở nên
không có điều hướng, `waitForURL` hết giờ). Khôi phục bản sửa, build lại: pass.

**Kiểm thử đã chạy.** `finish-direct-advance` (mới, 3 nhánh) pass; `finish-application` pass;
`mandatory-fail-finish` pass; `review-loop-metrics` pass; `npx next build` pass.

**Chưa kiểm.** Chưa bấm tay trên trình duyệt thật (chỉ Chromium headless qua Playwright); chưa thử
với hàng đợi có bộ lọc khác `NEEDS_VERIFICATION`; chưa đo trên hồ sơ thật ở backend (mock toàn bộ API).

## 2026-11-23 — "Xác nhận tất cả dòng đang hiện" ở màn duyệt theo tiêu chí

**Vấn đề.** Màn `by-criterion` gom nhiều hồ sơ cho **một** tiêu chí, nhưng mỗi dòng vẫn một cú bấm:
8 dòng đang hiện = 8 cú bấm cho cùng một quyết định giống nhau.

**Sửa.** Nút `Xác nhận tất cả dòng đang hiện` ở thanh trên. Bấm vào mở hộp thoại liệt kê đúng những
hồ sơ sẽ ghi (tên ứng viên; tối đa 10 dòng, quá thì "… và N hồ sơ khác"), rồi nút `Xác nhận N hồ sơ`.
Mỗi dòng vẫn là một `POST /assessments/results/{id}/review` riêng, ghi lần lượt, nên lịch sử
append-only giữ nguyên một dòng cho mỗi hồ sơ. Danh sách chỉ gồm dòng **đang hiện**, đang chờ xác
minh, có `result_id` và người xem có quyền xác minh — cùng điều kiện với nút của từng dòng. Khoá
một-lần-ghi dùng ref (`bulkInFlight`), không dùng state: state chỉ đổi sau lần render kế tiếp. Một
POST lỗi thì dừng, báo "đã xác nhận X/N", và bỏ các dòng đã ghi khỏi danh sách còn lại để bấm lại
không ghi trùng.

**Đo** (`tests/by-criterion-confirm-all.e2e.cjs`, 8 dòng đang hiện, bản production):

| | Từng dòng (đối chứng) | Xác nhận tất cả |
| --- | --- | --- |
| Cú bấm | **8** | **2** (mở danh sách + xác nhận) |
| POST | 8 | 8 |
| Danh sách xem trước | — | đúng 8 hồ sơ sẽ ghi; chưa ghi gì trước khi bấm |
| Bấm đúp nút xác nhận (một tác vụ JS) | — | 8 POST, không phải 16 |

Số cú bấm đếm bằng listener `click` pha capture trên `window` (cú bấm thật của người dùng), không
phải số lần gọi hàm.

**Đối chứng.** Build lại từ `HEAD` (bản không có nút): test **fail** vì không tìm thấy
`criterion-confirm-visible`. Bản có tính năng: pass.

**Sửa dữ liệu mock — lỗi thật của bộ test.** Lần chạy đầu, test bắt được `result_id` trùng: hồ sơ
`app-2` và `app-3` (nhóm so sánh trùng) cùng trả `r-c2`, tức hai hồ sơ khác nhau dùng chung một kết
quả. Hệ quả không chỉ ở test này: xác nhận ở hồ sơ này sẽ hiện "đã kiểm" ở hồ sơ kia. Đã sửa fixture
để mỗi hồ sơ có id riêng (`app-2:r-c2`, `app-3:r-c2`), đúng như handler chung đã ghi; cập nhật
`review-double-confirm` theo id mới, assertion giữ nguyên độ chặt.

**Kiểm.** `next build`; `npm run test:i18n` (khoá mới đã có trong `en.json`);
`by-criterion-confirm-all` (pass, số ở trên); `review-double-confirm`, `criterion-queue`,
`by-criterion-double-confirm`, `duplicate-compare` — đều pass.

**Chưa kiểm.** Chưa đo trên backend thật: mock trả tức thì nên 8 POST gần nhau về thời gian, dù vẫn
gửi tuần tự. Chưa thử nhánh "… và N hồ sơ khác" (cần > 10 dòng đang hiện, tức bấm "Tải thêm" hai
lần). Chưa thử trường hợp một POST lỗi giữa vòng: nhánh đó có xử lý nhưng chưa có test.

## 2026-11-23 — Rời hồ sơ là huỷ luôn request ghi chú đang bay

**Đính chính số đo trước.** Mục đề xuất ghi "mỗi lần chuyển gọi `private-notes` của hồ sơ **vừa
rời**". Đo lại bằng nhãn thời gian (console trong effect + `page.on('request')`, mốc là lúc bấm `n`):
request đó là của hồ sơ **vừa mở** — id trong URL trùng id trong request, gửi ~180 ms sau khi bấm, từ
`requestIdleCallback`. Id hồ sơ cũ không xuất hiện trong bất kỳ request ghi chú nào. Vậy không có
request ghi chú "thừa cho trang đã đi khỏi" để bỏ; số request mỗi lần chuyển vẫn là 1 và vẫn cần,
vì số ghi chú cạnh tiêu chí đọc từ danh sách đó.

**Vấn đề thật.** Vòng đời request sai: cờ `cancelled` chỉ bỏ qua câu trả lời, còn request vẫn chạy
hết cho một màn hình đã đổi; và trong lúc chờ, `notes` của hồ sơ cũ vẫn nằm trong state nên hồ sơ
mới hiện số ghi chú của hồ sơ trước.

**Sửa.** `applicationsApi.getPrivateNotes(id, signal)`; effect ghi chú tạo `AbortController`, cleanup
gọi `controller.abort()` (kèm `cancelIdle` như cũ), và câu trả lời bị huỷ (`ERR_CANCELED`) không bị
báo thành lỗi. Đầu effect xoá `notes`/`notesError` để hồ sơ mới không hiện ghi chú của hồ sơ cũ.
Ghi chú vẫn nạp đúng một lần cho mỗi hồ sơ sau khi hồ sơ dùng được; mở panel chỉ hiện bản đã nạp.

**Đo** (`tests/profile-transition-requests.cjs`, mock, bản production):

| | Trước | Sau |
| --- | --- | --- |
| `private-notes` mỗi lần chuyển (id) | 1, id = hồ sơ vừa mở | 1, id = hồ sơ vừa mở |
| Rời hồ sơ khi request đang bay (mock giữ 1,5 s) | hoàn tất `200` sau ~1,5 s cho hồ sơ đã rời | `net::ERR_ABORTED` ~75 ms sau khi rời |
| Request tải ghi chú khi mở panel | 0 | 0 |
| Tổng `GET` ba lần chuyển | 5 | 5 |

**Đối chứng.** Bỏ hai dòng `controller.abort()` rồi build lại: test **fail** ở
`ghi chú của /v1/applications/app-2/private-notes không được hoàn tất sau khi rời hồ sơ, thấy
["/v1/applications/app-2/private-notes","/v1/applications/app-8/private-notes"]`. Lần chạy đối chứng
đầu tiên pass vì phần sửa test chưa thực sự nằm trong file — bài học: phải `grep` lại file test sau
khi sửa, đừng tin "test xanh" khi chưa kiểm nó có chạy assertion mới.

**Kiểm.** `next build`; `profile-transition-requests` (assert id ghi chú từng lần chuyển, mở panel
không tải lại, huỷ khi rời), `profile-lazy-panels`, `list-to-profile-requests` — đều pass.

**Chưa kiểm.** Chưa đo trên backend thật. Trường hợp bấm `n` nhanh hơn ~180 ms thì request chưa được
gửi (đã bị `cancelIdle` chặn từ trước), nên không có gì để huỷ — chưa có test riêng cho nhịp đó.

## 2026-11-23 — Mỗi lần bấm `n` bớt hai `GET /v1/auth/me`

**Vấn đề.** Mỗi lần chuyển hồ sơ phát sinh **2** `GET /v1/auth/me`, trong tổng 4/4/3 `GET` của
ba lần chuyển — tức 6/11 request của cả vòng. Đo lại trên bản production trước khi sửa:
`auth/me` = 2, 2, 2.

**Nguyên nhân (đo, không đoán).** Thử đọc call stack qua CDP trước: chỉ ra được frame axios đã
minify, không phân biệt được chỗ gọi. Nên gắn tạm một tham số `?__me=…` cho từng chỗ gọi
`authApi.me` rồi đọc URL thật của request. Kết quả: hai request đến từ **hai chỗ khác nhau**,
cách nhau 40–60 ms, cùng một câu trả lời:

- `AppLayout` hỏi lại mỗi khi `pathname` đổi (effect phụ thuộc `pathname`, để làm mới quyền);
- trang hồ sơ hỏi **một lần khi mount** — nhưng Next gắn lại trang theo từng `applicantId`, nên
  "một lần khi mount" hoá ra là một lần cho mỗi hồ sơ.

**Sửa.** `lib/meCache.ts`: một bản dùng chung ngắn hạn, cùng kiểu với `rubricCache` — cửa sổ
**30 giây**, request đang bay dùng chung, lỗi thì bỏ khỏi bộ nhớ. Bản ghi gắn với **token** trong
`localStorage`, nên đăng xuất rồi đăng nhập tài khoản khác không đọc nhầm hồ sơ người trước; đổi
mật khẩu cũng xoá token nên cờ `must_change_password` không bị giữ lại. `AppLayout` và trang hồ sơ
cùng đọc qua `getCurrentUser()`.

**Đo lại** (`tests/profile-transition-requests.cjs`, cùng ba lần chuyển, bản production):

| | Trước | Sau |
| --- | --- | --- |
| `auth/me` mỗi lần chuyển | 2 / 2 / 2 | **0 / 0 / 0** |
| Tổng `GET` ba lần chuyển | 4 / 4 / 3 = **11** | 2 / 2 / 1 = **5** |
| `auth/me` khi mở hồ sơ đầu tiên | 4 | 2 |
| danh sách → hồ sơ (trung vị) | 6 | **4** |
| đối chứng tab mới (trung vị) | 9 | 8 |

**Đối chứng.** Bỏ đúng một dòng dùng chung trong `meCache` rồi build lại: test trả
`authPerTransition: [2,2,2]`, `fullLoopGetRequests: 11`, và **fail** ở dòng
`mỗi lần chuyển chỉ được hỏi auth/me tối đa một lần`. Phép kiểm mới không phải assert trang trí.

**Chốt chặn.** Assert `≤ 1` có thể xanh giả nếu danh tính không bao giờ được tải, nên test mở
menu tài khoản và chờ tên `Nguyễn Thu Hằng` lấy từ `auth/me`.

**Kiểm.** `next build` (typecheck); `profile-transition-requests` (pass); `list-to-profile-requests`
(ranking và danh sách vẫn 0; trung vị 6 → 4 và 9 → 8); `account-ui` (đăng xuất, đổi mật khẩu) pass.

**Chưa kiểm.** Chưa đo với backend thật — mock trả lời tức thì, nên số mili-giây sẽ khác còn số
request thì không. Chưa thử quyền bị thu hồi giữa phiên: với cửa sổ 30 giây, trang có thể dùng
quyền cũ tối đa 30 giây. Các màn khác (dashboard, danh sách ứng viên, danh sách vị trí) vẫn gọi
`authApi.me` trực tiếp — ngoài phạm vi phép đo lần này; `auth/me` còn 2 khi mở hồ sơ chính là lần
gọi riêng của trang danh sách.

## 2026-11-23 — Thanh dính dùng một bộ từ cho Xác nhận / Đánh dấu sai ở mọi khổ

**Vấn đề.** Dưới 600px hai nút quyết định ghi `Đúng` / `Sai`, từ 600px trở lên lại là
`Xác nhận` / `Đánh dấu sai` — cùng một hành động mà hai bộ từ. `Đúng`/`Sai` còn dễ đọc như kết luận
về **tiêu chí**, trong khi nút này nói về **trích dẫn** đang hiện.

**Đã cân nhắc.** Đổi cặp ngắn sang `Khớp`/`Không khớp` cho khỏi lẫn tiêu chí — nhưng như vậy vẫn
là hai bộ từ, và hai từ đó không khớp với câu trong hộp thoại ("Vì sao trích dẫn này không
đúng?") hay phần còn lại của màn hình. Chọn giữ `Xác nhận` / `Đánh dấu sai` ở **cả hai khổ**: đúng
nghĩa quyết định, trùng từ với hộp thoại, và không phải học hai cách gọi.

**Đo lại sau khi bỏ nhãn rút gọn** (`tests/sticky-bar-height.e2e.cjs`, 4 khổ): 390×844 vẫn
**152px, ba hàng**, Xác nhận và Đánh dấu sai vẫn cùng hàng, không tràn ngang; 768/1024/1440 vẫn
120px. Nhãn đầy đủ vốn đã vừa một hàng ở 390px vì hai nút này không có icon — bản rút gọn không
cần thiết cho bố cục, chỉ cho cách gọi tên.

**Bổ sung cùng ngày — phép kiểm nay phủ bốn khổ.** `sticky-review-actions` trước chỉ chạy 390px và
1440px, tức hai đầu; khoảng giữa không ai kiểm. Nay chạy 390×844, 768×1024, 1024×768, 1440×900 với
ba điều kiện cho mỗi khổ: nhãn đúng `Xác nhận` / `Đánh dấu sai` và **giống bộ từ của 390px**, hai nút
cùng hàng (so đường tâm dọc, lệch ≤ 2px — nút viền `Đánh dấu sai` cao hơn nút đặc 2px do đường
viền, nên so mép trên sẽ báo sai), và không tràn ngang. Đo được ở bốn khổ: nhãn giống nhau, lệch tâm
0px (390: tâm 206,5; 768: 182,5; 1024: 182,5; 1440: 190,5), không tràn ngang. Bản thân giao diện
không phải sửa — chỉ phép kiểm thiếu khổ.

**Hai khoá i18n `Đúng`/`Sai` đã xoá** khỏi `en.json` vì không còn chỗ dùng. Nhãn của Hoàn tất và
Trước/Tiếp vẫn có bản ngắn ở màn hẹp: đó là cùng một từ viết gọn (`Hoàn tất` = `Đã xử lý xong hồ sơ
này`), không phải hai khái niệm, và cần bản ngắn để hàng cuối vẫn đủ ba nút trong 390px.

**Kiểm.** `tsc --noEmit`, `eslint` hai file, `npm run test:i18n` (3/3), `npm run test:unit`
(131/131), `npm run build`. E2E trên bản production: `sticky-bar-height` (4 khổ),
`sticky-review-actions` (nay assert hai khổ dùng cùng một bộ từ, và nhãn là `Xác nhận` /
`Đánh dấu sai`), `review-double-confirm`, `mandatory-fail-finish` đều pass.

**Chưa kiểm.** Chỉ Chromium headless, chưa thử trên thiết bị thật; chưa thử với bản dịch tiếng
Anh (`Correct`/`Wrong` đã bị xoá, nhãn tiếng Anh nay dùng `Confirm`/`Mark as wrong` sẵn có).

## 2026-11-23 — Thanh dính ở khổ giữa: 768px và 1024px thấp hơn bản cũ, không cần đổi ngưỡng

**Vì sao đo thêm.** Lần làm gọn trước chỉ đo 390px và 1440px. Khoảng giữa (768/1024) là chỗ khó:
nhãn đầy đủ và icon điều hướng đã bật lại (từ 600px trở lên), trong khi thanh vẫn phải wrap — nếu
nhóm sai thì chính khoảng này lại cao hơn bản cũ.

**Cách đo.** Mở rộng `tests/sticky-bar-height.e2e.cjs` lên bốn khổ: 390×844, 768×1024, 1024×768,
1440×900; vẫn đo chiều cao, số hàng (gom theo tâm dọc), việc Xác nhận/Đánh dấu sai cùng hàng và
tràn ngang. Bản "trước" là checkout sạch của commit `5493738` (cha của `a7a3391`), build riêng và
chạy trên cổng 3100 với **cùng** script đo.

| Khổ | Trước (5493738) | Sau |
| --- | --- | --- |
| 390×844 | 400px · 6 hàng · 47,4% | **152px · 3 hàng · 18,0%** |
| 768×1024 | 168px · 3 hàng · 16,4% | **120px · 2 hàng · 11,7%** |
| 1024×768 | 168px · 3 hàng · 21,8% | **120px · 2 hàng · 15,6%** |
| 1440×900 | 128px · 2 hàng · 14,2% | 120px · 2 hàng · 13,3% |

Ở cả hai khổ giữa, thanh nay hai hàng như 1440px thay vì ba hàng, và thấp hơn 48px. Xác nhận /
Đánh dấu sai cùng hàng ở mọi khổ; không tràn ngang ở khổ nào. **Không phải chỉnh ngưỡng hay cách
nhóm** — bản mới tốt hơn bản cũ ở chính khoảng đang nghi.

**Chốt chặn.** Test thêm trần cho khổ giữa: 768 và 1024 phải ≤ 128px và không quá hai hàng (bản
cũ 168px / ba hàng), để lần sau có ai đổi nhóm mà làm thanh cao lại thì fail ngay.

**Kiểm.** `eslint` file test; chạy lại trên bản production hiện tại: cả bốn khổ pass, số y như bảng.

**Chưa kiểm.** Chỉ Chromium headless, chưa thử trên tablet thật; "trước" đo trên bản build tĩnh
của `5493738` chứ không phải cùng một tiến trình server, nhưng cùng script, cùng mock, cùng khổ.

## 2026-11-23 — Rubric dùng chung giữa các hồ sơ cùng vị trí: 14 → 11 request cho 3 lần chuyển

**Vấn đề.** Trang hồ sơ gọi `GET /v1/criteria/position/{id}/approved` mỗi lần mở, dù rubric thuộc
về **vị trí** chứ không thuộc hồ sơ — bấm `n` sang hồ sơ kế trong cùng vị trí không làm nó đổi.
Một vòng duyệt 6 tiêu chí chỉ chuyển hồ sơ một lần, nhưng duyệt liên tiếp nhiều hồ sơ thì request
này lặp y hệt mỗi lần.

**Thay đổi.** Thêm `src/lib/rubricCache.ts`: cache theo `positionId`, TTL 60 giây, request đang bay
dùng chung, lỗi thì bỏ khỏi bộ nhớ. Trang hồ sơ dùng `getApprovedRubric(positionId)` thay vì gọi
API trực tiếp. Vẫn là bản ngắn hạn như `profilePrefetch`: rubric sửa ở nơi khác sẽ tới trang sau tối
đa một phút, và chuyển sang vị trí khác thì khoá cache khác.

**Đo** — `tests/profile-transition-requests.cjs` (mới): mở danh sách → mở hồ sơ đầu → bấm `n` ba
lần; cửa sổ đếm chỉ mở trong lúc chuyển, không tính lần mở đầu.

| Lần chuyển | Trước: tổng `GET` (rubric) | Sau: tổng `GET` (rubric) |
| --- | --- | --- |
| 1 | 5 (1) | 4 (0) |
| 2 | 5 (1) | 4 (0) |
| 3 | 4 (1) | 3 (0) |
| **Cả 3 lần** | **14** | **11** |

Script tự fail nếu lần chuyển thứ hai trở đi còn gọi rubric, và còn mở "Yêu cầu gốc" của thẻ đầu
tiên để đọc câu mô tả lấy từ rubric — cache rỗng cũng làm số request đẹp, nên phải chứng minh nội
dung vẫn tới màn hình.

**Kiểm.** `tsc --noEmit`, `eslint` (3 file), `npm run build`. E2E trên bản production:
`profile-transition-requests` pass, `prefetch-next-profile`, `review-double-confirm`,
`sticky-review-actions`, `mandatory-fail-finish` đều pass.

**Chưa kiểm.** Chưa chạy với backend thật; TTL 60 giây chưa có test (sẽ cần chờ cả phút). Hai
request còn lại trong mỗi lần chuyển — `GET /v1/auth/me` hai lần và `private-notes` của hồ sơ vừa
rời — chưa xử lý trong lần này vì nằm ngoài câu hỏi về rubric.

## 2026-11-23 — Mở hồ sơ kế: một `GET` hồ sơ thay vì hai

**Vấn đề.** Bản tải trước vẽ được ngay, nhưng `loadData(initial)` vẫn gọi lại
`GET /v1/applications/{id}` ngay sau đó để "xác nhận". Với hồ sơ vừa tải trước xong vài trăm ms,
lần gọi đó chỉ lặp lại đúng dữ liệu vừa nhận — mỗi lần mở hồ sơ kế tốn hai request hồ sơ, cả vòng
duyệt tốn gấp đôi phần này.

**Sửa.** `profilePrefetch.ts` thêm `PREFETCH_REUSE_MS = 5 giây`; `takePrefetchedApplication` trả
`{ data, fresh }`. Trang hồ sơ vẽ ngay bằng `data` như cũ, nhưng chỉ đọc lại API khi `fresh` là
`false` — tức bản đã cũ hơn cửa sổ 5 giây. Bản cũ hơn 60 giây vẫn bị bỏ hẳn như trước. Phần áp
dụng dữ liệu (quyền, lịch sử, CV) được tách thành một hàm dùng chung cho cả hai đường, nên
đường không đọc lại vẫn đủ quyền và trạng thái như đường đọc lại.

**Đo** — `tests/prefetch-next-profile.e2e.cjs`, mock giữ request hồ sơ kế 600 ms, 3 lần lấy
trung vị. Test nay khẳng định **đúng một** `GET` hồ sơ cho mỗi lần mở (trước là "ít nhất hai").

| Bản | 3 lần (ms) | Trung vị | `GET` hồ sơ mỗi lần mở |
| --- | --- | --- | --- |
| Trước (luôn xác nhận lại) | 94, 100, 104 | 100 ms | 2 |
| Sau (chỉ đọc lại khi đã cũ) | 86, 87, 96 | **87 ms** | **1** |

Thời gian mở gần như không đổi — request thứ hai vốn không chặn lần vẽ đầu, nên thứ giảm được
là số request, không phải độ trễ. Nói cách khác: cùng một màn hình, nửa số request hồ sơ.

**Kịch bản thứ hai (mới) cho chiều ngược lại.** Chờ quá cửa sổ 5 giây rồi mới bấm `n`: đo được
`staleUsableMs: 84` (vẫn vẽ ngay từ bản tải trước, không quay lại spinner) và `detailRequests: 2`
(bản đã cũ nên có đọc lại API). Như vậy cửa sổ `fresh` thật sự có tác dụng, không phải bỏ luôn
lần xác nhận.

**Kiểm.** `tsc --noEmit`, `eslint` ba file, `npm run build`. E2E trên bản production:
`prefetch-next-profile` pass (cả hai kịch bản), `review-loop-metrics` pass (`withoutSelection`:
`getRequests: 0`, `requestsPerConfirm: [1,1]`; panel Profile mở sẵn: 0 `GET /profile`),
`review-double-confirm` pass.

**Chưa kiểm.** Chưa chạy với backend thật; 600 ms là độ trễ do mock dựng nên và 5 giây là cửa sổ
do mình chọn, chưa đo trên mạng thật. Test chép lại con số 5 giây thay vì import hằng số TS, nên
nếu đổi cửa sổ trong `profilePrefetch.ts` phải sửa cả test (nó sẽ fail rõ ràng, không im lặng).

## 2026-11-23 — Phép kiểm đường chuột của `review-double-confirm` không còn xanh giả

**Vấn đề.** Mục 2 của `tests/review-double-confirm.e2e.cjs` bấm `click({ force: true })` hai lần
vào nút Xác nhận trên thanh dính. Cú thứ hai rơi vào lúc React đã disable nút, nên trình duyệt
không phát sự kiện click: test vẫn xanh dù không có khoá nào. Phần đó chưa từng chứng minh đường
chuột bị chặn.

**Sửa.** Hai cú bấm nay xảy ra trong **cùng một tác vụ JS** (`button.click(); button.click();`),
ngay trong `page.evaluate`, và test đọc lại `disabled` **trước cú thứ hai**. Nếu React đã kịp
disable thì cú bấm đó bị trình duyệt chặn, phép kiểm vô nghĩa — nên test fail ngay với thông điệp
"cú bấm thứ hai phải tới được handler" thay vì lặng lẽ pass. Thêm một mốc 120ms để kiểm số POST
khi request đầu (700ms) còn đang bay.

**Đối chứng.** Bỏ dòng chặn `if (reviewSavingRef.current !== null) return;` ở trang hồ sơ, build
lại rồi chạy một probe tạm (chỉ đường chuột, để mục 1 không che mất kết quả):
`{"enabledBefore":true,"enabledForSecond":true}, posts: ["r-c2","r-c3","r-c3"]` — hai cú bấm đều
tới handler và ghi **hai** review cho `r-c3`. Khôi phục khoá, build lại: `["r-c2","r-c3"]`.

**Kiểm.** `review-double-confirm` pass trên bản production sau khi khôi phục nguồn; `eslint` pass;
`npm run build` pass; `git status` không còn thay đổi trong `src/`.

**Chưa kiểm.** Chưa chạy với backend thật; 700ms là độ trễ của mock.

## 2026-11-23 — Màn duyệt theo tiêu chí cũng chỉ ghi một review cho mỗi cú bấm

**Vấn đề.** `by-criterion/page.tsx` cũng gọi `reviewCriterionResult`, nhưng chỉ chặn bằng state:
nút Xác nhận / "Ghi lại" trong hộp thoại đánh dấu sai có `disabled={... || saving !== null}`. State
chỉ đổi **sau** lần render kế tiếp, nên hai cú bấm rơi vào cùng một nhịp (chuột nhanh, hoặc bấm
bàn phím hai lần) đều thấy "chưa lưu" và cùng gửi POST. Review là bảng append-only, nên đó là
cùng một quyết định bị ghi thành hai dòng — đúng lỗi đã sửa ở trang hồ sơ (`reviewSavingRef`),
nhưng màn này chưa có.

**Sửa.** Thêm `reviewInFlight` (ref, đổi ngay trong lần gọi đầu) làm khoá một-lần-ghi; `review()`
trả `'saved' | 'failed' | 'busy'` thay vì boolean, để chỗ gọi (nút Xác nhận và `submitReject`)
phân biệt được "bị bỏ qua vì đang lưu" với "lỗi thật" — nếu vẫn trả `false`, cú bấm thứ hai sẽ
hiện lỗi vô cớ. Hộp thoại chỉ đóng và chỉ báo lỗi khi có kết quả thật. Không đổi UI, không đổi
endpoint.

**Test mới `tests/by-criterion-double-confirm.e2e.cjs`.** Bấm hai lần **trong cùng một tác vụ JS**
(`button.click(); button.click();`) — cả hai xảy ra trước lần render đầu, nên nút khi đó vẫn
enabled: test đo đúng chốt chặn ở ref chứ không phải thuộc tính `disabled`. Mock giữ mỗi POST
700ms. Kiểm: đúng **1** POST cho `app-0:r-c2`, chip "Đã xác nhận", tiến độ `1/12`; rồi hộp thoại
đánh dấu sai của `app-1:r-c2` cũng bấm đôi → tổng cộng **2** review (`CONFIRMED`, `REJECTED`),
không có dòng trùng, hộp thoại đóng sau khi lưu.

**Đối chứng.** Bỏ dòng `if (reviewInFlight.current) return 'busy'` rồi build lại: test **fail** với
`cú bấm thứ hai trong lúc đang lưu không gửi thêm POST — 2 !== 1`. Khôi phục, build lại: pass.

**Kiểm.** `tsc --noEmit`, `eslint` hai file, `npm run build`. E2E trên bản build production:
test mới pass, `criterion-queue` pass (không hồi quy luồng xác nhận/đánh dấu sai/đổi tiêu chí).

**Chưa kiểm.** Chưa chạy với backend thật; 700ms là độ trễ do mock dựng nên, còn chốt chặn khoá
theo thời gian request chứ không theo đồng hồ. Chưa thử trên thiết bị cảm ứng thật.

## 2026-11-23 — Đo vòng duyệt với panel Profile đang mở sẵn, chặn mọi `GET /profile`

**Vì sao cần thêm kịch bản.** `tests/review-loop-metrics.cjs` trước đây đo vòng xác nhận khi panel
Profile **đóng**. Đó không phải cấu hình làm lỗi "panel bị gắn lại sau mỗi lần render" lộ ra: panel
đóng thì dù bị mount lại cũng chưa gọi `/profile` (chỉ nạp ở lần mở đầu), nên script vẫn xanh trong
khi bug quay lại. Cấu hình đúng để thử là panel **đang mở** rồi xác nhận hết tiêu chí.

**Kịch bản 5 (mới).** Mở panel bằng chính accordion `Profile ứng viên`, chờ response `/profile`
đầu tiên và chờ spinner biến mất (panel đã nạp xong, không phải chỉ vừa gửi request), rồi kiểm:
- mở panel = đúng **1** `GET …/profile` (không hơn: panel là một lần tải cho cả trang);
- xác nhận hết tiêu chí = **0** `GET …/profile` và **0** `GET …/status-events`; đây là chốt chặn
  sẵn có của `runLoop`, nay nhận thêm nhãn "panel Profile đang mở" để thông báo lỗi nói rõ cấu
  hình nào vừa hỏng;
- `aria-expanded` của panel **vẫn `true`** sau khi duyệt xong — panel bị mount lại thì tự đóng,
  nên đây là dấu hiệu trực tiếp của việc gắn lại, không chỉ là số request.

**Kết quả (bản build production, 1440×900).** `profileRequestsOnOpen: 1`,
`profileRequestsDuringConfirm: 0`, `panelStillExpanded: true`, 2 tiêu chí → 2 phím `1`, 2 POST
review (`requestsPerConfirm: [1, 1]`), `getRequests: 0` trong vòng xác nhận.

**Đối chứng.** Gắn tạm `key={`profile-${applicantId}-${Math.random()}`}` cho panel (buộc React
mount lại sau mỗi lần render), build lại và chạy: test **fail** với `panel vẫn mở sau khi xác nhận
hết tiêu chí — 'false' !== 'true'`. Khôi phục key cũ, build lại: pass. Vậy kịch bản bắt đúng cấu
hình đó, không phải một assert trang trí.

**Kiểm.** `eslint` file script; chạy trọn script 5 kịch bản trên bản build production (tất cả
pass), `npm run build` pass sau khi khôi phục nguồn.

**Chưa kiểm.** Chưa chạy với backend thật; số request đo trên mock. Chưa đo thời gian khi panel
mở (kịch bản này chỉ đếm request và trạng thái panel).

## 2026-11-23 — Danh sách → hồ sơ: 6 request, 0 lần gọi lại ranking và danh sách

**Vấn đề cần số.** Trang hồ sơ dựng bộ đếm "hồ sơ k/n" và prev/next từ hàng đợi. Trước đây mỗi
lần mở hồ sơ từ danh sách là một lần gọi lại `GET /v1/assessments/ranking/latest/{position}`
và cả danh sách `GET /v1/applications` — hai request lớn, chỉ để biết thứ tự những hồ sơ mà
trang trước vừa hiển thị. Nay danh sách để lại thứ tự đó trong `sessionStorage`
(`hra-applicant-navigation:{position}`) và trang hồ sơ dùng luôn, chỉ deep link lạnh mới dựng lại.

**Script đo `tests/list-to-profile-requests.cjs`.** Mở danh sách
`/positions/p1/applicants?queue=NEEDS_VERIFICATION&sort=REVIEW_PRIORITY`, chờ bảng dựng xong,
rồi **mới** bật cửa sổ đếm và bấm dòng đầu tiên — nhờ vậy chỉ đếm request do việc mở hồ sơ sinh
ra. Đếm `GET` vào `/v1/`, tách riêng hai path cần theo dõi. Chạy 3 lần mỗi nhánh, in một dòng
`LIST_TO_PROFILE {json}`.

**Đối chứng.** Xoá `sessionStorage` rồi bấm link trong cùng tab **không** phải đối chứng:
`onClick` của link ghi lại ngữ cảnh ngay trước khi điều hướng, nên tab vẫn có đủ thứ tự (đã thử,
đo được 0 request ranking — tức là phép đo không chứng minh gì). Đối chứng đúng là mở **cùng URL
hồ sơ đó ở tab mới**: `sessionStorage` rỗng như một link gửi cho đồng nghiệp, trang buộc phải
dựng lại hàng đợi từ ranking + danh sách. Trong nhánh này script **bắt buộc** thấy đúng 1 request
mỗi path, nếu không thì tự fail.

| Nhánh | 3 lần | Trung vị tổng `GET /v1` | ranking | danh sách | Bỏ request của khung |
| --- | --- | --- | --- | --- | --- |
| Từ danh sách (có `sessionStorage`) | 6, 6, 6 | **6** | **0** | **0** | **4** |
| Đối chứng: tab mới (rỗng `sessionStorage`) | 9, 9, 9 | 9 | 1 | 1 | 6 |

Chênh lệch 2 request đúng bằng ranking + danh sách. Con số 9 của đối chứng có thêm một request
`/v1/dashboard/work-queue` vì tab mới dựng lại cả khung ứng dụng (huy hiệu việc cần làm); đây
không phải request của hồ sơ, nên bảng tách riêng cột "bỏ request của khung" (`/v1/auth/me`,
`/v1/dashboard/work-queue`) — 4 so với 6, vẫn đúng chênh 2. Các request còn lại của một lần mở
hồ sơ: chi tiết hồ sơ, bộ tiêu chí đã duyệt, ghi chú riêng, và một lần tải trước dữ liệu hồ sơ
kế (app-0 khi hồ sơ đang mở là app-5).

**Kiểm.** `eslint` hai file test; script pass 3/3 lần ở cả hai nhánh với số y hệt nhau. Chạy trên
bản build production (`next start`), Chromium headless 1440×900.

**Chưa kiểm.** Chưa chạy với backend thật: số request là số *lần gọi*, không phải độ trễ; mock
trả lời tức thì nên không đo được thời gian tiết kiệm. Chưa đo trên mạng chậm hay thiết bị thật.

## 2026-11-23 — ranking-context-mock hết chập chờn: chờ đúng hồ sơ kế, không chờ thẻ h1 có sẵn

**Triệu chứng.** Chạy 3 lần thì 1–2 lần fail với `Unexpected GET /v1/applications/app-2`. Trước
đây ghi nhận là "flaky sẵn từ trước" và bỏ qua — nay tìm ra nguyên nhân, không phải nhiễu mạng.

**Nguyên nhân thật.** Mục 10 bấm "Hồ sơ tiếp theo" để sang app-2, nhưng mock chỉ có dữ liệu cho
app-0. Hai lỗi cộng lại:
1. Bước đó chờ `getByRole('heading', { level: 1 })` — một thẻ **đã có sẵn từ trang trước**, nên
   điều hướng client-side vừa đổi URL là test chạy tiếp trong khi hồ sơ app-2 còn đang tải;
2. request `GET /v1/applications/app-2` (và request tải trước hồ sơ kế tiếp theo) rơi vào nhánh
   "Unexpected", được đẩy vào mảng lỗi **sau** khi test đã kiểm tra mảng đó ở cuối — mục 11 đã
   điều hướng sang danh sách và có thể huỷ request trước khi nó tới route handler. Vì vậy cùng
   một lỗi lúc hiện lúc không.

**Sửa.** (a) Dựng dữ liệu cho mọi hồ sơ `app-N` trong hàng đợi (chi tiết, lịch sử trạng thái,
profile) từ chính danh sách xếp hạng, để trang hồ sơ mở bình thường thay vì rơi vào nhánh lỗi;
(b) chờ đúng **tên ứng viên của app-2** ("Ứng viên 3") thay vì thẻ h1 chung, và assert thêm URL
là `/applicants/app-2`. Không nới assertion nào: mục 10 vẫn kiểm đủ bộ đếm, prev/next, queue
trong URL; chỉ thay điểm chờ sai bằng điểm chờ đúng.

**Kiểm.** `ranking-context-mock` chạy **3/3 pass** sau khi sửa (trước khi sửa: 3/3 fail trên máy
này — lỗi chỉ chập chờn khi máy nhanh hơn). `eslint` pass.

**Chưa kiểm.** Chưa chạy lặp nhiều chục lần để khẳng định "không bao giờ flaky"; 3/3 là mức đã
đo. Chưa chạy với backend thật.

## 2026-11-22 — Thanh dính trên hồ sơ gọn lại ở màn hẹp: 400px → 152px

**Vấn đề.** Ở 390px mọi thứ trên thanh dính nằm trong một hàng flex `wrap`: ngữ cảnh hàng
đợi (ba dòng), bộ đếm, tên tiêu chí, Xác nhận, Đánh dấu sai, Hoàn tất, Hồ sơ trước, Hồ sơ tiếp
theo. Mỗi nút cao ~44px (theme đặt `padding: 10px 20px`), nhãn dài như "Đã xử lý xong hồ sơ
này" chiếm gần trọn một hàng → mỗi thứ một hàng, thanh cao **400px, 47,4% chiều cao màn hình**
(844px).

**Thay đổi.** Dưới 600px thanh là ba hàng có chủ đích thay vì để flex tự xuống dòng:
1. ngữ cảnh hàng đợi (một dòng, cắt ellipsis) + bộ đếm tiêu chí chờ;
2. tên tiêu chí (co lại được) + **Xác nhận và Đánh dấu sai cùng một hàng**;
3. Hoàn tất + Hồ sơ trước + Hồ sơ tiếp theo.

Nhãn chỉ đổi ở màn hẹp, từ 600px trở lên vẫn là chữ đầy đủ: `Đúng`/`Sai` (Xác nhận/Đánh dấu
sai), `Hoàn tất`, `Trước`/`Tiếp`. Icon của ba nút điều hướng ẩn dưới 600px — nhờ vậy ba nút
vẫn nằm chung một hàng mà nhãn không phải đổi. Hai khoá mới `Đúng`/`Sai` đã thêm vào
`en.json` ("Correct"/"Wrong"); các nhãn còn lại dùng khoá có sẵn.

**Một lỗi tự gây ra, đã sửa.** Ban đầu hàng ngoài giữ `flexWrap: 'wrap'` trong khi dưới 600px
nó là `flex-direction: column` — wrap theo hướng cột biến ba hàng thành ba *cột* cạnh nhau:
thanh rộng 565px trong khổ 390px (đo được, nút Xác nhận rơi ra ngoài màn hình). Sửa bằng
`flexWrap: { xs: 'nowrap', sm: 'wrap' }`.

**Đo** — `tests/sticky-bar-height.e2e.cjs` đo chiều cao thanh, số hàng (gom theo tâm dọc, vì
chip 24px và nút 45px cùng hàng lệch `top`), và hai nút quyết định có cùng hàng không; in một
dòng `STICKY {json}`.

| Khổ | Trước | Sau |
| --- | --- | --- |
| 390×844 | 400px — 47,4% màn hình | **152px — 18,0%** |
| 1440×900 | 128px — 14,2% | 120px — 13,3% |

Xác nhận và Đánh dấu sai cùng hàng ở 390px: **không → có**. Không tràn ngang ở cả hai khổ.
Đặt `HRA_E2E_STICKY_MAX_XS=170` để chốt trần chiều cao ở màn hẹp.

**Kiểm.** `tsc --noEmit`, `eslint`, `npm run test:i18n` (3/3), `npm run test:unit` (131/131),
`npm run build`. E2E trên bản production: `sticky-bar-height`, `sticky-review-actions`,
`review-auto-advance`, `review-double-confirm`, `criterion-queue`, `mandatory-fail-finish`,
`prefetch-next-profile`, `finish-application` đều pass. Ảnh: `artifacts/sticky-bar-390.png` và
`artifacts/sticky-bar-1440.png` (đã xem: ba hàng, không cắt chữ, không tràn).

**Chưa kiểm.** Chưa đo trên điện thoại thật (chỉ Chromium ở 390×844). Chiều cao mỗi hàng
không thể giảm thêm nếu không đổi `padding: 10px 20px` của theme cho nút — nay thanh đã đúng
ba hàng, muốn thấp nữa phải bỏ bớt phần tử chứ không phải xếp lại.

## 2026-11-22 — Tải trước dữ liệu hồ sơ kế tiếp: mở hồ sơ kế 704 ms → 100 ms

**Vấn đề.** `PrefetchProfile` chỉ gọi `router.prefetch(href)` — đúng việc mà chính
`next/link` của nút "Hồ sơ tiếp theo" đã làm khi link nằm trong khung nhìn. Vì vậy nó không tạo
ra khác biệt đo được. Thứ thật sự làm HR chờ khi bấm `n` không phải route mà là
`GET /v1/applications/{id}`: trang hồ sơ hiện spinner cho tới khi request đó xong.

**Thay đổi.** Thêm `src/lib/profilePrefetch.ts`: tải trước chính request dữ liệu hồ sơ kế, giữ
trong bộ nhớ của tab (một mục cho mỗi hồ sơ, hết hạn sau 60 giây, dùng một lần, lỗi thì bỏ qua
— tải trước thất bại không được làm hỏng gì). `PrefetchProfile` giờ nhận `applicantId` và gọi
việc tải trước trong `runWhenIdle`, y như trước; `loadData(initial)` lấy bản đã tải trước để
**vẽ ngay** rồi vẫn gọi lại API — màn hình không bao giờ tin dữ liệu cũ vô điều kiện.

**Đo.** `tests/prefetch-next-profile.e2e.cjs`: mock giữ request dữ liệu hồ sơ kế **600 ms**, đo
từ lúc bấm `n` tới lúc hồ sơ kế vẽ xong (tên ứng viên + thẻ tiêu chí), 3 lần lấy trung vị.

| Bản | 3 lần đo (ms) | Trung vị |
| --- | --- | --- |
| Có tải trước dữ liệu | 94, 100, 104 | **100 ms** |
| Đối chứng: bỏ dùng bản tải trước | 704, 706, 704 | **704 ms** |

Bản đối chứng là cùng một mã nguồn với `takePrefetchedApplication` trả `null` (một dòng, đã
gỡ sau khi đo), nên chênh lệch ~600 ms đúng bằng độ trễ của request — không phải nhiễu. Test
còn kiểm rằng sau khi vẽ từ bản tải trước vẫn có **request thứ hai** đọc lại hồ sơ từ API.

**Kiểm.** `tsc --noEmit`, `eslint` hai file, `npm run build`. E2E trên bản build production:
`prefetch-next-profile`, `review-double-confirm`, `review-auto-advance`, `profile-lazy-panels`,
`criterion-queue`, `mandatory-fail-finish`, `sticky-review-actions` đều pass; `npm run test:unit`
pass.

**Chưa kiểm.** Chưa chạy với backend thật: 600 ms là độ trễ do test dựng nên. Trên mạng thật,
mức tiết kiệm đúng bằng thời gian `GET /applications/{id}` của hồ sơ đó; nếu backend trả lời
trong 30 ms thì lợi ích cũng chỉ 30 ms. Chưa đo trên điện thoại thật hay mạng chậm.

## 2026-11-22 — Bấm `1` hai lần trên một tiêu chí: một review, con trỏ nhảy một lần

**Vấn đề.** Đường bàn phím không biết `reviewSaving`. Nút "Xác nhận" đã bị disable khi
`reviewSaving !== null`, nhưng phím `1` chỉ hỏi "tiêu chí này còn chờ HR không" — mà tiêu chí
chỉ hết chờ sau khi backend trả lời. Hai cú bấm sát nhau trong lúc request đầu còn bay cùng thấy
"chưa xác minh" và cùng gửi `POST …/review`. Review là bảng append-only, nên lịch sử của tiêu chí
có hai dòng `CONFIRMED` của cùng một người ở cùng một thời điểm — một quyết định được ghi hai lần.

**Vì sao chỉ dựa vào state là không đủ.** `setReviewSaving(resultId)` chỉ có hiệu lực sau khi
React vẽ lại. Cú bấm thứ hai có thể tới trước lần vẽ đó và vẫn đọc giá trị cũ. Vì vậy chốt chặn
nằm ở một `ref` đổi ngay trong lần gọi đầu (`reviewSavingRef`), và `handleReview` bỏ qua mọi
lần gọi khi đã có một lần ghi đang chạy. Con trỏ chỉ nhảy ở nhánh sau `await`, nên bỏ qua lần
bấm trùng cũng có nghĩa con trỏ chỉ nhảy một lần.

**Phím xác nhận.** `reviewShortcut` nhận thêm điều kiện `activeAwaitingReview && !reviewInFlight`:
đang lưu thì `1` không phải lệnh và cũng không bị `preventDefault`. Không mất thao tác nào của
HR: con trỏ chỉ sang tiêu chí kế sau khi request xong, nên không có cú bấm hợp lệ nào bị nuốt.

**Test mới `tests/review-double-confirm.e2e.cjs`.** Mock giữ mỗi POST review 700ms để hai lần
bấm chắc chắn rơi vào lúc đang lưu (nếu không, test chỉ đo tốc độ mạng). Test bấm `1` hai lần
liền, rồi kiểm: đúng **một** POST cho `r-c2`, tiến độ `1/2` (không phải 2), con trỏ sang `c3`;
sau đó bấm hai lần vào nút xác nhận cho tiêu chí thứ hai và kiểm tổng cộng đúng hai review
(`r-c2`, `r-c3`), không có dòng trùng.

**Đối chứng.** Tạm bỏ chốt chặn (`if (false) return;` + `canConfirm` không xét `reviewInFlight`)
rồi chạy lại test: **fail với `2 !== 1`** — đúng lỗi được báo. Khôi phục chốt chặn thì pass.

**Kiểm.** `tsc --noEmit`, `eslint` trên file trang, `npm run test:unit` (131/131), `npm run build`.
E2E trên bản build production: `review-double-confirm`, `review-auto-advance`, `mandatory-fail-finish`,
`sticky-review-actions` đều pass.

**Chưa kiểm.** Chưa chạy với backend thật (mock API trả lời trong trình duyệt). Con số 700ms là
của test, không phải độ trễ thật của endpoint; chốt chặn không phụ thuộc con số đó vì nó khoá
theo thời gian request chứ không theo đồng hồ.

## 2026-11-21 — Xác nhận tiêu chí: 0 request tải lại profile, và script đo tự chặn nếu tái diễn

**Truy vết.** Gắn tạm một dấu vết vào `load()` của `CandidateProfilePanel` để ghi lại
stack của mọi lần gọi, rồi chạy lại vòng duyệt: chỉ có **một** lần gọi, stack trỏ đúng vào
`onChange` của `AccordionSummary` (cú bấm mở panel), không có lần nào phát sinh từ việc xác
nhận tiêu chí. Đo trên hồ sơ 6 tiêu chí, panel **đang mở**, bấm xác nhận cả 6: `0,0,0,0,0,0`
request `/profile` — tổng cộng 1 cho cả lượt xem (lúc mở panel).

**Vì sao trước đây là 4.** Hai panel anh em (`CandidateProfilePanel`, `HRNotesPanel`) dùng chung
`key={applicantId}`. Khi hai phần tử cùng key nằm cạnh nhau, React gắn lại key chứ không giữ
định danh, nên mỗi lần trang render lại sau một lần xác nhận là subtree bị mount lại: 4 instance
panel cùng sống (mount mà không unmount theo nghĩa state bị bỏ), mỗi instance tự gọi `/profile`
khi mount. Đã sửa bằng key riêng (`profile-…`/`notes-…`) và panel chỉ tải ở lần mở accordion
đầu tiên. Con số "4" trong nhật ký trước là **4 lần lúc mở hồ sơ trên bản `bf16e19`**, cộng
thêm 2 lần sau mỗi lần xác nhận (13 lần cho một lượt xem).

**Chốt chặn.** `tests/review-loop-metrics.cjs` giờ in thêm `requestsPerConfirm` (số request sau
mỗi lần bấm xác nhận) và `getRequestCounts` (đếm theo path thay vì chỉ liệt kê), và **throw**
nếu trong vòng xác nhận có bất kỳ `GET …/profile` hay `GET …/status-events` nào. Chạy lại:
`requestsPerConfirm: [1, 1]` (đúng một POST review mỗi lần), `profileOrHistoryRequests: 0`,
`getRequests: 0`.

**Chưa kiểm.** Chưa chạy với backend thật. Con số trên đo trên Chromium headless với mock API;
nếu panel bị ép mount lại bằng một thay đổi khác trong tương lai, chốt chặn trong script sẽ báo
ngay chứ không im lặng như trước.

## 2026-11-21 — E2E cho nhánh hồ sơ trượt tiêu chí bắt buộc khi hoàn tất

**Vì sao cần.** Quy tắc "có tiêu chí MUST_HAVE kết luận NO_MATCH → chọn sẵn Loại vòng sàng
lọc" mới chỉ có unit test cho `suggestFinishStatus()`. Phần giao diện — hộp thoại có thật sự
chọn sẵn trạng thái đó, nút hoàn tất có bị chặn khi thiếu lý do, và có PATCH nào lọt ra trước
đó không — chưa có test nào chạy qua.

**Fixture mới.** `app-must-fail`: hồ sơ `IN_REVIEW`, tiêu chí c1 là MUST_HAVE nhưng kết luận
`NO_MATCH` (không có bằng chứng Python cho dịch vụ production) và vẫn chờ HR xác minh; c2 là
tiêu chí ưu tiên, không cần xác minh. Thêm route PATCH `/v1/applications/app-must-fail/status`
để ghi lại thân request. Các route cũ không đổi: `app-must-fail` không nằm trong danh sách
xếp hạng nên bộ đếm và prev/next của những test khác giữ nguyên.

**Test mới `tests/mandatory-fail-finish.e2e.cjs`.**
1. Mở hộp thoại hoàn tất → ô trạng thái hiện sẵn **Loại vòng sàng lọc**, dòng đề xuất nói rõ
   "Có tiêu chí bắt buộc chưa đạt… lý do vẫn cần bạn nhập", cảnh báo còn 1 tiêu chí chờ.
2. Nút hoàn tất **bị chặn**; nhập toàn khoảng trắng vẫn chặn.
3. Trước đó **không có PATCH trạng thái** và không có POST review nào; bấm cưỡng bức vào nút
   đang chặn cũng không gửi gì.
4. Nhập lý do → nút mở → gửi đúng một PATCH `REJECTED_SCREENING` kèm lý do, và một POST
   `CONFIRMED` cho tiêu chí bắt buộc; sau đó rời hồ sơ.

**Kiểm.** Test mới pass. Chạy lại không hồi quy: `finish-application`, `review-auto-advance`,
`sticky-review-actions`, `criterion-queue`, `capabilities`, `verify-only`, `duplicate-compare`,
`ranking-compact-mock`, `profile-lazy-panels`; unit **131/131**.

**Chưa kiểm.** Chưa chạy với backend thật (transition matrix và gate quyền là của mock, dựng
theo `APPLICATION_TRANSITIONS` trong `src/lib/applicationStatus.ts`). `ranking-context-mock`
vẫn flaky sẵn từ trước, lần này không chạy lại.

## 2026-11-21 — Thanh dính: hiện tên tiêu chí đang chọn, không phụ thuộc tooltip

**Vấn đề.** Trên thanh dính của hồ sơ, hai nút "Xác nhận"/"Đánh dấu sai" chỉ nói đang quyết
định cho tiêu chí nào qua tooltip. Trên điện thoại không có hover, nên HR thấy hai nút mà
không biết chúng áp cho tiêu chí nào — phải cuộn xuống thẻ bằng chứng để đoán.

**Sửa.** Thêm một chip nhỏ ngay cạnh hai nút, hiện `Đang chọn: <tên tiêu chí>`, cập nhật theo
tiêu chí đang chọn (kể cả khi tự nhảy sang tiêu chí kế sau khi xác nhận). Tên dài bị cắt bằng
ellipsis trên một dòng: tối đa 200px ở màn hẹp, 360px từ `sm` trở lên. Tooltip giữ nguyên cho
chuột. Dùng lại khoá i18n có sẵn `Đang chọn: {0}`, không thêm chuỗi mới.

**Kiểm.** `sticky-review-actions.e2e.cjs` (chạy ở 390px và 1440px) thêm assert: chip hiện tên
tiêu chí, nằm trong bề ngang màn hình, cao ≤ 30px (một dòng), `text-overflow: ellipsis`, và
sau khi xác nhận thì tên đổi sang tiêu chí kế. Không tràn ngang ở cả hai bề rộng. Ảnh chụp
390px/1440px xem bằng mắt: chip "Đang chọn: Thiết kế cơ sở..." nằm cùng dòng với nút Xác nhận.

**Chưa kiểm.** Chưa thử trên máy thật/trình duyệt di động thật (chỉ Chromium headless 390px).
Thanh dính ở 390px vẫn xếp mỗi nút một dòng (tình trạng có từ trước, chip không làm tăng số
dòng vì nó nằm chung dòng với "Xác nhận"), nên thanh vẫn cao — chưa gộp bớt nút.

## 2026-11-21 — Panel Profile ứng viên: không còn tự gọi lại `/profile` khi state hồ sơ đổi

**Đo lại đúng chỗ nghi ngờ.** Mở hồ sơ 6 tiêu chí, mở panel Profile, xác nhận 3 tiêu chí,
đổi tiêu chí đang chọn, mở panel ghi chú, đóng/mở lại panel — đếm `GET /v1/applications/{id}/profile`:

| Thời điểm | Trước (`bf16e19`) | Hiện tại |
|---|---|---|
| Vừa mở hồ sơ | 4 | **0** |
| Mở panel lần đầu | 4 | **1** |
| Sau 3 lần xác nhận tiêu chí | 10 | **1** |
| Sau khi đổi tiêu chí đang chọn | 12 | **1** |
| Sau khi mở panel ghi chú | 13 | **1** |
| Đóng rồi mở lại panel | 13 | **1** |

**Nguyên nhân (đã sửa ở lần trước, nay đo lại và khoá bằng test).** Hai panel anh em
(`CandidateProfilePanel` và `HRNotesPanel`) dùng chung `key={applicantId}` nên React gắn lại
key sai: mỗi lần trang render lại (mỗi lần xác nhận, đổi tiêu chí, mở hộp thoại) subtree bị
mount lại, panel nạp lại từ đầu và cộng dồn — 4 request ngay khi mở, rồi +2 mỗi lần xác nhận.
Đã đổi key thành `profile-${applicantId}` / `notes-${applicantId}`, và panel chỉ tải ở lần mở
accordion đầu tiên (`loadedOnce`), không tải khi mount. Vì vậy phần "tải lại còn sót" không
còn tái hiện: state đổi bao nhiêu lần cũng chỉ một request.

**Khoá lại.** `tests/profile-lazy-panels.e2e.cjs` thêm bước: mở panel, xác nhận 3 tiêu chí,
đổi tiêu chí, mở panel ghi chú → số request `/profile` phải giữ nguyên 1. Không còn đường
nào âm thầm quay lại hành vi cũ.

**Số toàn vòng (script baseline, 3 lần):** 20–22 request cả vòng, 8–9 request lúc mở,
`GET …/profile` **0** lần (baseline đầu tiên: 16 lần), mở tới dùng được 449–463 ms.

**Chưa kiểm.** Chưa chạy với backend thật. `ranking-context-mock` vẫn flaky đúng như trước
(2/3 lần pass, lỗi `Unexpected GET /v1/applications/app-2` ở bước chuyển sang danh sách sau
khi bấm "Hồ sơ tiếp theo"); lỗi này có từ trước lần sửa này.

## 2026-11-21 — Link "Mở hồ sơ" từ màn duyệt theo tiêu chí không kèm hàng đợi lạ

**Vấn đề.** Trên màn duyệt một tiêu chí, mỗi dòng có nút "Mở hồ sơ", nhưng href bị
gắn cứng `?queue=NEEDS_VERIFICATION&sort=REVIEW_PRIORITY`. Mở ra thì hồ sơ hiện bộ đếm
"hồ sơ k/n trong hàng đợi đang xem" của một hàng đợi HR không hề mở, và prev/next nhảy
theo hàng đợi đó — sang những hồ sơ không liên quan tới tiêu chí đang duyệt.

**Sửa.** `profileHref` giờ là đường dẫn hồ sơ thuần cộng đúng tiêu chí:
`/positions/{id}/applicants/{appId}#criterion-{criterionId}`. Bỏ import
`applicantProfileHref`/`ApplicantQueue`/`ApplicantSort` không còn dùng. Anchor vẫn trỏ
vào `id="criterion-…"` của `EvidenceCard` nên sang đó là đứng ngay tiêu chí đang duyệt;
không còn hàng đợi, hồ sơ hiện "Đang xem chi tiết hồ sơ" thay vì số thứ tự của hàng đợi sai.

**Kiểm.** `tsc` sạch, `eslint` sạch, `next build` OK. `tests/criterion-queue.e2e.cjs` nay
assert đúng `href` là `/positions/p1/applicants/app-1#criterion-c2` và không chứa
`queue=`/`sort=`; pass. `profile-lazy-panels` pass lại (không hồi quy ở trang hồ sơ).

## 2026-11-21 — Mở hồ sơ: cắt/hoãn request không cần cho màn hình đầu

**Đo lại trước khi sửa.** Mở hồ sơ (deep link `?queue=…&sort=…`) gọi 12 request: hồ sơ,
`/profile`, `/private-notes`, `/status-events`, rubric, ranking + toàn bộ danh sách ứng viên
(để dựng prev/next và bộ đếm "hồ sơ k/n"), `auth/me` (layout và trang), badge `work-queue`,
và prefetch RSC hồ sơ kế. Trong đó `/profile` và `/status-events` là hai khối accordion **đang
đóng**, chưa ai đọc.

**Đã làm.**

- **Profile ứng viên**: chỉ tải ở lần mở accordion đầu tiên, sau đó giữ nguyên; đóng rồi mở
  lại không tải lại. Panel không còn tự tải khi mount.
- **Lịch sử trạng thái**: tải khi mở accordion (có spinner trong lúc chờ), không tải trong
  `loadData` nữa.
- **Ghi chú nội bộ**, **auth/me của trang** (chỉ để hiện người phụ trách + nút nhận hồ sơ),
  **badge work-queue trên header**, và **prefetch hồ sơ kế** đều chạy khi trình duyệt rảnh
  (`runWhenIdle` trong `src/lib/idle.ts`, có hàm huỷ khi rời trang).
- **Prev/next và bộ đếm hàng đợi**: danh sách ứng viên đã để lại thứ tự id trong
  sessionStorage, nên đi từ danh sách sang hồ sơ không cần gọi lại ranking + danh sách nữa
  (0 request thay vì 2). Deep link lạnh vẫn dựng lại như cũ — nếu không, bộ đếm "hồ sơ 1/3"
  xuất hiện muộn và test prev/next cũ đỏ.

**Đo lại** (script baseline, 3 lần, trung vị; thêm mốc `profileFirstPaintMs` = lúc hồ sơ dùng
được, không chờ mạng lắng):

| Số đo | Trước | Sau | Đổi |
|---|---|---|---|
| Request lúc mở hồ sơ | 12 | **9** | −3 |
| — `GET …/profile` lúc mở | 1 | **0** | chỉ tải khi mở accordion |
| — `GET …/status-events` lúc mở | 1 | **0** | chỉ tải khi mở accordion |
| Tổng request cả vòng | 27 | **21** | −6 |
| Mở tới lúc dùng được | 522 ms | **444 ms** | −15% |
| Mở tới khi mọi request xong | 1135 ms | **1067 ms** | −6% |
| Số phím cả vòng | 7 | 7 | không đổi |
| 6 lần xác nhận | 512 ms | 465 ms | −9% |
| Sang hồ sơ kế | 148 ms | 137 ms | −7% |

**Đọc số cho đúng.** Con số "1,7 s" của lần đo đầu là mốc *mạng lắng* (networkidle), không
phải lúc HR dùng được: đo riêng thì hồ sơ dùng được sau ~500 ms cả trước và sau khi sửa, vì
các request kia chạy song song chứ không chặn. Vì vậy giá trị thật của lần này là **ít request
hơn** (27 → 21, mở trang 12 → 9) và **không tải dữ liệu cho khối đang đóng** — không phải
màn hình nhanh hơn 1,7 s. Mốc networkidle gần như không đổi (1135 → 1067 ms) đúng vì việc
hoãn vẫn hoàn tất trong cửa sổ đó.

**Kiểm.** `tsc` sạch, `eslint` sạch, `next build` OK, unit **131/131**, i18n **3/3**. E2E mới
`tests/profile-lazy-panels.e2e.cjs`: mở hồ sơ không gọi `/profile` hay `/status-events`; mở
profile tải đúng 1 lần, đóng/mở lại không tải lại; mở lịch sử tải đúng 1 lần. Các e2e cũ chạy
lại đều pass: `review-auto-advance`, `sticky-review-actions`, `finish-application`,
`verify-only`, `capabilities`, `duplicate-compare`, `criterion-queue`, `ranking-context-mock`,
`ranking-compact-mock`, `duplicate-warning`.

**Chưa kiểm.** Chưa thử backend thật. Số request của đường "đi từ danh sách" (bỏ được 2 request
ranking + danh sách) chưa đo riêng bằng script — script chỉ đo deep link lạnh. Còn 2 request
`auth/me` mỗi lần điều hướng (layout + trang) — gộp được nhưng cần chia sẻ state người dùng qua
context, chưa làm.

## 2026-11-21 — Sửa: mỗi lần xác nhận kéo theo tải lại `/profile` (16 → 1)

**Triệu chứng.** Baseline ghi 16 lần `GET /v1/applications/app-0/profile` cho một hồ sơ 6 tiêu
chí, thêm 1–2 lần sau mỗi lần xác nhận.

**Nguyên nhân.** Không phải hiệu ứng của panel tải lại. Đo trực tiếp trên trang (log tạm
`PANEL%MOUNT`, đếm `.MuiAccordion-root`):
`PAGE%MOUNT 1` rồi mỗi lần trang render lại, `CandidateProfilePanel` **mount thêm một lần
nữa** — sau khi mở trang có 4 khung "Profile ứng viên" nằm cạnh nhau trong DOM, bấm `j` thành
5. Mỗi bản là một instance thật, tự gọi `/profile` khi mount, bản cũ không bị gỡ.

Lý do là **hai children anh em trùng `key`**:

```jsx
{caps.viewCv && <CandidateProfilePanel key={applicantId} … />}
{caps.manageHrNotes && <HRNotesPanel key={applicantId} … />}
```

Hai panel cùng key `app-0` trong cùng một children array. React gặp key trùng thì không
reconcile được hai fiber đó với nhau và mount thêm bản mới thay vì cập nhật bản cũ; bản cũ
vẫn nằm trong DOM. Panel hồ sơ ứng viên là bản duy nhất tự tải dữ liệu khi mount nên mọi
request thừa đều rơi vào nó.

**Sửa.** Đổi key theo loại panel, vẫn giữ `applicantId` để panel được dựng lại khi đổi hồ sơ:
`key={`profile-${applicantId}`}` và `key={`notes-${applicantId}`}` (kèm chú thích trong code).
Không đổi dữ liệu, không thêm endpoint, không sửa cách ghi review.

**Đo lại bằng đúng script baseline** (3 lần, trung vị):

| Số đo | Trước | Sau | Đổi |
|---|---|---|---|
| Khung "Profile ứng viên" trong DOM | 4–5 | **1** | hết trùng lặp |
| `GET …/profile` mỗi hồ sơ | 16 | **1** | −15 |
| Tổng request trong vòng | 43 | **27** | −16 |
| — GET | 37 | **21** | −16 |
| — POST review | 6 | 6 | không đổi |
| Request để mở hồ sơ | 15 | **12** | −3 |
| Request sau mỗi lần xác nhận | ~4,7 | **~2,5** | −2,2 |
| Số phím cả vòng | 7 | 7 | không đổi |
| 6 lần xác nhận | 926 ms | **505 ms** | −45% |
| Mỗi lần xác nhận | 154 ms | **84 ms** | −45% |
| Sang hồ sơ kế | 257 ms | **141 ms** | −45% |
| Mở hồ sơ tới dùng được | 1704 ms | **1160 ms** | −32% |
| Thời gian ở trong hồ sơ | 2157 ms | **1490 ms** | −31% |

Request còn lại: `GET …/profile` 1, `status-events` 1, `private-notes` 1, `applications/app-0`
1, `criteria` 2, `ranking` 2, `auth/me` 4 (mỗi lần điều hướng một lần — layout), 6 POST review,
và 4 request của hồ sơ kế khi bấm `n`. Không còn request nào lặp theo số tiêu chí.

**Kiểm.** `tsc --noEmit` sạch, `eslint` sạch trên hai file; `next build` OK. E2E chạy lại đều
pass: `review-auto-advance`, `sticky-review-actions`, `finish-application`, `verify-only`,
`capabilities`, `duplicate-compare`, `criterion-queue`, và script đo baseline (assert đúng 6
POST, không có request lạ).

**Chưa kiểm.** Chưa thử trên backend thật; số thời gian phụ thuộc máy nên so theo trung vị
3 lần. Việc bấm `n` vẫn kéo 4 request của hồ sơ kế (`applications`, `status-events`,
`private-notes`, `profile`) — đó là lần tải đầu của hồ sơ mới, không phải tải lại.

## 2026-11-21 — Baseline: vòng duyệt một hồ sơ 6 tiêu chí

**Đo trước khi sửa gì.** Ba lần chạy `frontend/tests/measure-review-loop.e2e.cjs` trên mock
e2e sẵn có (`installMockApi`), hồ sơ app-0 được nối thêm c5/c6 ngay trong response của mock
để có đúng 6 tiêu chí đều đang chờ — không sửa fixture dùng chung, không thêm endpoint.
Cùng một kịch bản mỗi lần: mở hồ sơ trong hàng đợi `NEEDS_VERIFICATION` → bấm `1` cho tới
khi hết tiêu chí chờ → bấm `n` sang hồ sơ kế → đọc event `recordUxEvent` trong
`localStorage['hra-ux-events']`. Đếm request bằng `page.on('request')` chỉ trên trang đo.

| Số đo | Lần 1 | Lần 2 | Lần 3 | Trung vị |
|---|---|---|---|---|
| Số phím cho cả vòng | 7 | 7 | 7 | **7** |
| — phím xác nhận (`1`) | 6 | 6 | 6 | 6 |
| — phím sang hồ sơ kế (`n`) | 1 | 1 | 1 | 1 |
| — phím thừa | 0 | 0 | 0 | 0 |
| Tổng request trong vòng | 44 | 43 | 42 | **43** |
| — GET | 38 | 37 | 36 | 37 |
| — POST (ghi review) | 6 | 6 | 6 | 6 |
| Request để mở hồ sơ | 15 | 15 | 13 | 15 |
| Request phát sinh sau mỗi lần xác nhận | 4,8 | 4,7 | 4,8 | ~4,7 |
| 6 lần xác nhận (ms) | 1132 | 926 | 744 | **926** |
| Mỗi lần xác nhận (ms) | 189 | 154 | 124 | **154** |
| Từ hồ sơ này sang hồ sơ kế (ms), đồng hồ script | 294 | 247 | 257 | **257** |
| Khoảng lặng `PROFILE_CLOSED` → `PROFILE_OPENED` (ms) | 7 | 3 | 4 | 4 |
| Mở hồ sơ tới lúc dùng được (ms) | 1809 | 1506 | 1704 | 1704 |
| Thời gian ở trong hồ sơ (`duration_ms`) | 2526 | 2157 | 2064 | 2157 |

**Đọc số.**

- Vòng 6 tiêu chí tốn **7 phím**: mỗi tiêu chí một phím, không có phím thừa — vì xác nhận
  tự nhảy sang tiêu chí chờ kế tiếp, và `n` sang hồ sơ sau. Đây là mức sàn cho kịch bản
  "mỗi tiêu chí một quyết định riêng"; muốn ít hơn nữa thì phải gộp quyết định, không phải
  bớt phím điều hướng.
- **43 request cho một hồ sơ 6 tiêu chí** là chỗ còn nhiều: chỉ 6 request là ghi thật
  (một POST mỗi tiêu chí). Trong 37 GET, `GET /v1/applications/app-0/profile` bị gọi **16
  lần** — 1–2 lần lúc mở và thêm 1–2 lần sau *mỗi* lần xác nhận, tức khoảng 2,3 request
  thừa cho mỗi tiêu chí. Hồ sơ (`/v1/applications/app-0`), ghi chú riêng và lịch sử trạng
  thái thì **không** bị gọi lại sau khi xác nhận — phần bỏ tải lại toàn hồ sơ vẫn giữ.
- Thời gian **từ hồ sơ này sang hồ sơ kế là ~257 ms** (đồng hồ script, tới khi hồ sơ mới
  dựng xong). Khoảng lặng giữa hai event `recordUxEvent` chỉ 4 ms vì `PROFILE_OPENED` bắn
  ngay khi component mount, trước khi dữ liệu về — nên số dùng để so là 257 ms, còn 4 ms
  chỉ nói rằng điều hướng nội bộ không có quãng trắng.
- Mở một hồ sơ tốn ~1,7 s và HR ở trong hồ sơ ~2,2 s: với hồ sơ 6 tiêu chí, phần lớn thời
  gian là chờ mở, không phải ra quyết định.

**Cách đo lại.** `HRA_E2E_BASE_URL=… node tests/measure-review-loop.e2e.cjs` in ra một dòng
`BASELINE {json}` (thêm `HRA_MEASURE_DEBUG=1` để in request phát sinh sau từng lần xác nhận).
Số phụ thuộc máy chạy nên so theo trung vị của 3 lần, không so một lần.

## 2026-11-21 — Duyệt một tiêu chí trên nhiều hồ sơ

**Vấn đề.** Khi một tiêu chí bị nghi trên cả loạt hồ sơ (ví dụ "thiết kế cơ sở dữ
liệu quan hệ"), việc của HR là đọc *cùng một chỗ* trên vài chục CV rồi quyết
từng hồ sơ. Trang hồ sơ làm đúng một hồ sơ một lúc: mở hồ sơ, cuộn tới tiêu chí,
bấm, quay lại danh sách — lặp lại đến hết danh sách, và mỗi vòng đều phải tìm
lại đúng tiêu chí đó.

**Đã làm.**

- **Màn mới** `/positions/[id]/applicants/by-criterion`, mở từ nút `Duyệt theo
  tiêu chí` ngay cạnh `Mở hồ sơ kế tiếp` ở danh sách ứng viên.
- **Danh sách dựng từ ranking, không thêm endpoint**: một request ranking đã kèm
  kết quả từng tiêu chí của mọi hồ sơ, nên màn hiện ngay tên, hạng, kết luận và
  điểm của tiêu chí đang chọn. Chọn tiêu chí bằng ô chọn ở đầu màn; mặc định
  nhảy vào tiêu chí đầu tiên còn hồ sơ chờ, không phải tiêu chí đầu danh sách.
- **Mỗi dòng một hồ sơ, một trích dẫn** của tiêu chí đó (nguyên văn + số trang),
  kèm `Xác nhận` / `Đánh dấu sai` tại chỗ. Ghi vẫn qua
  `POST /assessments/results/{id}/review` sẵn có; đánh dấu sai bắt buộc nêu lý do.
- **Chỉ tiêu chí đang chờ mới cho thao tác**: dòng không bị gắn cờ ghi "Không
  cần xác minh", dòng đã kiểm ghi "Đã xác nhận"/"Đã đánh dấu sai" và khoá nút,
  thiếu quyền ghi review thì ghi rõ. Nút ở trạng thái khoá thay vì bấm rồi báo lỗi.
- **Mở hồ sơ đầy đủ** từ đúng dòng, kèm `#criterion-…` để sang đó là đứng ngay
  tiêu chí đang duyệt.
- **Tiến độ theo tiêu chí**: "Đã xác minh 2/12 hồ sơ theo tiêu chí này", đếm trên
  hồ sơ bị gắn cờ chứ không phải mọi dòng.
- **Tải theo trang**: mỗi trang 8 hồ sơ, chỉ tải chi tiết (trích dẫn, `result_id`,
  lần kiểm trước) của những dòng đang hiện; tiêu chí có hàng trăm hồ sơ không
  sinh hàng trăm request ngay khi mở màn.

**Kiểm thử đã chạy.** `tsc --noEmit` sạch; `eslint` sạch; unit **128/128** (4 test
mới cho `criterionQueue`: lọc theo xét tuyển + có kết quả, giữ thứ tự hạng và cờ
xác minh, sáu trạng thái dòng, đếm tiến độ chỉ trên hồ sơ bị gắn cờ); i18n **3/3**
(19 khoá mới); `next build` OK. e2e mới `tests/criterion-queue.e2e.cjs` pass: nút
trong danh sách mở đúng màn, mặc định chọn tiêu chí đang chờ, "0/12" và trang đầu
"8/12", trích dẫn + trang 3 của app-0, xác nhận tại chỗ → "Đã xác nhận", khoá nút
của dòng đó, "1/12", **hồ sơ khác vẫn chờ**, POST đúng `app-0:r-c2`/CONFIRMED;
chuyển sang tiêu chí không gắn cờ → "Không cần xác minh", "0/0", không ghi gì;
quay lại thì quyết định cũ còn; đánh dấu sai thiếu lý do bị khoá, có lý do thì
ghi REJECTED kèm lý do, "2/12"; link mở hồ sơ đúng `app-1` + `#criterion-c2`;
chưa bấm "Tải thêm" thì không gọi quá 8 chi tiết, bấm thì đủ 12. Fixture: hồ sơ
trong ranking giờ có `result_id` riêng từng hồ sơ (`app-0:r-c2`) để xác minh một
dòng không biến các dòng khác thành đã kiểm. Các e2e cũ chạy lại đều pass:
`finish-application`, `duplicate-warning`, `duplicate-compare`,
`sticky-review-actions`, `verify-only`, `review-auto-advance`, `capabilities`,
`ranking-compact-mock`, `ranking-context-mock`.

**Chưa kiểm.** Chưa thử trên backend thật. Ở 390px màn mới chưa được đo bằng mắt
(dòng dùng flex-wrap nên sẽ xuống hàng). `ranking-context-mock` một lần báo
`Unexpected GET /v1/applications/app-2` ngay sau khi điều hướng khỏi trang hồ sơ —
request của trang đang bị rời đi, chạy lại hai lần đều pass; test đã có từ trước và
không liên quan màn mới. `applicants-large-list-mock` vẫn fail vì mock riêng thiếu
route `/duplicate-signals` (có từ trước).

## 2026-11-21 — So sánh cạnh nhau hai hồ sơ bị gắn cờ trùng

**Vấn đề.** Cảnh báo trùng chỉ nêu tên hồ sơ đối ứng và một link sang hồ sơ đó.
Muốn quyết định, HR mở A, đọc định danh và bốn tiêu chí, quay lại danh sách, mở B
rồi so trong đầu — trong khi hai CV cần được nhìn ở hai trang khác nhau cùng lúc.
Không có chỗ nào trong hệ thống đặt hai hồ sơ cạnh nhau.

**Đã làm.**

- **Màn so sánh mới** `/positions/[id]/applicants/compare?left=…&right=…`. Cặp
  đang xem nằm trong URL, nên mở lại, tải lại hay gửi cho đồng nghiệp vẫn đúng
  hai hồ sơ; vào thiếu tham số thì màn nói rõ thay vì đoán.
- **Định danh hai bên**: tên, ID, email, điện thoại, tệp gốc, trạng thái, điểm
  tổng hợp, độ phủ bằng chứng, và link mở hồ sơ đầy đủ — đây là phần trả lời
  "có phải cùng một người không".
- **CV mỗi bên một khung riêng**: tải khi được yêu cầu, con trỏ trang độc lập,
  bấm trích dẫn ở tiêu chí nào thì chỉ khung của bên đó nhảy tới trang đó. Hai
  bên giữ được hai trang khác nhau — đúng thứ không làm được khi mở A rồi mở B.
- **Kết quả tiêu chí theo dòng**, hai bên trong cùng một dòng, kèm chip kết luận,
  điểm, trích dẫn và nút mở trang CV. Dòng hai bên kết luận khác nhau được đánh
  dấu "Khác kết luận", và đầu màn ghi tổng: "Khác kết luận ở 3/4 tiêu chí".
- **Lý do bị gắn cờ**: loại tín hiệu và độ tin cậy lấy từ `/duplicate-signals`,
  đối chiếu đúng cặp (bảng tín hiệu có thể ghi ngược thứ tự hai bên).
- **Lối vào**: trên dòng bị gắn cờ ở danh sách ứng viên, cạnh tên hồ sơ đối ứng
  có nút `So sánh`.

**Phạm vi giữ nguyên.** Màn so sánh không có hành động ghi nào — không đổi trạng
thái, không ghi review, không tự "dismiss" tín hiệu trùng (backend chưa có
endpoint đó). Mọi quyết định vẫn thực hiện ở hồ sơ, nơi đã có sẵn luồng và quyền.

**Kiểm thử đã chạy.** `tsc --noEmit` sạch; `eslint` sạch trên 3 file; unit
**127/127** (thêm 3 test cho `duplicateCompare`: dựng URL, tìm tín hiệu không phụ
thuộc thứ tự, đếm tiêu chí khác kết luận); i18n **3/3**; `next build` OK; e2e mới
`tests/duplicate-compare.e2e.cjs` pass với `DUPLICATE_SIGNALS` trong fixture (nút
So sánh trên dòng mở đúng cặp, hai định danh khác email, tín hiệu "Cùng email ·
92%", "Khác kết luận ở 3/4", c4 không bị đánh dấu, chưa tải CV nào khi mở màn, bấm
trích dẫn bên trái → khung trái trang 3 và chỉ 1 request CV, bấm bên phải → khung
phải trang 5 còn trái vẫn trang 3, nút "Trang sau" của khung trái không kéo khung
phải). Fixture có thêm `COMPARE_APPLICATIONS` để hai bên thật sự khác nhau.
Các e2e danh sách đã chạy lại và pass: `duplicate-warning`, `ranking-compact-mock`,
`ranking-context-mock`.

**Chưa kiểm.** Chưa thử trên backend thật; đề xuất/dữ liệu đều từ mock.
`applicants-large-list-mock.e2e.cjs` đang fail vì mock riêng của nó thiếu route
`/duplicate-signals` — lỗi có từ trước lượt này (trang danh sách đã tự tải tín hiệu
trùng từ trước), không liên quan màn so sánh. Màn so sánh chưa được đo ở 390px;
bố cục dựa trên Grid `xs=12` nên hai bên xếp chồng, chưa kiểm bằng mắt.

## 2026-11-21 — Hồ sơ: hộp thoại hoàn tất chọn sẵn đề xuất, thanh dính mang việc chính

**Vấn đề.** Hai chỗ cuối cùng còn bắt HR làm thêm một bước mà máy đã biết câu trả lời.

1. **Hộp thoại hoàn tất luôn mở ở "Giữ nguyên trạng thái".** Hồ sơ đã có điểm tổng
   hợp, kết quả từng tiêu chí và bước chuyển hợp lệ, nhưng HR vẫn phải mở ô chọn,
   tự suy ra nên chuyển sang đâu, rồi bấm thêm một ô "Tôi đã đối chiếu…" trước khi
   nút hoàn tất bấm được — ba thao tác cho một quyết định đã nằm sẵn trong dữ liệu.
2. **Việc chính của màn hồ sơ nằm ngoài tầm tay.** Trạng thái "còn mấy tiêu chí
   chờ" chỉ có trong khối tiến độ phía trên, còn hai nút Xác nhận/Đánh dấu sai chỉ
   nằm trong từng thẻ bằng chứng. HR đọc CV ở cột phải (trên điện thoại là cuộn
   xuống dưới), muốn quyết định phải cuộn ngược lên đúng thẻ đang xem.

**Đã làm.**

- **Chọn sẵn trạng thái đề xuất.** `suggestFinishStatus` (hàm thuần, có unit test)
  chọn theo thứ tự: có tiêu chí bắt buộc chưa đạt → loại ở vòng sàng lọc; hồ sơ
  còn "Mới" → "Đang xem"; "Đang xem" và điểm ≥ 60 → Shortlist; đã shortlist →
  phỏng vấn; còn lại giữ nguyên. Hộp thoại mở với giá trị đó, hiện một dòng nói vì
  sao, và HR vẫn đổi được. Đề xuất loại **không** bỏ qua bước nhập lý do.
- **Gộp cam kết vào nút chính.** Bỏ ô đánh dấu; thay bằng một dòng ngay trên nút
  ("Nút bên dưới là xác nhận của bạn: đã đối chiếu 2 tiêu chí trên với CV…") và
  nhãn nút "Xác nhận đã kiểm 2 tiêu chí và hoàn tất". Vẫn là một hành động rõ ràng
  của HR — bấm nút chính là cam kết, không tự động coi việc mở hộp thoại là đã kiểm.
  Điều kiện chặn duy nhất còn lại: loại hồ sơ mà chưa nêu lý do.
- **Thanh dính mang việc chính.** Thêm chip `Còn 2/2 tiêu chí chờ` (→ `Đủ 2/2 tiêu
  chí` khi xong) và hai nút `Xác nhận` / `Đánh dấu sai` cho tiêu chí đang chọn,
  đặt ngay trên thanh dính trước nút hoàn tất. Tooltip nêu tên tiêu chí đang chọn;
  hết việc thì cả hai nút tự tắt. Nút dùng chung `handleReview` với bàn phím và với
  thẻ bằng chứng, nên không có đường ghi thứ hai.

**Số đo.** Với hồ sơ đang xem, thao tác phải làm để hoàn tất một hồ sơ có 2 tiêu
chí chờ:

| Bước | Trước | Sau |
| --- | --- | --- |
| Chọn trạng thái sau khi hoàn tất | mở ô chọn + chọn 1 dòng (2 cú bấm) | 0 (đã chọn sẵn, đổi được) |
| Cam kết đã đối chiếu | 1 cú bấm vào ô đánh dấu | 0 (nằm trong nút chính) |
| Bấm xác nhận tiêu chí trên điện thoại 390px | phải cuộn tới thẻ bằng chứng | 0 cuộn: hai nút nằm trong khung nhìn (e2e kiểm `boundingBox` trong 390×844) |

**Kiểm thử đã chạy.** `tsc --noEmit` sạch; `eslint` sạch trên 2 file sửa; unit
**124/124** (thêm 6 test cho `suggestFinishStatus`, đã thêm file vào `test:unit`);
i18n **3/3**; `next build` OK; e2e mới `tests/sticky-review-actions.e2e.cjs` pass ở
cả 390×844 và 1440×900 (chip đếm đúng, hai nút trong khung nhìn, bấm xác nhận ghi
nhận và chuyển tiêu chí, mở đúng hộp thoại lý do khi đánh dấu sai, hết việc thì
nút tắt); `finish-application`, `verify-only`, `capabilities` pass sau khi cập nhật
theo luồng mới (ba test này trước đó dựa vào ô đánh dấu).

**Chưa kiểm.** Chưa thử trên backend thật; đề xuất trạng thái dựa trên dữ liệu mock.
Ngưỡng 60 điểm là hằng số `SHORTLIST_MIN_SCORE` chọn theo màu điểm đang dùng trong
trang, chưa phải chính sách do backend trả về — nếu tuyển dụng đổi ngưỡng thì phải
sửa ở đây.

## 2026-11-21 — Hồ sơ: xác nhận xong tự sang tiêu chí kế, không tải lại cả hồ sơ

**Vấn đề.** Vòng xác minh một hồ sơ bắt HR bấm thừa ở hai chỗ, đo trên mock
(`tests/review-loop-metrics.cjs`, 2 tiêu chí bị gắn cờ c2/c3):

1. **Con trỏ đứng lại sau khi xác nhận.** Người đã chọn tiêu chí bằng `j` (đúng
   như dòng phím tắt hướng dẫn) thì sau khi bấm `1`, con trỏ vẫn ở tiêu chí vừa
   xong; lần bấm `1` kế tiếp không làm gì. Đo được **16 phím cho 2 tiêu chí, 7
   lần bấm vô ích**, và hồ sơ vẫn kẹt ở "Đã xác minh 1/2" sau 8 vòng bấm.
2. **Mỗi lần xác nhận tải lại cả hồ sơ.** `handleReview` gọi `loadData()`, kéo
   theo `GET /applications/{id}`, `GET /status-events`, `GET /profile` (nhiều
   lần) và `GET /private-notes`: **15 GET cho 2 tiêu chí**, trang nhấp nháy, và
   chính lần tải lại đó là thứ làm con trỏ nhảy về chỗ cũ.
3. **CV không đi theo tiêu chí.** CV đang mở ở trang 3 của c2; xác nhận xong con
   trỏ sang c3 (trang 4) nhưng khung CV vẫn ở trang 3.

**Đã làm.**

- **Cập nhật tại chỗ thay vì tải lại.** `applyReview` ghi bản ghi review mà
  backend vừa trả về vào đúng tiêu chí trong `application`, không gọi
  `loadData()`. Hiệu ứng tải ghi chú đổi phụ thuộc từ cả object `application`
  sang một boolean quyền, nên một lần xác nhận không còn kéo theo lần tải ghi
  chú nữa.
- **Tự nhảy tiêu chí kế.** `nextPendingCriterionId` (thuần, có unit test) chọn
  tiêu chí còn chờ kế tiếp: đi tiếp về phía trước, chỉ quay lại tiêu chí còn chờ
  phía trên khi phía trước đã hết — bỏ sót nó sẽ im lặng. Không còn gì chờ thì
  con trỏ giữ nguyên ở tiêu chí vừa xác nhận.
- **CV đi theo con trỏ.** `focusCriterion` dùng chung cho `j/k` và cho bước nhảy
  sau xác nhận: đặt tiêu chí đang chọn, cuộn tới thẻ, và chuyển khung CV sang
  đúng trang trích dẫn — nhưng chỉ khi CV đã được HR mở (giữ nguyên quy tắc
  không tải CV trước khi được yêu cầu).
- **Tải trước hồ sơ kế tiếp.** `PrefetchProfile` gọi `router.prefetch` cho href
  của hồ sơ kế tiếp ngay khi hồ sơ hiện tại mở xong, không phụ thuộc việc link
  có nằm trong khung nhìn hay không.

**Số đo trước/sau** (cùng script, cùng mock, 1440×900):

| Chỉ số | Trước | Sau |
| --- | --- | --- |
| Phím để xác nhận 2 tiêu chí, không chọn tay | 2 | 2 |
| Phím để xác nhận 2 tiêu chí, có chọn tay bằng `j` | 16 (7 vô ích) | 3 (0 vô ích) |
| GET `/applications/{id}` + `/status-events` mỗi lần xác nhận | 2 | 0 |
| Tổng GET `/v1` cho 2 tiêu chí (không chọn tay) | 15 | 4 |
| Trang CV sau khi xác nhận (CV đang mở trang 3) | 3 | 4 |
| Request route hồ sơ kế tiếp trước khi bấm `n` | 1 | 1 |
| Thời gian tới khi hồ sơ kế tiếp hiện tên | 159 ms | 152–200 ms (dao động) |

Việc tải trước hồ sơ kế tiếp **không đo được cải thiện**: `<Link>` của nút "Hồ
sơ tiếp theo" nằm trong khung nhìn nên Next đã prefetch route đó từ trước. Lệnh
`router.prefetch` giữ lại để việc tải trước không phụ thuộc bố cục, nhưng trung
thực mà nói nó chưa tạo ra khác biệt đo được ở màn này.

**Phạm vi giữ nguyên.** Không thêm endpoint, không đổi shape dữ liệu: review vẫn
là `POST /assessments/results/{id}/review`, quyền vẫn do backend quyết. Không có
bước nhảy trạng thái nào; xác minh vẫn không đổi `application_status`. Panel
`Profile ứng viên` và ghi chú vẫn là hai component riêng.

**Kiểm thử đã chạy.** `npx tsc --noEmit` sạch; `eslint` sạch trên 2 file sửa;
unit **118/118** (thêm 4 test cho `nextPendingCriterionId`); i18n **3/3**;
`next build` OK; e2e mới `tests/review-auto-advance.e2e.cjs` pass (tự nhảy tiêu
chí, không có GET tải lại, CV 3→4, prefetch hồ sơ kế tiếp); e2e
`tests/finish-application.e2e.cjs` pass (vòng hoàn tất không hồi quy).

**Chưa kiểm.** Panel `Profile ứng viên` vẫn gọi lại `/v1/applications/{id}/profile`
mỗi khi state hồ sơ đổi (4 request lúc mở trang, và sau mỗi lần xác nhận) — hành
vi có từ trước, không sửa trong lượt này, và là phần còn lại duy nhất của câu
"tải lại hồ sơ". Chưa thử trên backend thật; toàn bộ số đo lấy từ mock tĩnh.

## 2026-11-21 — Danh sách ứng viên: một thanh lọc, lối vào hồ sơ kế tiếp ở đầu trang

**Vấn đề.** Trước bảng dữ liệu của `/positions/[id]/applicants` có tám khối xếp
chồng: dòng đếm, hai nút chế độ xem, câu giải thích, hàng chip hàng đợi, hàng
chip người phụ trách, hàng ba ô chọn tiêu chí, hàng tìm kiếm + sắp xếp, và dòng
"hiển thị x/y". Ở 1440×900 dòng dữ liệu đầu tiên nằm ở **700px** và chỉ thấy **2**
dòng. Ba vấn đề cụ thể:

1. Hai nút `Xếp hạng` / `Cần rà soát` trùng đúng hai lựa chọn của ô `Sắp xếp`,
   và bấm chúng còn âm thầm đặt lại hàng đợi về `Tất cả`.
2. Hàng chip người phụ trách chiếm một dòng riêng dù chỉ là một câu hỏi phụ.
3. Muốn mở hồ sơ kế tiếp, HR phải cuộn xuống bảng rồi tự tìm dòng — trong khi
   việc chính của màn này là duyệt liên tiếp.

**Đã làm.**

- **Một thanh lọc thay sáu khối.** Tìm kiếm, người phụ trách, sắp xếp ở hàng đầu;
  tiêu chí, bằng chứng, thời gian chờ ở hàng thứ hai; câu giải thích cách sắp
  xếp là dòng chú thích cuối thanh. Người phụ trách thành ô chọn (vẫn giữ số đếm
  trong từng lựa chọn) thay cho hàng chip. Nút `Xoá bộ lọc và tìm kiếm` chuyển
  vào thanh, và giờ cũng xoá luôn bộ lọc người phụ trách — trước đây bấm "xoá bộ
  lọc" mà bộ lọc đó vẫn còn.
- **Bớt nút trùng.** Bỏ hai nút chế độ xem; `Xếp hạng`/`Ưu tiên rà soát` chỉ còn
  một nơi là ô `Sắp xếp danh sách`. Đổi chế độ không còn đặt lại hàng đợi.
- **Lối vào "hồ sơ kế tiếp".** Nút `Mở hồ sơ kế tiếp` nằm ngay cạnh hành động
  chính ở header, trỏ vào hồ sơ đầu tiên trong danh sách đang xem mà còn việc
  (chưa xếp hạng hoặc bằng chứng cần xác minh); tooltip nêu tên ứng viên. Link
  mang theo ngữ cảnh duyệt (hàng đợi, từ khoá) như mọi link hồ sơ khác.
- **Chip hàng đợi gọn hơn.** Chip cỡ nhỏ ở mọi màn hình; trên điện thoại chúng
  chảy thành **một dải cuộn ngang** thay vì bảy dòng (390px không tràn ngang).

**Đo.** Cùng dữ liệu mock, 1440×900: dòng dữ liệu đầu tiên **700px → 610px**, số
dòng thấy trong màn đầu **2 → 3**. Thanh lọc cao 138px cho hai hàng điều khiển.

**Giữ nguyên.** Mọi hành vi lọc: chip hàng đợi kèm số đếm toàn vị trí, lọc theo
bằng chứng và thời gian chờ, tìm kiếm theo tên, sắp xếp 5 kiểu, `Cách đọc danh
sách` (mặc định đóng, mở bằng bàn phím), dòng đếm `Hiển thị x/y`, thanh hành
động nổi, biên bản lô và cột `Xem` của bảng.

**Kiểm.** `tsc --noEmit`, `eslint` (2 file sửa), unit **114/114**, i18n **3/3**,
`next build`. E2E: `ranking-compact-mock` (sửa selector: chọn chế độ qua ô Sắp
xếp thay hai nút đã bỏ; ngưỡng dòng đầu siết 720px → 660px; thêm assert thanh
lọc gọn và nút hồ sơ kế tiếp), `ranking-context-mock` (thêm mock
`/v1/dashboard/work-queue` cho badge header), `applicant-criteria-filter`,
`bulk-actions` — tất cả pass. Ảnh kiểm (không commit):
`artifacts/applicants-filter-bar.png`, `artifacts/applicants-filter-bar-390.png`.

**Chưa kiểm.** Chưa chạy trên backend thật (mọi e2e ở trên dùng mock);
`synthetic-ui` vẫn cần backend disposable + fixture token thật nên không chạy
được ở đây. Chưa đo lại trên màn 360px cho trang này (bulk-actions có chạy 360px
và pass, nhưng đó là thanh hành động, không phải thanh lọc).

## 2026-11-21 — Bố cục lại trang chi tiết vị trí: một việc chính, không lặp CTA

**Vấn đề.** Trang `/positions/[id]` là nơi HR ở lâu nhất nhưng bố cục buộc họ
đọc lại cùng một thông tin nhiều lần và cuộn mới bấm được việc chính:

1. Header có 6 nút cùng cỡ (Ứng viên, Đổi Hiring Manager, Dùng rubric, Chỉnh sửa
   vị trí, Đề xuất tiêu chí AI, Tải lên CV) — không nút nào nổi bật, xuống dòng
   lung tung ở màn hình 1280px.
2. Trước khi tới nội dung phải đi qua 3 khối xếp chồng: 6 thẻ số liệu, stepper,
   thẻ "hành động tiếp theo" — cùng nhắc lại một việc.
3. Tab "Danh sách ứng viên" lặp lại 4 thẻ số liệu đã có ở trên, cộng 2 nút dẫn
   tới cùng một trang xếp hạng, trong khi việc thật của tab là nhận CV.
4. Tab tiêu chí mở bằng nguyên văn JD (đã có tab JD riêng), rồi danh sách tiêu
   chí, lịch sử duyệt, và **nút duyệt nằm cuối cùng** — phải cuộn hết trang.
5. Đổi tab xong tải lại trang là quay về tab đầu; không gửi link thẳng cho đồng
   nghiệp được.
6. Nút "Tải lên CV" bị khoá mà không nói vì sao.

**Đã làm.**

- **Header hai tầng.** Hàng chính chỉ còn `Ứng viên (N)` và `Nhận CV` (nút thứ
  hai có tooltip giải thích khi bị khoá: cần bộ tiêu chí đã duyệt và vị trí đang
  mở). Hàng phụ cỡ nhỏ: `Đề xuất tiêu chí AI`, `Chỉnh sửa vị trí`, `Đổi Hiring
  Manager`. `Dùng rubric đã xuất bản` chuyển vào thanh công cụ của tab tiêu chí —
  đúng nơi HR chọn nguồn tiêu chí.
- **Ba khối thành một thẻ tổng quan.** `WorkflowStepper` thành dải chip 5 bước
  (bước hiện tại tô đậm, bước bị chặn đỏ, tooltip trạng thái); `PositionSummary`
  thành dải 6 số ngang vẫn bấm được để mở đúng hàng đợi; `NextActionCard` thêm
  biến thể `bare` để nằm cùng thẻ. Bớt ~2 khung và ~300px cuộn trước nội dung.
- **Tab ứng viên.** Bỏ 4 thẻ số liệu trùng và nút trùng: còn khung nhận CV (việc
  chính) + một dòng số liệu + một nút `Mở trang xếp hạng`.
- **Duyệt tiêu chí lên đầu tab.** Thẻ duyệt (trạng thái, vai trò của bạn, nút
  Từ chối / HR duyệt & gửi HM / duyệt trực tiếp / HM duyệt) nằm ngay dưới các
  cảnh báo, trên danh sách tiêu chí. Bỏ khối JD đầy đủ ở đầu tab, thay bằng nút
  `Xem JD · vN` trong thanh trọng số.
- **Tab gắn URL.** `?tab=criteria|applications|shortlist|jd` cập nhật bằng
  `replaceState` (Back vẫn về trang trước), áp dụng cho cả nút `Nhận CV` và
  "hành động tiếp theo". Nhãn tab kèm số đếm: `Tiêu chí (7)`, `Ứng viên (12)`,
  `Shortlist (4)`, `Mô tả công việc (JD) · v3`.
- **Chi tiết nhỏ.** Chip nhóm vị trí + hạn ứng tuyển ngay dưới tiêu đề (trước đây
  hạn chỉ thấy trong hộp thoại chỉnh sửa). `ApplyRubric`/`HiringManagerChange`
  nhận prop `size` để dùng được ở hàng phụ.

**Kiểm thử đã chạy (pass).**

| Lệnh | Kết quả |
| --- | --- |
| `npx tsc --noEmit` | 0 lỗi |
| `npx eslint` (6 file đã sửa) | 0 lỗi |
| `npm run test:i18n` | 3/3 pass (đã bổ sung 8 khoá tiếng Anh) |
| `npm run test:unit` | 114/114 pass |
| `npm run build` | build thành công, `/positions/[id]` 24.6 kB |

**Kiểm bằng trình duyệt (mock API).** Thêm `frontend/tests/mock-api-server.cjs`
dựng từ `tests/fixtures/hr-screens.cjs`, chạy ở cổng 8000 để Next.js proxy `/v1`
trả dữ liệu fixture; chạy `next start` và chụp màn hình ở 1280px và 900px. Năm
chỗ lệch lộ ra và đã sửa:

1. Tab cuối bị cắt thành "Mô tả công…" kèm nút cuộn — bỏ `· vN` khỏi nhãn và
   thu padding/font của tab; nay `scrollWidth` = `width` nên không tràn.
2. Ở cột hẹp, tên tiêu chí bị bóp còn vài chữ mỗi dòng và nút Xóa bị cắt — cho
   hàng tiêu đề xuống dòng, chip trọng số xuống dưới tên, Sửa/Xóa giữ một hàng.
3. Nút của "hành động tiếp theo" lơ lửng giữa thẻ (khối co theo nội dung) — tách
   thẻ tổng quan thành ba hàng có divider, nút nằm sát mép phải.
4. Khối tổng quan vẫn chiếm chỗ ở tab Ứng viên, đẩy khung nhận CV xuống dưới màn
   hình — chỉ hiện ở tab Tiêu chí; khung nhận CV nay nằm trong màn hình đầu.
5. Nút "Đề xuất tiêu chí AI" (và "Nhận CV") bị khoá im lặng — thêm tooltip nêu
   lý do, đọc được cả từ cây accessibility.

Đã xác nhận trên trình duyệt: header hai tầng đúng thứ bậc, dải chip bước một
hàng, dải số liệu đọc được cùng lúc, thẻ duyệt nằm ngay dưới tab bar (trước danh
sách tiêu chí), đổi tab cập nhật `?tab=`, F5 ở `?tab=jd` vẫn ở tab JD.

**E2E chạm trang vị trí.** Chạy bốn test được nêu, trên `next start` (127.0.0.1:3000)
với chromium headless shell cài trong máy. Hai test phải bổ sung mock, vì code đã
thêm hai lời gọi mà mock của test chưa có:

- `/v1/dashboard/work-queue` — badge "việc cần làm" trên header gọi ở mọi trang
  đã đăng nhập, kể cả trang vị trí; thiếu route thì test báo "Unexpected request"
  ở bước kiểm cuối dù mọi assertion đều đã qua.
- `POST /v1/criteria/generate/{id}` — luồng tạo vị trí sinh bộ tiêu chí nháp ngay
  sau khi tạo; thiếu route thì trang tạo đứng lại ở `/positions/new` và
  `account-ui` timeout khi chờ `?tab=criteria`.

| Test | Kết quả |
| --- | --- |
| `position-open-partial-failure.e2e.cjs` | pass (sau khi thêm mock work-queue) |
| `workflow-create-mock.e2e.cjs` | pass (sau khi thêm mock work-queue) |
| `account-ui.e2e.cjs` | pass (thêm mock work-queue + generate sau tạo vị trí) |
| `synthetic-ui.e2e.cjs` | **không chạy được ở đây** — cần backend disposable ở chế độ
  `testing` + fixture có token thật và dữ liệu seed; môi trường này chỉ có mock tĩnh |

Nhãn tab tiếng Anh `Job description (JD)` mà `synthetic-ui` bấm vẫn khớp sau khi bỏ
"· vN" (kiểm riêng trên mock ở locale `en`, mở được luôn hộp thoại tạo phiên bản
JD), nên việc đổi nhãn không làm hỏng test đó.

**Ghi chú môi trường.** Chromium headless shell trong sandbox này thiếu
`libnspr4/libnss3/libX*/fontconfig` và không có font nào (mọi chữ render cao 0px,
`getByText` báo hidden). Đã tải `.deb` của các thư viện + `fonts-dejavu-core`,
giải nén vào một thư mục riêng rồi chạy test với `LD_LIBRARY_PATH` và
`FONTCONFIG_FILE` trỏ vào đó. Không sửa gì trong repo cho việc này.

**Chưa kiểm.** Chưa thử ở ≤768px ngoài lần chạy `account-ui` (mobile 390px của
trang tài khoản) và chưa chạy `synthetic-ui` (lý do ở trên).
## 2026-11-21 (2) — Health báo ClamAV, và hồ sơ vào khi máy quét chết có dấu vết

**Hai việc, cùng một gốc: máy quét virus hỏng mà không ai biết.**

### 1. `/health/ready` báo trạng thái ClamAV

Trước: endpoint chỉ kiểm DB. `clamd` chết thì đường nhận CV trả 503 trong khi
health vẫn nói `ready` — không tín hiệu nào cho giám sát (HANG-01/HANG-03).

Nay trả thêm `clamav: connected | unavailable | disabled`. Ba giá trị, cố ý
không gộp: `disabled` (chưa cấu hình socket, chủ ý) khác `unavailable` (đã cấu
hình nhưng hỏng) — gộp lại thì không phân biệt được "chưa bật" với "đang lỗi".

**Không** trả 503 khi máy quét chết. Chỉ đường nộp CV phụ thuộc nó; xem vị trí,
chấm hồ sơ đã nhận, duyệt rubric vẫn chạy. 503 sẽ khiến load balancer rút backend
và biến "thiếu máy quét" thành "sập toàn hệ thống". Có cờ
`READINESS_REQUIRE_CLAMAV` (mặc định tắt) cho ai muốn siết.

Probe chỉ mở socket rồi đóng, không gửi dữ liệu — health chạy liên tục, đẩy tệp
qua clamd trong đó là tự tạo tải và có thể bị tính là một lượt quét.

### 2. Nhận hồ sơ khi máy quét chết — có cờ, có dấu, có audit

Trước: `careers_intake.py` chặn cứng ngay đầu request khi thiếu socket. Ở vòng
thử nghiệm, một dịch vụ phụ hỏng làm tắc **toàn bộ** form ứng tuyển.

Nay giữ nguyên hành vi mặc định (fail-closed 503), nhưng khi bật
`PUBLIC_CAREERS_UNSCANNED_FILES_ENABLED` thì vẫn nhận, với ba ràng buộc:

- Tệp **bẩn** luôn chặn 400 — nhánh `INFECTED` đứng **trước** nhánh đọc cờ, và
  có test khoá thứ tự đó.
- Bản ghi mang `application_documents.scan_state = 'UNSCANNED'` (migration
  `00038`, đã áp).
- Audit riêng `CAREERS_UNSCANNED_FILE_ACCEPTED`, không nhồi vào JSON của lần
  nhận hồ sơ — câu hỏi "hồ sơ nào vào lúc máy quét chết" phải tra bằng
  `action_type`.

Giao diện hồ sơ hiện chip vàng "Tệp chưa quét virus" kèm tooltip.

**Vì sao khác `jd_import.py`:** ở đó cờ chỉ cần một câu cảnh báo vì tệp gốc
không được lưu. Ở đây tệp được lưu và xử lý tiếp, nên cái giá của việc nhận bừa
cao hơn — vì vậy phải có dấu trên bản ghi, không chỉ một câu cảnh báo.

**Ghi chú vận hành.** Đường Gmail thử nghiệm gọi cùng hàm ghi và không truyền
cờ, nên mặc định `unscanned=False` → `'SCANNED'`. Đúng cho đường đó: nó đã chặn
`ScanVerdict.UNAVAILABLE` thành `REVIEW/ANTIVIRUS_UNAVAILABLE` từ trước khi ghi.

**Kiểm thử.** Backend 581 passed / 174 skipped (thêm 22: 8 cho health, 14 cho
đường nhận tệp). Unit frontend 127/127. `tsc`, `lint`, `build` sạch.

## 2026-11-21 — Nhóm vị trí có API quản trị, và `/careers` chỉ còn một nguồn nhóm

**Vấn đề 1 — mở một ngành tuyển dụng mới phải chạy SQL.** Bảng `job_families`
chỉ có dữ liệu mồi từ migration `00023`. Muốn thêm nhóm, người có quyền vào
database phải tự `INSERT`. Không có màn hình, không có audit.

**Đã làm.** `backend/app/api/job_families.py`:
`GET /job-families` (kèm `position_count`/`template_count`; `include_inactive`
chỉ ADMIN), `POST` (chuẩn hoá mã `IT Digital` → `IT_DIGITAL`, trùng mã → 409),
`PATCH` (chỉ `name` + `is_active`; tắt nhóm còn vị trí → 409 kèm số lượng).
Không có DELETE: nhóm đã gắn với vị trí/rubric thì xoá là mất chỗ trỏ tới.
`code` bất biến sau khi tạo vì rubric mẫu và báo cáo tham chiếu tới nó.
Màn hình `/admin/job-families` theo khuôn phòng ban.

**Vấn đề 2 — hai nguồn "nhóm" song song, và nguồn công khai là nguồn cũ.**
`/careers` lọc và gom danh mục theo cột text `positions.job_family`, trong khi
vị trí/rubric dùng bảng `job_families`. Hệ quả đo được trên dữ liệu thật
(`myrymlqdbyqmpynesiwk`): vị trí gán nhóm qua bảng có cột text `NULL` → lọc
theo bảng ra `IT & Digital`, lọc theo cột text ra `null`. Nhóm mới tạo trong
màn hình quản trị sẽ **không** xuất hiện trong danh mục ở `/careers`.

**Đã làm.** `/careers/jobs` và `/careers/filters` join `job_families` qua
`job_family_id` và đọc `f.name`; tham số `job_family` của API so với `f.name`.
Dùng `LEFT JOIN` để vị trí chưa gán nhóm **vẫn hiện tin** — hiện tại toàn bộ
tin thật đều chưa gán nhóm, `JOIN` sẽ làm trang trống hoàn toàn. Đổi tên nhóm
trong API quản trị giờ cập nhật luôn bản sao text trong cùng transaction.

**Phạm vi giữ nguyên.** Không xoá cột `positions.job_family`: cột vẫn được ghi
lúc tạo/sửa vị trí như bản sao lịch sử, nhưng không còn ai đọc để lọc/gom nhóm.
Không có migration mới — thay đổi thuần đọc.

**Kiểm thử.** Backend 559 passed / 174 skipped (thêm 41 test: 27 tĩnh + 16 gọi
thật endpoint với DB giả cho job_families, 7 khoá nguồn nhóm của `/careers`).
Unit frontend 127/127. `tsc`, `lint`, `build` sạch. **Chưa kiểm:** 38 test e2e
Playwright không chạy được trong sandbox (thiếu Chromium và Next server), nên
luồng `/careers` trên trình duyệt thật chưa được xác nhận lại.

## 2026-11-20 — Sáu cải tiến vòng duyệt hồ sơ: hàng đợi, phím tắt, lý do loại, ghi chú, người phụ trách

**Vấn đề.** Sáu chỗ HR phải làm lại việc máy đã biết, đo trên chính luồng duyệt
hồ sơ:

1. Dashboard báo "17 hồ sơ chờ xác minh" nhưng bấm vào chỉ mở **danh sách**, rồi
   HR tự tìm hàng đầu tiên — mỗi lượt mất thêm hai lần bấm và một lần đọc.
2. Xác minh 10–15 tiêu chí toàn bằng chuột; bàn tay đang ở bàn phím vẫn phải rời ra.
3. Khi loại hồ sơ, HR gõ lại cùng một lý do cho hàng chục hồ sơ cùng vị trí,
   trong khi hệ thống đã biết tiêu chí nào `NO_MATCH`/`UNCLEAR`.
4. Nhận xét về một tiêu chí bị dồn xuống ô ghi chú chung cuối trang, mất ngữ cảnh.
5. Hai HR cùng một vị trí không biết ai đang giữ hồ sơ nào, nên làm trùng hoặc
   cùng bỏ sót.
6. Không có tín hiệu nào cho biết "có gì mới" từ lần mở app trước.

**Đã làm (theo đúng thứ tự commit).**

- **Hàng đợi mở thẳng hồ sơ.** `backend/app/services/workspace.py` thêm
  `next_application_id` tính đúng định nghĩa của từng loại việc, dùng lại chính
  các hàm đếm (`_needs_verification`, `_in_screening`, `_WORK_TYPE_QUEUES`) để
  con số trên dashboard và hồ sơ được mở không lệch nhau; `api/dashboard.py` gắn
  id đó vào item. Frontend `lib/workQueueEntry.ts` dựng href, giữ `?queue=` để
  trang hồ sơ dựng lại hàng đợi và tiến độ 3/17 sẵn có.
- **Phím tắt xác minh.** `lib/reviewKeyboard.ts` (logic thuần): `j`/`k` hoặc mũi
  tên di chuyển tiêu chí (dừng ở hai đầu, không vòng), `y`/`n` xác nhận/từ chối.
  Chặn khi đang gõ trong input/textarea, khi có dialog mở, và bỏ qua phím có
  Ctrl/Meta/Alt — để không cướp phím của trình duyệt hay của ô ghi chú.
- **Gợi ý lý do loại.** `lib/rejectionReasons.ts` nhớ lý do đã dùng **theo vị
  trí** trong localStorage và đề xuất từ tiêu chí `NO_MATCH`/`UNCLEAR` của chính
  hồ sơ (kèm tên tiêu chí). Chọn bằng chip, không thêm combobox; không đổi API.
- **Ghi chú cạnh tiêu chí.** Migration `00036` thêm
  `application_private_notes.criterion_id`; `POST /private-notes` nhận
  `criterion_id` và **kiểm tra tiêu chí thuộc đúng vị trí** của hồ sơ. Trang hồ
  sơ gom ghi chú về một nguồn: ghi chú theo tiêu chí hiện trong `EvidenceCard`,
  ghi chú chung ở panel cuối trang, chip "N ghi chú riêng tư" ở đầu hồ sơ cuộn
  tới panel.
- **Người phụ trách hồ sơ.** Migration `00036` thêm `assigned_to`/`assigned_at` +
  index; `PATCH /applications/{id}/assignment` cho HR tự nhận/bỏ nhận, giao cho
  người khác chỉ HR Lead/Admin và người nhận phải là HR của vị trí; mọi thay đổi
  ghi `audit_events`. Danh sách/chi tiết trả thêm `assigned_to_name`. UI: chip
  "Phụ trách: …" + nút Nhận/Bỏ nhận; danh sách ứng viên có bộ lọc
  **Của tôi / Chưa ai nhận** kèm số đếm trên toàn vị trí.
- **Nhắc việc mới.** `lib/workQueueDigest.ts` so snapshot work-queue lần trước
  (localStorage) với hiện tại; badge số việc trên header và dải "có gì mới" trên
  dashboard. Không thêm bảng/endpoint: số liệu đã có sẵn ở work-queue.

**Kiểm thử đã chạy (pass).**

| Lệnh | Kết quả |
| --- | --- |
| `node --test tests/work-queue-entry.test.cjs` | 4/4 |
| `node --test tests/review-keyboard.test.cjs` | 6/6 |
| `node --test tests/rejection-reasons.test.cjs` | 6/6 |
| `node --test tests/work-queue-digest.test.cjs` | 6/6 |
| `node --test tests/criterion-notes.test.cjs tests/applicant-ownership.test.cjs` | 8/8 |
| `node --test tests/ux-metrics.test.cjs` | 11/11 |
| `node --test tests/i18n.test.cjs` | 3/3 |
| `npx tsc --noEmit` / `npx eslint` (các file đã sửa) | pass |
| `python -m py_compile` (`applications.py`, `candidate_details.py`, `schemas/applications.py`) | pass |

**Việc còn chờ / lưu ý.**

- **Migration `00036` chưa áp lên database nào.** Phải chạy trước khi thử: nhận
  hồ sơ, ghi chú theo tiêu chí, lọc "Của tôi".
- **Chưa chạy backend thật.** Môi trường này không có Postgres/pytest, nên các
  endpoint mới (`PATCH …/assignment`, `criterion_id` trong notes) mới chỉ được
  biên dịch, chưa được gọi. Cần thử bằng tài khoản HR và HR Lead thật, gồm cả
  trường hợp HR thường cố giao hồ sơ cho người khác (phải 403).
- **Hàng đợi/dashboard chưa lọc theo người phụ trách** — số liệu vẫn là toàn vị
  trí; chỉ màn danh sách ứng viên có bộ lọc mới. Nếu muốn "việc của tôi" ở
  dashboard thì phải thêm tham số lọc vào work-queue (việc riêng, chưa làm).
- **Lý do loại chỉ lưu ở trình duyệt** (localStorage theo vị trí), chưa lên
  backend; đổi máy/người là mất gợi ý. Cố ý, để không phải mở API mới.
- **Chưa kiểm giao diện/e2e.** Không có Chromium trong môi trường này; chip,
  ô ghi chú và phím tắt mới chỉ được typecheck/lint và test logic thuần.
- Email nhắc việc định kỳ (bước b của mục nhắc việc) **chưa làm** — cần chọn dịch
  vụ gửi email trước.

## 2026-11-19 — Tích hợp nhánh `freebuff` vào nhánh làm việc, gộp hai backlog

**Vấn đề.** Công việc UI/UX nằm trên `freebuff/1434fda45407dc1a68600843` (18
commit, rẽ từ `6aa867f`), còn các bản sửa tiêu chí nằm trên
`arena/ea6e2570-vinit-hrapp`. Hai nhánh chưa từng gặp nhau, và cả hai đều sửa
`frontend/src/i18n/en.json` — file dùng chung, nên không thể deploy riêng lẻ.

**Đã làm.** Nhánh `freebuff` đã tự merge `arena` vào trước (`4ff30da`), nên lần
này chỉ cần fast-forward, **không phát sinh xung đột**. Đã kiểm:

- `en.json`: giữ đủ 1694 key của freebuff **và** 18 key của phần sinh tiêu chí;
  không key nào bị mất. Tổng 1712 key.
- Bộ dữ liệu demo **vẫn là bản tiếng Anh** (`CV_01_daniel_whitfield.docx`…) —
  yêu cầu bắt buộc, không bị ghi đè.
- Không file nào trong phần sinh tiêu chí bị freebuff sửa: `criteriaGeneration.ts`,
  `CreatePositionProgressDialog.tsx`, `positions/new`, `deterministic_matching.py`,
  `api/criteria.py` đều giữ nguyên.
- Hai effect đọc `?tab=` trong trang vị trí vẫn không nhân đôi (một khi mount, một
  trong `handleAction`).

**Kiểm thử trên code đã hợp nhất.** Backend **432 passed**, 174 skipped. Frontend:
`tsc` sạch, unit **84 passed**, i18n 3/3, `next build` thành công, eslint sạch.
Con số unit 84 khớp chính xác phép cộng 49 + 27 + 8.

**Dọn dẹp.** Gộp `doc/HANG_CHO_VIEC.md` vào cuối `doc/VIEC_CHO_LAM.md` (phần B) và
xoá file cũ: hai backlog tên gần giống nhau là nguồn gây nhầm. Ghi chú bàn giao
nằm ngay dưới phần hướng dẫn dùng file.

**Chưa kiểm.** Không có Chromium trong môi trường này nên **toàn bộ e2e mới chưa
chạy được** — chỉ unit/contract test và build. Cần chạy các e2e đó trên máy có
trình duyệt trước khi tin vào các luồng hành động hàng loạt, retention và đo
lường UX.

## 2026-11-19 — Đo tác động của chính các cải tiến UX (thời gian xử lý, hồ sơ quá hạn, mức dùng lô)

**Vấn đề.** Dashboard chỉ có số lượng hàng đợi, nên bốn lượt cải tiến trước đều dừng
ở “cảm giác tốt hơn”: không có số nào cho biết HR mất bao lâu để đóng một hồ sơ cần
xác minh, hay còn bao nhiêu hồ sơ chờ quá 7 ngày. Không đo thì không biết việc nào
thật sự giúp, và cũng không có dữ liệu để chọn việc tiếp theo.

**Thay đổi.**

- `frontend/src/lib/uxMetrics.ts` (mới): bốn event nhẹ — `PROFILE_OPENED`,
  `PROFILE_CLOSED` (kèm thời lượng), `VERIFICATION_COMPLETED`, `BULK_RUN` (số hồ sơ,
  số lỗi, thời gian). Ghi vào `localStorage` của chính máy HR, giới hạn 500 event gần
  nhất, đọc lại có kiểm tra kiểu/bounds nên dữ liệu hỏng không dựng ra số đo giả.
  **Không gửi lên máy chủ và không ghi tên, CV hay nội dung hồ sơ** — chỉ id hồ sơ,
  thời điểm, thời lượng; unit test khẳng định việc này.
- Gắn đo tại đúng ba chỗ người dùng nêu: mở/rời hồ sơ (`applicants/[applicantId]`,
  một cặp event mỗi lượt xem), hoàn tất hồ sơ (ghi khi `handleFinish` thành công,
  không ghi khi lỗi), và chạy lô (`runBulkRows`, ghi cả lô lẫn phần lỗi để thấy lô có
  thật sự thay được việc làm từng hồ sơ). Đo lường không chạm vào luồng nghiệp vụ:
  mọi lỗi storage đều bị nuốt.
- Khối **“Tác động của cải tiến UX”** trên dashboard: trung vị thời gian ở trong hồ
  sơ, thời gian từ lần mở đầu tiên đến lúc hoàn tất (ghép với lần mở *sớm nhất* để
  mở lại không làm thời gian ngắn đi giả tạo), số hồ sơ đã hoàn tất, mức dùng lô
  (số hồ sơ · lỗi · thời gian trung bình), và **hồ sơ chờ xác minh quá hạn** lấy từ
  `work-queue` của máy chủ. Nút “Xoá số đo” chỉ xoá khoá của module này.
- Hai loại số đo được nói rõ ngay trên màn hình: số cục bộ chỉ tính trên trình duyệt
  này; số hồ sơ quá hạn và tuổi hồ sơ lâu nhất là số toàn hệ thống từ máy chủ.

**Phạm vi giữ nguyên.** Không sửa backend, không thêm bảng/endpoint, không đổi luồng
nghiệp vụ hay quyền.

**Kiểm thử.** `frontend/tests/ux-metrics.test.cjs` (mới, 9 test): ghi nối tiếp + giới
hạn 500 event, bỏ event hỏng/lạ, chỉ lưu id và thời lượng (không có tên/email/CV), trung vị thời gian ở hồ sơ không
bị lệch bởi một lượt rất dài, thời gian hoàn tất tính từ lần mở đầu tiên và không
ghép bừa khi thiếu mốc mở, tổng hợp lô (tỉ lệ lỗi 0.167 cho 5/30), chưa có event thì
mọi số đo là `null` chứ không phải 0, xoá số đo không đụng token phiên, và storage
bị chặn không làm hỏng luồng gọi.
`frontend/tests/ux-metrics.e2e.cjs` (mới) chạy dashboard thật với event đã gieo: khối
hiện 2,5 phút (trung vị), 20 phút (mở → hoàn tất), 1 lô với 12 hồ sơ · 1 lỗi, số quá
hạn 6 lấy từ máy chủ; nút xoá chỉ xoá khoá của module; mở một hồ sơ thật rồi rời đi
thì event `PROFILE_OPENED`/`PROFILE_CLOSED` được ghi đúng id và thời lượng, và
không có tên ứng viên hay email trong storage.
Hồi quy xanh: `ux03-dashboard`, `bulk-actions`, `finish-application` (ba màn vừa được
gắn đo) — `bulk-actions` còn khẳng định lô vẫn chạy đúng endpoint cũ sau khi thêm đo.

**Chưa kiểm.** Số đo hoàn toàn cục bộ: chưa có bảng event/endpoint tổng hợp phía máy
chủ, nên chưa đo được toàn bộ nhóm HR hay nhiều máy — đó là việc tiếp theo nếu cần
số liệu để bảo vệ quyết định. E2E mới chỉ khẳng định event mở/rời hồ sơ; việc ghi
`BULK_RUN` và `VERIFICATION_COMPLETED` mới được kiểm ở mức unit test của lib và qua
hồi quy luồng, chưa có assert riêng trong e2e. Chưa thử trên dữ liệu staging thật.

## 2026-11-19 — Màn “Dữ liệu & lưu trữ”: hàng đợi retention và timeline quyết định theo hồ sơ

**Vấn đề.** Backend đã có `backend/app/api/retention.py` từ trước (liệt kê case, tạo,
xác nhận, huỷ) nhưng frontend không có màn nào, nên muốn xử lý hàng đợi lưu trữ/xoá
dữ liệu thì phải gọi API tay. HR cũng không có chỗ xem lại chuỗi quyết định của một
hồ sơ khi đối chiếu với trường hợp xoá.

**Thay đổi.**

- `frontend/src/lib/api.ts`: thêm `retentionApi` với đúng bốn thao tác người dùng làm
  được — `listCases`, `generateCases`, `confirmCase`, `cancelCase`. Hai endpoint còn
  lại của backend (`execute`, `recover`) **không** được đưa lên màn hình: chúng xoá
  dữ liệu thật và cần quy trình vận hành riêng; thêm nút đó là vượt phạm vi và tăng
  rủi ro.
- `frontend/src/lib/retention.ts` (mới): kiểu `RetentionCase`, nhãn trạng thái (Chờ
  xác nhận / Đã lên lịch xoá / Đã xoá dữ liệu / Đã huỷ), nhãn thực thi, `summarize`,
  và quan trọng nhất là **quy tắc hiển thị đúng như máy chủ sẽ chấp nhận**:
  `canConfirmRetentionCase` chỉ bật khi case `PENDING`, đã đến hạn và không có lần
  thực thi đang chạy (backend trả 422 nếu chưa đến hạn, 409 nếu đã xoá/đang xoá);
  `canCancelRetentionCase` không bật khi đang thực thi; `hasApplicationTimeline`
  tắt timeline với hồ sơ đã xoá.
- `frontend/src/app/data-retention/page.tsx` (mới): chọn vị trí (tự chọn vị trí đã
  đóng đầu tiên), dòng tổng hợp (tổng · đến hạn · chờ xác nhận · đã lên lịch · đã
  huỷ), bảng trường hợp với mã ẩn danh, hạn xoá, trạng thái, trạng thái thực thi,
  thời điểm xác nhận và nút hành động. “Tạo trường hợp lưu trữ” mở hộp thoại giải
  thích rằng chỉ vị trí đã đóng và quá hạn mới sinh case, bước này chưa xoá gì; kết
  quả nói rõ tạo được bao nhiêu case (hoặc vì sao không tạo được). Xác nhận/huỷ đều
  có hộp thoại riêng nói rõ hậu quả, gọi đúng endpoint `POST …/confirm` và
  `POST …/cancel`, rồi cập nhật đúng dòng đó.
- **Timeline theo hồ sơ**: mỗi dòng mở được lịch sử quyết định của chính hồ sơ đó
  bằng endpoint sẵn có `GET /applications/{id}/status-events` (ai đổi, khi nào, từ
  trạng thái nào sang đâu, lý do, ghi chú). 403 hiện thông báo “chỉ HR phụ trách”,
  hồ sơ đã xoá thì nút timeline bị tắt kèm giải thích.
- 403 khi tải danh sách (vị trí ngoài phạm vi) hiện đúng thông báo thay vì bảng
  rỗng gây hiểu nhầm là “không có case”. Sidebar có mục **Dữ liệu & lưu trữ**
  (nhóm HR, cạnh Shortlist); quyền thật vẫn do backend quyết định.
- Toàn bộ chuỗi mới đi qua `t()` và có bản dịch tiếng Anh.

**Phạm vi giữ nguyên.** Không sửa backend, không đổi schema, không thêm endpoint:
chỉ dùng đúng hợp đồng retention và status-events đang có.

**Kiểm thử.** `frontend/tests/retention-cases.test.cjs` (mới, 6 test) cho tổng hợp
đếm, nút xác nhận/huỷ đúng điều kiện máy chủ chấp nhận, hồ sơ đã xoá không có
timeline, nhãn lạ không render `undefined`, và đếm ngày đến hạn với ngày thiếu/sai.
`frontend/tests/retention-ui.e2e.cjs` (mới) chạy trang thật với API giả: danh sách
case + tổng hợp, nút Confirm bật/tắt đúng, tạo case báo kết quả và tải lại danh sách,
xác nhận/huỷ gửi đúng POST và đổi chip của dòng, timeline mở đúng lịch sử quyết định
và đóng lại được, case đã xoá không có timeline, và vị trí 403 hiện thông báo.
Hồi quy `a11y-mock` pass sau khi thêm mục sidebar.

**Chưa kiểm.** VM này không có backend/Postgres nên mọi phản hồi retention (kể cả
403, 409, 422) chỉ mô phỏng bằng mock; chưa thử trên dữ liệu thật ở staging.
Bước `execute`/`recover` chưa có UI — cố ý, xem phần Phạm vi.

## 2026-11-19 — Trang tuyển dụng công khai: song ngữ, form tệp dùng được trên điện thoại

**Vấn đề.** `/careers` là bề mặt duy nhất ứng viên thấy, nhưng tiêu đề, nhãn form,
nút và phần đồng ý Talent Pool đều hardcode tiếng Việt, không có chuyển ngôn ngữ;
chỉ có thông báo lỗi đi qua `t()`. Ô tệp là `<input type="file">` mặc định của trình
duyệt — trên điện thoại nó bé, khó bấm và không nói đã chọn CV nào, nên sinh viên
nộp bằng điện thoại dễ bỏ cuộc ngay từ cửa.

**Thay đổi.**

- Toàn bộ chuỗi của trang đi qua `t()`: tiêu đề, cảnh báo chỉ dùng dữ liệu tổng hợp,
nút ứng tuyển, nhãn từng trường, mô tả Talent Pool, mã rút, thông báo thành công và
thông báo lỗi tải danh sách. Khoảng 25 khoá mới có bản dịch tiếng Anh trong
`src/i18n/en.json`.
- `LanguageSwitcher` đặt ở góc phải tiêu đề trang (cùng thành phần các trang công khai
khác đang dùng), nên ứng viên đổi VI/EN ngay tại chỗ; `<html lang>` đổi theo.
- Form được làm lại: các trường `fullWidth` với `autoComplete` đúng loại, nút chọn
CV là `Button component="label"` cao 44px chứa input tệp (vẫn giữ `name="cv"`,
`accept=".pdf,.docx"`), tên tệp đã chọn hiện ngay dưới nút, hai nút gửi/hủy xếp dọc
trên điện thoại và cao 44px. Bỏ `required` trên input tệp ẩn (trình duyệt báo
“invalid form control … is not focusable”) và kiểm tra tệp trước khi gửi, với thông
báo rõ ràng.
- Không đổi API hay payload: vẫn `POST /v1/careers/jobs/{id}/apply` với
`request_id`, `pool_opt_in`, `pool_token` và tệp multipart.

**Kiểm thử.** `frontend/tests/careers-public.e2e.cjs` (mới) với API tuyển dụng giả:
đổi sang EN thì tiêu đề/nhãn/nút/đồng ý/thông báo đều đổi và `html[lang]=en`, đổi lại
VI vẫn đúng; trên 390×844 form không cuộn ngang, mọi nút ≥ 44px và nằm trong màn
hình, chọn tệp xong thấy tên `careers-cv.pdf`, gửi đi đúng một request multipart có
`request_id` + `pool_opt_in` + tệp và hiện thông báo đã nhận. `docx`/`tsc`/`eslint`/unit
đều giữ nguyên xanh.

**Chưa kiểm.** Chưa thử trên thiết bị thật (e2e dùng viewport 390×844, có touch);
chưa có backend thật ở VM này nên phản hồi 202/409/422 của API tuyển dụng chỉ mô
phỏng bằng mock. Trang demo `/careers-demo` vẫn tiếng Việt — ngoài phạm vi yêu cầu.

## 2026-11-19 — Lô hàng loạt sống sót khi đóng tab: biên bản được giữ, chỗ dừng trung thực

**Vấn đề.** Mục 5 của danh sách cải tiến có ba phần: tiến trình, kết quả từng hồ sơ
và thử lại phần lỗi (đã làm ở mục trước), còn phần thứ ba chưa xong — **đóng tab là
mất dấu việc đang chạy**. Lô 30–50 hồ sơ chỉ cần một lần rớt mạng là HR mất biên bản:
không biết hồ sơ nào đã ghi, hồ sơ nào lỗi, và hồ sơ đang ghi dở thì đã sang trạng
thái mới hay chưa.

**Thay đổi.**

- `frontend/src/lib/bulkActionRun.ts`: biên bản lô được tuần tự hóa (`version`,
  `position_id`, `mode`, `reason`, `rows`, `saved_at`) và đọc lại qua
  `parseStoredBulkRun()`. Dữ liệu sai phiên bản, của vị trí khác, JSON hỏng, hoặc dòng
  có bước không hợp lệ bị bỏ toàn bộ — không dựng ra biên bản giả.
- Trạng thái mới `interrupted`: dòng đang chạy đúng lúc lô bị dừng được đánh dấu
  **“Chưa rõ kết quả”**, giữ số bước đã biết nhưng **không** được tự thử lại, vì bước
  cuối có thể đã lưu. `retryFailed()` chỉ đụng dòng `failed`; tiến trình đếm thêm
  `interrupted`.
- Màn xếp hạng lưu lô vào `localStorage` sau mỗi thay đổi (chỉ khi đã có hồ sơ rời
  trạng thái chờ, nên mở rồi đóng không tạo cảnh báo rác), và xoá khi mọi hồ sơ đã
  xong. Khi mở lại trang, nếu còn hồ sơ chưa xong thì hiện một dải nhắc:
  “Lô Shortlist lần trước chưa xong: 1/2 hồ sơ đã cập nhật, 1 lỗi, 0 chưa rõ kết quả”
  với **Xem biên bản** (mở lại đúng hộp thoại, đúng lý do chung, đúng chỗ dừng) và
  **Bỏ qua** (xoá bản lưu).
- Dòng bị gián đoạn trong hộp thoại nói rõ “Lô bị gián đoạn khi đang ghi hồ sơ này;
  mở hồ sơ để kiểm tra trạng thái trước khi làm lại” kèm link mở hồ sơ; khi chỉ còn
  dòng chưa rõ thì hộp thoại chỉ có **Đóng**, không có nút thử lại.
- Nút hành động của lô đã dừng đổi thành **Đóng** + **Thử lại {n} hồ sơ lỗi** (chỉ
  hiện khi thật sự có dòng lỗi), và `handleBulkApply` không chạy khi không còn dòng
  chờ — bấm nhầm không sinh thông báo “Đã cập nhật 0 hồ sơ”.

**Phạm vi giữ nguyên.** Vẫn tuần tự từng `PATCH /applications/{id}/status` hiện có,
không endpoint mới, không đổi schema hay ma trận trạng thái. `localStorage` chỉ là
bản lưu phía trình duyệt của chính HR, không gửi đi đâu; bị chặn storage thì lô vẫn
chạy bình thường.

**Kiểm thử.** `frontend/tests/bulk-run.test.cjs` thêm 3 test: dòng đang ghi thành
“chưa rõ” và không bị thử lại, lưu/đọc lại đúng và loại payload sai (sai vị trí, sai
phiên bản, JSON hỏng, dòng vô lý), dòng `running` khi đọc lại thành `interrupted`.
`frontend/tests/bulk-recovery.e2e.cjs` (mới) chạy một lô lỗi thật, **tải lại trang**,
thấy dải nhắc đúng số liệu, mở biên bản, thử lại chỉ đúng hồ sơ lỗi, rồi tải lại lần
nữa để chắc bản lưu đã được xoá; và một cảnh tab chết giữa bước hai: dòng hiện “Chưa
rõ kết quả”, có link mở hồ sơ, không có nút thử lại.

**Chưa kiểm.** Chưa thử trên trình duyệt thật khi mất mạng giữa request (e2e mô phỏng
bằng một PATCH trả 503 và bằng bản lưu viết tay); chưa có backend thật ở VM này.

## 2026-11-19 — Bảng DOCX giữ hàng cột; lọc hồ sơ theo bằng chứng và thời gian chờ

**Vấn đề 1 — CV dạng bảng đọc lệch hàng.** Bộ đọc DOCX duyệt mọi `w:p` trong tài
liệu, kể cả đoạn nằm trong ô bảng, nên bảng bị làm phẳng thành một dòng cho mỗi ô:
“Python”, “2022”, “VinIT” rơi xuống ba dòng và HR đối chiếu nhầm hàng khi so với tiêu
chí. CV sinh viên rất hay dùng bảng, nên đây là lỗi đọc sai chứ không chỉ là xấu.

**Thay đổi 1.** `frontend/src/lib/docxText.ts` giữ nguyên cấu trúc: duyệt con của
`w:body` theo đúng thứ tự, `w:p` thành đoạn, `w:tbl` thành **bảng** (hàng `w:tr`, ô
`w:tc`, text các đoạn trong ô ghép lại). Ô trộn giữ đúng vị trí cột (`w:gridSpan` → ô
trống đệm), hàng tiêu đề chỉ được đánh dấu khi Word đánh dấu (`w:tblHeader`), không
đoán. Nội dung trong content control (`w:sdt`) vẫn được đọc. `extractDocxBlocks()`
trả block cho phần hiển thị; `extractDocxParagraphs()` cũ vẫn còn cho chỗ chỉ cần
text (mỗi hàng bảng thành một dòng tab). `CVDocumentViewer` render block bảng bằng
`Table` của MUI, có tiêu đề khi Word đánh dấu. Vẫn không thêm thư viện, không đổi
backend, không dùng `innerHTML`.

**Vấn đề 2 — ô tìm chỉ lọc tên.** Dòng đếm chỉ nói “Đang lọc theo tên”, trong khi
việc HR làm hằng ngày là “hồ sơ nào thiếu bằng chứng cho tiêu chí X” và “hồ sơ nào
chờ tôi xác minh quá 3 ngày”; hai câu đó trước đây phải mở từng hồ sơ để tự dò.

**Thay đổi 2.** `frontend/src/lib/applicantReview.ts` thêm
`ApplicantCriteriaFilter` (`criterionId`, `outcome`, `verificationWaitingDays`) và
`matchesApplicantCriteriaFilter()`, ghép với bộ lọc hàng đợi và ô tên thay vì thay
thế nhau:

- “Thiếu bằng chứng” gồm kết quả `UNCLEAR`, kết quả còn `requires_verification`, và
  hồ sơ **không có** kết quả cho tiêu chí đó (kể cả hồ sơ chưa đánh giá) — đúng tập
  hồ sơ HR phải xem.
- Kết quả khác (`Chưa đáp ứng`, `Đã đáp ứng`, `Mọi kết quả`) lọc đúng kết quả đó;
  `MATCH` bao gồm `STRONG_MATCH`.
- “Chờ xác minh quá N ngày” đòi cả cờ cần xác minh **và** tuổi hồ sơ; hồ sơ không
  rõ ngày tạo không bị coi là đã chờ đủ N ngày.
- Màn xếp hạng có ba ô chọn (tiêu chí / bằng chứng / thời gian chờ), dòng đếm nói
  đúng đang lọc gì, và “Xoá bộ lọc và tìm kiếm” đặt lại cả ba. Không đổi API, không
  đổi schema; danh sách tiêu chí lấy từ chính `criterion_results` đã có trong xếp hạng.

**Kiểm thử.** `frontend/tests/applicant-criteria-filter.test.cjs` (mới, 5 test) cho
“thiếu bằng chứng”, từng kết quả, thời gian chờ (kể cả ngày tạo không rõ), và việc
ghép với hàng đợi/ô tên. `applicant-criteria-filter.e2e.cjs` (mới) bấm thật ba ô chọn
trên dữ liệu xếp hạng biến thiên và đối chiếu số dòng + tên dòng. `docx-preview.e2e.cjs`
giờ phục vụ một DOCX **có bảng** và kiểm bảng giữ đúng hàng, đúng thứ tự cột, hàng
tiêu đề là `th` thật.

**Chưa kiểm.** Không có backend chạy ở VM này nên dữ liệu xếp hạng thật vẫn qua
mock; DOCX thật của ứng viên (bảng trộn ô phức tạp, ảnh, chữ trong shape) chưa được
thử — bộ đọc vẫn chỉ đọc text, không dựng lại bố cục.

## 2026-11-19 — Hành động hàng loạt có biên bản: tiến trình, chỗ dừng, thử lại phần lỗi

**Vấn đề.** Shortlist/loại hàng loạt chạy lần lượt từng hồ sơ rồi mới báo kết quả,
nên với lô vài chục hồ sơ HR chỉ thấy nút “Đang cập nhật 20 hồ sơ…” không biết đang
ở hồ sơ nào. Khi một hồ sơ lỗi giữa đường, toàn bộ lỗi bị dồn thành một câu trong
Snackbar, kèm một câu cứng “đã ghi nhận bước Mới → Đang xem, chưa tới Shortlist”
hiển thị cho mọi trường hợp — kể cả khi hồ sơ lỗi ngay bước đầu và chưa ghi gì.
Muốn cứu những hồ sơ lỗi, HR phải chạy lại cả lô: hồ sơ đã xong bị gọi lại, và với
hồ sơ dừng giữa đường bước đã ghi lại bị lặp trong lịch sử.

**Thay đổi.**

- `frontend/src/lib/bulkActionRun.ts` (mới): lô được chốt thành danh sách hồ sơ kèm
  **các bước hợp lệ** lấy đúng từ ma trận chuyển trạng thái hiện có (Mới → Đang xem
  → Shortlist; Đang xem → Shortlist; loại một bước). Mỗi dòng nhớ `applied` (số bước
  đã ghi) và `reached_status`, nên biết chính xác chỗ dừng và biết lần sau đi tiếp
  từ đâu. `retryFailed()` chỉ đưa các dòng lỗi về chờ, `remainingSteps()` trả phần
  còn thiếu; `stopPoint()` trả `null` khi hồ sơ lỗi ngay bước đầu (chưa ghi gì thì
  không được nói “đã sang Đang xem”).
- Hộp thoại xác nhận giữ **biên bản tại chỗ**: tiến trình “Đang xử lý 2/5: <tên>”
  kèm thanh tiến độ, và từng hồ sơ có chip trạng thái (Chờ xử lý / Đang xử lý / Xong
  / Lỗi). Hồ sơ lỗi hiện lý do từ máy chủ và **chỗ dừng** (“Đã ghi nhận bước Đang
  xem, chưa tới Shortlist.”).
- Chỉ khi **tất cả** hồ sơ đều lỗi mới không có gì để thử lại; còn lại nút “Thử lại
  {n} hồ sơ lỗi” chạy đúng tập lỗi, không gọi lại hồ sơ đã xong và không lặp bước đã
  ghi. Lựa chọn trên trang được thu về đúng các hồ sơ lỗi, nên thanh hành động không
  mời chạy lại việc đã hoàn tất. Lô thành công toàn bộ vẫn đóng hộp thoại và báo
  bằng thông báo như trước.

**Phạm vi giữ nguyên.** Không thêm endpoint, không đổi schema hay ma trận chuyển
trạng thái: mỗi bước vẫn là một lần gọi `PATCH /applications/{id}/status` hiện có,
 và lý do chung vẫn được gửi cho từng hồ sơ. Lý do dùng cho thử lại là lý do còn
 trong hộp thoại, nên loại hàng loạt thử lại vẫn bắt buộc có lý do.

**Kiểm thử.** `frontend/tests/bulk-run.test.cjs` (mới, 5 test) cho bước hợp lệ, lọc
hồ sơ không có bước, thử lại chỉ phần lỗi và đi tiếp từ bước còn thiếu, chỗ dừng,
và đếm tiến trình. `bulk-actions.e2e.cjs` bổ sung cảnh lỗi thật: một hồ sơ Đang xem
chậm (thấy tiến trình), một hồ sơ Mới lỗi ở bước Shortlist (thấy lý do + chỗ dừng),
rồi thử lại chỉ gọi đúng hồ sơ lỗi và đúng bước còn thiếu.

## 2026-11-19 — Gom quyền màn hồ sơ về một object `capabilities`

**Vấn đề.** Màn hồ sơ tự quyết định hiện gì từ hai cờ rời `can_update_status` và
`can_manage_hr_notes`, trong khi mỗi endpoint có cổng riêng: ghi nhận xác minh bằng
chứng (`POST /assessments/results/{id}/review`) chỉ nhận quyền HR notes, còn
`can_update_status` là quyền đổi trạng thái. Hai quyền này không luôn đi cùng nhau —
ADMIN toàn cục có quyền đổi trạng thái nhưng không có quyền HR notes — nên người đó
vẫn thấy nút “Trích dẫn đúng, đã kiểm” / “Trích dẫn sai”, và bấm vào là **403**. Nút
“Đã xử lý xong hồ sơ này” cũng gửi review cho mọi tiêu chí còn chờ, nên cả vòng hoàn
tất hỏng ngay ở bước đầu.

**Thay đổi.**

- `backend/app/core/permissions.py`: `_application_access_flags` trả **một cờ cho một
  hành động** — `view_cv`, `view_evidence`, `update_status`, `review_evidence`,
  `manage_hr_notes`, `edit_profile`, `view_status_history`, `reprocess_cv` — mỗi cờ
  trùng đúng cổng của endpoint tương ứng. `application_capabilities()` công bố object
  này; `application_access()` cũ vẫn trả ba cờ như trước nhưng tính từ cùng một lần
  đọc, nên các chỗ gọi cũ không phải sửa và hai đường không thể lệch nhau.
- `backend/app/schemas/applications.py`: schema `ApplicationCapabilities`, gắn vào
  `ApplicationWithAssessment`. Ba cờ phẳng giữ nguyên cho client cũ.
- `backend/app/api/applications.py`: `GET /applications/{id}` trả `capabilities`;
  `view_evidence` được thu hẹp theo từng assessment, nên share chỉ tóm tắt vẫn không
  thấy bằng chứng.
- `frontend/src/lib/applicationCapabilities.ts` (mới): đọc object, đổi sang tên
  camelCase, có dự phòng ba cờ rời cho payload cũ; cờ thiếu = `false` (ẩn nút, không
  để lộ 403). `review_evidence` **không** suy ra từ `update_status`.
- Màn hồ sơ dùng một biến `caps` cho mọi nút: xác minh theo `reviewEvidence`, đổi
  trạng thái / lịch sử / xử lý lại CV theo `updateStatus`, ghi chú HR theo
  `manageHrNotes`, sửa hồ sơ theo `editProfile`. Bước hoàn tất chỉ gửi review cho
  người có quyền xác minh, và hộp thoại nói rõ phần việc còn lại vẫn chờ HR thay vì
  đòi xác nhận một việc họ không ghi được.

**Kiểm thử.** `tests/application-capabilities.test.cjs` (4 test: đọc đúng object, quyền
đổi trạng thái không kéo theo quyền xác minh, dự phòng cờ rời, cờ thiếu = false) —
`npm run test:unit` 48/48; `test:i18n` 3/3; `type-check` và `lint` pass; `py_compile`
ba file backend pass. e2e: `capabilities` (mới — người chỉ đổi được trạng thái: không
có nút xác minh, hộp thoại giải thích, không có request review nào), `verify-only`,
`finish-application`, `ux02-review`, `ranking-context` — pass. Fixture chung nay mô tả
đúng một HR phụ trách (đủ cả hai quyền); trước đó nó là “đổi trạng thái nhưng không
có quyền notes”, tức đúng hình dạng gây 403, và mock vẫn trả 201 nên lỗi bị che.

**Chưa kiểm.** Chưa chạy bộ test backend: VM này không cài được dependency Python
(`pytest` không có, không có virtualenv), nên object capabilities mới được kiểm ở
phía frontend với payload mô phỏng và chỉ đảm bảo biên dịch ở backend. Chưa thử với
API thật + DB thật cho các tổ hợp quyền khác (share chỉ tóm tắt, Hiring Manager).

## 2026-11-19 — Test i18n bắt được nhãn trong `src/lib` và lỗi trang ứng tuyển

**Vấn đề.** Test i18n chỉ quét file `.tsx` và chỉ tìm `t('<literal>')`, nên hai loại
chuỗi thoát lưới. (1) Nhãn khai báo trong `src/lib` (bảng nhãn hàng đợi, thông điệp
lỗi trả về nguyên văn): giao diện dịch chúng qua `t(LABELS[x])` nên test không thấy
khoá nào và một nhãn mới có thể lên production mà không có bản dịch. (2) Lỗi của
form ứng tuyển công khai: `careers/page.tsx` render thẳng `{error}`, nên câu tiếng
Việt vẫn hiện nguyên khi người dùng chọn tiếng Anh, dù khoá đã có bản dịch trong
`en.json`.

**Thay đổi.**

- `frontend/tests/i18n.test.cjs`: đọc bằng AST thay vì regex (comment không bị tính
  là nhãn) và mở rộng phạm vi thành đúng hai luật: `t('literal')` ở mọi file
  `.ts`/`.tsx` dưới `src` (trừ `src/i18n`), cộng mọi literal tiếng Việt trong
  `src/lib`. Literal nằm trong phép so sánh (`===`, `==`, `!==`, `!=`) được bỏ qua
  vì đó là hợp đồng với server (`'IN_REVIEW'`, `'application/pdf'`), không phải nhãn.
  Sau khi mở rộng đã rút lại còn hai luật này (bỏ nhánh `PropertyAssignment` /
  `ReturnStatement` thừa) và kiểm chứng âm: test bắt được literal trong
  `src/lib/intake.ts` và `src/lib/workQueueLabels.ts`, và không đòi dịch mã trạng thái.
- `frontend/src/app/careers/page.tsx`: render `{t(error)}`.
- `frontend/src/i18n/en.json`: thêm 6 bản dịch cho các câu lỗi của form ứng tuyển
  (không rõ đã nhận hay chưa, mã yêu cầu đã dùng, yêu cầu hết hạn, dịch vụ chưa
  sẵn sàng, dữ liệu không hợp lệ, lỗi chung).
- `frontend/tests/intake-ui.e2e.cjs`: thêm một lượt chạy giao diện tiếng Anh — gửi
  hồ sơ thử nghiệm với API bị ngắt và khẳng định câu lỗi hiện bằng tiếng Anh, không
  rơi về tiếng Việt.

**Kiểm thử.** `npm run test:i18n` 3/3, `npm run test:unit` 44/44, `npm run lint` và
`npm run build` pass; e2e `intake-ui` pass (gồm kiểm tra "Careers failure message
follows the selected language: OK").

**Chưa kiểm.** Chưa dịch phần còn lại của trang careers (tiêu đề, nút, cảnh báo vẫn
là tiếng Việt ở cả hai ngôn ngữ); mới kiểm đúng câu lỗi mà form trả về.

## 2026-11-19 — Bỏ nốt từ vựng "matching" khỏi bản dịch tiếng Anh

**Vấn đề.** Giao diện đã thay "matching" bằng từ vựng nghiệp vụ ở lượt trước, nhưng
`frontend/src/i18n/en.json` vẫn còn 11 khoá mở đầu bằng "Điểm matching", "Nhóm
matching", "Chạy matching"… Không màn hình nào còn hỏi những khoá này, nên chúng là
bản dịch mồ côi: người đọc file dễ tưởng giao diện vẫn dùng "matching", và lần sau
thêm lại thuật ngữ cũ sẽ không ai thấy mâu thuẫn. Ngược lại, khoá "Tất cả" (nhãn bộ
lọc đầu tiên) đang được dùng thật nhưng thiếu bản dịch, nên ở giao diện tiếng Anh
nhãn đó vẫn là tiếng Việt.

**Thay đổi** (chỉ dữ liệu, `frontend/src/i18n/en.json`):

- Xoá 11 khoá chứa "matching": "Điểm matching tổng hợp", "Lọc theo nhóm matching",
  "Nhóm matching", "Điểm matching", "Điểm matching cao nhất", "Chưa matching",
  "Chạy matching", "Một số hồ sơ đã sẵn sàng nhưng chưa được matching.", "Đã
  matching", "Hồ sơ chưa matching", "Matching & HR rà soát".
- Thêm `"Tất cả": "All"`.

**Kiểm thử.** `npm run test:i18n` 3/3 (test quét đúng các khoá `t('...')` trong
`src`), `npm run build` pass.

**Chưa kiểm.** Chưa mở lại màn hình xếp hạng ở chế độ tiếng Anh để nhìn nhãn bộ lọc
sau khi thêm bản dịch; chỉ khẳng định bằng test và build.

## 2026-11-19 — Thanh hành động nổi dùng được trên điện thoại

**Vấn đề.** Đo trên Chromium 390×844 (và 360×640): thanh hành động nổi
(`position: fixed`, `left: 50%`, không có `width`) co lại còn **195px rộng và
311px cao** — chiếm hơn một phần ba màn hình, nhãn nút gãy dòng, và trang không
chừa chỗ nên **dòng hồ sơ cuối nằm dưới thanh** (card cuối kết thúc ở 752px,
thanh bắt đầu ở 521px). Nút trong thanh chỉ cao 43–45px, nút xác nhận trong hộp
thoại còn thấp hơn mức chạm thoải mái.

**Thay đổi** (`frontend/src/app/positions/[id]/applicants/page.tsx`):

- Thanh trải hết bề ngang trên điện thoại (`left/right: 8px`, bỏ `translateX`),
  giữ kiểu canh giữa trên desktop; nhãn không gãy dòng, cỡ chữ 13px trên mobile
  để ba hành động xếp vừa hai dòng thay vì bốn.
- Mọi nút trong thanh và hai nút của hộp thoại cao **tối thiểu 44px**; hộp thoại
  xếp nút theo cột trên điện thoại để nút xác nhận rộng và nằm cuối tầm tay.
- Trang đo chiều cao thật của thanh (`ResizeObserver`) và tự chừa
  `padding-bottom` tương ứng, nên hồ sơ cuối luôn cuộn lên trên thanh thay vì bị
  che; không dùng con số cứng vì chiều cao thanh phụ thuộc bề ngang.
- Kết quả đo lại: 390×844 → thanh 167px cao, không chồng lấn (card cuối 581px,
  thanh 669px); 360×640 → thanh 167px, card cuối 357px, thanh 465px.

**Kiểm thử.** Bổ sung mục 5 vào `frontend/tests/bulk-actions.e2e.cjs`: chạy lại
luồng ở 390×844 và 360×640, khẳng định thanh trải sát hai mép, cao ≤ 40% màn
hình, đủ 4 nút với chiều cao ≥ 44px và không tràn ngang, card cuối cùng nằm trên
thanh sau khi cuộn hết, nút xác nhận ≥ 44px và nằm trọn trong màn hình, không có
exception phía client.

| Lệnh | Kết quả |
| --- | --- |
| `npm run test:e2e:bulk-actions` (có kiểm tra mobile) | pass |
| `npm run test:e2e:ranking-context`, `ranking-compact`, `duplicate-warning` | pass |
| `npm run type-check` / `npm run lint` / `npm run test:unit` / `npm run build` | pass |

**Chưa kiểm.** Chưa thử trên thiết bị thật hay trình duyệt di động khác
(iOS Safari, thanh địa chỉ động làm `innerHeight` thay đổi); chưa xem ảnh chụp —
chỉ đo hình học qua Chromium headless. Chưa kiểm bàn phím ảo che thanh khi gõ lý do
chung trong hộp thoại.

## 2026-11-19 — Shortlist hàng loạt được cả hồ sơ Mới (hai bước)

**Vấn đề.** Thanh hành động hàng loạt chỉ shortlist hồ sơ Đang xem; hồ sơ Mới bị
bỏ qua và hiện cảnh báo “cần chuyển sang Đang xem trước”. HR vừa lọc ra một lô
ứng viên mới vừa xem xong vẫn phải mở từng hồ sơ bấm hai lần, hoặc bỏ lô đó.

**Thay đổi** (chỉ frontend, không thêm endpoint, không đổi state machine):

- `frontend/src/app/positions/[id]/applicants/page.tsx`: lô shortlist nay gồm cả
  hồ sơ `NEW`. Mỗi hồ sơ Mới được đẩy qua đúng hai bước của ma trận hiện có:
  `NEW → IN_REVIEW → SHORTLIST`, mỗi bước một lần gọi
  `PATCH /applications/{id}/status`; hồ sơ Đang xem vẫn một bước.
- Hộp thoại xác nhận nêu rõ: số hồ sơ Mới sẽ **ghi nhận hai lần chuyển trạng
  thái** (`Mới → Đang xem → Shortlist`), mỗi bước là một lần gọi API trạng thái
  hiện có nên lịch sử hồ sơ có hai mục. Từng dòng trong danh sách được đánh dấu
  “Mới · 2 bước chuyển trạng thái”.
- Cảnh báo “bỏ qua” chỉ còn dành cho hồ sơ không shortlist được từ trạng thái
  hiện tại (đã Shortlist, hoặc ngoài vòng sàng lọc).
- Lỗi giữa hai bước được báo đúng chỗ dừng: hồ sơ Mới đã lưu bước đầu nhưng
  chưa tới Shortlist thì thông báo nói rõ, để HR không tưởng hồ sơ còn nguyên
  trạng thái.
- Thông báo thành công nêu số hồ sơ Mới đã ghi hai lần chuyển trạng thái.

**Kiểm thử.**

| Lệnh | Kết quả |
| --- | --- |
| `npm run type-check` / `npm run lint` / `npm run test:i18n` / `npm run test:unit` | pass |
| `npm run build` | pass |
| `npm run test:e2e:bulk-actions` (cập nhật) | pass |
| `npm run test:e2e:ranking-context`, `ux03-dashboard`, `duplicate-warning`, `vocabulary-locale` | pass |

E2E chọn 3 hồ sơ (Đang xem + đã Shortlist + Mới) và xác nhận: nút ghi
“Shortlist 2 hồ sơ”; hộp thoại có thông báo hai bước và dòng “Mới · 2 bước”;
chỉ bỏ qua 1 hồ sơ; các request đúng thứ tự
`app-0 SHORTLIST`, `app-11 IN_REVIEW`, `app-11 SHORTLIST`; thông báo cuối nêu
“hai lần chuyển trạng thái”.

**Chưa kiểm.** Chưa chạy với backend thật (mock chấp nhận mọi bước, chỉ kiểm
thứ tự request). Nhánh lỗi giữa hai bước chỉ được đọc trong code, chưa có e2e
giả lập PATCH thứ hai thất bại. Chưa xem trực quan hộp thoại — chỉ kiểm qua
Chromium headless.

## 2026-11-19 — Xem CV DOCX ngay trong màn hồ sơ (UX mục 4)

**Vấn đề.** Khung “CV gốc” chỉ nhúng được PDF. Với CV `.docx`, HR chỉ thấy dòng
“Tệp DOCX cần được tải xuống để xem.” — phải tải tệp ra ngoài rồi mở bằng Word
mới đọc được, trong khi việc đang làm là đối chiếu bằng chứng AI với nội dung CV
ngay trên màn hình.

**Phương án đã chọn.** Đọc tệp ngay trong trình duyệt, **không đổi backend và
không thêm thư viện tài liệu**:

- `.docx` là một ZIP chứa `word/document.xml`. Trình duyệt đã có
  `DecompressionStream('deflate-raw')`, nên chỉ cần đọc central directory của
  ZIP, giải nén đúng entry đó và lấy text từ các run `<w:t>` (kèm `w:tab`,
  `w:br`). File mới: `frontend/src/lib/docxText.ts`.
- Nội dung được render thành các đoạn văn bằng React text node, **không dùng
  `innerHTML`**, nên tệp CV không thể chèn HTML/script vào app.
- `CVDocumentViewer` thêm nhánh hiển thị văn bản DOCX cuộn được, kèm ghi chú
  “bố cục gốc có thể khác, tải CV gốc để xem đúng định dạng”. Nút chuyển trang
  vẫn tắt vì bản xem này không có số trang.
- Trang hồ sơ chỉ đọc DOCX **sau khi HR bấm “Xem CV gốc”** (giữ nguyên nguyên tắc
  tải theo yêu cầu); nếu không đọc được (tệp hỏng, `.doc` đổi đuôi, ZIP mã hoá)
  thì hiện thông báo và giữ nguyên nút tải bản gốc — không bao giờ mất đường lấy
  tệp.
- Lý do không chọn các phương án khác: chuyển DOCX→PDF ở server cần thêm
  LibreOffice/converter vào đường request (rủi ro vận hành, đổi backend); dùng
  thư viện render DOCX phía client (mammoth…) thêm dependency nặng và mở thêm bề
  mặt render HTML. Cách này chỉ thêm một file thuần TS đọc văn bản.

**Kiểm thử.**

| Lệnh | Kết quả |
| --- | --- |
| `npm run type-check` / `npm run lint` / `npm run test:i18n` / `npm run test:unit` | pass |
| `npm run build` | pass |
| `npm run test:e2e:docx-preview` (mới) | pass |
| `npm run test:e2e:ux04-sticky-viewer`, `ux02-review`, `finish-application`, `verify-only` | pass |

E2E mới dựng **DOCX thật** trong fixture (tự viết ZIP + WordprocessingML, nén
DEFLATE) và xác nhận: mở hồ sơ không tải CV; sau khi bấm chỉ có đúng một request
`cv-file`; văn bản hiện đủ từng đoạn, đoạn đầu đúng thứ tự; không có iframe PDF;
không có XML thô trong DOM; nút “Trang sau” bị tắt; có câu nhắc tải bản gốc;
không có exception phía client.

**Chưa kiểm.** Chưa thử với tệp DOCX thật nhiều trang/bảng biểu từ Word (fixture
là DOCX tối giản, có nén): bảng và cột sẽ được làm phẳng thành đoạn văn, không
giữ bố cục. Chưa xử lý `.doc` cũ (không phải ZIP) — sẽ rơi vào thông báo “không
đọc được” kèm nút tải gốc. Tệp DOCX có mật khẩu cũng rơi vào nhánh đó. Chưa đo
hiệu năng với CV dài trên thiết bị yếu.

## 2026-11-19 — Nút “Đã xử lý xong hồ sơ này” cho người chỉ có quyền xác minh

**Vấn đề.** Nút hoàn tất hồ sơ và cả nút xác nhận/xoá từng tiêu chí đều bị khoá
theo `can_update_status`. Backend lại cho phép xác minh bằng chứng theo
`can_manage_hr_notes` (`POST /assessments/results/{id}/review`). Người chỉ được
xác minh bằng chứng vì vậy không có cách nào đưa hồ sơ ra khỏi hàng đợi “Cần xác
minh” — vòng hoàn tất bị khoá cứng.

**Thay đổi** (chỉ frontend; không thêm endpoint, không đổi state machine, không
đổi quyền ở backend):

- `frontend/src/app/positions/[id]/applicants/[applicantId]/page.tsx`: nút hoàn
  tất và nút xác nhận tiêu chí hiện khi người dùng **xác minh được bằng chứng
  hoặc đổi được trạng thái** (`can_manage_hr_notes || can_update_status`), không
  còn phụ thuộc riêng `can_update_status`.
- Hộp thoại hoàn tất: phần chọn trạng thái (dropdown, lý do loại, ghi chú) chỉ
  hiện khi có quyền đổi trạng thái. Khi không có quyền đó, hộp thoại ghi rõ
  “Bạn chỉ có quyền xác minh bằng chứng; hồ sơ giữ nguyên trạng thái sau khi
  hoàn tất.” và `handleFinish` không gọi API đổi trạng thái.
- Thanh điều hướng hồ sơ trước/tiếp theo và đường quay lại danh sách xếp hạng
  cũng dùng điều kiện trên, để người chỉ xác minh vẫn đi hết hàng đợi.
- `frontend/src/i18n/en.json`: thêm bản dịch cho câu giải thích mới.

**Kiểm thử.**

| Lệnh | Kết quả |
| --- | --- |
| `npm run type-check` / `npm run lint` / `npm run test:i18n` / `npm run test:unit` | pass |
| `npm run build` | pass |
| `npm run test:e2e:verify-only` (mới) | pass |
| `npm run test:e2e:finish-application`, `ux02-review`, `ux04-sticky-viewer`, `ux08-feedback`, `ranking-compact`, `duplicate-warning` | pass |

E2E mới dùng hồ sơ giả `app-verifier` (`can_update_status: false`,
`can_manage_hr_notes: true`) và xác nhận: nút hoàn tất hiện; hộp thoại không có
`finish-status` nhưng có thông báo giải thích; vẫn bắt buộc tick xác nhận đã xem
bằng chứng; khi xác nhận chỉ gọi `POST .../review` cho từng tiêu chí, **không**
gửi `PATCH .../status`; sau đó chuyển sang danh sách kèm cờ `completed=1`.

**Chưa kiểm.** Chưa chạy với backend thật. Nhánh quyền chỉ-xác-minh hiện chỉ
được dựng bằng mock; nếu backend đổi cổng quyền của endpoint review thì frontend
phải đổi theo cùng. Khi người dùng chỉ có quyền đổi trạng thái (ví dụ ADMIN toàn
cục, `can_manage_hr_notes` false) nút xác nhận tiêu chí vẫn hiện như trước và
backend vẫn có thể trả 403 — hành vi cũ, không thuộc phạm vi thay đổi này.

## 2026-11-19 — Một bộ từ vựng hàng đợi, bỏ thuật ngữ “matching”, ngày theo ngôn ngữ

**Vấn đề.** Dashboard và trang xếp hạng gọi cùng một việc bằng hai tên khác nhau
(“File CV cần HR kiểm tra” / “Cần kiểm tra file”; “Hồ sơ cần xác minh bằng chứng” /
“Cần xác minh”), nên HR phải học lại từ vựng khi đổi màn hình. UI còn dùng chữ
“matching” của lập trình viên, và nhiều chỗ format ngày cứng `vi-VN` dù người
dùng đã chọn tiếng Anh.

**Thay đổi.**

- `frontend/src/lib/workVocabulary.ts` (mới): một nguồn duy nhất cho tên việc và
  ba cụm **Cần tôi xử lý / Cần tôi quyết / Đã quyết**, kèm hàm xếp từng loại
  việc Dashboard và từng hàng đợi xếp hạng vào cụm.
- `frontend/src/lib/applicantReview.ts` và `frontend/src/lib/workQueueLabels.ts`
  lấy nhãn từ module đó: chip lọc và việc trên Dashboard dùng đúng một cách gọi.
- Dashboard: `WorkQueueList` nhóm việc theo ba cụm có tiêu đề và số lượng; cụm
  “Đã quyết” hiện số hồ sơ đã xác minh xong (giữ `data-testid`
  `verification-complete-summary`), thay cho dòng rời phía trên.
- Trang xếp hạng: chip lọc được nhóm theo cùng ba cụm, ghi cụm ngay trước các
  chip trên cùng dòng chảy để không đẩy bảng dữ liệu xuống (đo lại: dòng đầu
  647px, vẫn dưới ngưỡng 720px của `ranking-compact`).
- Bỏ thuật ngữ “matching” khỏi UI: `Nhóm matching` → `Mức phù hợp`,
  `Điểm matching cao nhất` → `Điểm phù hợp cao nhất`, `Chưa matching` →
  `Chưa đánh giá`, `Đã matching` → `Đã đánh giá`, `Chạy matching` →
  `Chạy đánh giá`, `Matching & HR rà soát` → `Đánh giá & HR rà soát`.
- Định dạng ngày dùng `dateLocale` của ngôn ngữ đang chọn thay cho `vi-VN` cứng
  ở: `EvidenceCard`, `careers`, `careers-demo`, `talent-pool`,
  `talent-pool-demo`, `gmail-test`.
- `frontend/src/i18n/en.json`: 13 chuỗi mới cho cụm, nhãn và thông báo.
- Test: thêm assertion cụm/từ vựng vào `work-queue-labels.test.cjs`; loader của
  `workspace-ui` và `queue-contract` biết shim `./workVocabulary`; e2e mới
  `vocabulary-locale.e2e.cjs`; `ranking-context` mock thêm endpoint cảnh báo
  trùng (trang tự tải từ mục trước). `loadDuplicates` giờ chịu được payload
  không phải mảng thay vì làm sập cả trang.

**Kiểm thử đã chạy (pass).**

| Lệnh | Kết quả |
| --- | --- |
| `npm run type-check` / `npm run lint` | pass |
| `npm run test:i18n` | 3/3 |
| `npm run test:unit` | 44/44 (thêm test cụm) |
| `npm run build` | pass |
| `npm run test:e2e:vocabulary-locale` | pass |
| `npm run test:e2e:ux03-dashboard` | pass |
| `npm run test:e2e:ranking-compact` | pass (dòng đầu 647px) |
| `npm run test:e2e:ranking-context` | pass |
| `npm run test:e2e:duplicate-warning`, `bulk-actions`, `finish-application`, `deadline-mock` | pass |

E2E xác nhận: Dashboard và chip xếp hạng cùng có ba cụm “Cần tôi xử lý / Cần tôi
quyết / Đã quyết” và cùng từ ngữ cho từng việc; không còn chữ “matching” trong
nội dung hiển thị của Dashboard và trang xếp hạng; với ngôn ngữ tiếng Anh, hạn
ứng tuyển hiển thị `11/25/2026` thay vì `25/11/2026`.

**Chưa kiểm.** Chưa chạy với backend thật. Các trang public (careers, talent-pool)
đã dùng `dateLocale` nhưng chỉ được kiểm qua `careers-demo`; chưa xem trực quan
ở breakpoint khác ngoài 1440×1000.

## 2026-11-19 — Cảnh báo trùng không còn ngõ cụt

**Vấn đề.** Dòng bị gắn cờ chỉ hiện “Hồ sơ trùng lặp” mà không nói trùng với ai.
Muốn biết phải cuộn xuống cuối trang và bấm “Tải cảnh báo trùng”; vào hàng đợi
“Cảnh báo trùng” cũng không tự có dữ liệu. Cảnh báo vì thế không dẫn tới hành
động nào.

**Thay đổi (chỉ UI).**

- `frontend/src/app/positions/[id]/applicants/page.tsx`
  - Ngay trên dòng bị gắn cờ (bảng desktop và card mobile) có khối
    `duplicate-counterpart-{application_id}`: “Trùng với:” + tên hồ sơ đối ứng,
    là link mở thẳng hồ sơ đó (giữ nguyên queue/sort/từ khoá hiện tại).
  - Trạng thái của khối: đang tải thì báo đang tải; lỗi thì có nút thử lại;
    chưa có cặp thì nói rõ — không còn im lặng.
  - Danh sách cảnh báo trùng **tự tải** khi vào hàng đợi `DUPLICATE` và khi
    danh sách có dòng bị gắn cờ (một request cho mỗi lượt xem); `loadDuplicates`
    chuyển thành `useCallback` để effect không lặp vô hạn khi lỗi.
  - Card “Cặp cảnh báo trùng” ở cuối trang vẫn còn làm nơi xem toàn bộ cặp.
- `frontend/src/i18n/en.json`: 5 chuỗi mới.
- `frontend/tests/fixtures/hr-screens.cjs`: thêm một cặp cảnh báo trùng
  (`app-3` ↔ `app-9`) thay cho danh sách rỗng, dùng chung cho các e2e hiện có.
- `frontend/tests/duplicate-warning.e2e.cjs` + `npm run test:e2e:duplicate-warning`;
  ghi chú trong `frontend/tests/README.md`.

**Kiểm thử đã chạy (pass).**

| Lệnh | Kết quả |
| --- | --- |
| `npm run type-check` | pass |
| `npm run lint` | pass |
| `npm run test:i18n` | 3/3 |
| `npm run test:unit` | 43/43 |
| `npm run build` | pass |
| `npm run test:e2e:duplicate-warning` | pass (Chromium, mock `/v1`) |
| `npm run test:e2e:ranking-compact` | pass (dòng đầu vẫn ở 607px) |
| `npm run test:e2e:bulk-actions` | pass |
| `npm run test:e2e:finish-application` | pass |

E2E xác nhận: dòng bị gắn cờ hiện đúng tên đối ứng mà không cần bấm gì; chỉ
một request cảnh báo trùng được gửi; link mở hồ sơ `app-9`; vào
`?queue=DUPLICATE` tự tải cảnh báo và chỉ còn 2 dòng bị gắn cờ, mỗi dòng nêu
đúng đối ứng; dòng không bị gắn cờ không có khối này; không có request `/v1`
ngoài mock.

**Chưa kiểm.** Chưa chạy với backend/DB thật (không đổi backend). Khối đối ứng
trên card mobile nằm cùng component nhưng chỉ được kiểm ở desktop; chưa xem
trực quan ở các breakpoint khác. `test:e2e:applicants-mock` vẫn fail sẵn trên
HEAD vì `reactStrictMode` (đã đối chiếu ở mục trước).

## 2026-11-19 — Chọn nhiều dòng và xử lý hàng loạt trên trang xếp hạng

**Vấn đề.** Mỗi lần shortlist hay loại, HR phải mở từng hồ sơ. Ô chọn ở đầu
dòng lại chỉ bật cho hồ sơ đã shortlist (dùng để chia sẻ), nên không thể xử lý
một lô hồ sơ mới. Trang xếp hạng vì thế không dùng được như bàn làm việc.

**Thay đổi (giữ nguyên schema và ma trận chuyển trạng thái).**

- `frontend/src/app/positions/[id]/applicants/page.tsx`
  - Mọi hồ sơ còn trong vòng sàng lọc (`NEW`, `IN_REVIEW`, `SHORTLIST`) đều
    chọn được; hồ sơ ngoài sàng lọc bị khoá và có tooltip giải thích. Chọn tất
    cả chỉ áp dụng cho các dòng đang hiển thị trong vòng sàng lọc.
  - Thanh hành động nổi (`bulk-action-bar`, cố định đáy màn hình) hiện khi có
    lựa chọn: đếm số đã chọn, `Bỏ chọn`, `Shortlist N hồ sơ`, `Loại N hồ sơ`,
    `Chia sẻ Shortlist`.
  - Mỗi hành động mở dialog xác nhận: liệt kê hồ sơ sẽ đổi, nêu số bị bỏ qua,
    và lý do chung (bắt buộc khi loại, tuỳ chọn khi shortlist).
  - Shortlist hàng loạt chỉ áp dụng cho hồ sơ `IN_REVIEW` — đúng ma trận hiện
    tại (`NEW → SHORTLIST` không hợp lệ, hồ sơ đã Shortlist không cần làm lại);
    số còn lại được báo “Bỏ qua N hồ sơ”.
  - Loại hàng loạt gửi `REJECTED_SCREENING` kèm lý do chung cho từng hồ sơ.
  - Gọi tuần tự endpoint hiện có `PATCH /applications/{id}/status` cho từng hồ
    sơ; lỗi một hồ sơ không xoá kết quả của các hồ sơ đã lưu — banner báo
    “Đã cập nhật a/b hồ sơ” kèm danh sách lỗi.
  - Chia sẻ Shortlist vẫn chỉ gửi hồ sơ `SHORTLIST` trong lựa chọn.
- `frontend/src/i18n/en.json`: 27 chuỗi mới (thanh hành động, dialog, thông báo).
- `frontend/tests/bulk-actions.e2e.cjs` + `npm run test:e2e:bulk-actions`;
  ghi chú trong `frontend/tests/README.md`.

**Kiểm thử đã chạy (pass).**

| Lệnh | Kết quả |
| --- | --- |
| `npm run type-check` | pass |
| `npm run lint` | pass |
| `npm run test:i18n` | 3/3 |
| `npm run test:unit` | 43/43 |
| `npm run build` | pass |
| `npm run test:e2e:bulk-actions` | pass (Chromium, mock `/v1`) |
| `npm run test:e2e:finish-application` | pass |
| `npm run test:e2e:ux02-review` | pass |

**Chưa kiểm.** Chưa chạy với backend/DB thật. `test:e2e:applicants-mock` đang
fail sẵn trên HEAD (dev server bật `reactStrictMode` nên effect chạy hai lần,
`pagesRequested` thành `[1,1,2,2]`); đã đối chiếu bằng cách chạy lại với file
`page.tsx` của HEAD — cùng một lỗi, không phải hồi quy của thay đổi này.

## 2026-11-19 — Hoàn tất hồ sơ trong một hành động

**Vấn đề.** Vòng duyệt một hồ sơ đang phải bấm rời rạc: xác nhận từng trích dẫn,
mở dropdown đổi trạng thái, xác nhận dialog, rồi bấm "Hồ sơ tiếp theo". Mỗi hồ sơ
tốn nhiều lần bấm và HR dễ bỏ dở giữa chừng, hàng đợi không được dọn.

**Thay đổi (chỉ UI, không đổi state machine/API).**

- `frontend/src/app/positions/[id]/applicants/[applicantId]/page.tsx`
  - Nút chính **"Đã xử lý xong hồ sơ này"** đặt trong `StickyActionBar` sẵn có
    (không thêm thanh mới, giữ nguyên layout đã đo). Chỉ hiển thị khi
    `application.can_update_status` và không ở chế độ chia sẻ (`share`).
  - Dialog hoàn tất gồm: danh sách tiêu chí còn chờ xác minh, checkbox attest
    ("Tôi đã đối chiếu … và xác nhận trích dẫn là đúng"), select trạng thái
    (mặc định giữ nguyên, lý do bắt buộc khi chọn `REJECTED*`), checkbox chuyển
    sang hồ sơ kế tiếp.
  - Trình tự gọi API giữ nguyên: `reviewCriterionResult` cho từng tiêu chí còn
    chờ → `updateStatus` nếu trạng thái đổi → điều hướng `keepContext()` sang hồ
    sơ kế tiếp với cờ `completed=1`, hoặc quay lại danh sách khi hết hàng đợi.
  - Trang đích hiện banner "Đã xử lý xong hồ sơ trước. Đang xem hồ sơ tiếp theo."
    rồi xoá `completed` khỏi URL bằng `replaceState` để refresh không lặp lại.
  - Lỗi giữa chừng: báo "một số bước có thể đã được lưu nhưng hồ sơ chưa được
    chuyển", không điều hướng và không tuyên bố hoàn tất.
- `frontend/src/i18n/en.json`: thêm bản dịch tiếng Anh cho 16 chuỗi mới.
- `frontend/tests/fixtures/hr-screens.cjs`: mock tổng quát cho `app-*` (chi tiết,
  `PATCH /status`, status-events, profile, cv-file) để trang hồ sơ kế tiếp tải được.
- `frontend/tests/finish-application.e2e.cjs` + `npm run test:e2e:finish-application`;
  ghi chú trong `frontend/tests/README.md`.

**Giữ nguyên.** Không thêm endpoint, không đổi `APPLICATION_TRANSITIONS`, quyền,
consent, matching hay luồng phê duyệt. Việc ghi `CONFIRMED` chỉ xảy ra khi HR tick
attestation — không có xác nhận tự động.

**Kiểm thử đã chạy (pass).**

| Lệnh | Kết quả |
| --- | --- |
| `npm run type-check` | pass |
| `npm run lint` | pass |
| `npm run test:i18n` | 3/3 |
| `npm run test:unit` | 43/43 |
| `npm run build` | pass |
| `npm run test:e2e:finish-application` | pass (Chromium, mock toàn bộ `/v1`) |
| `npm run test:e2e:ux02-review` | pass (không hồi quy luồng xác minh cũ) |

E2E xác nhận: nút xuất hiện một lần; nút hoàn tất bị khoá khi còn tiêu chí chưa
attest; hoàn tất gửi đúng các `POST …/review` với `CONFIRMED` và **không** gửi
PATCH trạng thái; chuyển hồ sơ giữ `queue` + `completed=1` và hiện banner; khi chọn
`REJECTED_SCREENING` vẫn bắt buộc lý do và PATCH đúng payload; không có request
`/v1` nào ngoài mock.

**Chưa kiểm.** Chưa chạy với backend/DB thật (không đổi backend). Chỉ kiểm giao
diện ở 1440×900; chưa xem lại các breakpoint khác.
