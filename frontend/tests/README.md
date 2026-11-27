# Kiểm thử giao diện

## Chạy cả bộ e2e

45 bài `*.e2e.cjs` được khai trong [`e2e-manifest.cjs`](e2e-manifest.cjs) theo ba nhóm — **xanh** (chạy được chỉ với Next server + mock `/v1`), **đỏ** (đang hỏng, ghi lý do) và **cần stack thật**. `run-e2e.cjs` chạy từng bài trong một tiến trình riêng và in `PASS`/`FAIL` từng file:

```bash
cd frontend
npm run build && npx next start -p 3000 &
HRA_E2E_BASE_URL=http://127.0.0.1:3000 npm run test:e2e            # cả bộ, báo cả bài đỏ
HRA_E2E_BASE_URL=http://127.0.0.1:3000 npm run test:e2e:green      # đúng nhóm CI chạy
HRA_E2E_BASE_URL=http://127.0.0.1:3000 npm run test:e2e -- --only sticky --timeout 60
```

Muốn một bài từ nhóm đỏ sang nhóm xanh thì sửa mã (hoặc mock của fixture) rồi chuyển dòng của nó trong manifest; đừng nới assertion. `test-manifest.test.cjs` canh việc này: file e2e có trên đĩa mà không có trong manifest, hoặc nhóm xanh không được CI gọi, đều làm test đỏ.

`npm run test:i18n` chạy unit test không cần browser: dictionary, interpolation, chuyển ngôn ngữ của thông báo đang hiển thị và kiểm tra key UI có bản dịch Anh.

`npm run test:e2e:accounts` kiểm tra bootstrap, quản trị tài khoản, đổi mật khẩu tạm, HR chọn HM, phân quyền và mobile bằng Chromium. Script intercept **toàn bộ** `/v1` và dùng response giả, không gọi Auth/backend thật; vẫn chỉ chạy với Next server cục bộ dùng một lần. Ví dụ sau khi chạy Next cục bộ trên port 3000 và cài Chromium:

```bash
HRA_E2E_BASE_URL=http://127.0.0.1:3000 npm run test:e2e:accounts
```

Có thể chỉ định `HRA_E2E_CHROMIUM_EXECUTABLE` và `HRA_E2E_CHROMIUM_ARGS`; test UI mock này không thay thế test tích hợp PostgreSQL hoặc Supabase Auth thật.

`npm run test:e2e:synthetic` là smoke test Playwright cho login/ngôn ngữ, lỗi đăng nhập, JD dialog, chỉnh profile, ghi chú HR, Admin AI, quyền HM, lỗi backend, tải lại/hydration và mobile. **Test có ghi dữ liệu**: tạo profile version, thêm ghi chú và kích hoạt cấu hình AI. Chỉ chạy trên hệ thống cục bộ **dùng một lần, hoàn toàn tổng hợp**, không kết nối DB/Storage/project thật và không dùng CV thật. Kiểm tra loopback và `APP_ENV=testing` chỉ giảm rủi ro; chúng **không chứng minh** database phía sau là dùng một lần. Người chạy phải tự xác minh trước.

Cần tạo sẵn backend `APP_ENV=testing` (worker tắt) và frontend proxy `/v1` tới backend đó, DB cục bộ đã có đủ migrations và dữ liệu giả. Tạo file fixture JSON riêng, không commit, gồm `hr_token`, `hm_token`, `position`, `app_b`, `app_c`; token là JWT ngắn hạn chỉ dùng cho môi trường giả. Dữ liệu test gồm vị trí `Software Engineer (dữ liệu giả)` với đơn vị `Đơn vị minh họa`, ứng viên `Ứng viên giả Bình` được chia sẻ cho HM chỉ ở chế độ summary, và `Ứng viên giả Chi` có tài liệu CV giả cho HR sửa. HR demo đồng thời có ADMIN; allowlist chứa `synthetic-local-model`, `synthetic-alternative-model` và endpoint local. Test không gọi model/worker thật.

Cài Chromium tương thích với `playwright-core` và thư viện OS cần thiết, sau đó ví dụ:

```bash
cd frontend
npm ci
# Chỉ tải Chromium vào môi trường kiểm thử khi phù hợp chính sách của bạn:
npx playwright-core install chromium
HRA_E2E_SYNTHETIC=1 \
HRA_E2E_BASE_URL=http://127.0.0.1:3000 \
HRA_E2E_HEALTH_URL=http://127.0.0.1:8001/health \
HRA_E2E_FIXTURE=/đường/dẫn/fixture-tổng-hợp.json \
  npm run test:e2e:synthetic
```

Có thể chỉ định `HRA_E2E_CHROMIUM_EXECUTABLE` cho binary có sẵn và `HRA_E2E_CHROMIUM_ARGS` là JSON array khi môi trường CI cô lập cần flags riêng. Không lưu fixture/token hay binary browser vào Git. Test này không chứng minh Supabase Auth/Storage, OCR, model thật hay tính an toàn production.

`npm run test:e2e:intake-mock` chạy Playwright trên server Next cục bộ **với mọi request `/v1` được intercept bằng response giả**, không gọi API, Gmail hay database thật. Nó kiểm tra form rút bị vô hiệu hóa khi JavaScript chưa tải, mất phản hồi Careers và retry giữ cùng request/token, withdrawal, Gmail REVIEW → retry → xác nhận thông tin giả, Talent Pool scan. Các file và tài khoản trong test đều giả; không thay thế kiểm thử hạ tầng thật. Cần Chromium tương thích và thư viện hệ thống, sau đó:

```bash
HRA_E2E_SYNTHETIC=1 HRA_E2E_BASE_URL=http://127.0.0.1:3000 \
  npm run test:e2e:intake-mock
```

Có thể đặt `HRA_E2E_CHROMIUM_EXECUTABLE` và `HRA_E2E_CHROMIUM_ARGS` như test khác. Chỉ dùng server cục bộ dùng một lần. Test chủ động fail nếu gặp `/v1` ngoài mock; không truy cập thư thật hay đưa token thật vào fixture.

## Mock UI checks for the HR/HM UX slice

These tests drive a **disposable local** Next server and intercept every `/v1`
call in the browser; they prove UI behaviour only (no backend, Supabase,
Storage, ClamAV or VPS involvement).

- `workflow-create-mock.e2e.cjs` — create-position page, required JD, mocked
  DOCX/TXT and link import, optional idempotent retry after a 503 (same
  `request_id`, unedited payload, form locked while reconciling).
- `applicants-large-list-mock.e2e.cjs` — 123 applicant queue: paged loading
  stops at a short page, only 50 rows mount first, "show 50 more" expands to
  123 without changing rank order, and changing the queue resets the window.
- `shortlist-workspace-mock.e2e.cjs` — `/shortlist/[id]` workspace on desktop
  and mobile: per-candidate drafts survive switching, legacy `?share=` deep
  link, share-scoped CV/evidence gate, and data removal when the API answers
  403 after the tab becomes visible again.
- `shortlist-filter-mock.e2e.cjs` — share inbox filtering by position.
- `account-ui.e2e.cjs` — bootstrap/login, mandatory password change, account
  admin, HM selection in the create form (asserts the retry-safe
  `request_id`) and mobile layout.

Run with `HRA_E2E_BASE_URL` pointing at the local server and a Chromium
executable (see the commands in `doc/PLAN_CAI_TIEN_WORKFLOW_UX_HR_HM.md`).

- `docx-preview.e2e.cjs` — a DOCX CV served as real bytes is read in the page:
  nothing fetched on open, text readable after asking, no PDF iframe, page
  controls disabled, and the "original layout may differ" note kept.
- `verify-only.e2e.cjs` — the finish action for a reviewer who may verify
  evidence but not change status: the action is available, the status picker is
  hidden with an explanation, verification is recorded with the attestation, no
  status PATCH is sent, and the completion flag still carries over.
- `vocabulary-locale.e2e.cjs` — one work vocabulary for both queue screens:
  the dashboard and the ranking chips use the same three clusters (Cần tôi xử
  lý / Cần tôi quyết / Đã quyết) and the same wording per task, no screen shows
  the word "matching", and dates follow the selected language (vi day-first,
  en month-first).
- `duplicate-warning.e2e.cjs` — duplicate warnings are actionable where they
  appear: the flagged row names its counterpart and links to that profile, the
  signal list loads automatically (no bottom-of-page button), and the duplicate
  queue shows exactly the flagged rows with their counterparts.
- `bulk-actions.e2e.cjs` — the ranking list's multi-select and floating
  action bar: every screening row (including NEW and not-yet-shortlisted ones)
  is selectable, bulk shortlist only touches In review rows and reports the
  skipped ones, bulk rejection stays blocked without one shared reason, and the
  batch uses the existing per-application status endpoint only.
- `finish-application.e2e.cjs` — the profile's `Đã xử lý xong hồ sơ này`
  action: citation verification cannot be recorded without the reviewer's
  attestation, finishing records the flagged citations, advances to the next
  profile with the queue context and a one-time banner, leaves the recruiting
  status untouched unless one is chosen, and still requires a reason for a
  rejection.
- `a11y-mock.e2e.cjs` — accessible-name audit of every visible, focusable
  control on the create page and the share workspace (desktop and mobile),
  keyboard-only reach of the required title field, `aria-pressed` candidate
  selection, evidence accordion opened with Enter, and no horizontal overflow.
  It is a smoke check, **not** a screen-reader or contrast audit.
