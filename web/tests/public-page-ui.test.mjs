import assert from "node:assert/strict";
import { before,after,test } from "node:test";
import { chromium } from "playwright";
import axe from "axe-core";
import { mkdir } from "node:fs/promises";
const base=process.env.US009_BASE_URL;
if(!base)throw new Error("Run npm run test:public-ui after npm run build");
let browser;
before(async()=>{browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||"chrome",headless:true})});
after(async()=>{await browser?.close()});
async function screen(t,{mobile=false,role=null,javascript=true}={}){
  const context=await browser.newContext({viewport:mobile?{width:360,height:800}:{width:1280,height:900},javaScriptEnabled:javascript,isMobile:mobile,hasTouch:mobile});t.after(()=>context.close());
  if(role)await context.addCookies([{name:"ako_session",value:`ui-${role}`,url:base,httpOnly:true,sameSite:"Lax"}]);
  const page=await context.newPage(),errors=[],requests=[];
  page.on("pageerror",e=>errors.push(e.message));page.on("request",req=>{if(req.url().includes("/api/"))requests.push(req.url())});t.after(()=>assert.deepEqual(errors,[]));
  return{page,context,requests};
}
async function home(page){const response=await page.goto(base);assert.equal(response.status(),200);await page.getByRole("heading",{name:"English classes",exact:true}).waitFor();}
async function forms(page){await page.getByLabel("Username",{exact:true}).waitFor();await page.getByLabel("Name (required)",{exact:true}).waitFor();}

for(const role of [null,"teacher","coordinator"])test(`class information is public for ${role||"anonymous visitor"}`,async t=>{
  const{page,requests}=await screen(t,{role});await home(page);await forms(page);
  const facts=page.locator("#class-information");for(const text of ["Class day","Class time","Venue address","Contact","Monday","10:00 am to 12:00 pm"])await facts.getByText(text,{exact:true}).waitFor();
  assert.ok(await facts.getByRole("link",{name:"Send an enquiry",exact:true}).getAttribute("href"));assert.equal(requests.length,0);
});
test("details are grouped before enquiry and staff login",async t=>{
  const{page}=await screen(t);await home(page);
  const position=await page.evaluate(()=>["class-information","enquiries","staff-login"].map(id=>document.getElementById(id).getBoundingClientRect().top));assert.ok(position[0]<position[1]&&position[1]<position[2]);
  await page.getByText("These are sample details. Please confirm before visiting.",{exact:true}).waitFor();
});
test("360px layout is readable with no horizontal scroll",async t=>{
  const{page}=await screen(t,{mobile:true});await home(page);await forms(page);
  const layout=await page.evaluate(()=>({width:innerWidth,body:document.documentElement.scrollWidth,font:getComputedStyle(document.body).fontSize,core:[...document.querySelectorAll('#class-information dd')].map(e=>({size:getComputedStyle(e).fontSize,width:e.getBoundingClientRect().width}))}));
  assert.ok(layout.body<=layout.width);assert.ok(parseFloat(layout.font)>=18);assert.ok(layout.core.every(e=>parseFloat(e.size)>=18));
  if(process.env.UI_SCREENSHOT_DIR){await mkdir(process.env.UI_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:process.env.UI_SCREENSHOT_DIR+"/club-mobile.png",fullPage:true});}
});
test("long venue and contact text wrap inside narrow screens",async t=>{
  const{page}=await screen(t,{mobile:true});await home(page);
  await page.locator('#class-information dd').nth(2).evaluate(e=>e.textContent='Māoriāēīōū'.repeat(24));await page.locator('#class-information dd a').evaluate(e=>e.textContent='long'.repeat(60)+'@example.test');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
});
test("plain English sentences are at most fifteen words",async t=>{
  const{page}=await screen(t);await home(page);await forms(page);
  const texts=await page.locator('h1,h2,h3,p,dt,dd,label,legend,button').allTextContents();
  for(const text of texts)for(const sentence of text.split(/[.!?]+(?:\s|$)/u))assert.ok(sentence.trim().split(/\s+/u).filter(Boolean).length<=15,sentence);
});
test("class information survives JavaScript being disabled",async t=>{
  const{page,requests}=await screen(t,{javascript:false});await home(page);await page.getByText("Monday",{exact:true}).waitFor();
  assert.equal(await page.locator('input[name="username"]').count(),0);assert.equal(await page.locator('input[name="contact"]').count(),0);assert.equal(requests.length,0);
  await page.getByText('Turn on JavaScript to send an enquiry.',{exact:true}).waitFor();
});
test("no unreviewed greeting, learner photos or private menu is published",async t=>{
  const{page}=await screen(t);await home(page);await forms(page);
  assert.equal(await page.getByText("Kia ora",{exact:true}).count(),0);assert.equal(await page.locator('img,video').count(),0);
  assert.equal(await page.getByRole('link',{name:'Learners',exact:true}).count(),0);assert.equal(await page.getByRole('link',{name:'Attendance reports',exact:true}).count(),0);
});
test("keyboard skip link moves focus to class information",async t=>{
  const{page}=await screen(t);await home(page);await page.keyboard.press('Tab');assert.equal(await page.locator(':focus').textContent(),'Skip to class information');await page.keyboard.press('Enter');assert.equal(await page.locator(':focus').getAttribute('id'),'class-information');
});
test("public menu links reach enquiry and staff sections",async t=>{
  const{page}=await screen(t);await home(page);await page.getByRole('navigation',{name:'Public menu'}).getByRole('link',{name:'Ask about classes',exact:true}).click();await page.waitForURL('**/#enquiries');
  await page.getByRole('navigation',{name:'Public menu'}).getByRole('link',{name:'Staff login',exact:true}).click();await page.waitForURL('**/#staff-login');await page.getByLabel('Username',{exact:true}).waitFor();
});
test("existing enquiry consent and submission still work",async t=>{
  const{page}=await screen(t);let body;
  await page.route('**/api/user/enquiries',async route=>{body=route.request().postDataJSON();await route.fulfill({status:201,json:{message:'Thank you, the club will contact you'}})});
  await home(page);await forms(page);await page.getByLabel('Name (required)',{exact:true}).fill('Test Visitor');await page.getByLabel('Contact (required)',{exact:true}).fill('visitor@example.test');
  await page.getByRole('button',{name:'Send enquiry',exact:true}).click();await page.getByText('Please consent to being contacted by the club',{exact:true}).waitFor();assert.equal(body,undefined);
  await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Send enquiry',exact:true}).click();await page.getByText('Thank you, the club will contact you',{exact:true}).waitFor();assert.equal(body.consent,true);
});
test("staff login errors remain on the same public URL",async t=>{
  const{page}=await screen(t);await page.route('**/api/user/login',route=>route.fulfill({status:401,json:{detail:'bad'}}));await home(page);await forms(page);
  await page.getByLabel('Username',{exact:true}).fill('wrong');await page.getByLabel('Password',{exact:true}).fill('wrong');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.getByText('Username or password is incorrect',{exact:true}).waitFor();assert.equal(new URL(page.url()).pathname,'/');
});
for(const role of ['teacher','coordinator'])test(`${role} login still reaches its role home`,async t=>{
  const{page,context}=await screen(t);
  await page.route('**/api/user/login',async route=>{await context.addCookies([{name:'ako_session',value:`ui-${role}`,url:base,httpOnly:true,sameSite:'Lax'}]);await route.fulfill({json:{sessionid:'fixture',user_id:'11111111-1111-4111-8111-111111111111',role,expires_at:new Date(Date.now()+1800000).toISOString()}})});
  await page.route('**/api/user/session',route=>route.fulfill({json:{user_id:'11111111-1111-4111-8111-111111111111',display_name:'Test staff',role,expires_at:new Date(Date.now()+1800000).toISOString()},headers:{'X-Session-Expires-At':new Date(Date.now()+1800000).toISOString()}}));
  await home(page);await forms(page);await page.getByLabel('Username',{exact:true}).fill('test');await page.getByLabel('Password',{exact:true}).fill('test');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL(base+'/'+role);await page.getByRole('navigation',{name:role==='teacher'?'Teacher menu':'Coordinator menu'}).waitFor();
});
for(const path of ['/missing-public-page','/public/unknown/deep-page'])test(`friendly HTTP 404 for ${path}`,async t=>{
  const{page}=await screen(t,{mobile:true});const response=await page.goto(base+path);assert.equal(response.status(),404);await page.getByRole('heading',{name:'Page not found',exact:true}).waitFor();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.getByRole('link',{name:'Go to home page',exact:true}).click();await page.waitForURL(base+'/');await page.getByRole('heading',{name:'English classes',exact:true}).waitFor();
});
for(const path of ['/','/missing-public-page'])test(`axe finds no accessibility violations on ${path}`,async t=>{
  const{page}=await screen(t,{mobile:true});await page.goto(base+path);if(path==='/')await forms(page);
  await page.addScriptTag({content:axe.source});const result=await page.evaluate(async()=> (await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})).violations.map(v=>({id:v.id,help:v.help,nodes:v.nodes.map(n=>n.target)})));assert.deepEqual(result,[]);
});
