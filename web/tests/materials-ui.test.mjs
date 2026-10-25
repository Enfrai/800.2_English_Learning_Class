import assert from 'node:assert/strict';
import { before,after,test } from 'node:test';
import { chromium } from 'playwright';
const base=process.env.US013_UI_BASE_URL;
if(!base)throw new Error('Run npm run test:materials-ui after npm run build');
let browser;
before(async()=>{browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'chrome',headless:true})});
after(async()=>{await browser?.close()});
const mid='33333333-3333-4333-8333-333333333333';
async function screen(t,{cookie='valid',message='',files=[{id:mid,file_name:'Te reo Māori.pdf',file_size:12}],status=200}={}){
  const context=await browser.newContext({viewport:{width:360,height:800}});
  t.after(()=>context.close());
  if(cookie)await context.addCookies([{name:'ako_materials',value:cookie,url:base,httpOnly:true,sameSite:'Lax'}]);
  let failed=status!==200;
  await context.route('**/api/access/learner/materials',route=>route.fulfill({status:failed?status:200,json:failed?{detail:'unavailable'}:{session_date:'2026-10-26',materials:files,message}}));
  const page=await context.newPage();
  const errors=[];page.on('pageerror',error=>errors.push(error.message));t.after(()=>assert.deepEqual(errors,[]));
  await page.goto(base+'/materials');
  return {page,context,recover:()=>{failed=false}};
}
test('unregistered visitor redirects to sign-in without file metadata',async t=>{
  const {page}=await screen(t,{cookie:null});
  await page.waitForURL('**/sign-in');
  assert.equal(await page.getByText('Te reo Māori.pdf',{exact:true}).count(),0);
  await page.getByText('Please scan the class QR code to sign in.').waitFor();
});
test('invalid or expired cookie also redirects at the server',async t=>{
  const {page}=await screen(t,{cookie:'expired'});await page.waitForURL('**/sign-in');
  assert.equal(await page.getByRole('link',{name:/Download/}).count(),0);
});
test('shared files retain macrons and original download name',async t=>{
  const {page,context}=await screen(t);
  await page.getByText('Te reo Māori.pdf',{exact:true}).first().waitFor();
  await context.route(`**/api/access/learner/materials/${mid}/download`,route=>route.fulfill({body:'%PDF-content',contentType:'application/pdf',headers:{'Content-Disposition':"attachment; filename*=UTF-8''Te%20reo%20M%C4%81ori.pdf"}}));
  const downloading=page.waitForEvent('download');await page.getByRole('link',{name:'Download Te reo Māori.pdf'}).click();
  assert.equal((await downloading).suggestedFilename(),'Te reo Māori.pdf');
});
for(const message of ['Materials will be added soon','No materials for today'])test(message,async t=>{
  const {page}=await screen(t,{message,files:[]});await page.getByText(message,{exact:true}).waitFor();
  assert.equal(await page.getByRole('link',{name:/Download/}).count(),0);
});
test('service failure can be retried without a new sign-in',async t=>{
  const {page,recover}=await screen(t,{status:503});await page.getByRole('alert').filter({hasText:'Materials are not available'}).waitFor();recover();
  await page.getByRole('button',{name:'Try again'}).click();await page.getByText('Te reo Māori.pdf',{exact:true}).first().waitFor();
});
test('long filenames fit 360px, body is 18px and links at least 44px',async t=>{
  const name='Māori_'.repeat(30)+'.pdf';const {page}=await screen(t,{files:[{id:mid,file_name:name,file_size:12}]});
  await page.getByText(name,{exact:true}).first().waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.ok(await page.locator('body').evaluate(el=>parseFloat(getComputedStyle(el).fontSize))>=18);
  assert.ok((await page.getByRole('link',{name:/Download/}).boundingBox()).height>=44);
});
test('client expiry hides files and asks learner to scan again',async t=>{
  const {page}=await screen(t,{status:401});await page.getByText('Please scan a class code and sign in again.').waitFor();
  assert.equal(await page.getByRole('link',{name:/Download/}).count(),0);
});
test('successful QR sign-in opens materials without a staff account',async t=>{
  const context=await browser.newContext({viewport:{width:360,height:800}});t.after(()=>context.close());
  await context.route('**/api/access/checkin/test',route=>route.fulfill({json:{session_date:'2026-10-26'}}));
  await context.route('**/api/access/checkin/test/sign-in',async route=>{
    await context.addCookies([{name:'ako_materials',value:'valid',url:base,httpOnly:true,sameSite:'Lax'}]);
    return route.fulfill({status:201,json:{message:'You are signed in',session_date:'2026-10-26'}});
  });
  await context.route('**/api/access/learner/materials',route=>route.fulfill({json:{session_date:'2026-10-26',materials:[],message:'No materials for today'}}));
  const page=await context.newPage();await page.goto(base+'/sign-in/test');
  await page.getByLabel('First name').fill('Aroha');await page.getByLabel('Family name').fill('Test');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByText('You are signed in',{exact:true}).waitFor();
  await page.getByRole('link',{name:'Lesson materials',exact:true}).click();
  await page.getByText('No materials for today',{exact:true}).waitFor();
  assert.equal((await context.cookies()).some(cookie=>cookie.name==='ako_session'),false);
});

test('teacher can link a lesson and sees a failed save instead of a false success',async t=>{
  const sid='22222222-2222-4222-8222-222222222222';
  const context=await browser.newContext();t.after(()=>context.close());
  await context.addCookies([{name:'ako_session',value:'teacher',url:base,httpOnly:true,sameSite:'Lax'}]);
  await context.route('**/api/user/**',route=>route.fulfill({json:route.request().url().endsWith('/learners')?[]:{user_id:'11111111-1111-4111-8111-111111111111',display_name:'Test teacher',role:'teacher',expires_at:new Date(Date.now()+1800000).toISOString()},headers:{'X-Session-Expires-At':new Date(Date.now()+1800000).toISOString()}}));
  await context.route('**/api/staff/lesson/lessons',route=>route.fulfill({json:[{id:mid,title:'Transport lesson'}]}));
  let saved=null,fail=false;
  await context.route(`**/api/staff/access/sessions/${sid}/lesson`,route=>{
    if(route.request().method()==='PUT'){
      if(fail)return route.fulfill({status:503,json:{detail:'Unavailable'}});
      saved=route.request().postDataJSON().lesson_id;
    }
    return route.fulfill({json:{lesson_id:saved}});
  });
  await context.route(`**/api/staff/access/sessions/${sid}/attendance`,route=>route.fulfill({json:{session_date:'2026-10-26',editable:true,present_count:0,records:[],corrected_learner_ids:[]}}));
  const page=await context.newPage();await page.goto(base+`/sessions/${sid}/attendance`);
  await page.getByLabel('Lesson',{exact:true}).selectOption(mid);
  await page.getByRole('button',{name:'Save lesson',exact:true}).click();
  await page.getByText('Lesson saved for this class.').waitFor();assert.equal(saved,mid);
  fail=true;await page.getByLabel('Lesson',{exact:true}).selectOption('');
  await page.getByRole('button',{name:'Save lesson',exact:true}).click();
  await page.getByText('The lesson could not be saved. Please try again.').waitFor();assert.equal(saved,mid);
});
