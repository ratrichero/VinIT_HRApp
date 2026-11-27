const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const base = process.env.HRA_E2E_BASE_URL;
if (!base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) throw new Error('Use a local disposable Next server.');
const state = { created: null, fileType: null, urls: [], attempts: 0, generateCalls: 0, generateFail: 0,
  // 'opaque' = request bị proxy cắt: trả 504 HTML KHÔNG có detail, nhưng tiêu chí đã lưu.
  mode: process.env.HRA_E2E_GENERATE_MODE || 'ok', versionsAfterGenerate: 0,
  // 'error500' = đọc tiêu chí nổ (đúng lỗi "Không thể tải thông tin vị trí" trên VPS)
  listMode: process.env.HRA_E2E_LIST_MODE || 'empty' };
const json = (r,b,s=200) => r.fulfill({status:s,contentType:'application/json',body:JSON.stringify(b)});
(async () => {
 const browser = await chromium.launch({executablePath:process.env.HRA_E2E_CHROMIUM_EXECUTABLE, args:process.env.HRA_E2E_CHROMIUM_ARGS ? JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS) : [],headless:true});
 const context = await browser.newContext({viewport:{width:1280,height:900}});
 await context.addInitScript(() => { localStorage.setItem('hra_access_token','synthetic-token'); localStorage.setItem('hra_locale','vi'); });
 const errors=[];
 await context.route('**/v1/**', async r => {
  const q = r.request(); const u = new URL(q.url()); const p = u.pathname; const method=q.method();
  if(p === '/v1/auth/me') return json(r,{user_id:'hr',display_name:'HR giả',system_roles:['HR_LEAD'],position_assignments:[]});
  if(p === '/v1/departments') return json(r,[{department_id:'dept',name:'IT test',code_format:'REQ-IT-{SEQ:000}',next_sequence:1}]);
  if(p === '/v1/users') return json(r,[{user_id:'hm',display_name:'HM giả'}]);
  if(p === '/v1/rubric-library/families') return json(r,[]);
  if(p === '/v1/jd-import/file' && method==='POST') { state.fileType=q.headers()['content-type']; return json(r,{content:'JD giả từ file: Python và SQL',warning:'Rà soát nội dung'}); }
  if(p === '/v1/jd-import/url' && method==='POST') { state.urls.push(q.postDataJSON().url); return json(r,{content:'JD giả từ link: dữ liệu Python',warning:'Rà soát nội dung'}); }
  if(p === '/v1/positions' && method==='POST') { state.attempts+=1; if(state.attempts===1) { state.created=q.postDataJSON(); return json(r,{detail:'Synthetic outage'},503); }
    state.retried=q.postDataJSON(); return json(r,{position_id:'position'},200); }
  if(p === '/v1/positions' && method==='GET') return json(r,[]);
  if(p === '/v1/dashboard/summary') return json(r,{open_positions:0,total_applications:0,applications_by_status:{SHORTLIST:0},files_needing_hr_review:0});
  // Badge "việc cần làm" trên header gọi work-queue ở mọi trang đã đăng nhập.
  if(p === '/v1/dashboard/work-queue') return json(r,{generated_at:'2026-11-19T03:00:00Z',summary:{},items:[]});
  // Chuông thông báo (arena) hỏi hộp thư ngay khi mount; hộp thư rỗng.
  if(p === '/v1/notifications') return json(r,{items:[],unread_count:0});
  if(p === '/v1/criteria/generate/position' && method==='POST') { state.generateCalls+=1;
    if(state.generateCalls<=state.generateFail) return json(r,{detail:'AI trả về bộ tiêu chí không hợp lệ. Vui lòng thử lại.'},502);
    if(state.mode==='opaque') { state.versionsAfterGenerate=1;
      return r.fulfill({status:504,contentType:'text/html',body:'<html><body>504 Gateway Time-out</body></html>'}); }
    state.versionsAfterGenerate=1;
    return json(r,{criteria_version_id:'cv',version_number:1,status:'DRAFT'},202); }
  if(p === '/v1/positions/position') return json(r,{position_id:'position',position_code:'REQ-IT-001',title:'Backend giả',status:'OPEN'});
  if(p === '/v1/positions/position/jd-versions') return json(r,[{jd_version_id:'jd',version_number:1,content_text:'JD giả từ link: dữ liệu Python',language_code:'vi'}]);
  if(p === '/v1/criteria/position/position/versions') {
    if(state.listMode==='error500') return r.fulfill({status:500,contentType:'text/plain',body:'Internal Server Error'});
    return json(r, state.versionsAfterGenerate ? [{criteria_version_id:'cv',version_number:1,status:'DRAFT',criteria:[]}] : []); }
  if(p === '/v1/positions/position/workspace') return json(r,{},404);
  if(p === '/v1/dashboard/position/position') return json(r,{total_applications:0,applications_processing:0,files_needing_hr_review:0,applications_by_status:{SHORTLIST:0}});
  if(p === '/v1/operations/position/position/active') return json(r,null);
  errors.push(`Unexpected ${method} ${p}`); return json(r,{detail:'Unexpected request'},500);
 });
 const page=await context.newPage(); page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/positions');
 await page.getByRole('button',{name:'Tạo vị trí mới'}).click();
 await page.waitForURL('**/positions/new');
 assert.equal(await page.getByRole('dialog').count(),0);
 const create=page.getByRole('button',{name:'Tạo vị trí và tiếp tục'});
 assert.equal(await create.isDisabled(),true);
 // Missing fields are named up front instead of leaving a silently disabled button.
 await page.getByText('Còn thiếu: Tên vị trí, Đơn vị / Phòng ban, Hiring Manager, Nội dung JD.').waitFor();
 await page.getByRole('textbox',{name:/Tên vị trí/}).fill('Backend giả');
 await page.getByRole('textbox',{name:/Tên vị trí/}).blur();
 await page.getByText('Còn thiếu: Đơn vị / Phòng ban, Hiring Manager, Nội dung JD.').waitFor();
 await page.getByLabel('Đơn vị / Phòng ban').click(); await page.getByRole('option',{name:'IT test'}).click();
 await page.getByLabel('Hiring Manager').fill('HM'); await page.getByRole('option',{name:'HM giả'}).click();
 assert.equal(await create.isDisabled(),true,'JD required');
 await page.getByRole('button',{name:'Tải tệp DOCX / TXT'}).click();
 await page.getByLabel('Chọn tệp JD').setInputFiles({name:'jd.txt',mimeType:'text/plain',buffer:Buffer.from('JD synthetic')});
 await page.getByRole('button',{name:'Đọc tệp'}).click();
 await page.getByLabel('Nội dung JD').waitFor(); await page.waitForFunction(() => document.querySelector('textarea')?.value.includes('JD giả từ file'));
 assert.match(state.fileType,/multipart\/form-data; boundary=/i);
 await page.getByRole('button',{name:'Nhập từ link'}).click();
 await page.getByLabel('Link JD').fill('https://careerportalvinuni.talent.vn/job/example-123');
 page.once('dialog',d=>d.accept());
 await page.getByRole('button',{name:'Lấy nội dung JD'}).click();
 await page.waitForFunction(() => document.querySelector('textarea')?.value.includes('JD giả từ link'));
 assert.equal(state.urls.length,1);
 await create.click();
 await page.getByText(/Kết quả tạo chưa rõ/).waitFor();
 assert.equal(await page.getByRole('textbox',{name:/Tên vị trí/}).isDisabled(),true,'form locked while reconciling');
 assert.match(state.created.request_id,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,'client sends a v4 request id');
 await page.getByRole('button',{name:'Thử lại cùng yêu cầu'}).click();
 // Tạo xong là sinh tiêu chí luôn, có hộp thoại chặn màn hình báo đang chạy.
 await page.waitForURL('**/positions/position?tab=criteria');
 assert.equal(state.generateCalls,1,'criteria generation is triggered automatically after create');
 // Ca đã gặp: request sinh tiêu chí bị cắt ở proxy (504 HTML, không có detail)
 // nhưng backend vẫn lưu xong. Trang phải hỏi lại và đi tiếp, KHÔNG báo lỗi.
 assert.equal(await page.getByRole('dialog').count(),0,'no stuck dialog after a cut request');
 assert.equal(state.retried.request_id,state.created.request_id,'retry must reuse the request id');
 assert.equal(state.retried.jd_content,state.created.jd_content,'retry must not resend edited content');
 assert.equal('jd_language_code' in state.created,false,'ngôn ngữ JD không còn do client chọn'); assert.match(state.created.jd_content,/JD giả từ link/); assert.equal(state.created.department_id,'dept'); assert.equal(state.created.hiring_manager_user_id,'hm');
 await browser.close(); if(errors.length) throw Error(errors.join('\n'));
 console.log('Create page, required JD, mocked imports, auto criteria generation, optional create retry and replay-safe navigation: OK; all /v1 intercepted.');
})().catch(e=>{console.error(e);process.exit(1)});
