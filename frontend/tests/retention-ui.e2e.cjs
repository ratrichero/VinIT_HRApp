/**
 * The "Data & retention" screen.
 *
 * The backend has had the retention queue for a while (list, generate, confirm,
 * cancel) but HR had no screen, so the only way to work the queue was the API.
 * This test drives the screen against a mock that mirrors the real contract:
 *  1. It lists the cases of a closed position with the states HR acts on, and only
 *     offers "Confirm" on a case the server would actually accept (due, pending,
 *     no execution in flight).
 *  2. Generating cases says what happened and reloads the list.
 *  3. Confirming and cancelling post to the case endpoints and update that row.
 *  4. Timeline opens the application's decision history, and a case whose
 *     application is already deleted says so instead of offering an empty timeline.
 *  5. A position the user cannot see answers 403 and the screen explains it
 *     instead of showing an empty table.
 */
const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const { me } = require('./fixtures/hr-screens.cjs');

const base = process.env.HRA_E2E_BASE_URL;
if (!base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) {
  throw Error('Use local Next server only');
}

const POSITIONS = [
  { position_id: 'p1', position_code: 'REQ-2026-014', title: 'Senior Backend Engineer', status: 'CLOSED', department_name: 'Nền tảng' },
  { position_id: 'p2', position_code: 'REQ-2026-021', title: 'Data Engineer', status: 'OPEN', department_name: 'Dữ liệu' },
];

const baseCase = {
  position_id: 'p1',
  policy_version: 'rp-3',
  position_closed_at: '2025-11-01T00:00:00Z',
  created_at: '2026-11-01T00:00:00Z',
  confirmed_by: null,
  confirmed_at: null,
};

function installRetentionApi(context) {
  const calls = [];
  const unexpected = [];
  let cases = [
    { ...baseCase, retention_case_id: 'case-1', application_id: 'app-1', application_opaque_id: 'aaaa1111bbbb2222', due_date: '2026-11-01T00:00:00Z', status: 'PENDING', execution_status: null, execution_in_progress_or_recovery: false, is_due: true },
    { ...baseCase, retention_case_id: 'case-2', application_id: 'app-2', application_opaque_id: 'cccc3333dddd4444', due_date: '2027-05-01T00:00:00Z', status: 'PENDING', execution_status: null, execution_in_progress_or_recovery: false, is_due: false },
    { ...baseCase, retention_case_id: 'case-3', application_id: null, application_opaque_id: 'eeee5555ffff6666', due_date: '2026-10-01T00:00:00Z', status: 'DELETED', execution_status: 'COMPLETED', execution_in_progress_or_recovery: false, is_due: false },
  ];
  let listCalls = 0;
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  const route = async r => {
    const request = r.request();
    const url = new URL(request.url());
    const p = url.pathname;
    if (p === '/v1/auth/me') return json(r, me);
    if (p === '/v1/positions' && request.method() === 'GET') return json(r, POSITIONS);
    if (p === '/v1/retention/positions/p1/cases' && request.method() === 'GET') {
      listCalls += 1;
      return json(r, cases);
    }
    if (p === '/v1/retention/positions/p2/cases' && request.method() === 'GET') {
      return json(r, { detail: 'Bạn không có quyền xem retention của vị trí này' }, 403);
    }
    if (p === '/v1/retention/positions/p1/cases/generate' && request.method() === 'POST') {
      calls.push({ method: 'POST', path: p });
      cases = [
        ...cases,
        { ...baseCase, retention_case_id: 'case-4', application_id: 'app-4', application_opaque_id: '9999aaaabbbbcccc', due_date: '2026-11-01T00:00:00Z', status: 'PENDING', execution_status: null, execution_in_progress_or_recovery: false, is_due: true },
      ];
      return json(r, { position_id: 'p1', policy_version: 'rp-3', retention_months: 12, due_date: '2026-11-01T00:00:00Z', created_count: 1, cases: [] });
    }
    const action = p.match(/^\/v1\/retention\/cases\/([^/]+)\/(confirm|cancel)$/);
    if (action && request.method() === 'POST') {
      const [, caseId, kind] = action;
      calls.push({ method: 'POST', path: p, caseId, kind });
      const current = cases.find(item => item.retention_case_id === caseId);
      const updated = kind === 'confirm'
        ? { ...current, status: 'SCHEDULED_FOR_DELETION', confirmed_at: '2026-11-19T09:00:00Z' }
        : { ...current, status: 'CANCELLED' };
      cases = cases.map(item => (item.retention_case_id === caseId ? updated : item));
      return json(r, updated);
    }
    // Hai route của khung trang: chuông thông báo và thẻ hàng đợi việc trong
    // AppLayout. Trang này không kiểm chúng, nên trả rỗng — trước đây chúng bị
    // tính là "endpoint lạ" và làm đỏ một bài không liên quan.
    if (p === '/v1/notifications' && request.method() === 'GET') return json(r, { items: [], unread_count: 0 });
    if (p === '/v1/dashboard/work-queue' && request.method() === 'GET') return json(r, []);
    if (p === '/v1/applications/app-1/status-events' && request.method() === 'GET') {
      return json(r, [
        { event_id: 'e2', previous_status: 'SHORTLIST', new_status: 'REJECTED_SCREENING', reason: 'Không đáp ứng yêu cầu bắt buộc', note: null, changed_at: '2026-10-20T08:00:00Z', changed_by_name: 'Nguyễn Thu Hằng' },
        { event_id: 'e1', previous_status: 'IN_REVIEW', new_status: 'SHORTLIST', reason: null, note: 'Đã đối chiếu bằng chứng', changed_at: '2026-10-18T08:00:00Z', changed_by_name: 'Nguyễn Thu Hằng' },
      ]);
    }
    unexpected.push(`${request.method()} ${p}${url.search}`);
    return json(r, {});
  };
  return context.route('**/v1/**', route).then(() => ({ calls, unexpected, listCalls: () => listCalls }));
}

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.HRA_E2E_CHROMIUM_EXECUTABLE,
    args: JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS || '[]'),
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.addInitScript(() => {
    localStorage.setItem('hra_access_token', 'retention');
    localStorage.setItem('hra_locale', 'vi');
  });
  const { calls, unexpected, listCalls } = await installRetentionApi(context);
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error)));

  await page.goto(`${base}/data-retention`, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'Dữ liệu & lưu trữ' }).waitFor();
  await page.getByTestId('retention-case-case-1').waitFor();

  // --- 1. The queue as HR acts on it ---------------------------------------
  assert.match(await page.getByTestId('retention-summary').innerText(), /Tổng 3 trường hợp · 1 đến hạn · 2 chờ xác nhận · 0 đã lên lịch xoá · 0 đã huỷ/);
  assert.match(await page.getByTestId('retention-status-case-1').innerText(), /Chờ xác nhận/);
  assert.match(await page.getByTestId('retention-status-case-3').innerText(), /Đã xoá dữ liệu/);
  assert.equal(await page.getByTestId('retention-confirm-case-1').isEnabled(), true, 'a due pending case can be confirmed');
  assert.equal(await page.getByTestId('retention-confirm-case-2').isDisabled(), true, 'the server rejects confirming before the due date');
  assert.equal(await page.getByTestId('retention-cancel-case-2').isEnabled(), true, 'a pending case can be cancelled');
  assert.equal(await page.getByTestId('retention-timeline-case-3').isDisabled(), true, 'a deleted application has no timeline');

  // --- 2. Generating cases says what happened and reloads ------------------
  await page.getByTestId('retention-generate-open').click();
  await page.getByTestId('retention-generate-dialog').waitFor();
  const beforeGenerate = listCalls();
  await page.getByTestId('retention-generate-confirm').click();
  await page.getByTestId('retention-notice').waitFor();
  assert.match(await page.getByTestId('retention-notice').innerText(), /Đã tạo 1 trường hợp lưu trữ/);
  assert.equal(calls.filter(call => call.path.endsWith('/cases/generate')).length, 1);
  await page.getByTestId('retention-case-case-4').waitFor({ timeout: 10000 });
  assert.ok(listCalls() > beforeGenerate, 'the list is reloaded after generating');

  // --- 3. Confirm one case, cancel another ---------------------------------
  await page.getByTestId('retention-confirm-case-1').click();
  await page.getByTestId('retention-action-dialog').waitFor();
  assert.match(await page.getByTestId('retention-action-dialog').innerText(), /vào hàng đợi xoá/);
  await page.getByTestId('retention-action-confirm').click();
  await page.getByTestId('retention-action-dialog').waitFor({ state: 'detached', timeout: 10000 });
  await page.waitForFunction(() => (document.querySelector('[data-testid="retention-status-case-1"]')?.textContent || '').includes('Đã lên lịch xoá'));
  assert.match(await page.getByTestId('retention-notice').innerText(), /Đã xác nhận trường hợp/);

  await page.getByTestId('retention-cancel-case-2').click();
  await page.getByTestId('retention-action-dialog').waitFor();
  await page.getByTestId('retention-action-confirm').click();
  await page.getByTestId('retention-action-dialog').waitFor({ state: 'detached', timeout: 10000 });
  await page.waitForFunction(() => (document.querySelector('[data-testid="retention-status-case-2"]')?.textContent || '').includes('Đã huỷ'));
  assert.deepEqual(calls.map(call => call.kind || null), [null, 'confirm', 'cancel']);

  // --- 4. Timeline per application -----------------------------------------
  await page.getByTestId('retention-timeline-case-1').click();
  const timeline = page.getByTestId('retention-timeline-list-case-1');
  await timeline.waitFor();
  assert.match(await timeline.innerText(), /Đang xem → Shortlist/, 'the decision history is shown in the application’s language');
  assert.match(await timeline.innerText(), /Nguyễn Thu Hằng/);
  assert.match(await timeline.innerText(), /Lý do: Không đáp ứng yêu cầu bắt buộc/);
  await page.getByTestId('retention-timeline-case-1').click();
  await timeline.waitFor({ state: 'detached' });

  // --- 5. A position without retention permission says so ------------------
  await page.getByRole('combobox', { name: 'Vị trí' }).click();
  await page.getByRole('option', { name: /Data Engineer/ }).click();
  await page.getByRole('alert').filter({ hasText: 'Bạn không có quyền xem dữ liệu lưu trữ của vị trí này' }).waitFor();

  assert.deepEqual(pageErrors, [], `no client-side exceptions: ${pageErrors.join(' | ')}`);
  assert.deepEqual(unexpected, [], `all API calls are accounted for: ${unexpected.join(', ')}`);
  console.log('Data & retention: cases listed with server-accurate actions, generation reported and reloaded, confirm/cancel post per case and update the row, per-application decision timeline opens, a deleted application has no timeline, and a position without permission explains the 403: OK');
  await browser.close();
})().catch(err => { console.error(err); process.exit(1); });
