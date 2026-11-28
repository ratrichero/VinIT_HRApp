const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const base = process.env.HRA_E2E_BASE_URL;
if (!base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) throw Error('Use local Next server only');
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
const TOTAL = 123;
const ranking = Array.from({ length: TOTAL }, (_, index) => ({
  application_id: `app-${String(index).padStart(3, '0')}`,
  position_id: 'p1',
  candidate_name: `Ứng viên ${index + 1}`,
  rank_number: index + 1,
  matching_status: index % 4 === 0 ? 'NEEDS_HR_VERIFICATION' : 'MEETS_MANDATORY',
  matching_score: 90 - (index % 40),
  evidence_coverage: index % 5 === 0 ? 0.4 : 1,
  needs_verification: index % 4 === 0,
  has_mismatch: false,
  criterion_results: [],
}));
const applications = ranking.map((item, index) => ({
  application_id: item.application_id,
  position_id: 'p1',
  application_status: index < 20 ? 'SHORTLIST' : index < 60 ? 'IN_REVIEW' : 'NEW',
  file_processing_status: index % 7 === 0 ? 'NEEDS_HR_REVIEW' : 'COMPLETED',
  has_duplicate_warning: index % 11 === 0,
  created_at: '2031-01-01T00:00:00Z',
}));

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.HRA_E2E_CHROMIUM_EXECUTABLE, args: JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS || '[]') });
  const errors = [];
  const c = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await c.addInitScript(() => { localStorage.setItem('hra_access_token', 'test'); localStorage.setItem('hra_locale', 'vi'); });
  const pagesRequested = [];
  await c.route('**/v1/**', async r => {
    const p = new URL(r.request().url()).pathname;
    const params = new URL(r.request().url()).searchParams;
    if (p === '/v1/auth/me') return json(r, { user_id: 'hr', display_name: 'HR giả', system_roles: ['HR_RECRUITER'], position_assignments: [] });
    if (p === '/v1/assessments/ranking/latest/p1') return json(r, ranking);
    if (p === '/v1/applications') {
      const page = Number(params.get('page') || 1);
      const size = Number(params.get('page_size') || 50);
      pagesRequested.push(page);
      return json(r, applications.slice((page - 1) * size, page * size));
    }
    if (p === '/v1/operations/position/p1/active') return json(r, null);
    if (p === '/v1/scorecards/reminders') return json(r, []);
    // Chuông thông báo của AppLayout gọi ngay khi mount; hộp thư rỗng giữ nguyên bố cục.
    if (p === '/v1/notifications' && r.request().method() === 'GET') return json(r, { items: [], unread_count: 0 });
    // Màn danh sách ứng viên hỏi tín hiệu trùng khi mount; không có cặp nào trùng.
    if (p === '/v1/positions/p1/duplicate-signals') return json(r, []);
    if (p === '/v1/dashboard/work-queue') return json(r, []);
    errors.push(`Unexpected ${p}`);
    return json(r, {}, 500);
  });
  const page = await c.newPage();
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(base + '/positions/p1/applicants');
  await page.getByRole('heading', { name: 'Danh sách ứng viên' }).waitFor();
  // Paging must stop after a short page, not loop forever on a bounded set.
  assert.deepEqual(pagesRequested.sort((a, b) => a - b), [1, 2]);
  // First window shows 50 of the filtered queue and offers an explicit expansion.
  const rowsBefore = await page.locator('table tbody tr').count();
  assert.equal(rowsBefore, 50, `expected a bounded 50-row window, got ${rowsBefore}`);
  await page.getByText(/Đang hiển thị 50\/123 hồ sơ/).waitFor();
  await page.getByRole('button', { name: 'Hiện thêm 50 hồ sơ' }).click();
  assert.equal(await page.locator('table tbody tr').count(), 100);
  await page.getByRole('button', { name: 'Hiện thêm 50 hồ sơ' }).click();
  assert.equal(await page.locator('table tbody tr').count(), 123);
  assert.equal(await page.getByRole('button', { name: 'Hiện thêm 50 hồ sơ' }).count(), 0);
  // Rank order was never rewritten by the windowing.
  assert.match(await page.locator('table tbody tr').first().innerText(), /1/);
  // Keyboard reachability of the main controls. R6-a moved "Làm mới" into the
  // actions menu, so the primary button and that menu trigger are what must be
  // reachable from the keyboard — and the menu item must actually be operable.
  await page.getByRole('button', { name: 'Chạy đánh giá & xếp hạng' }).focus();
  await page.keyboard.press('Tab');
  assert.equal(
    await page.evaluate(() => document.activeElement?.getAttribute('aria-label') || ''),
    'Hành động khác: Làm mới, Chia sẻ Shortlist',
    'the menu trigger names what is inside it',
  );
  await page.getByRole('button', { name: /Hành động khác/ }).press('Enter');
  assert.equal(await page.getByRole('menuitem', { name: 'Làm mới' }).isVisible(), true, 'the refresh action is still reachable, one level down');
  await page.keyboard.press('Escape');
  // Switching the queue filter resets the window to 50 again.
  await page.getByRole('button', { name: /Cần xác minh/ }).click();
  await page.waitForFunction(() => document.querySelectorAll('table tbody tr').length <= 50);
  if (errors.length) throw Error(errors.join('\n'));
  await c.close();
  await browser.close();
  console.log('Large applicant list: paged loading, bounded 50-row window, explicit expansion and filters: OK; all /v1 intercepted');
})().catch(e => { console.error(e); process.exit(1); });
