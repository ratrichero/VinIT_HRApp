const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const base = process.env.HRA_E2E_BASE_URL;
if (!base || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) throw Error('Use local Next server only');
const json=(r,body,status=200)=>r.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.HRA_E2E_CHROMIUM_EXECUTABLE,args:JSON.parse(process.env.HRA_E2E_CHROMIUM_ARGS||'[]')});
 for(const width of [1280,390]) {
  let revoked=false; const errors=[];
  const c=await browser.newContext({viewport:{width,height:900}});
  await c.addInitScript(()=>{localStorage.setItem('hra_access_token','test');localStorage.setItem('hra_locale','vi');});
  await c.route('**/v1/**', async r=>{const p=new URL(r.request().url()).pathname;
   if(p==='/v1/auth/me') return json(r,{user_id:'hm',display_name:'HM',system_roles:['HIRING_MANAGER'],position_assignments:[]});
   if(p==='/v1/shortlist/shared-with-me') return json(r,[]);
   if(p==='/v1/scorecards/reminders') return json(r,[]);
   if(p==='/v1/notifications') return json(r,{items:[],unread_count:0});
   if(p==='/v1/dashboard/work-queue') return json(r,[]);
   if(p==='/v1/shortlist/share-1') return revoked ? json(r,{detail:'Đã thu hồi'},403) : json(r,{share_id:'share-1',position_id:'p1',position:{title:'Vị trí giả'},status:'ACTIVE',allow_cv_view:false,applications:[{application_id:'a',candidate_name:'An giả'},{application_id:'b',candidate_name:'Bình giả'}],feedback:[]});
   if(p==='/v1/applications/a') return json(r,{application_id:'a',position_id:'p1',can_view_cv:false,can_view_assessment_evidence:false,latest_assessment:null,documents:[]});
   if(p==='/v1/applications/b') return json(r,{application_id:'b',position_id:'p1',can_view_cv:false,can_view_assessment_evidence:false,latest_assessment:null,documents:[]});
   if(p==='/v1/scorecards/share/share-1') return json(r,['a','b'].map((id,i)=>({scorecard_id:`s${id}`,application_id:id,status:'IN_PROGRESS',revision:1,due_at:'2031-01-01T00:00:00Z',can_edit:true,waiting_for_assessment:false,criteria_version_id:'criteria',assessment_id:'assessment',strengths:'',concerns:'',overall_recommendation:null,criteria:[{criterion_id:`criterion${i}`,name:'Python',description:'Test',rating:null,insufficient_evidence:false}]})));
   errors.push(`Unexpected ${p}`); return json(r,{},500);
  });
  const page=await c.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/shortlist?share=share-1'); await page.waitForURL('**/shortlist/share-1');
  await page.getByRole('heading',{name:/Không gian đánh giá shortlist/}).waitFor();
  await page.getByLabel('Điểm mạnh').filter({visible:true}).fill('Nháp của An');
  await page.getByRole('button',{name:'Bình giả'}).click();
  await page.getByLabel('Điểm mạnh').filter({visible:true}).fill('Nháp của Bình');
  await page.getByRole('button',{name:'An giả'}).click();
  assert.equal(await page.getByLabel('Điểm mạnh').filter({visible:true}).inputValue(),'Nháp của An');
  // Evidence sits beside the scorecard but stays share-scoped: a summary-only share shows no CV.
  await page.getByRole('button',{name:'CV và bằng chứng đánh giá'}).click();
  await page.getByText('Shortlist này không cho phép xem CV gốc.').first().waitFor();
  await page.getByRole('button',{name:'CV và bằng chứng đánh giá'}).click();
  assert.match(await page.getByRole('link',{name:'Xem hồ sơ ứng viên'}).getAttribute('href'),/share=share-1/);
  page.once('dialog',d=>d.dismiss()); await page.getByRole('link',{name:'Quay lại shortlist'}).click();
  assert.match(page.url(),/shortlist\/share-1/);
  // The workspace only refetches after a real absence (>=30s hidden), so advance the clock.
  revoked=true; await page.evaluate(() => {
    const realNow = Date.now.bind(Date);
    let offset = 0;
    Date.now = () => realNow() + offset;
    document.dispatchEvent(new Event('visibilitychange'));
    offset = 40_000;
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.getByText('Quyền truy cập shortlist không còn hoặc shortlist không tồn tại.').waitFor();
  assert.equal(await page.getByText('An giả').count(),0);
  if(errors.length) throw Error(errors.join('\n')); await c.close();
 }
 await browser.close(); console.log('Shortlist workspace desktop/mobile, drafts, evidence gate, deep link and revoked access: OK; APIs mocked');
})().catch(e=>{console.error(e);process.exit(1)});
