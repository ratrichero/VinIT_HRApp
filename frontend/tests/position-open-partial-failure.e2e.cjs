const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const base = process.env.HRA_E2E_BASE_URL;
if (!base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) throw new Error('Use a local disposable Next server.');
const json = (r,b,s=200) => r.fulfill({status:s,contentType:'application/json',body:JSON.stringify(b)});

// Regression for the reported bug: a brand-new position opened with
// "Không thể tải thông tin vị trí" because reading the criteria returned a bare
// 500 with no `detail`. The position itself was fine, so the page must open,
// keep the position visible, and say which part failed.
(async () => {
 const browser = await chromium.launch({executablePath:process.env.HRA_E2E_CHROMIUM_EXECUTABLE, args:process.env.HRA_E2E_CHROMIUM_ARGS ? JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS) : [],headless:true});
 const context = await browser.newContext({viewport:{width:1280,height:900}});
 await context.addInitScript(() => { localStorage.setItem('hra_access_token','synthetic-token'); localStorage.setItem('hra_locale','vi'); });
 const errors=[];
 await context.route('**/v1/**', async r => {
  const q = r.request(); const u = new URL(q.url()); const p = u.pathname; const method=q.method();
  if(p === '/v1/auth/me') return json(r,{user_id:'hr',display_name:'HR giả',system_roles:['HR_LEAD'],position_assignments:[{position_id:'position',position_role:'HR_RECRUITER'}]});
  if(p === '/v1/positions/position') return json(r,{position_id:'position',position_code:'REQ-IT-001',title:'Backend giả',status:'OPEN',created_by:'hr',created_at:'2026-11-05T00:00:00Z'});
  // The failure under test: criteria cannot be read at all.
  if(p === '/v1/criteria/position/position/versions') return r.fulfill({status:500,contentType:'text/plain',body:'Internal Server Error'});
  if(p === '/v1/positions/position/jd-versions') return json(r,[{jd_version_id:'jd',version_number:1,content_text:'JD giả',language_code:'en'}]);
  if(p === '/v1/positions/position/workspace') return json(r,{},404);
  if(p === '/v1/dashboard/position/position') return json(r,{total_applications:0,applications_processing:0,files_needing_hr_review:0,applications_by_status:{SHORTLIST:0}});
  // Badge "việc cần làm" trên header gọi work-queue ở mọi trang đã đăng nhập.
  if(p === '/v1/dashboard/work-queue') return json(r,{generated_at:'2026-11-19T03:00:00Z',summary:{},items:[]});
  // Chuông thông báo (arena) hỏi hộp thư ngay khi mount; hộp thư rỗng.
  if(p === '/v1/notifications') return json(r,{items:[],unread_count:0});
  if(p === '/v1/operations/position/position/active') return json(r,null);
  if(p === '/v1/positions') return json(r,[]);
  if(p === '/v1/departments') return json(r,[]);
  if(p === '/v1/rubric-library/families') return json(r,[]);
  errors.push(`Unexpected ${method} ${p}`); return json(r,{detail:'Unexpected request'},500);
 });
 const page=await context.newPage(); page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/positions/position?tab=criteria');

 // The position must be readable: title present, no blocking error page.
 await page.getByText('Backend giả').first().waitFor({timeout:15000});
 assert.equal(await page.getByText('Không thể tải thông tin vị trí',{exact:false}).count(),0,
   'a broken criteria call must not claim the position could not be loaded');
 // ...and the partial failure must be named, not hidden.
 const warning = page.getByText(/Vị trí đã mở nhưng/);
 await warning.waitFor();
 assert.match(await warning.innerText(), /tiêu chí/);
 // The criteria tab is still usable (it shows the generate action).
 assert.ok(await page.getByRole('button',{name:/Đề xuất tiêu chí AI|Tạo phiên bản tiêu chí mới/}).count() > 0,
   'criteria controls stay available so HR can retry generation');
 await browser.close(); if(errors.length) throw Error(errors.join('\n'));
 console.log('Position opens and names the failed section when criteria cannot be read: OK; all /v1 intercepted.');
})().catch(e=>{console.error(e);process.exit(1)});
