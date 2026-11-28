const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const base = process.env.HRA_E2E_BASE_URL;
if (!base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) throw Error('Use local Next server only');
const json = (r, body, status=200) => r.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
(async () => {
 const browser = await chromium.launch({executablePath:process.env.HRA_E2E_CHROMIUM_EXECUTABLE,args:JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS || '[]')});
 for (const width of [1280, 390]) {
  const c=await browser.newContext({viewport:{width,height:900}}); const errors=[];
  await c.addInitScript(() => {localStorage.setItem('hra_access_token','test');localStorage.setItem('hra_locale','vi');});
  await c.route('**/v1/**', async r=>{const p=new URL(r.request().url()).pathname;
   if(p==='/v1/auth/me') return json(r,{user_id:'hm',display_name:'HM',system_roles:['HIRING_MANAGER'],position_assignments:[]});
   if(p==='/v1/scorecards/reminders') return json(r,[]);
   if(p==='/v1/notifications') return json(r,{items:[],unread_count:0});
   if(p==='/v1/dashboard/work-queue') return json(r,[]);
   if(p==='/v1/shortlist/shared-with-me') return json(r,[{share_id:'one',position_id:'p1',position:{title:'Synthetic Alpha',position_code:'A'},direction:'received',status:'ACTIVE'},{share_id:'two',position_id:'p2',position:{title:'Synthetic Beta',position_code:'B'},direction:'received',status:'ACTIVE'}]);
   errors.push(p);return json(r,{},500);
  });
  const page=await c.newPage(); page.on('pageerror', e=>errors.push(e.message));
  await page.goto(base+'/shortlist?position=p1');
  await page.getByText('Đang lọc chia sẻ theo vị trí này.',{exact:false}).waitFor();
  assert.equal(await page.getByText('Synthetic Beta',{exact:true}).filter({visible:true}).count(),0);
  await page.getByRole('button',{name:'Xóa bộ lọc'}).click();
  await page.getByText('Synthetic Beta',{exact:true}).filter({visible:true}).waitFor();
  assert.equal(new URL(page.url()).search,'');
  await c.close(); if(errors.length) throw Error(errors.join('\n'));
 }
 await browser.close(); console.log('Shortlist position filter desktop/mobile: OK; all /v1 intercepted');
})().catch(e=>{console.error(e);process.exit(1)});
