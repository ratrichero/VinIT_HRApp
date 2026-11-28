// Danh sách e2e duy nhất: file nào chạy, file nào không, và vì sao.
//
// Trước file này, 45 file `*.e2e.cjs` nằm trong repo mà 15 file không được
// script nào nhắc tới, và CI không có job e2e nào — đúng loại lỗi mà
// `test-manifest.test.cjs` đã canh cho `*.test.cjs`: test xanh trên máy người
// viết, không chạy ở đâu cả.
//
// Ba nhóm, và một file chỉ được nằm ở đúng một nhóm:
//
//  - GREEN: đã chạy xanh trên một Next server dựng từ `npm run build` + Chromium
//    của playwright-core, chỉ mock `/v1` trong browser. Đây là nhóm CI chạy.
//  - RED: đang đỏ. **Không sửa test để làm xanh** — ghi lý do thật, để nhóm xanh
//    là nhóm đã kiểm, không phải nhóm đã bị nới.
//  - NEEDS_STACK: cần backend/demo/fixture thật, không thể chạy bằng mock.
//
// Đo ngày 2026-11-27 trên Next 15.5.29 (build sạch) + Chromium 156 của
// playwright-core 1.64.1, `HRA_E2E_BASE_URL` trỏ server vừa build.

/** Chạy được chỉ với Next server + mock `/v1`; CI chạy đúng nhóm này. */
const GREEN = [
  'a11y-mock.e2e.cjs',
  'account-ui.e2e.cjs',
  'applicant-criteria-filter.e2e.cjs',
  'applicants-large-list-mock.e2e.cjs',
  'bulk-actions.e2e.cjs',
  'bulk-recovery.e2e.cjs',
  'by-criterion-confirm-all.e2e.cjs',
  'by-criterion-double-confirm.e2e.cjs',
  'capabilities.e2e.cjs',
  'criterion-queue.e2e.cjs',
  'deadline-work-queue-mock.e2e.cjs',
  'docx-preview.e2e.cjs',
  'draft-back-guard-mock.e2e.cjs',
  'duplicate-compare.e2e.cjs',
  'duplicate-warning.e2e.cjs',
  'finish-application.e2e.cjs',
  'finish-direct-advance.e2e.cjs',
  'mandatory-fail-finish.e2e.cjs',
  'measure-review-loop.e2e.cjs',
  'position-open-partial-failure.e2e.cjs',
  'prefetch-next-profile.e2e.cjs',
  'profile-lazy-panels.e2e.cjs',
  'ranking-compact-mock.e2e.cjs',
  'ranking-context-mock.e2e.cjs',
  'retention-ui.e2e.cjs',
  'review-auto-advance.e2e.cjs',
  'review-double-confirm.e2e.cjs',
  'settings-mock.e2e.cjs',
  'shortlist-filter-mock.e2e.cjs',
  'shortlist-workspace-mock.e2e.cjs',
  'sticky-bar-height.e2e.cjs',
  'sticky-review-actions.e2e.cjs',
  'ux02-review.e2e.cjs',
  'ux03-dashboard.e2e.cjs',
  'ux08-feedback.e2e.cjs',
  'verify-only.e2e.cjs',
  'vocabulary-locale.e2e.cjs',
  'workflow-create-mock.e2e.cjs',
];

/**
 * Đang đỏ. Mỗi dòng là một sự thật đã quan sát, không phải phỏng đoán: lý do ghi
 * theo lỗi thật của lần chạy. Sửa thì sửa **mã** (hoặc mock của fixture), rồi
 * chuyển file lên GREEN — đừng nới assertion cho vừa.
 *
 * 6 bài từng nằm ở đây vì mock **riêng của từng bài** (không phải fixture dùng
 * chung) thiếu route mà khung trang gọi ở mọi trang đã đăng nhập:
 * `/v1/notifications`, `/v1/dashboard/work-queue`, và với màn danh sách ứng viên
 * là `/v1/positions/p1/duplicate-signals`. Thêm route trả rỗng là đủ — không
 * assertion nào bị nới, và mỗi bài vẫn tự đỏ nếu route đó biến mất.
 */
const RED = [
  { file: 'careers-public.e2e.cjs', why: 'TimeoutError: chờ phần tử không xuất hiện' },
  { file: 'test-data-purge-mock.e2e.cjs', why: 'TimeoutError: chờ phần tử không xuất hiện' },
  { file: 'intake-ui.e2e.cjs', why: 'TimeoutError, kể cả khi đặt HRA_E2E_SYNTHETIC=1' },
  { file: 'ux-metrics.e2e.cjs', why: 'assert "leaving the profile records the leave event" sai' },
  { file: 'ux04-sticky-viewer.e2e.cjs', why: 'tiêu đề CV phải thoát thanh dính 143px, đo được 118px' },
];

/** Không chạy được bằng mock: cần backend/demo/fixture thật. */
const NEEDS_STACK = [
  { file: 'careers-demo.e2e.cjs', why: 'cần CAREERS_DEMO_E2E=1 + backend demo tổng hợp thật' },
  { file: 'synthetic-ui.e2e.cjs', why: 'cần HRA_E2E_HEALTH_URL + HRA_E2E_FIXTURE + backend APP_ENV=testing' },
];

const names = list => list.map(entry => (typeof entry === 'string' ? entry : entry.file));

module.exports = {
  GREEN: names(GREEN),
  RED,
  NEEDS_STACK,
  ALL: [...names(GREEN), ...names(RED), ...names(NEEDS_STACK)],
};
