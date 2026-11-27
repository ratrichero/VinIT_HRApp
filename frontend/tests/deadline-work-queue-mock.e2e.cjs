const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');

const base = process.env.HRA_E2E_BASE_URL;
if (!base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) {
  throw Error('Use a local disposable Next.js server.');
}
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

// Dashboard work queue: deadline items (R5-B1), waiting age (R5-B2) and the
// "open positions" card that no longer counts positions closed for intake.
const DAY = 24 * 60 * 60 * 1000;
const iso = ms => new Date(Date.now() + ms).toISOString();

const queue = {
  generated_at: iso(0),
  summary: {
    positions_needing_attention: 4,
    files_needing_review: 2,
    applications_needing_verification: 3,
    duplicate_alerts: 0,
    criteria_pending_action: 0,
    shares_without_feedback: 0,
    positions_deadline_passed: 1,
    positions_deadline_soon: 1,
    applications_waiting_over_threshold: 3,
    oldest_waiting_days: 12,
    median_waiting_days: 4,
  },
  items: [
    { item_id: 'd1', type: 'POSITION_DEADLINE_PASSED', priority: 'HIGH', position_id: 'p1', position_code: 'REQ-001', position_title: 'Backend Engineer', position_status: 'OPEN', count: 1, target: { pathname: '/positions/p1', search: 'tab=overview' }, due_at: iso(-2 * DAY), days_left: -2 },
    { item_id: 'd2', type: 'POSITION_DEADLINE_SOON', priority: 'MEDIUM', position_id: 'p3', position_code: 'DEVOPS-7', position_title: 'DevOps Engineer', position_status: 'OPEN', count: 1, target: { pathname: '/positions/p3', search: 'tab=overview' }, due_at: iso(3 * DAY), days_left: 3 },
    { item_id: 'x1', type: 'NEEDS_VERIFICATION', priority: 'HIGH', position_id: 'p1', position_code: 'REQ-001', position_title: 'Backend Engineer', position_status: 'OPEN', count: 3, target: { pathname: '/positions/p1/applicants', search: 'queue=NEEDS_VERIFICATION' } },
    // A backend deployed ahead of this build: unknown type must not print "undefined".
    { item_id: 'u1', type: 'SOMETHING_FROM_THE_FUTURE', priority: 'LOW', position_id: 'p2', position_code: 'REQ-002', position_title: 'Data Engineer', position_status: 'OPEN', count: 1, target: { pathname: '/positions/p2' } },
  ],
};

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.HRA_E2E_CHROMIUM_EXECUTABLE,
    args: JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS || '[]'),
  });
  const c = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await c.addInitScript(() => { localStorage.setItem('hra_access_token', 'test'); localStorage.setItem('hra_locale', 'vi'); });
  await c.route('**/v1/**', async r => {
    const p = new URL(r.request().url()).pathname;
    if (p === '/v1/auth/me') return json(r, { user_id: 'hr', display_name: 'HR', system_roles: ['HR_RECRUITER'], position_assignments: [] });
    if (p === '/v1/dashboard/summary') return json(r, { open_positions: 1, open_positions_deadline_passed: 2, total_applications: 9, applications_by_status: { SHORTLIST: 2 }, files_needing_hr_review: 2 });
    if (p === '/v1/dashboard/work-queue') return json(r, queue);
    if (p === '/v1/scorecards/reminders') return json(r, []);
    if (p === '/v1/positions') return json(r, []);
    // Chuông thông báo trong AppLayout hỏi hộp thư ngay khi mount; hộp thư rỗng.
    // Thiếu route này thì fallback bên dưới trả 500 và test đỏ ở lỗi console.
    if (p === '/v1/notifications') return json(r, { items: [], unread_count: 0 });
    return json(r, { detail: `Unexpected ${p}` }, 500);
  });
  const page = await c.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(`${base}/dashboard`, { waitUntil: 'networkidle' });
  await page.locator('#work-queue').waitFor();

  const text = await page.locator('#work-queue').innerText();
  assert.match(text, /Vị trí đã quá hạn ứng tuyển/, 'deadline items get their own label');
  assert.match(text, /Vị trí sắp hết hạn ứng tuyển/);
  assert.match(text, /Đã quá hạn 2 ngày/, 'an overdue position says how overdue');
  assert.match(text, /Còn 3 ngày tới hạn/);
  assert.match(text, /1 vị trí đã quá hạn ứng tuyển · 1 vị trí sắp hết hạn/, 'summary line counts both kinds');
  assert.match(text, /3 hồ sơ chờ quá 7 ngày · lâu nhất 12 ngày/, 'waiting age is stated, not implied');
  assert.match(text, /Việc cần xử lý/, 'an unknown item type falls back to neutral wording');
  assert.doesNotMatch(text, /undefined/, 'nothing renders as undefined');

  // The KPI still shows one number, but explains the positions it hides.
  const firstScreen = await page.locator('main').first().innerText();
  assert.match(firstScreen, /2 vị trí đã quá hạn, không nhận hồ sơ/, 'the open-positions card explains the difference');

  // Deep links keep the whole queue: the deadline item is not a dead end.
  await page.locator('#work-queue').getByRole('link', { name: /Xem vị trí/ }).first().click();
  await page.waitForURL(/\/positions\/p1/, 'a deadline item links to its position');
  assert.match(decodeURIComponent(page.url()), /tab=overview/);

  if (errors.length) throw Error(errors.join('\n'));
  await c.close();
  await browser.close();
  console.log('Deadline work queue: passed/soon labels, days-left wording, waiting-age summary, open-positions card note and unknown-type fallback: OK; all /v1 intercepted');
})().catch(e => { console.error(e); process.exit(1); });
