/* Verify QR lifecycle, A4 printing and automatic attendance in a real browser.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */
import assert from "node:assert/strict";
import { before,after,test } from "node:test";
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
const base=process.env.US011_UI_BASE_URL;
if(!base)throw new Error("Run npm run test:checkin-ui after npm run build");
const sid="22222222-2222-4222-8222-222222222222",lid="33333333-3333-4333-8333-333333333333",today="2026-10-26";
let browser;
before(async()=>{browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||"chrome",headless:true})});after(async()=>{await browser?.close()});
async function screen(t,{role="teacher",past=false,mobile=false,initial="not-open"}={}){
  const context=await browser.newContext({viewport:mobile?{width:360,height:900}:{width:1280,height:1000}});t.after(()=>context.close());
  if(role)await context.addCookies([{name:"ako_session",value:`ui-${role}`,url:base,httpOnly:true,sameSite:"Lax"}]);
  await context.addInitScript(()=>{window.print=function(){window.parent.__printed=(window.parent.__printed||0)+1;};});
  const day=past?"2026-10-24":today;
  const state={kind:initial,opens:0,closes:0,reads:0,fail:false,busy:false,release:null,token:"x".repeat(43),expires:new Date(Date.now()+4*3600000).toISOString(),present:false,late:null,delayRead:false,failAttendance:false,delayAttendance:false,attendanceLate:null,attendanceReads:0};
  const windowData=()=>({state:state.kind,session_date:day,can_open:!past,opened_at:new Date().toISOString(),expires_at:state.expires,sign_in_url:state.kind==="open"?`http://192.168.1.20:8080/sign-in/${state.token}`:null,qr_svg:state.kind==="open"?'<svg xmlns="http://www.w3.org/2000/svg" width="90mm" height="90mm" viewBox="0 0 90 90"><path d="M10 10h70v70H10z" fill="black"/></svg>':null});
  await context.route("**/api/user/**",route=>route.fulfill({json:route.request().url().endsWith("/learners")?[{id:lid,first_name:"Māia",family_name:"Test"}]:{user_id:sid,display_name:"Test teacher",role,expires_at:new Date(Date.now()+1800000).toISOString()},headers:{"X-Session-Expires-At":new Date(Date.now()+1800000).toISOString()}}));
  await context.route("**/api/staff/lesson/**",route=>route.fulfill({json:[]}));
  await context.route("**/api/staff/access/sessions/**",async route=>{
    const request=route.request(),path=new URL(request.url()).pathname,method=request.method();
    if(path.endsWith("/check-in")){
      if(method==="GET"){state.reads++;const snapshot=windowData();if(state.delayRead)await new Promise(resolve=>state.late=resolve);return route.fulfill(state.fail?{status:503,json:{detail:"unavailable"}}:{json:snapshot});}
      if(state.busy&&method==="POST")await new Promise(resolve=>state.release=resolve);
      if(state.fail)return route.fulfill({status:503,json:{detail:"unavailable"}});
      if(method==="POST"){state.opens++;state.kind="open";}
      if(method==="DELETE"){state.closes++;state.kind="closed";}
      return route.fulfill({json:windowData()});
    }
    if(path.endsWith("/attendance")){
      if(method==="GET")state.attendanceReads++;
      if(method==="GET" && state.failAttendance)return route.fulfill({status:503,json:{detail:"unavailable"}});
      if(method==="POST")state.present=true;
      const previous=state.present;
      if(method==="GET" && state.delayAttendance)await new Promise(resolve=>state.attendanceLate=resolve);
      return route.fulfill({json:method==="POST"?{present_count:1,attendance:{learner_id:lid,status:"present",recorded_by:sid,recorded_at:new Date().toISOString()}}:{session_date:day,editable:!past,present_count:previous?1:0,records:previous?[{learner_id:lid,status:"present",recorded_by:sid,recorded_at:new Date().toISOString()}]:[],corrected_learner_ids:[]}});
    }
    if(path.endsWith("/lesson"))return route.fulfill({json:{lesson_id:null}});
    if(path.endsWith("/corrections"))return route.fulfill({json:[]});
    return route.fulfill({json:{id:sid,session_date:day,today,lesson_id:null,lesson_title:null,lesson_unavailable:false,attendance_count:0,present_count:0,can_delete:true}});
  });
  const page=await context.newPage(),errors=[];page.on("pageerror",e=>errors.push(e.message));t.after(()=>assert.deepEqual(errors,[]));
  return{page,state};
}
const button=(page,name)=>page.getByRole("button",{name,exact:true});
async function open(page){await page.goto(base+`/sessions/${sid}`);await button(page,"Open check-in").waitFor();}
async function show(page){await button(page,"Open check-in").click();await page.getByText("Check-in is open",{exact:true}).waitFor();}

test("today's classroom has a QR check-in entry",async t=>{const{page}=await screen(t);await open(page);await page.getByRole("heading",{name:"QR check-in",exact:true}).waitFor();});
test("opening shows code and session link within two seconds",async t=>{const{page,state}=await screen(t);await open(page);const start=Date.now();await show(page);await page.getByAltText("QR code for class sign-in").waitFor();assert.ok(Date.now()-start<2000);assert.equal(state.opens,1);assert.ok((await page.getByRole("link",{name:/192.168.1.20/}).getAttribute("href")).endsWith(state.token));});
test("refreshing keeps the existing code without another POST",async t=>{const{page,state}=await screen(t);await open(page);await show(page);await page.reload();await page.getByAltText("QR code for class sign-in").waitFor();assert.equal(state.opens,1);});
test("close removes the code and its sign-in link",async t=>{const{page,state}=await screen(t);await open(page);await show(page);await button(page,"Close check-in").click();await page.getByText("Check-in is closed",{exact:true}).waitFor();assert.equal(await page.getByAltText("QR code for class sign-in").count(),0);assert.equal(state.closes,1);});
test("past classrooms cannot open check-in",async t=>{const{page}=await screen(t,{past:true});await open(page);assert.equal(await button(page,"Open check-in").isDisabled(),true);});
test("coordinators can use the same controls",async t=>{const{page}=await screen(t,{role:"coordinator"});await open(page);await show(page);await button(page,"Close check-in").click();await page.getByText("Check-in is closed",{exact:true}).waitFor();});
test("open failure is retryable with no false QR",async t=>{const{page,state}=await screen(t);await open(page);state.fail=true;await button(page,"Open check-in").click();await page.getByText(/Check-in could not be updated/).waitFor();assert.equal(await page.getByAltText("QR code for class sign-in").count(),0);state.fail=false;await show(page);});
test("close failure keeps the displayed code and allows retry",async t=>{const{page,state}=await screen(t);await open(page);await show(page);state.fail=true;await button(page,"Close check-in").click();await page.getByText(/Check-in could not be updated/).waitFor();assert.equal(await page.getByAltText("QR code for class sign-in").count(),1);state.fail=false;await button(page,"Close check-in").click();await page.getByText("Check-in is closed",{exact:true}).waitFor();});
test("repeated clicks while opening submit once",async t=>{const{page,state}=await screen(t);await open(page);state.busy=true;await button(page,"Open check-in").click();await button(page,"Opening…").waitFor();assert.equal(await button(page,"Opening…").isDisabled(),true);state.release();await page.getByText("Check-in is open",{exact:true}).waitFor();assert.equal(state.opens,1);});
test("QR printing uses an isolated A4 sheet with a code larger than 8cm",async t=>{
  const{page}=await screen(t);await open(page);await show(page);await button(page,"Print QR code").click();
  await page.waitForFunction(()=>window.__printed===1);
  const frame=page.frames().find(f=>f!==page.mainFrame());assert.ok(frame);
  const width=await frame.locator("img").evaluate(e=>e.getBoundingClientRect().width);assert.ok(width>=8*96/2.54);
  const html=await frame.content();assert.ok(html.includes("size: A4"));assert.ok(html.includes(today));assert.equal((await frame.locator("nav").count()),0);
});
test("expiry hides the code without a reload",async t=>{const{page,state}=await screen(t);await open(page);state.expires=new Date(Date.now()+1500).toISOString();await show(page);await page.getByText("Check-in has expired",{exact:true}).waitFor({timeout:5000});assert.equal(await page.getByAltText("QR code for class sign-in").count(),0);});
test("another staff member's close appears on refresh",async t=>{const{page,state}=await screen(t);await open(page);await show(page);state.kind="closed";await page.getByText("Check-in is closed",{exact:true}).waitFor({timeout:7000});});
test("learner sign-in appears in attendance within ten seconds",async t=>{
  const{page,state}=await screen(t);await page.goto(base+`/sessions/${sid}/attendance`);await page.getByText("Māia Test",{exact:true}).waitFor();
  const before=Date.now();assert.equal(await page.locator(`#present-${lid}`).isChecked(),false);state.present=true;await page.waitForFunction(id=>document.getElementById(`present-${id}`)?.checked,lid,{timeout:10000});assert.ok(Date.now()-before<10000);await page.getByText("Present 1 of 1",{exact:true}).waitFor();
});
test("mobile QR and token link fit 360px with Ako styles",async t=>{
  const{page}=await screen(t,{mobile:true});await open(page);await show(page);
  const size=await page.evaluate(()=>({width:innerWidth,body:document.documentElement.scrollWidth,font:getComputedStyle(document.body).fontSize}));assert.ok(size.body<=size.width);assert.ok(parseFloat(size.font)>=18);
  const image=await page.getByAltText("QR code for class sign-in").boundingBox();assert.ok(image.width<=312);
  if(process.env.UI_SCREENSHOT_DIR){await mkdir(process.env.UI_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:process.env.UI_SCREENSHOT_DIR+"/qr-mobile.png",fullPage:true});}
});
test("anonymous visitors cannot reach classroom QR management",async t=>{const{page,state}=await screen(t,{role:null});await page.goto(base+`/sessions/${sid}`);await page.waitForURL(base+"/");assert.equal(state.reads,0);});


test("a late status response cannot restore a closed QR code",async t=>{
  const{page,state}=await screen(t);await open(page);await show(page);state.delayRead=true;
  for(let i=0;i<300&&!state.late;i++)await new Promise(resolve=>setTimeout(resolve,25));
  assert.ok(state.late);await button(page,"Close check-in").click();await page.getByText("Check-in is closed",{exact:true}).waitFor();state.delayRead=false;state.late();
  await page.waitForTimeout(200);assert.equal(await page.getByAltText("QR code for class sign-in").count(),0);
});
test("failed live refresh keeps attendance and recovers",async t=>{
  const{page,state}=await screen(t);state.present=true;await page.goto(base+`/sessions/${sid}/attendance`);await page.getByText("Present 1 of 1",{exact:true}).waitFor();state.failAttendance=true;
  await page.getByText("Live attendance could not refresh. Retrying…",{exact:true}).waitFor({timeout:6000});assert.equal(await page.locator(`#present-${lid}`).isChecked(),true);
  state.failAttendance=false;state.present=false;await page.waitForFunction(id=>!document.getElementById(`present-${id}`)?.checked,lid,{timeout:6000});
});
test("late background attendance cannot undo a manual tick",async t=>{
  const{page,state}=await screen(t);await page.goto(base+`/sessions/${sid}/attendance`);await page.getByText("Māia Test",{exact:true}).waitFor();state.delayAttendance=true;
  for(let i=0;i<200&&!state.attendanceLate;i++)await new Promise(resolve=>setTimeout(resolve,25));assert.ok(state.attendanceLate);
  await page.locator(`#present-${lid}`).check();await page.getByText("Present 1 of 1",{exact:true}).waitFor();state.delayAttendance=false;state.attendanceLate();
  await page.waitForTimeout(200);assert.equal(await page.locator(`#present-${lid}`).isChecked(),true);
});


test("slow background refreshes do not overlap or starve updates",async t=>{
  const{page,state}=await screen(t);await page.goto(base+`/sessions/${sid}/attendance`);await page.getByText("Māia Test",{exact:true}).waitFor();
  state.delayAttendance=true;state.present=true;
  for(let i=0;i<200&&!state.attendanceLate;i++)await new Promise(resolve=>setTimeout(resolve,25));assert.ok(state.attendanceLate);
  await page.waitForTimeout(3300);assert.equal(state.attendanceReads,2);
  state.delayAttendance=false;state.attendanceLate();await page.waitForFunction(id=>document.getElementById(`present-${id}`)?.checked,lid,{timeout:2000});
});
