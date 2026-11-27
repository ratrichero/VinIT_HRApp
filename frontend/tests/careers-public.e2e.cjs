/**
 * The public /careers page — the only surface an applicant ever sees.
 *
 * It used to be hardcoded Vietnamese with no language switch, and the file field
 * was the browser's default input, which on a phone is a tiny control that never
 * says which CV was chosen. Applicants are mostly students on phones, so this
 * test checks the three things that were missing:
 *  1. The page switches language: title, form labels, buttons and the consent
 *     text all change, and <html lang> follows.
 *  2. On a 390px phone the form fits without horizontal scrolling, its buttons
 *     are ≥44px tall, and the chosen file name is visible before sending.
 *  3. Submitting still posts the same fields (request_id, file, consent) and
 *     shows the receipt in the selected language.
 */
const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');

const base = process.env.HRA_E2E_BASE_URL;
if (!base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) {
  throw Error('Use local Next server only');
}

const JOB = {
  position_id: 'p1',
  position_code: 'REQ-2026-014',
  title: 'Senior Backend Engineer (Python)',
  org_unit: 'Nền tảng & Hạ tầng',
  work_location: 'Hà Nội',
  work_mode: 'Hybrid',
  employment_type: 'Full-time',
  application_deadline_at: '2026-12-31T17:00:00Z',
  description: 'Xây dựng dịch vụ Python chạy production.',
  can_apply_test: true,
  accepting_applications: true,
};

async function installCareersApi(context) {
  const unexpected = [];
  const applications = [];
  await context.route('**/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const p = url.pathname;
    if (p === '/v1/careers/jobs' && request.method() === 'GET') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [JOB], next_cursor: null }) });
    }
    if (/^\/v1\/careers\/jobs\/[^/]+\/apply$/.test(p) && request.method() === 'POST') {
      applications.push({ body: request.postData() || '', contentType: request.headers()['content-type'] || '' });
      return route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ application_id: 'app-careers', status: 'NEW' }) });
    }
    unexpected.push(`${request.method()} ${p}${url.search}`);
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) });
  });
  return { unexpected, applications };
}

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.HRA_E2E_CHROMIUM_EXECUTABLE,
    args: JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS || '[]'),
  });

  // --- 1. Language switching on the desktop page ---------------------------
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript(() => localStorage.setItem('hra_locale', 'vi'));
  const { unexpected } = await installCareersApi(context);
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error)));

  await page.goto(`${base}/careers`, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'Vị trí đang tuyển dụng' }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Xem chi tiết' }).count(), 1);
  assert.match(await page.locator('body').innerText(), /Chỉ kiểm thử với CV và thông tin tổng hợp/);

  await page.getByRole('button', { name: 'English' }).click();
  await page.getByRole('heading', { name: 'Open positions' }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.lang), 'en', '<html lang> must follow the switch');
  assert.equal(await page.getByRole('button', { name: 'View Detail' }).count(), 1);
  // Cảnh báo "chỉ dùng dữ liệu tổng hợp" đã bỏ: form nay nhận email thật và
  // câu đồng ý nói về việc lưu hồ sơ 12 tháng.
  assert.match(await page.locator('body').innerText(), /Free-form CVs and details only/);

  await page.getByRole('button', { name: 'View Detail' }).click();
  await page.getByLabel('Candidate name').waitFor();
  assert.equal(await page.getByLabel('Email').count(), 1);
  assert.equal(await page.getByRole('button', { name: 'Submit application' }).count(), 1);
  assert.match(await page.locator('body').innerText(), /I agree to submit my application/);
  assert.match(await page.locator('body').innerText(), /No file selected/);

  // The demo path relies on this exact name; keep it addressable by name.
  assert.equal(await page.locator('input[name=cv]').count(), 1);

  await page.getByRole('button', { name: 'Tiếng Việt' }).click();
  await page.getByRole('heading', { name: /Nộp hồ sơ cho vị trí này/ }).waitFor();
  assert.equal(await page.getByLabel('Tên ứng viên').count(), 1);
  assert.deepEqual(pageErrors, [], `no client-side exceptions: ${pageErrors.join(' | ')}`);
  assert.deepEqual(unexpected, [], `all API calls are accounted for: ${unexpected.join(', ')}`);
  await context.close();

  // --- 1b. Intake đóng thì KHÔNG hiện tin nào ------------------------------
  // Một trang tuyển dụng liệt kê việc mà bấm vào không nộp được là trang hỏng.
  const closed = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await closed.addInitScript(() => localStorage.setItem('hra_locale', 'vi'));
  await closed.route('**/v1/careers/jobs**', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ items: [], next_cursor: null, accepting_applications: false, reason: 'INTAKE_NOT_OPEN' }),
  }));
  await closed.route('**/v1/careers/filters', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ employment_types: [], job_families: [] }) }));
  const closedPage = await closed.newPage();
  await closedPage.goto(`${base}/careers`, { waitUntil: 'networkidle' });
  await closedPage.getByText('Hiện chưa mở nhận hồ sơ').waitFor();
  assert.equal(await closedPage.getByRole('button', { name: 'Xem chi tiết' }).count(), 0,
    'no listing rows may be shown while intake is closed');
  await closed.close();

  // --- 2 + 3. A phone-sized form: fits, 44px targets, chosen file, submit ---
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await mobile.addInitScript(() => localStorage.setItem('hra_locale', 'vi'));
  const { unexpected: mobileUnexpected, applications } = await installCareersApi(mobile);
  const phone = await mobile.newPage();
  const phoneErrors = [];
  phone.on('pageerror', error => phoneErrors.push(String(error)));

  await phone.goto(`${base}/careers`, { waitUntil: 'networkidle' });
  await phone.getByRole('heading', { name: 'Vị trí đang tuyển dụng' }).waitFor();
  await phone.getByRole('button', { name: 'Xem chi tiết' }).click();
  await phone.getByTestId('careers-apply-form').waitFor();

  // The file control is a real button with a readable size, not the tiny native input.
  const pickBox = await phone.getByTestId('careers-cv-pick').boundingBox();
  assert.ok(pickBox.height >= 44, `the CV picker needs a 44px touch target, got ${pickBox.height}px`);
  assert.equal(await phone.getByText('Chưa chọn tệp nào.').count(), 1);

  await phone.locator('input[name=cv]').setInputFiles({
    name: 'careers-cv.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.4\n% synthetic CV for the public careers form\n'),
  });
  await phone.getByTestId('careers-cv-name').waitFor();
  assert.match(await phone.getByTestId('careers-cv-name').innerText(), /careers-cv\.pdf/, 'the chosen file is named before sending');

  // No horizontal scroll, and the two actions stack with thumb-sized targets.
  const geometry = await phone.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    buttons: [...document.querySelectorAll('[data-testid="careers-apply-form"] button')].map(button => ({
      label: (button.textContent || '').trim(),
      height: Math.round(button.getBoundingClientRect().height),
      right: Math.round(button.getBoundingClientRect().right),
    })),
  }));
  assert.ok(geometry.scrollWidth <= geometry.innerWidth + 1, `the form must not scroll sideways: ${geometry.scrollWidth} > ${geometry.innerWidth}`);
  for (const button of geometry.buttons) {
    assert.ok(button.height >= 44, `"${button.label}" needs a 44px target, got ${button.height}px`);
    assert.ok(button.right <= geometry.innerWidth + 1, `"${button.label}" must stay on screen`);
  }

  await phone.getByLabel('Tên ứng viên').fill('Ứng viên tổng hợp');
  await phone.getByLabel('Email').fill('ung.vien@example.test');
  await phone.getByRole('button', { name: 'Gửi hồ sơ' }).click();
  await phone.getByText('Đã tiếp nhận hồ sơ', { exact: false }).waitFor();

  assert.equal(applications.length, 1, 'exactly one submission');
  assert.match(applications[0].contentType, /multipart\/form-data/, 'the CV is still posted as a multipart form');
  assert.match(applications[0].body, /name="request_id"/, 'the idempotency request id is still sent');
  assert.match(applications[0].body, /name="pool_opt_in"/);
  assert.match(applications[0].body, /careers-cv\.pdf/, 'the selected CV is uploaded');

  assert.deepEqual(phoneErrors, [], `no client-side exceptions: ${phoneErrors.join(' | ')}`);
  assert.deepEqual(mobileUnexpected, [], `all API calls are accounted for: ${mobileUnexpected.join(', ')}`);
  await mobile.close();

  console.log('Public careers page: language switch translates the whole page, the phone form fits without sideways scroll with 44px targets, names the chosen CV, and still posts request_id + multipart file with a translated receipt: OK');
  await browser.close();
})().catch(err => { console.error(err); process.exit(1); });
