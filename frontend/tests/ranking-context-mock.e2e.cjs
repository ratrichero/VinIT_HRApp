const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const base = process.env.HRA_E2E_BASE_URL;
if (!base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) throw Error('Use local Next server only');
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

// Ranking queue deep links, browse context, lazy CV loading and the clear-filter action.
const TOTAL = 6;
const ranking = Array.from({ length: TOTAL }, (_, index) => ({
  application_id: `app-${index}`,
  position_id: 'p1',
  candidate_name: `Ứng viên ${index + 1}`,
  rank_number: index + 1,
  matching_status: index % 2 === 0 ? 'NEEDS_HR_VERIFICATION' : 'MEETS_MANDATORY',
  matching_score: 90 - index,
  evidence_coverage: index % 2 === 0 ? 0.4 : 1,
  needs_verification: index % 2 === 0,
  has_mismatch: false,
  criterion_results: [{ criterion_id: 'c1', name: 'Python', description: 'D', rating: 4, insufficient_evidence: false, comment: null, evidence_page: 2 }],
}));
const applications = ranking.map((item, index) => ({
  application_id: item.application_id,
  position_id: 'p1',
  application_status: 'IN_REVIEW',
  file_processing_status: index === 1 ? 'NEEDS_HR_REVIEW' : 'COMPLETED',
  has_duplicate_warning: index === 2,
  // Fixed past date so the "waiting N days" line has something real to show;
  // a future timestamp is deliberately hidden by daysWaiting().
  created_at: '2026-01-01T00:00:00Z',
}));

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.HRA_E2E_CHROMIUM_EXECUTABLE, args: JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS || '[]') });
  const errors = [];
  const cvRequests = [];
  const c = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await c.addInitScript(() => { localStorage.setItem('hra_access_token', 'test'); localStorage.setItem('hra_locale', 'vi'); });
  await c.route('**/v1/**', async r => {
    const url = new URL(r.request().url());
    const p = url.pathname;
    const params = url.searchParams;
    if (p === '/v1/auth/me') return json(r, { user_id: 'hr', display_name: 'HR', system_roles: ['HR_RECRUITER'], position_assignments: [] });
    if (p === '/v1/assessments/ranking/latest/p1') return json(r, ranking);
    if (p === '/v1/applications') return json(r, applications);
    if (p === '/v1/operations/position/p1/active') return json(r, null);
    if (p === '/v1/scorecards/reminders') return json(r, []);
    if (p === '/v1/positions' && r.request().method() === 'GET') return json(r, [
      { position_id: 'p1', position_code: 'REQ-001', title: 'Backend Engineer', status: 'OPEN', criteria_status: 'APPROVED' },
      { position_id: 'p2', position_code: 'REQ-002', title: 'Data Engineer', status: 'PAUSED', criteria_status: 'DRAFT' },
      { position_id: 'p3', position_code: 'DEVOPS-7', title: 'DevOps Engineer', status: 'OPEN', criteria_status: 'APPROVED' },
    ]);
    if (p === '/v1/dashboard/summary') return json(r, { open_positions: 2, total_applications: 0, applications_by_status: { SHORTLIST: 0 }, files_needing_hr_review: 0 });
    // Badge "việc cần làm" trên header gọi work-queue ở mọi trang đã đăng nhập.
    if (p === '/v1/dashboard/work-queue') return json(r, { generated_at: '2026-11-19T03:00:00Z', summary: {}, items: [] });
    // Hai khối arena mới gọi ngay khi mở trang: chuông thông báo (hộp thư) và
    // khối "Lịch phỏng vấn" trong hồ sơ (danh sách buổi). Cả hai rỗng.
    if (p === '/v1/notifications') return json(r, { items: [], unread_count: 0 });
    if (p === '/v1/interviews') return json(r, []);
    if (p === '/v1/positions/p1') return json(r, {
      position_id: 'p1', position_code: 'REQ-1', title: 'Backend', status: 'OPEN', department_id: 'd1',
      workflow: { next_action: { code: 'REVIEW_FILES', blocked_reason_code: null, target: { pathname: '/positions/p1/applicants', search: 'queue=FILE_REVIEW' } } },
    });
    if (p.startsWith('/v1/applications/') && p.endsWith('/cv-file')) {
      cvRequests.push(p);
      return r.fulfill({ status: 200, contentType: 'application/pdf', body: '%PDF-1.4 fake' });
    }
    if (p === '/v1/applications/app-0') return json(r, {
      application_id: 'app-0', position_id: 'p1', can_view_cv: true, can_update_status: true,
      can_manage_hr_notes: false, can_view_assessment_evidence: true,
      application_status: 'IN_REVIEW', file_processing_status: 'COMPLETED',
      has_duplicate_warning: false, documents: [{ original_filename: 'cv.pdf', mime_type: 'application/pdf' }],
      identity: { display_name: 'Ứng viên 1' },
      latest_assessment: {
        matching_status: 'MEETS_MANDATORY', matching_score: 80, evidence_coverage: 0.5,
        criterion_results: [{ criterion_id: 'c1', name: 'Python', description: 'D', rating: 4, insufficient_evidence: false, comment: null, outcome: 'STRONG_MATCH' }],
      },
    });
    if (p === '/v1/applications/app-0/status-events') return json(r, []);
    if (p === '/v1/applications/app-0/profile') return json(r, {
      profile_version_id: 'pv1', version_number: 1,
      identity: { display_name: 'Ứng viên 1', email: null, phone: null }, facts: [],
    });
    // Bước "Hồ sơ tiếp theo" (mục 10) mở app-2, và trang hồ sơ tải trước dữ liệu
    // hồ sơ kế tiếp ngay sau đó. Trước đây hai request này rơi vào nhánh
    // "Unexpected", mà mục 10 lại chỉ chờ một thẻ h1 vốn đã có từ trang trước,
    // nên test chạy tiếp khi hồ sơ mới còn đang tải — lúc bắt được request lúc
    // không, và test chập chờn. Dựng dữ liệu cho mọi hồ sơ trong hàng đợi để
    // trang mở bình thường, rồi chờ đúng tên ứng viên thay vì một thẻ chung.
    const detailOf = (id) => {
      const row = ranking.find(item => item.application_id === id);
      return {
        application_id: id, position_id: 'p1', can_view_cv: true, can_update_status: true,
        can_manage_hr_notes: false, can_view_assessment_evidence: true,
        application_status: 'IN_REVIEW', file_processing_status: 'COMPLETED',
        has_duplicate_warning: false, documents: [],
        identity: { display_name: row?.candidate_name || id },
        latest_assessment: {
          matching_status: row?.matching_status || 'NEEDS_HR_VERIFICATION',
          matching_score: row?.matching_score ?? null,
          evidence_coverage: row?.evidence_coverage ?? null,
          criterion_results: (row?.criterion_results || []).map(result => ({ ...result, outcome: 'MATCH' })),
        },
      };
    };
    const detailId = p.match(/^\/v1\/applications\/(app-\d+)$/);
    if (detailId && detailId[1] !== 'app-0') return json(r, detailOf(detailId[1]));
    const nestedId = p.match(/^\/v1\/applications\/(app-\d+)\/(status-events|profile)$/);
    if (nestedId && nestedId[1] !== 'app-0') {
      return json(r, nestedId[2] === 'profile'
        ? { profile_version_id: `pv-${nestedId[1]}`, version_number: 1, identity: { display_name: detailOf(nestedId[1]).identity.display_name, email: null, phone: null }, facts: [] }
        : []);
    }
    // The profile page loads the approved rubric so a reviewer can read what each
    // criterion asked for. Not part of what this test checks, but it must not be
    // reported as an unexpected call.
    if (p === '/v1/criteria/position/p1/approved') return json(r, { criteria: [] });
    // The ranking page loads duplicate signals by itself when a row is flagged.
    if (p === '/v1/positions/p1/duplicate-signals') return json(r, []);
    errors.push(`Unexpected ${r.request().method()} ${p}${url.search}`);
    return json(r, {}, 200);
  });
  const page = await c.newPage();
  page.on('pageerror', e => { errors.push(e.message); if (process.env.HRA_DEBUG) console.log('PAGEERROR', e.message); });
  if (process.env.HRA_DEBUG) page.on('response', res => { if (res.url().includes('/v1/')) console.log('RESP', res.status(), new URL(res.url()).pathname + new URL(res.url()).search); });

  // 1. A work-queue deep link filters the list (the backend used to send a code the page ignored).
  await page.goto(base + '/positions/p1/applicants?queue=FILE_REVIEW');
  await page.getByRole('heading', { name: 'Danh sách ứng viên' }).waitFor();
  await page.getByText(/Hàng đợi: Cần kiểm tra file/).waitFor();
  assert.equal(await page.locator('table tbody tr').count(), 1, 'only the file-review application is listed');

  // 2. Lower-case links still work, and unknown codes fall back to "all" instead of lying.
  await page.goto(base + '/positions/p1/applicants?queue=file_review');
  await page.getByRole('heading', { name: 'Danh sách ứng viên' }).waitFor();
  await page.getByText(/Hàng đợi: Cần kiểm tra file/).waitFor();
  await page.goto(base + '/positions/p1/applicants?queue=nonsense');
  await page.getByRole('heading', { name: 'Danh sách ứng viên' }).waitFor();
  assert.equal(await page.locator('table tbody tr').count(), TOTAL, 'an unknown queue must not silently narrow the list');

  // 3. The count line separates "shown / total", the search term and the queue.
  await page.goto(base + '/positions/p1/applicants?queue=NEEDS_VERIFICATION&q=viên 1');
  await page.getByRole('heading', { name: 'Danh sách ứng viên' }).waitFor();
  const countLine = await page.getByTestId('applicant-count').innerText();
  assert.match(countLine, /1\/6/, `expected the shown/total split, got ${countLine}`);
  assert.match(countLine, /Đang lọc theo tên: “viên 1”/, 'the typed search must be named explicitly');
  assert.match(countLine, /Hàng đợi: Cần xác minh/, 'the active queue must be named');
  // Queue counts stay whole-position numbers, not search results.
  await page.getByRole('button', { name: /^Cần xác minh: 3 hồ sơ/ }).waitFor();

  // 4. Clearing filters resets both the queue and the search.
  await page.getByTestId('clear-applicant-filters').click();
  await page.waitForFunction(() => document.querySelectorAll('table tbody tr').length === 6);
  assert.equal(await page.evaluate(() => window.location.search), '');
  assert.equal(await page.getByTestId('clear-applicant-filters').count(), 0, 'the reset disappears when nothing is filtered');

  // 5. Profile links carry the context, so a new tab can rebuild the filtered list.
  await page.goto(base + '/positions/p1/applicants?queue=NEEDS_VERIFICATION&q=viên 1');
  await page.getByRole('heading', { name: 'Danh sách ứng viên' }).waitFor();
  const firstProfileLink = await page.locator('table tbody tr a[href*="/applicants/app-"]').first().getAttribute('href');
  assert.match(firstProfileLink, /queue=NEEDS_VERIFICATION/, `profile link lost the queue: ${firstProfileLink}`);
  assert.match(firstProfileLink, /q=vi%C3%AAn\+1/, `profile link lost the search: ${firstProfileLink}`);

  // 6. Opening a profile does not fetch the CV; the back link restores the list.
  cvRequests.length = 0;
  await page.goto(base + firstProfileLink);
  await page.waitForTimeout(2500);
  if (process.env.HRA_DEBUG) {
    console.log('DEBUG url', page.url());
    console.log('DEBUG body', (await page.evaluate(() => document.body.innerText)).replace(/\n+/g, ' | ').slice(-600));
  }
  await page.getByText('CV gốc chưa được tải. Bằng chứng AI bên trái đọc được mà không cần mở tệp.').waitFor();
  assert.equal(cvRequests.length, 0, 'the CV must not be fetched just because the profile opened');
  const backHref = await page.getByRole('link', { name: /Quay lại danh sách xếp hạng/ }).getAttribute('href');
  assert.match(backHref, /queue=NEEDS_VERIFICATION/);
  assert.match(backHref, /restore=scroll/);

  // 7. Asking for the file loads it once, and a citation jump requests it too.
  await page.getByRole('button', { name: 'Xem CV gốc' }).click();
  await page.waitForFunction(() => document.querySelectorAll('#cv-pdf-viewer').length === 1);
  assert.equal(cvRequests.length, 1, 'exactly one authorized CV request');
  await page.reload();
  await page.getByText('CV gốc chưa được tải. Bằng chứng AI bên trái đọc được mà không cần mở tệp.').waitFor();
  assert.equal(cvRequests.length, 1, 'a reload does not re-fetch the CV on its own');

  // 8. The position list is searchable by title and code, and the URL keeps it.
  await page.goto(base + '/positions');
  await page.getByRole('heading', { name: 'Danh sách vị trí tuyển dụng' }).waitFor();
  await page.getByTestId('position-count').waitFor();
  assert.match(await page.getByTestId('position-count').innerText(), /3\/3 vị trí/);
  await page.getByRole('button', { name: 'Đang mở (2)' }).waitFor();
  const search = page.getByRole('textbox', { name: 'Tìm theo tên hoặc mã vị trí' });
  await search.fill('devops');
  await page.waitForFunction(() => document.querySelectorAll('table tbody tr').length === 1);
  assert.match(await page.getByTestId('position-count').innerText(), /1\/3 vị trí/);
  await page.waitForTimeout(200);
  assert.match(new URL(page.url()).search, /q=devops/, 'the search stays in the URL so the view can be shared');
  await search.fill('REQ-002');
  await page.waitForFunction(() => document.querySelectorAll('table tbody tr').length === 1);
  assert.match(await page.locator('table tbody tr').first().innerText(), /Data Engineer/, 'a position code finds its position');
  // Status filter and search compose, and one action clears both.
  await page.getByRole('button', { name: 'Đang mở (2)' }).click();
  await page.getByRole('cell', { name: 'Không có vị trí nào khớp bộ lọc hoặc tìm kiếm.' }).waitFor();
  await page.getByRole('button', { name: 'Xoá bộ lọc và tìm kiếm' }).click();
  await page.waitForFunction(() => document.querySelectorAll('table tbody tr').length === 3);
  assert.equal(await page.evaluate(() => window.location.search), '');
  // A shared filtered link opens filtered.
  await page.goto(base + '/positions?status=OPEN&q=devops');
  await page.getByRole('heading', { name: 'Danh sách vị trí tuyển dụng' }).waitFor();
  await page.waitForFunction(() => document.querySelectorAll('table tbody tr').length === 1);
  assert.match(await page.getByTestId('position-count').innerText(), /1\/3 vị trí/);

  // --- 9. Browser Back/Forward revisits the filter, not the previous site ----
  // Changing the queue is a deliberate move between two views, so it must push a
  // history entry; typing in the search box must not (one entry per keystroke).
  await page.goto(base + '/positions/p1/applicants?queue=NEEDS_VERIFICATION&sort=REVIEW_PRIORITY');
  await page.getByTestId('applicant-count').waitFor();
  const historyStart = await page.evaluate(() => window.history.length);
  await page.getByRole('button', { name: /Đã shortlist/ }).click();
  await page.waitForTimeout(300);
  assert.match(decodeURIComponent(page.url()), /queue=SHORTLIST/, 'the queue is in the URL');
  assert.equal(await page.evaluate(() => window.history.length), historyStart + 1, 'a queue change adds one entry');
  await page.getByRole('button', { name: /Cần xác minh/ }).click();
  await page.waitForTimeout(300);
  const historyAfterTwo = await page.evaluate(() => window.history.length);
  assert.equal(historyAfterTwo, historyStart + 2, 'each deliberate move adds exactly one entry');
  const searchBox = page.getByRole('textbox', { name: /Tìm kiếm theo tên/ });
  await searchBox.fill('Hà');
  await page.waitForTimeout(400);
  assert.equal(await page.evaluate(() => window.history.length), historyAfterTwo, 'searching replaces instead of pushing');
  await page.goBack();
  await page.waitForTimeout(600);
  assert.match(decodeURIComponent(page.url()), /queue=SHORTLIST/, 'Back returns to the previous filter');
  assert.match(await page.getByTestId('applicant-count').innerText(), /Hàng đợi: Đã shortlist/);
  await page.goBack();
  await page.waitForTimeout(600);
  assert.match(decodeURIComponent(page.url()), /queue=NEEDS_VERIFICATION/, 'Back again reaches the first filter');
  assert.match(await page.getByTestId('applicant-count').innerText(), /Hàng đợi: Cần xác minh/);
  await page.goForward();
  await page.waitForTimeout(600);
  assert.match(decodeURIComponent(page.url()), /queue=SHORTLIST/, 'Forward replays the move');
  // The queue counts agree with the backend definition: a NOT_ASSESSED row is
  // "chưa matching" only, never also "cần xác minh".
  const queueLabels = await page.getByTestId('queue-chip-counts').innerText().catch(() => '');
  assert.match(queueLabels, /Cần xác minh \(3\)/, `chip counts must follow the shared definition (got ${queueLabels})`);
  assert.match(queueLabels, /Tất cả \(6\)/, 'every fixture row is in screening, so all six stay in the list');

  // --- 10. Prev/next survive a cold deep link -------------------------------
  // Regression for UX-R2: these used to exist only while sessionStorage still
  // held the list, so a link opened in a new tab silently disabled them.
  await page.evaluate(() => window.sessionStorage.clear());
  await page.goto(base + '/positions/p1/applicants/app-0?queue=NEEDS_VERIFICATION&sort=REVIEW_PRIORITY');
  await page.getByRole('heading', { level: 1 }).waitFor();
  assert.match(await page.evaluate(() => document.body.innerText), /Hồ sơ 1\/3 trong hàng đợi/, 'the counter is rebuilt from the URL');
  // app-0 is first in this queue, so "previous" is legitimately disabled; what
  // matters is that "next" is a live link rather than a dead button.
  assert.equal(await page.getByRole('link', { name: /Hồ sơ tiếp theo/ }).count(), 1, 'stepping forward works without sessionStorage');
  assert.equal(await page.getByRole('button', { name: /Hồ sơ trước/ }).isDisabled(), true, 'the first row has nowhere to go back to');
  await page.getByRole('link', { name: /Hồ sơ tiếp theo/ }).click();
  // Chờ đúng hồ sơ kế đã dựng (tên ứng viên của app-2), không chờ một thẻ h1 có
  // sẵn từ trang trước: chờ thẻ chung thì bước sau điều hướng đi trong lúc hồ sơ
  // mới còn đang tải, và request của nó tới sau khi test đã kiểm tra lỗi.
  await page.getByRole('heading', { level: 1, name: 'Ứng viên 3' }).waitFor();
  assert.match(decodeURIComponent(page.url()), /\/applicants\/app-2(\?|$)/, 'stepping opens the next profile');
  assert.match(decodeURIComponent(page.url()), /queue=NEEDS_VERIFICATION/, 'stepping keeps the queue in the URL');

  // --- 11. Age is shown, rank is untouched ---------------------------------
  await page.goto(base + '/positions/p1/applicants');
  await page.getByTestId('applicant-count').waitFor();
  const firstRow = await page.locator('table tbody tr').first().innerText();
  assert.match(firstRow, /(Chờ \d+ ngày|Nhận hôm nay)/, 'reviewers can see how long a file has been waiting');

  if (errors.length) {
    // Phân biệt lỗi mạng do điều hướng (trình duyệt huỷ request khi trang đang
    // dựng) với lỗi thật: chỉ in kèm URL để lần sau không phải đoán.
    throw Error(`${errors.join('\n')}\nURL cuối: ${page.url()}`);
  }
  await c.close();
  await browser.close();
  console.log('Ranking context: deep-link queues, shown/total counts, clear filters, context-carrying profile links, lazy CV, searchable positions, Back/Forward and cold-link prev/next: OK; all /v1 intercepted');
})().catch(e => { console.error(e); process.exit(1); });
