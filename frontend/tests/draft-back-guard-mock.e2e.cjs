const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const base = process.env.HRA_E2E_BASE_URL;
if (!base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) throw Error('Use local Next server only');
const json = (r, body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
const cards = (revision = 1) => ['a', 'b'].map((id, i) => ({
  scorecard_id: `s${id}`, application_id: id, status: 'IN_PROGRESS', revision,
  due_at: '2031-01-01T00:00:00Z', can_edit: true, waiting_for_assessment: false,
  criteria_version_id: 'criteria', assessment_id: 'assessment', strengths: '', concerns: '',
  overall_recommendation: null, can_reopen: false, can_change_due: false, can_view_history: false,
  criteria: [{ criterion_id: `cr${i}`, name: 'Python', description: 'Test', rating: null, insufficient_evidence: false, comment: null }],
}));

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.HRA_E2E_CHROMIUM_EXECUTABLE, args: JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS || '[]') });
  const errors = [];
  const c = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await c.addInitScript(() => { localStorage.setItem('hra_access_token', 'test'); localStorage.setItem('hra_locale', 'vi'); });
  let revision = 1;
  let revoked = false;
  let savedStrengths = '';
  await c.route('**/v1/**', async r => {
    const req = r.request(); const p = new URL(req.url()).pathname; const method = req.method();
    if (p === '/v1/auth/me') return json(r, { user_id: 'hm', display_name: 'HM', system_roles: ['HIRING_MANAGER'], position_assignments: [] });
    if (p === '/v1/scorecards/reminders') return json(r, []);
    // Chuông thông báo của AppLayout gọi ngay khi mount; hộp thư rỗng giữ nguyên bố cục.
    if (p === '/v1/notifications' && method === 'GET') return json(r, { items: [], unread_count: 0 });
    if (p === '/v1/dashboard/work-queue' && method === 'GET') return json(r, []);
    if (p === '/v1/shortlist/shared-with-me') return json(r, []);
    if (p === '/v1/shortlist/share-draft') return revoked ? json(r, { detail: 'Đã thu hồi' }, 403) : json(r, { share_id: 'share-draft', position_id: 'p1', position: { title: 'Vị trí' }, status: 'ACTIVE', allow_cv_view: false, applications: [{ application_id: 'a', candidate_name: 'An' }, { application_id: 'b', candidate_name: 'Bình' }], feedback: [] });
    if (p === '/v1/scorecards/share/share-draft') return json(r, cards(revision).map(c => ({ ...c, strengths: c.scorecard_id === 'sa' ? savedStrengths : c.strengths })));
    if (method === 'PUT' && p === '/v1/scorecards/sa') {
      // Echo what was saved and advance the revision, like the real API.
      const body = JSON.parse(req.postData() || '{}');
      assert.equal(body.expected_revision, revision, 'save must send the revision it was loaded with');
      savedStrengths = body.strengths || '';
      revision += 1;
      return json(r, { ...cards(revision)[0], strengths: savedStrengths });
    }
    if (p === '/v1/applications/a' || p === '/v1/applications/b') return json(r, { application_id: p.split('/').pop(), position_id: 'p1', can_view_cv: false, can_view_assessment_evidence: false, latest_assessment: null, documents: [] });
    errors.push(`${method} ${p}`); return json(r, {}, 500);
  });
  const page = await c.newPage();
  page.on('pageerror', e => errors.push(e.message));
  // Enter from the inbox so Back has somewhere real to go.
  await page.goto(base + '/shortlist');
  await page.getByRole('heading', { name: /Shortlist/ }).first().waitFor().catch(() => {});
  await page.goto(base + '/shortlist/share-draft');
  await page.getByRole('heading', { name: /Không gian đánh giá shortlist/ }).waitFor();
  assert.equal(await page.getByLabel('Điểm mạnh').filter({ visible: true }).inputValue(), '');

  // 1. Draft survives a full reload of the page.
  await page.getByLabel('Điểm mạnh').filter({ visible: true }).fill('Nháp sống qua reload');
  await page.getByLabel('Điểm cần xem xét').filter({ visible: true }).fill('Lo ngại A');
  await page.getByLabel('Phản hồi của bạn').fill('Phản hồi chưa gửi');
  await page.waitForTimeout(700);
  // A reload is a real unload: the guard asks, and the test accepts it.
  const acceptOnce = async (d) => d.accept();
  page.on('dialog', acceptOnce);
  await page.reload();
  page.off('dialog', acceptOnce);
  await page.getByRole('heading', { name: /Không gian đánh giá shortlist/ }).waitFor();
  await page.getByLabel('Điểm mạnh').filter({ visible: true }).waitFor();
  assert.equal(await page.getByLabel('Điểm mạnh').filter({ visible: true }).inputValue(), 'Nháp sống qua reload');
  assert.equal(await page.getByLabel('Điểm cần xem xét').filter({ visible: true }).inputValue(), 'Lo ngại A');
  assert.equal(await page.getByLabel('Phản hồi của bạn').inputValue(), 'Phản hồi chưa gửi');
  await page.getByText(/Đã khôi phục nháp scorecard/).waitFor();
  await page.getByText(/Đã khôi phục phản hồi chưa gửi/).waitFor();

  // 2. A server-side revision change invalidates the old draft instead of replaying it.
  revision = 2;
  await page.evaluate(() => {
    // Simulate the server advancing while this browser kept an older draft.
    localStorage.setItem('hra:draft:scorecard:share-draft:sa', JSON.stringify({ saved_at: Date.now(), data: { revision: 1, card: { strengths: 'Bản cũ' } } }));
  });
  await page.reload();
  await page.getByRole('heading', { name: /Không gian đánh giá shortlist/ }).waitFor();
  await page.getByLabel('Điểm mạnh').filter({ visible: true }).waitFor();
  assert.equal(await page.getByLabel('Điểm mạnh').filter({ visible: true }).inputValue(), '', 'a stale revision must not be restored');
  const stale = await page.evaluate(() => localStorage.getItem('hra:draft:scorecard:share-draft:sa'));
  assert.equal(stale, null, 'the stale draft is deleted');

  // 2b. Saving sends the draft to the server and drops the local copy.
  await page.getByLabel('Điểm mạnh').filter({ visible: true }).fill('Đã lưu lên server');
  await page.waitForTimeout(600);
  const beforeSave = await page.evaluate(() => localStorage.getItem('hra:draft:scorecard:share-draft:sa'));
  assert.ok(beforeSave, 'typing writes a local draft before saving');
  await page.getByRole('button', { name: 'Lưu nháp scorecard' }).first().click();
  await page.getByText('Đã lưu lên server').last().waitFor();
  await page.waitForTimeout(300);
  assert.equal(await page.evaluate(() => localStorage.getItem('hra:draft:scorecard:share-draft:sa')), null, 'a saved scorecard keeps no local draft');
  assert.ok(await page.evaluate(() => localStorage.getItem('hra:draft:share-feedback:share-draft')), 'other drafts of the same share are untouched');

  // A reload after saving restores nothing and shows the saved value.
  await page.reload();
  await page.getByRole('heading', { name: /Không gian đánh giá shortlist/ }).waitFor();
  await page.getByLabel('Điểm mạnh').filter({ visible: true }).waitFor();
  assert.equal(await page.getByLabel('Điểm mạnh').filter({ visible: true }).inputValue(), 'Đã lưu lên server');
  assert.equal(await page.getByText(/Đã khôi phục nháp scorecard/).count(), 0, 'nothing is "restored" after a save');

  // 3. Back navigation with unsaved work asks first; cancelling keeps the page and draft.
  await page.getByLabel('Điểm mạnh').filter({ visible: true }).fill('Nháp trước khi Back');
  await page.waitForTimeout(600);
  let asked = 0;
  page.on('dialog', async dialog => { asked += 1; await dialog.dismiss(); });
  await page.goBack();
  await page.waitForTimeout(600);
  assert.equal(asked, 1, 'Back must ask once');
  assert.match(page.url(), /shortlist\/share-draft/);
  assert.equal(await page.getByLabel('Điểm mạnh').filter({ visible: true }).inputValue(), 'Nháp trước khi Back');

  // 4. Confirming Back actually leaves the share workspace.
  page.removeAllListeners('dialog');
  page.on('dialog', async dialog => { asked += 1; await dialog.accept(); });
  await page.goBack();
  await page.waitForURL(url => !/shortlist\/share-draft/.test(url.pathname), { timeout: 5000 });
  assert.doesNotMatch(page.url(), /shortlist\/share-draft/, `expected to leave, got ${page.url()}`);
  assert.equal(asked, 2);
  assert.match(page.url(), /\/shortlist/, 'returns to the previous screen, not an arbitrary URL');

  // 5. Losing access purges local drafts for that share only.
  await page.evaluate(() => {
    localStorage.setItem('hra:draft:share-feedback:share-other', JSON.stringify({ saved_at: Date.now(), data: { content: 'keep' } }));
  });
  revoked = true;
  await page.goto(base + '/shortlist/share-draft');
  await page.getByText('Quyền truy cập shortlist không còn hoặc shortlist không tồn tại.').waitFor();
  const left = await page.evaluate(() => ({
    mine: Object.keys(localStorage).filter(key => key.startsWith('hra:draft:') && key.includes('share-draft')),
    other: Object.keys(localStorage).filter(key => key.includes('share-other')),
  }));
  assert.deepEqual(left.mine, [], 'drafts of a revoked share are removed');
  assert.equal(left.other.length, 1, 'other shares keep their drafts');

  if (errors.length) throw Error(errors.join('\n'));
  await browser.close();
  console.log('Drafts + Back/Forward guard: reload restore, stale-revision rejection, cancel/confirm Back and purge on access loss: OK; all /v1 intercepted');
})().catch(e => { console.error(e); process.exit(1); });
