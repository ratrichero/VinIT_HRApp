// Local browser UI test: all /v1 requests mocked, never a real backend or CV.
const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const base = process.env.HRA_E2E_BASE_URL;
if (process.env.HRA_E2E_SYNTHETIC !== '1' || !base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) throw Error('Set HRA_E2E_SYNTHETIC=1 and HRA_E2E_BASE_URL to a disposable local Next.js server.');
const json = (r, b, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) });
const position = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const other = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const receipt = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const application = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
const stamp = '2026-01-01T12:00:00+00:00';
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.HRA_E2E_CHROMIUM_EXECUTABLE, args: JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS || '[]'), headless: true });
  const errors = [], state = { submissions: [], withdrawal: null, retry: 0, identityPuts: [], scanned: 0, mail: { receipt_id: receipt, message_id: 'synthetic-message', status: 'REVIEW', reason: 'ANTIVIRUS_UNAVAILABLE', application_id: null, updated_at: stamp } };
  const noJs = await browser.newContext({ javaScriptEnabled: false });
  const noJsPage = await noJs.newPage();
  await noJsPage.goto(base + '/pool-withdraw', { waitUntil: 'domcontentloaded' });
  assert.equal(await noJsPage.getByLabel('Mã rút lựa chọn').isDisabled(), true);
  assert.equal(await noJsPage.getByRole('button', { name: 'Gửi yêu cầu rút' }).isDisabled(), true);
  await noJs.close();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript(() => localStorage.setItem('hra_access_token', 'fake-hr-test-token'));
  await context.route('**/v1/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname, method = req.method();
    if (path === '/v1/auth/me') return json(route, { user_id: 'synthetic-user', email: 'hr@example.test', display_name: 'HR giả', must_change_password: false, system_roles: ['HR_LEAD'], position_assignments: [] });
    if (path === '/v1/careers/jobs' && method === 'GET') return json(route, { items: [{ position_id: position, position_code: 'TEST-01', title: 'Vị trí giả', org_unit: null, work_location: null, work_mode: null, employment_type: null, application_deadline_at: '2099-01-01T00:00:00Z', description: null, can_apply_test: true }], next_cursor: null });
    if (path === `/v1/careers/jobs/${position}/apply` && method === 'POST') { state.submissions.push(req.postData()); if (state.submissions.length === 1) return route.abort('failed'); return json(route, { message: 'Đã nhận' }, 202); }
    if (path === '/v1/talent-pool/withdraw' && method === 'POST') { state.withdrawal = req.postDataJSON(); return json(route, { message: 'Nếu mã hợp lệ' }); }
    if (path === '/v1/gmail-test/review' && method === 'GET') return json(route, { items: [state.mail], spam_mode: 'GMAIL_LABELS_ONLY_TEST' });
    if (path === `/v1/gmail-test/review/${receipt}/retry` && method === 'POST') { state.retry++; state.mail = { ...state.mail, status: 'ACCEPTED', reason: null, application_id: application }; return json(route, { status: 'ACCEPTED', reason: null }); }
    if (path === `/v1/gmail-test/review/${receipt}/identity` && method === 'GET') return json(route, { receipt_id: receipt, application_id: application, position_id: position, display_name: 'Gmail thử nghiệm', email: 'gmail-test@example.test', updated_at: stamp });
    if (path === `/v1/gmail-test/review/${receipt}/identity` && method === 'PUT') { state.identityPuts.push(req.postDataJSON()); return json(route, { message: 'Đã lưu', updated_at: stamp }); }
    if (path === '/v1/positions' && method === 'GET') return json(route, [{ position_id: position, title: 'Vị trí giả', position_code: 'TEST-01' }, { position_id: other, title: 'Vị trí đích giả', position_code: 'TEST-02' }]);
    if (path === '/v1/talent-pool/scan' && method === 'GET') { state.scanned++; return json(route, { items: [], next_cursor: null }); }
    errors.push(`Unexpected API: ${method} ${path}`); return json(route, { detail: 'Unmocked synthetic API' }, 500);
  });
  const page = await context.newPage(); page.on('pageerror', e => errors.push(e.stack || e.message));
  const visible = text => page.getByText(text, { exact: false }).filter({ visible: true }).first().waitFor({ timeout: 20000 });
  try {
    await page.goto(base + '/careers', { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: 'Xem chi tiết' }).first().click();
    await page.getByLabel('Tên ứng viên').fill('Người giả');
    await page.getByLabel('Email').fill('person@example.test');
    await page.locator('input[type=file]').setInputFiles({ name: 'fake.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-synthetic-only') });
    await page.getByRole('checkbox').check();
    const token = (await page.locator('code').first().innerText()).trim(); assert.match(token, /^[0-9a-f]{64}$/);
    await page.getByRole('button', { name: 'Gửi hồ sơ' }).click();
    await visible('Không biết hồ sơ đã được nhận hay chưa');
    assert.equal((await page.locator('code').first().innerText()).trim(), token);
    await page.getByRole('button', { name: 'Gửi hồ sơ' }).click();
    await visible('Đã tiếp nhận hồ sơ');
    const field = (body, name) => body.match(new RegExp(`name="${name}"\\r\\n\\r\\n([^\\r]+)`))?.[1];
    assert.equal(state.submissions.length, 2);
    for (const name of ['request_id', 'pool_token', 'pool_opt_in', 'name', 'email']) { assert.ok(field(state.submissions[0], name), `missing ${name}`); assert.equal(field(state.submissions[0], name), field(state.submissions[1], name), `retry changed ${name}`); }
    assert.equal(field(state.submissions[0], 'pool_token'), token);
    await page.goto(base + '/pool-withdraw', { waitUntil: 'networkidle' });
    await page.getByLabel('Mã rút lựa chọn').fill(token); await page.getByRole('button', { name: 'Gửi yêu cầu rút' }).click(); await visible('phản hồi không xác nhận mã có tồn tại'); assert.equal(state.withdrawal.token, token);
    console.log('Careers uncertain outcome, same request/token retry, withdrawal: OK');
    await page.goto(base + '/gmail-test', { waitUntil: 'networkidle' }); await visible('Máy quét mã độc không sẵn sàng'); await visible('không có SpamAssassin');
    await page.getByRole('button', { name: 'Thử lại', exact: true }).click(); await visible('Kết quả thử lại: Đã tiếp nhận hồ sơ'); assert.equal(state.retry, 1);
    await page.getByRole('button', { name: 'Xác nhận thông tin giả' }).click(); await page.getByLabel('Tên giả').fill('Ứng viên giả'); await page.getByLabel('Email giả @example.test').fill('test@example.test');
    assert.equal(await page.getByRole('button', { name: 'Lưu thông tin giả' }).isDisabled(), true);
    await page.getByRole('checkbox', { name: 'Tôi xác nhận đây chỉ là thông tin giả.' }).check(); await page.getByRole('button', { name: 'Lưu thông tin giả' }).click(); await visible('Đã lưu thông tin giả do HR xác nhận');
    assert.deepEqual(state.identityPuts, [{ display_name: 'Ứng viên giả', email: 'test@example.test', expected_updated_at: stamp, confirm_synthetic: true }]);
    console.log('Gmail review retry and synthetic identity confirmation: OK');
    await page.goto(base + '/talent-pool', { waitUntil: 'networkidle' }); await visible('Danh sách chỉ phản ánh điều kiện tại thời điểm tìm');
    await page.getByRole('combobox', { name: 'Vị trí nguồn' }).click(); await page.getByRole('option', { name: 'TEST-01 · Vị trí giả', exact: true }).click();
    await page.getByRole('combobox', { name: 'Vị trí đích có rubric duyệt' }).click(); await page.getByRole('option', { name: 'TEST-02 · Vị trí đích giả', exact: true }).click();
    await page.getByRole('button', { name: 'Tìm hồ sơ đủ điều kiện' }).click(); await visible('không có kết quả đủ điều kiện tại thời điểm tìm'); assert.equal(state.scanned, 1);
    console.log('Talent Pool snapshot and empty result: OK');
    // --- The careers error is translated, not just wrapped in t() ------------
    // Same aborted submit, English UI. Only the message is asserted: the rest of
    // this public demo page is still intentionally Vietnamese.
    const english = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await english.addInitScript(() => {
      localStorage.setItem('hra_access_token', 'fake-hr-test-token');
      localStorage.setItem('hra_locale', 'en');
    });
    await english.route('**/v1/**', async route => {
      const req = route.request(), path = new URL(req.url()).pathname, method = req.method();
      if (path === '/v1/auth/me') return json(route, { user_id: 'synthetic-user', email: 'hr@example.test', display_name: 'Fake HR', must_change_password: false, system_roles: ['HR_LEAD'], position_assignments: [] });
      if (path === '/v1/careers/jobs' && method === 'GET') return json(route, { items: [{ position_id: position, position_code: 'TEST-01', title: 'Vị trí giả', org_unit: null, work_location: null, work_mode: null, employment_type: null, application_deadline_at: '2099-01-01T00:00:00Z', description: null, can_apply_test: true }], next_cursor: null });
      if (path === `/v1/careers/jobs/${position}/apply` && method === 'POST') return route.abort('failed');
      return json(route, { detail: 'Unmocked synthetic API' }, 500);
    });
    const englishPage = await english.newPage();
    await englishPage.goto(base + '/careers', { waitUntil: 'networkidle' });
    await englishPage.getByRole('button', { name: 'View Detail' }).first().click();
    await englishPage.getByLabel('Candidate name').fill('Synthetic Person');
    await englishPage.getByLabel('Email').fill('person@example.test');
    await englishPage.locator('input[type=file]').setInputFiles({ name: 'fake.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-synthetic-only') });
    await englishPage.getByRole('button', { name: 'Gửi hồ sơ' }).click();
    await englishPage.getByText('We cannot tell whether the application was received', { exact: false }).first().waitFor({ timeout: 20000 });
    assert.equal(await englishPage.getByText('Không biết hồ sơ đã được nhận hay chưa', { exact: false }).count(), 0, 'the English UI must not fall back to the Vietnamese message');
    console.log('Careers failure message follows the selected language: OK');
    await english.close();

    if (errors.length) throw Error(errors.join('\n'));
  } catch (error) { console.error('Synthetic UI:', (await page.locator('body').innerText()).slice(0, 4000)); throw error; } finally { await browser.close(); }
})().catch(err => { console.error(err); process.exit(1); });
