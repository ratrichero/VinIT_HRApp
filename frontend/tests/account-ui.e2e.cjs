const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');

// Every /v1 request is intercepted below; never sends account mutations to a
// backend. The Next server itself must still be a disposable local instance.
const base = process.env.HRA_E2E_BASE_URL;
if (!base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) {
  throw new Error('Set HRA_E2E_BASE_URL to a local Next.js server.');
}
const executablePath = process.env.HRA_E2E_CHROMIUM_EXECUTABLE;
const args = process.env.HRA_E2E_CHROMIUM_ARGS ? JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS) : [];
const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

(async () => {
  const browser = await chromium.launch({ executablePath, args, headless: true });
  const errors = [];
  const state = {
    available: true, bootstrapBody: null, createdBody: null, changeBody: null, positionBody: null, directoryUrl: null,
    users: [
      { user_id: 'admin-id', email: 'admin@example.org', display_name: 'Synthetic Admin', roles: ['ADMIN'], account_status: 'ACTIVE', must_change_password: false },
      { user_id: 'hm-id', email: 'hm@example.org', display_name: 'Hằng HM', roles: ['HIRING_MANAGER'], account_status: 'ACTIVE', must_change_password: false },
    ], positions: [],
  };
  async function setup(context) {
    await context.route('**/v1/**', async route => {
      const req = route.request(); const url = new URL(req.url()); const path = url.pathname; const method = req.method();
      const token = req.headers().authorization || '';
      const admin = token === 'Bearer admin-token';
      const hr = token === 'Bearer hr-token';
      const temp = token === 'Bearer temp-token';
      if (path === '/v1/auth/bootstrap-status') return json(route, { available: state.available });
      if (path === '/v1/auth/bootstrap' && method === 'POST') { state.bootstrapBody = req.postDataJSON(); state.available = false; return json(route, { user_id: 'admin-id' }, 201); }
      if (path === '/v1/auth/login') {
        const email = req.postDataJSON().email;
        if (email === 'admin@example.org') return json(route, { access_token: 'admin-token', user: { id: 'admin-id', must_change_password: false } });
        if (email === 'hr@example.org') return json(route, { access_token: 'hr-token', user: { id: 'hr-id', must_change_password: false } });
        if (email === 'temp@example.org') return json(route, { access_token: 'temp-token', user: { id: 'temp-id', must_change_password: true } });
        return json(route, { detail: 'Email hoặc mật khẩu không đúng' }, 401);
      }
      if (path === '/v1/auth/change-password') { state.changeBody = req.postDataJSON(); return json(route, { changed: true }); }
      if (path === '/v1/auth/me') {
        if (!admin && !hr && !temp) return json(route, { detail: 'Could not validate credentials' }, 401);
        return json(route, { user_id: admin ? 'admin-id' : hr ? 'hr-id' : 'temp-id',
          email: admin ? 'admin@example.org' : 'hr@example.org', display_name: admin ? 'Synthetic Admin' : 'Synthetic HR',
          must_change_password: temp, system_roles: admin ? ['ADMIN'] : ['HR_RECRUITER'], position_assignments: [] });
      }
      if (path === '/v1/admin/users' && !admin) return json(route, { detail: 'Admin role required for this endpoint' }, 403);
      if (path === '/v1/admin/users' && method === 'GET') {
        let users = state.users;
        const role = url.searchParams.get('role'); if (role) users = users.filter(u => u.roles.includes(role));
        const q = url.searchParams.get('search'); if (q) users = users.filter(u => `${u.display_name} ${u.email}`.toLowerCase().includes(q.toLowerCase()));
        return json(route, { items: users, page: 1, has_more: false });
      }
      if (path === '/v1/admin/users' && method === 'POST') {
        state.createdBody = req.postDataJSON();
        state.users.push({ ...state.createdBody, password: undefined, user_id: 'new-id', account_status: 'ACTIVE', must_change_password: true });
        return json(route, { user_id: 'new-id', must_change_password: true }, 201);
      }
      if (path.startsWith('/v1/admin/users/') && method === 'PATCH' && admin) {
        const id = path.split('/').pop(); const user = state.users.find(item => item.user_id === id);
        Object.assign(user, req.postDataJSON()); return json(route, user);
      }
      if (path === '/v1/dashboard/summary') return json(route, { total_applications: 0 });
      // Badge "việc cần làm" trên header gọi work-queue ở mọi trang đã đăng nhập.
      if (path === '/v1/dashboard/work-queue') return json(route, { generated_at: '2026-11-19T03:00:00Z', summary: {}, items: [] });
      // Chuông thông báo (arena) hỏi hộp thư ngay khi mount, và mỗi 60 giây.
      // Hộp thư rỗng: test này kiểm tài khoản, không kiểm thông báo.
      if (path === '/v1/notifications' && method === 'GET') return json(route, { items: [], unread_count: 0 });
      // Tạo vị trí xong là sinh bộ tiêu chí nháp luôn (luồng mới); thiếu route này
      // thì trang tạo vị trí đứng lại ở /positions/new và không chuyển trang.
      if (path === '/v1/criteria/generate/position-id' && method === 'POST') {
        return json(route, { criteria_version_id: 'cv-id', version_number: 1, status: 'DRAFT' }, 202);
      }
      if (path === '/v1/positions' && method === 'GET') return json(route, state.positions);
      if (path === '/v1/positions' && method === 'POST') {
        state.positionBody = req.postDataJSON();
        state.positions.push({ ...state.positionBody, position_id: 'position-id', status: 'OPEN', created_by: 'hr-id', created_at: new Date().toISOString() });
        return json(route, { position_id: 'position-id' }, 201);
      }
      if (path === '/v1/departments') return json(route, [{ department_id: 'dept-id', name: 'IT Test', code_format: 'REQ-IT-{SEQ:000}', next_sequence: 1 }]);
      if (path === '/v1/rubric-library/families') return json(route, []);
      if (path === '/v1/positions/position-id') return json(route, { position_id: 'position-id', position_code: 'REQ-IT-001', title: 'Synthetic Engineer', status: 'OPEN' });
      if (path === '/v1/positions/position-id/jd-versions') return json(route, [{ jd_version_id: 'jd-id', version_number: 1, content_text: 'Synthetic job description for testing.', language_code: 'vi' }]);
      if (path === '/v1/criteria/position/position-id/versions') return json(route, []);
      if (path === '/v1/positions/position-id/workspace') return json(route, { detail: 'Synthetic unavailable' }, 404);
      if (path === '/v1/users') { state.directoryUrl = url; return json(route, [{ user_id: 'hm-id', display_name: 'Hằng HM' }]); }
      errors.push(`Unmocked API request: ${method} ${path}`); return json(route, { detail: 'Unexpected synthetic request' }, 500);
    });
  }
  function watch(page) { page.on('pageerror', e => errors.push(e.stack || e.message)); }
  const visible = async (page, text) => page.getByText(text, { exact: false }).filter({ visible: true }).first().waitFor({ timeout: 15000 });
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await setup(desktop); const page = await desktop.newPage(); watch(page);
  await page.goto(base + '/');
  await page.getByRole('button', { name: 'Khởi tạo Admin đầu tiên' }).click();
  await page.getByLabel('Họ và tên').fill('Synthetic Admin');
  await page.getByLabel('Email').fill('admin@example.org');
  await page.getByLabel('Mã khởi tạo').fill('synthetic-setup-code-of-sufficient-length');
  await page.getByLabel('Mật khẩu Admin').fill('synthetic-admin-password');
  await page.getByLabel('Xác nhận mật khẩu').fill('synthetic-admin-password');
  await page.getByRole('button', { name: 'Tạo Admin', exact: true }).click();
  await visible(page, 'Đã tạo Admin'); assert.equal(state.bootstrapBody.email, 'admin@example.org');
  await page.getByRole('button', { name: 'Quay lại đăng nhập' }).click();
  await page.getByLabel('Email').fill('admin@example.org'); await page.locator('input[type="password"]').fill('synthetic-admin-password');
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click(); await visible(page, 'Danh sách vị trí tuyển dụng');
  await page.getByRole('link', { name: 'Quản lý tài khoản' }).click(); await visible(page, 'Synthetic Admin');
  await page.getByRole('button', { name: 'Tạo tài khoản', exact: true }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('Họ và tên').fill('Synthetic Recruiter'); await dialog.getByLabel('Email').fill('new@example.org');
  await dialog.getByLabel('Mật khẩu tạm thời').fill('synthetic-temporary-password');
  await dialog.getByLabel('Xác nhận mật khẩu').fill('synthetic-temporary-password');
  await dialog.getByRole('button', { name: 'Lưu tài khoản' }).click();
  await visible(page, 'Đã tạo tài khoản'); await visible(page, 'Synthetic Recruiter');
  assert.deepEqual(state.createdBody.roles, ['HR_RECRUITER']);
  assert.equal(state.createdBody.email, 'new@example.org');
  await page.getByRole('button', { name: 'Chỉnh sửa tài khoản Synthetic Recruiter' }).click();
  dialog = page.getByRole('dialog'); await dialog.getByLabel('Họ và tên').fill('Synthetic Recruiter Updated');
  await dialog.getByRole('button', { name: 'Lưu tài khoản' }).click(); await visible(page, 'Đã cập nhật tài khoản');
  await visible(page, 'Synthetic Recruiter Updated');
  await page.getByRole('button', { name: 'English', exact: true }).click(); await visible(page, 'Account management');
  await visible(page, 'HR recruiter');
  console.log('Bootstrap, Admin account creation/edit and bilingual UI: OK');

  const temporary = await browser.newContext({ viewport: { width: 1280, height: 800 } }); await setup(temporary);
  const tp = await temporary.newPage(); watch(tp); await tp.goto(base + '/');
  await tp.getByLabel('Email').fill('temp@example.org'); await tp.locator('input[type="password"]').fill('synthetic-temporary-password');
  await tp.getByRole('button', { name: 'Đăng nhập', exact: true }).click(); await visible(tp, 'Đổi mật khẩu tạm thời');
  await tp.getByLabel('Mật khẩu tạm thời').fill('synthetic-temporary-password');
  await tp.getByLabel('Mật khẩu mới').fill('synthetic-new-password'); await tp.getByLabel('Xác nhận mật khẩu').fill('synthetic-new-password');
  await tp.getByRole('button', { name: 'Đổi mật khẩu', exact: true }).click(); await visible(tp, 'Đã đổi mật khẩu');
  assert.equal(state.changeBody.new_password, 'synthetic-new-password'); assert.equal(await tp.evaluate(() => localStorage.getItem('hra_access_token')), null);
  console.log('First-login mandatory password change and local sign-out: OK');

  const recruiter = await browser.newContext({ viewport: { width: 1280, height: 800 } }); await setup(recruiter);
  await recruiter.addInitScript(() => localStorage.setItem('hra_access_token', 'hr-token'));
  // The temp-password context is still mounted and can keep a navigation pending;
  // close it before reusing the dev server so the check measures the recruiter page.
  await temporary.close();
  const hp = await recruiter.newPage(); watch(hp); await hp.goto(base + '/positions'); await visible(hp, 'Danh sách vị trí tuyển dụng');
  assert.equal(await hp.getByRole('link', { name: 'Quản lý tài khoản' }).count(), 0);
  await hp.getByRole('button', { name: 'Tạo vị trí mới' }).click();
  await hp.waitForURL('**/positions/new');
  await hp.getByRole('textbox', { name: /Tên vị trí/ }).fill('Synthetic Engineer');
  await hp.getByLabel('Đơn vị / Phòng ban').click(); await hp.getByRole('option', { name: 'IT Test' }).click();
  await hp.getByLabel('Hiring Manager').fill('Hằng'); await hp.getByRole('option', { name: 'Hằng HM' }).click();
  await hp.getByLabel('Nội dung JD').fill('Synthetic job description for testing.');
  await hp.getByRole('button', { name: 'Tạo vị trí và tiếp tục' }).click();
  // App Router navigates on the client, so only wait for the URL, not a document load.
  await hp.waitForURL('**/positions/position-id?tab=criteria', { waitUntil: 'commit' });
  assert.equal(state.directoryUrl.searchParams.get('role'), 'HIRING_MANAGER'); assert.equal(state.positionBody.hiring_manager_user_id, 'hm-id');
  // Không còn gửi jd_language_code: máy chủ tự dò ngôn ngữ từ nội dung JD.
  assert.equal('jd_language_code' in state.positionBody, false, 'ngôn ngữ JD không còn do client chọn');
  assert.match(state.positionBody.request_id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/, 'create sends a retry-safe request id');
  await hp.goto(base + '/admin/users'); await visible(hp, 'Chỉ quản trị viên mới có quyền truy cập.');
  console.log('HR selects an HM role and cannot access account administration: OK');

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } }); await setup(mobile);
  await mobile.addInitScript(() => localStorage.setItem('hra_access_token', 'admin-token'));
  const mp = await mobile.newPage(); watch(mp); await mp.goto(base + '/admin/users'); await visible(mp, 'Synthetic Admin');
  const width = await mp.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  assert.ok(width.scroll <= width.client + 1, JSON.stringify(width));
  await mp.getByRole('button', { name: 'Tạo tài khoản', exact: true }).click(); await visible(mp, 'Xác minh đúng email');
  console.log(`Mobile account list and dialog: OK (${width.scroll}/${width.client})`);
  await browser.close(); if (errors.length) throw Error(errors.join('\n'));
  console.log('No browser page errors; all /v1 calls intercepted in the synthetic browser test.');
})().catch(error => { console.error(error); process.exit(1); });
