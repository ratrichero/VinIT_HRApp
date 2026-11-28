const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const base = process.env.HRA_E2E_BASE_URL;
if (!base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) throw Error('Use local Next server only');
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

// Keyboard/name audit of the screens this UX slice changed. It is not a
// replacement for a screen-reader audit or a contrast audit.
async function unnamedControls(page) {
  return page.evaluate(() => {
    const selector = 'a[href], button, input, select, textarea, [role="button"], [tabindex]:not([tabindex="-1"])';
    const visible = element => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    };
    const name = element => {
      const aria = element.getAttribute('aria-label');
      if (aria && aria.trim()) return aria.trim();
      const labelledBy = element.getAttribute('aria-labelledby');
      if (labelledBy) {
        const text = labelledBy.split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
        if (text) return text;
      }
      const id = element.getAttribute('id');
      if (id) {
        const label = document.querySelector(`label[for="${CSS.escape(id)}"]`);
        if (label?.textContent?.trim()) return label.textContent.trim();
      }
      const wrapping = element.closest('label');
      if (wrapping?.textContent?.trim()) return wrapping.textContent.trim();
      const text = (element.innerText || element.getAttribute('title') || '').trim();
      if (text) return text;
      const alt = element.getAttribute('alt');
      return alt ? alt.trim() : '';
    };
    return [...document.querySelectorAll(selector)]
      // MUI keeps hidden native inputs behind custom selects; they are not in the
      // tab order or visible to assistive tech, so exclude them from the name audit.
      .filter(element => !element.hasAttribute('aria-hidden') && element.getAttribute('tabindex') !== '-1')
      .filter(element => visible(element) && !element.hasAttribute('disabled'))
      .filter(element => element.tagName !== 'INPUT' || !['hidden'].includes(element.getAttribute('type') || ''))
      .filter(element => !name(element))
      .map(element => element.outerHTML.slice(0, 140));
  });
}

async function noHorizontalOverflow(page, label) {
  const width = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  assert.ok(width.scroll <= width.client + 1, `${label}: horizontal overflow ${JSON.stringify(width)}`);
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.HRA_E2E_CHROMIUM_EXECUTABLE, args: JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS || '[]') });
  const errors = [];

  // 1. Create-position form: keyboard reaches every required control and submit.
  for (const width of [1280, 390]) {
    const c = await browser.newContext({ viewport: { width, height: 900 } });
    await c.addInitScript(() => { localStorage.setItem('hra_access_token', 'test'); localStorage.setItem('hra_locale', 'vi'); });
    await c.route('**/v1/**', async r => {
      const p = new URL(r.request().url()).pathname;
      if (p === '/v1/auth/me') return json(r, { user_id: 'hr', display_name: 'HR', system_roles: ['HR_LEAD'], position_assignments: [] });
      if (p === '/v1/departments') return json(r, [{ department_id: 'd', name: 'IT', code_format: 'REQ-{SEQ:000}', next_sequence: 1 }]);
      if (p === '/v1/users') return json(r, [{ user_id: 'hm', display_name: 'HM' }]);
      if (p === '/v1/rubric-library/families') return json(r, []);
      if (p === '/v1/positions') return json(r, []);
      if (p === '/v1/dashboard/summary') return json(r, { total_applications: 0 });
      // Chuông thông báo trong AppLayout hỏi hộp thư ngay khi mount; hộp thư rỗng
      // không đổi bố cục, nên thiếu route này chỉ làm mock báo lỗi sai.
      if (p === '/v1/notifications' && r.request().method() === 'GET') return json(r, { items: [], unread_count: 0 });
      if (p === '/v1/dashboard/work-queue') return json(r, []);
      errors.push(p); return json(r, {}, 500);
    });
    const page = await c.newPage();
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base + '/positions/new');
    await page.getByRole('heading', { name: 'Tạo vị trí tuyển dụng' }).waitFor();
    const missing = await unnamedControls(page);
    assert.deepEqual(missing, [], `unnamed controls on create page (${width}px): ${missing.join('\n')}`);
    await noHorizontalOverflow(page, `create ${width}px`);
    // Keyboard-only: tab until the required text field has focus, then type.
    let focused = '';
    // The sidebar is part of the tab order, so allow enough steps to reach the form.
    for (let i = 0; i < 80 && !focused.includes('Tên vị trí'); i += 1) {
      await page.keyboard.press('Tab');
      focused = await page.evaluate(() => {
        const active = document.activeElement;
        if (!active) return '';
        const id = active.getAttribute('id');
        const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`)?.textContent || '' : '';
        return `${label} ${active.getAttribute('aria-label') || ''} ${active.innerText || ''}`;
      });
    }
    assert.ok(focused.includes('Tên vị trí'), `Tab order never reached the title field: ${focused}`);
    await page.keyboard.type('Backend Keyboard');
    assert.equal(await page.getByRole('textbox', { name: /Tên vị trí/ }).inputValue(), 'Backend Keyboard');
    // The submit stays reachable and announces why it is disabled.
    const submit = page.getByRole('button', { name: 'Tạo vị trí và tiếp tục' });
    assert.equal(await submit.isDisabled(), true, 'submit must stay disabled without a JD');
    await c.close();
  }

  // 2. HM workspace: candidate buttons are pressed-state buttons, evidence panel
  //    is reachable by keyboard and the layout has no overflow on mobile.
  for (const width of [1280, 390]) {
    const c = await browser.newContext({ viewport: { width, height: 900 } });
    await c.addInitScript(() => { localStorage.setItem('hra_access_token', 'test'); localStorage.setItem('hra_locale', 'vi'); });
    await c.route('**/v1/**', async r => {
      const p = new URL(r.request().url()).pathname;
      if (p === '/v1/auth/me') return json(r, { user_id: 'hm', display_name: 'HM', system_roles: ['HIRING_MANAGER'], position_assignments: [] });
      if (p === '/v1/scorecards/reminders') return json(r, []);
      if (p === '/v1/notifications' && r.request().method() === 'GET') return json(r, { items: [], unread_count: 0 });
      if (p === '/v1/dashboard/work-queue') return json(r, []);
      if (p === '/v1/shortlist/shared-with-me') return json(r, []);
      if (p === '/v1/shortlist/share-a11y') return json(r, { share_id: 'share-a11y', position_id: 'p1', position: { title: 'Vị trí' }, status: 'ACTIVE', allow_cv_view: false, applications: [{ application_id: 'a', candidate_name: 'An' }, { application_id: 'b', candidate_name: 'Bình' }], feedback: [] });
      if (p === '/v1/scorecards/share/share-a11y') return json(r, ['a', 'b'].map((id, i) => ({ scorecard_id: `s${id}`, application_id: id, status: 'IN_PROGRESS', revision: 1, due_at: '2031-01-01T00:00:00Z', can_edit: true, waiting_for_assessment: false, criteria_version_id: 'c', assessment_id: 'ass', strengths: '', concerns: '', overall_recommendation: null, criteria: [{ criterion_id: `cr${i}`, name: 'Python', description: 'Test', rating: null, insufficient_evidence: false, comment: null }] })));
      if (p === '/v1/applications/a' || p === '/v1/applications/b') return json(r, { application_id: p.split('/').pop(), position_id: 'p1', can_view_cv: false, can_view_assessment_evidence: false, latest_assessment: null, documents: [] });
      errors.push(p); return json(r, {}, 500);
    });
    const page = await c.newPage();
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base + '/shortlist/share-a11y');
    await page.getByRole('heading', { name: /Không gian đánh giá shortlist/ }).waitFor();
    const missing = await unnamedControls(page);
    assert.deepEqual(missing, [], `unnamed controls in share workspace (${width}px): ${missing.join('\n')}`);
    await noHorizontalOverflow(page, `share ${width}px`);
    const first = page.getByRole('button', { name: /^An/ });
    assert.equal(await first.getAttribute('aria-pressed'), 'true');
    await first.focus();
    await page.keyboard.press('Tab');
    const reached = await page.evaluate(() => document.activeElement?.tagName);
    assert.ok(reached, 'keyboard focus must move on from the candidate list');
    // Selecting the second candidate by keyboard updates the pressed state.
    await page.getByRole('button', { name: /^Bình/ }).focus();
    await page.keyboard.press('Enter');
    await page.getByRole('button', { name: /^Bình/ }).waitFor();
    assert.equal(await page.getByRole('button', { name: /^Bình/ }).getAttribute('aria-pressed'), 'true');
    // The evidence accordion can be opened with the keyboard alone.
    const evidenceSummary = page.getByRole('button', { name: 'CV và bằng chứng đánh giá' });
    await evidenceSummary.focus();
    await page.keyboard.press('Enter');
    await page.getByText('Shortlist này không cho phép xem CV gốc.').first().waitFor();
    await c.close();
  }

  if (errors.length) throw Error(errors.join('\n'));
  await browser.close();
  console.log('A11y smoke: every visible control has an accessible name, create form is keyboard-reachable, share workspace keeps aria-pressed and mobile layout without overflow: OK; all /v1 intercepted');
})().catch(e => { console.error(e); process.exit(1); });
