/* Verify learner history navigation, filtering, empty states and readonly UI.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */
import assert from "node:assert/strict";
import { before,after,test } from "node:test";
import { chromium } from "playwright";
import { mkdir,readFile } from "node:fs/promises";
const base=process.env.US016_UI_BASE_URL,id="11111111-1111-4111-8111-111111111111",url=`/learners/${id}/history`;
let browser;
before(async()=>{browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||"chrome"});});
after(async()=>browser?.close());
const fixture=()=>({learner:{id,name:"Māia Example"},sessions:[24,23,22,21,20].map((d,i)=>({session_id:String(d),session_date:`2026-10-${d}`,status:i%2===0?"Present":"Absent"})),present_count:3,total_count:5,has_records:true,start_date:null,end_date:null});
async function screen(t,{role="coordinator",mobile=false}={}){
  const context=await browser.newContext({viewport:mobile?{width:360,height:800}:{width:1280,height:900}});t.after(()=>context.close());
  if(role)await context.addCookies([{name:"ako_session",value:`ui-${role}`,url:base,httpOnly:true,sameSite:"Lax"}]);
  await context.route("**/api/user/**",r=>r.fulfill({json:r.request().url().endsWith("/learners")?[{id,first_name:"Māia",family_name:"Example",is_active:true,created_at:"2026-10-20T00:00:00Z"}]:{user_id:id,display_name:"Staff",role,expires_at:new Date(Date.now()+1800000).toISOString()},headers:{"X-Session-Expires-At":new Date(Date.now()+1800000).toISOString()}}));
  const state={requests:[],status:200,data:fixture(),detail:"private details",delay:false,release:null};
  await context.route("**/api/staff/access/learners/*/attendance-history*",async r=>{
    const request=new URL(r.request().url());state.requests.push({method:r.request().method(),query:request.search});
    if(state.delay)await new Promise(resolve=>state.release=resolve);
    const data=structuredClone(state.data),from=request.searchParams.get("start_date"),to=request.searchParams.get("end_date");
    data.sessions=data.sessions.filter(row=>(!from||row.session_date>=from)&&(!to||row.session_date<=to));data.total_count=data.sessions.length;data.present_count=data.sessions.filter(r=>r.status==="Present").length;
    await r.fulfill({status:state.status,json:state.status===200?data:{detail:state.detail}});
  });
  const page=await context.newPage();const errors=[];page.on("pageerror",e=>errors.push(e.message));t.after(()=>assert.deepEqual(errors,[]));
  return {page,state,context};
}
const button=(p,name)=>p.getByRole("button",{name,exact:true});
async function open(page){await page.goto(base+url);await page.getByText("Present 3 of 5",{exact:true}).waitFor();}
for(const role of ["coordinator","teacher"])test(`${role} opens history from learner list and sees readonly 3 of 5`,async t=>{
  const {page,state}=await screen(t,{role});await page.goto(base+"/learners");await page.getByRole("link",{name:"Attendance history for Māia Example",exact:true}).click();
  await page.getByText("Present 3 of 5",{exact:true}).waitFor();assert.equal(await page.locator("tbody tr").count(),5);
  assert.deepEqual(await page.locator("tbody th").allTextContents(),[24,23,22,21,20].map(d=>`2026-10-${d}`));
  assert.equal(await page.getByRole("checkbox").count(),0);assert.equal(await button(page,"Save").count(),0);assert.ok(state.requests.every(r=>r.method==="GET"));
  await page.getByRole("link",{name:"Back to learners",exact:true}).click();await page.waitForURL(base+"/learners");
});
test("inclusive range updates list and summary, reset restores all",async t=>{
  const {page,state}=await screen(t);await open(page);await page.getByLabel("Start date",{exact:true}).fill("2026-10-21");await page.getByLabel("End date",{exact:true}).fill("2026-10-23");await button(page,"Apply dates").click();
  await page.getByText("Present 1 of 3",{exact:true}).waitFor();assert.equal(await page.locator("tbody tr").count(),3);assert.equal(state.requests.at(-1).query,"?start_date=2026-10-21&end_date=2026-10-23");
  await button(page,"Reset dates").click();await page.getByText("Present 3 of 5",{exact:true}).waitFor();assert.equal(await page.getByLabel("Start date",{exact:true}).inputValue(),"");
});
test("one-sided same-day and empty date ranges",async t=>{
  const {page}=await screen(t);await open(page);await page.getByLabel("Start date",{exact:true}).fill("2026-10-24");await button(page,"Apply dates").click();await page.getByText("Present 1 of 1",{exact:true}).waitFor();
  await page.getByLabel("End date",{exact:true}).fill("2026-10-24");await button(page,"Apply dates").click();await page.getByText("Present 1 of 1",{exact:true}).waitFor();
  await page.getByLabel("Start date",{exact:true}).fill("2026-11-01");await page.getByLabel("End date",{exact:true}).fill("");await button(page,"Apply dates").click();await page.getByText("No class sessions in this date range",{exact:true}).waitFor();await page.getByText("Present 0 of 0",{exact:true}).waitFor();
});
test("invalid range prevents request and focuses end date",async t=>{
  const {page,state}=await screen(t);await open(page);await page.getByLabel("Start date",{exact:true}).fill("2026-10-25");await page.getByLabel("End date",{exact:true}).fill("2026-10-20");await button(page,"Apply dates").click();await page.getByText("Start date must be before end date",{exact:true}).waitFor();assert.equal(state.requests.length,1);assert.equal(await page.locator("#history-end").evaluate(e=>e===document.activeElement),true);
});
test("unrecorded learner has exact empty state",async t=>{const {page,state}=await screen(t);state.data={...fixture(),sessions:[],total_count:0,present_count:0,has_records:false};await page.goto(base+url);await page.getByText("No attendance recorded yet",{exact:true}).waitFor();assert.equal(await page.locator("table").count(),0);});
for(const [status,message] of [[403,"You do not have permission"],[404,"Learner not found"]])test(`safe ${status} without stale data`,async t=>{const {page,state}=await screen(t);await open(page);state.status=status;await button(page,"Apply dates").click();await page.getByText(message,{exact:true}).waitFor();assert.equal(await page.locator("table").count(),0);assert.equal(await page.getByText("private details",{exact:true}).count(),0);});
test("service failure retains filters and retries",async t=>{const {page,state}=await screen(t);await open(page);state.status=503;await page.getByLabel("Start date",{exact:true}).fill("2026-10-24");await button(page,"Apply dates").click();await page.getByText("Attendance history could not be loaded. Please try again.",{exact:true}).waitFor();state.status=200;await button(page,"Try again").click();await page.getByText("Present 1 of 1",{exact:true}).waitFor();});
test("expired API session redirects to login",async t=>{const {page,state}=await screen(t);state.status=401;await page.goto(base+url);await page.waitForURL(base+"/");});
test("anonymous direct history address redirects",async t=>{const {page,state}=await screen(t,{role:null});await page.goto(base+url);await page.waitForURL(base+"/");assert.equal(state.requests.length,0);});
test("loading disables filters and hides stale results",async t=>{const {page,state}=await screen(t);await open(page);state.delay=true;await button(page,"Apply dates").click();await page.getByText("Loading attendance history…",{exact:true}).waitFor();assert.equal(await button(page,"Apply dates").isDisabled(),true);assert.equal(await page.locator("table").count(),0);state.release();await page.getByText("Present 3 of 5",{exact:true}).waitFor();});
test("mobile, large names and accessible labels use Ako controls",async t=>{
  const {page,state}=await screen(t,{mobile:true});state.data.learner.name="Māia "+"Long".repeat(50);await open(page);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.ok(await page.locator("tbody td").first().evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=18));
  await page.addScriptTag({path:new URL("../node_modules/axe-core/axe.min.js",import.meta.url).pathname});const results=await page.evaluate(async()=>axe.run(document,{runOnly:{type:"tag",values:["wcag2a","wcag2aa"]}}));assert.deepEqual(results.violations.map(r=>r.id),[]);
  const dir=process.env.UI_SCREENSHOT_DIR;if(dir){await mkdir(dir,{recursive:true});await page.screenshot({path:dir+"/history-mobile.png",fullPage:true});}
});
test("calendar opens from field and icon; empty dates are dark",async t=>{
  const {page}=await screen(t);await open(page);const input=page.locator("#history-start");await input.evaluate(e=>{e.showPicker=()=>{window.pickerCalls=(window.pickerCalls||0)+1;};});
  await input.click({position:{x:10,y:15}});const box=await input.boundingBox();await input.click({position:{x:box.width-15,y:15}});assert.equal(await page.evaluate(()=>window.pickerCalls),2);assert.equal(await input.getAttribute("data-empty"),"true");assert.equal(await input.evaluate(e=>getComputedStyle(e).color),await input.evaluate(e=>{const probe=document.createElement("span");probe.style.color="var(--slate)";e.parentElement.append(probe);const color=getComputedStyle(probe).color;probe.remove();return color;}));
});
