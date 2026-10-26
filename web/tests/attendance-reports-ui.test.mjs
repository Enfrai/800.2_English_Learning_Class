/* Verify report downloads, native calendar pickers and responsive Ako UI.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */
import assert from "node:assert/strict";
import { before, after, test } from "node:test";
import { chromium } from "playwright";
import { readFile, mkdir } from "node:fs/promises";
const base = process.env.US005_UI_BASE_URL;
if (!base) throw new Error("Run npm run test:reports-ui after npm run build");
let browser;
before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || "chrome", headless: true }); });
after(async () => { await browser?.close(); });
async function screen(t, { role="coordinator", mobile=false }={}) {
  const context = await browser.newContext({ viewport: mobile ? { width:360,height:900 } : { width:1280,height:900 }, acceptDownloads:true });
  t.after(() => context.close());
  if (role) await context.addCookies([{ name:"ako_session",value:`ui-${role}`,url:base,httpOnly:true,sameSite:"Lax" }]);
  await context.route("**/api/user/**",route => route.fulfill({json:{ user_id:"11111111-1111-4111-8111-111111111111",display_name:"Test coordinator",role:role||"coordinator",expires_at:new Date(Date.now()+1800000).toISOString() },headers:{"X-Session-Expires-At":new Date(Date.now()+1800000).toISOString()}}));
  const state={requests:[],status:200,detail:"",pending:false,release:null};
  await context.route("**/api/staff/access/reports/attendance",async route=>{
    const payload=route.request().postDataJSON();state.requests.push(payload);
    if(state.pending)await new Promise(resolve=>state.release=resolve);
    if(state.status!==200)return route.fulfill({status:state.status,json:{detail:state.detail}});
    return route.fulfill({contentType:payload.format==="pdf"?"application/pdf":"text/csv; charset=utf-8",body:payload.format==="pdf"?"%PDF-1.7 report-fixture":"\ufeffLearner name,2026-10-24\r\nMāia Test,Present\r\n"});
  });
  const page=await context.newPage(),errors=[];
  page.on("pageerror",error=>errors.push(error.message));t.after(()=>assert.deepEqual(errors,[]));
  return {page,state};
}
const button=(page,name)=>page.getByRole("button",{name,exact:true});
async function fill(page,start="2026-10-24",end="2026-10-26") {
  await page.getByLabel("Start date",{exact:true}).fill(start);await page.getByLabel("End date",{exact:true}).fill(end);
}
async function open(page) { await page.goto(base+"/reports/attendance");await button(page,"Download PDF").waitFor(); }

test("coordinator navigation opens the report page",async t=>{
  const {page}=await screen(t);await page.goto(base+"/coordinator");await page.getByRole("link",{name:"Attendance reports",exact:true}).click();
  await page.getByRole("heading",{name:"Attendance reports",exact:true}).waitFor();await button(page,"Download PDF").waitFor();
});
test("both dates are required and focus the first error",async t=>{
  const {page,state}=await screen(t);await open(page);await button(page,"Download PDF").click();
  await page.getByText("Start date is required",{exact:true}).waitFor();await page.getByText("End date is required",{exact:true}).waitFor();
  assert.equal(await page.locator("#report-start").evaluate(e=>e===document.activeElement),true);assert.equal(state.requests.length,0);
});
test("missing end date blocks CSV export",async t=>{
  const {page,state}=await screen(t);await open(page);await page.getByLabel("Start date",{exact:true}).fill("2026-10-24");await button(page,"Download CSV").click();
  await page.getByText("End date is required",{exact:true}).waitFor();assert.equal(state.requests.length,0);
});
test("reversed dates show the exact message without export",async t=>{
  const {page,state}=await screen(t);await open(page);await fill(page,"2026-10-26","2026-10-24");await button(page,"Download PDF").click();
  await page.getByText("Start date must be before end date",{exact:true}).waitFor();assert.equal(state.requests.length,0);
});
for(const format of ["pdf","csv"])test(`${format} downloads a real file with a stable filename`,async t=>{
  const {page,state}=await screen(t);await open(page);await fill(page);
  const downloadPromise=page.waitForEvent("download");await button(page,`Download ${format.toUpperCase()}`).click();const download=await downloadPromise;
  assert.equal(download.suggestedFilename(),`ako-attendance-2026-10-24-2026-10-26.${format}`);
  const bytes=await readFile(await download.path());assert.ok(bytes.length>0);
  assert.ok(bytes.toString().includes(format==="pdf"?"%PDF":"Māia Test"));
  assert.deepEqual(state.requests,[{start_date:"2026-10-24",end_date:"2026-10-26",format}]);
  await page.getByText(`${format.toUpperCase()} download started.`,{exact:true}).waitFor();
});
test("same-day report is allowed",async t=>{
  const {page,state}=await screen(t);await open(page);await fill(page,"2026-10-24","2026-10-24");const waiting=page.waitForEvent("download");await button(page,"Download CSV").click();await waiting;
  assert.equal(state.requests[0].start_date,state.requests[0].end_date);
});
test("empty range shows the exact message and no download",async t=>{
  const {page,state}=await screen(t);await open(page);await fill(page);state.status=404;state.detail="No classes found for these dates";
  let downloads=0;page.on("download",()=>downloads++);await button(page,"Download PDF").click();await page.getByText("No classes found for these dates",{exact:true}).waitFor();
  assert.equal(downloads,0);assert.equal(await page.getByLabel("Start date",{exact:true}).inputValue(),"2026-10-24");
});
test("service failure retains dates and can be retried",async t=>{
  const {page,state}=await screen(t);await open(page);await fill(page);state.status=503;await button(page,"Download CSV").click();
  await page.getByText("The report could not be downloaded. Please try again.",{exact:true}).waitFor();state.status=200;
  const waiting=page.waitForEvent("download");await button(page,"Download CSV").click();await waiting;assert.equal(state.requests.length,2);
});
test("server field errors focus the matching input",async t=>{
  const {page,state}=await screen(t);await open(page);await fill(page);state.status=422;state.detail={field:"end_date",message:"Start date must be before end date"};
  await button(page,"Download PDF").click();await page.getByText("Start date must be before end date",{exact:true}).waitFor();assert.equal(await page.locator("#report-end").getAttribute("aria-invalid"),"true");
});
test("busy state disables both downloads and preserves one request",async t=>{
  const {page,state}=await screen(t);await open(page);await fill(page);state.pending=true;await button(page,"Download PDF").click();
  await page.getByText("Preparing your attendance report…",{exact:true}).waitFor();assert.equal(await button(page,"Download CSV").isDisabled(),true);
  assert.equal(await page.getByLabel("Start date",{exact:true}).isDisabled(),true);assert.equal(state.requests.length,1);
  const waiting=page.waitForEvent("download");state.release();await waiting;await button(page,"Download PDF").waitFor();
});
test("changing dates clears stale success and validation",async t=>{
  const {page}=await screen(t);await open(page);await button(page,"Download PDF").click();await fill(page);assert.equal(await page.getByText("Start date is required",{exact:true}).count(),0);
  const waiting=page.waitForEvent("download");await button(page,"Download CSV").click();await waiting;await page.getByText("CSV download started.",{exact:true}).waitFor();
  await page.getByLabel("End date",{exact:true}).fill("2026-10-25");assert.equal(await page.getByText("CSV download started.",{exact:true}).count(),0);
});
test("backend role denial is visible without a file",async t=>{
  const {page,state}=await screen(t);await open(page);await fill(page);state.status=403;await button(page,"Download PDF").click();await page.getByText("You do not have permission",{exact:true}).waitFor();
});
test("expired API login redirects to login",async t=>{
  const {page,state}=await screen(t);await open(page);await fill(page);state.status=401;await button(page,"Download CSV").click();await page.waitForURL(base+"/");
});
test("teacher sees no report navigation and direct URL returns 403",async t=>{
  const {page,state}=await screen(t,{role:"teacher"});await page.goto(base+"/teacher");await page.getByRole("navigation",{name:"Teacher menu"}).waitFor();
  assert.equal(await page.getByRole("link",{name:"Attendance reports",exact:true}).count(),0);
  const response=await page.goto(base+"/reports/attendance");assert.equal(response.status(),403);await page.getByText("You do not have permission",{exact:true}).waitFor();assert.equal(state.requests.length,0);
});
test("anonymous visitors return to login without exporting",async t=>{
  const {page,state}=await screen(t,{role:null});await page.goto(base+"/reports/attendance");await page.waitForURL(base+"/");assert.equal(state.requests.length,0);
});
test("360px page keeps shared Ako style and usable controls",async t=>{
  const {page}=await screen(t,{mobile:true});await open(page);await fill(page);
  const dimensions=await page.evaluate(()=>({width:innerWidth,body:document.documentElement.scrollWidth,font:getComputedStyle(document.body).fontSize,button:getComputedStyle(document.querySelector('button.btn[type="submit"]')).backgroundColor}));
  assert.ok(dimensions.body<=dimensions.width);assert.ok(parseFloat(dimensions.font)>=18);assert.equal(dimensions.button,"rgb(31, 78, 121)");
  for(const label of ["Download PDF","Download CSV"]){const box=await button(page,label).boundingBox();assert.ok(box.height>=44);}
  if(process.env.UI_SCREENSHOT_DIR){await mkdir(process.env.UI_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:process.env.UI_SCREENSHOT_DIR+"/attendance-reports-mobile.png",fullPage:true});}
});
test("keyboard submission downloads PDF",async t=>{
  const {page,state}=await screen(t);await open(page);await fill(page);const waiting=page.waitForEvent("download");await page.getByLabel("End date",{exact:true}).press("Enter");await waiting;assert.equal(state.requests[0].format,"pdf");
});

for (const id of ["report-start", "report-end"]) test(`${id} opens its native calendar from the input and icon`, async t => {
  const { page } = await screen(t); await open(page);
  await page.evaluate(() => {
    const native = HTMLInputElement.prototype.showPicker;
    window.__calendarOpened = [];
    HTMLInputElement.prototype.showPicker = function () {
      native.call(this);
      window.__calendarOpened.push(this.id);
    };
  });
  const input = page.locator(`#${id}`);
  const box = await input.boundingBox();
  await input.click({ position: { x: 25, y: box.height / 2 } });
  assert.deepEqual(await page.evaluate(() => window.__calendarOpened), [id]);
  await page.keyboard.press("Escape");
  await input.click({ position: { x: box.width - 18, y: box.height / 2 } });
  assert.deepEqual(await page.evaluate(() => window.__calendarOpened), [id, id]);
  await page.keyboard.press("Escape");
});
test("empty dates are dark slate and selected dates use normal text colour", async t => {
  const { page } = await screen(t); await open(page);
  for (const id of ["report-start", "report-end"]) {
    const input = page.locator(`#${id}`);
    assert.equal(await input.evaluate(e => getComputedStyle(e).color), "rgb(74, 90, 107)");
    await input.fill("2026-10-24");
    assert.equal(await input.evaluate(e => getComputedStyle(e).color), "rgb(28, 39, 51)");
    await input.fill("");
    assert.equal(await input.evaluate(e => getComputedStyle(e).color), "rgb(74, 90, 107)");
  }
});
test("unsupported calendar API retains manual entry without errors", async t => {
  const { page } = await screen(t); await open(page);
  await page.evaluate(() => { HTMLInputElement.prototype.showPicker = undefined; });
  await page.locator("#report-start").click({ position: { x: 20, y: 20 } });
  await fill(page);
  assert.equal(await page.getByLabel("Start date", { exact: true }).inputValue(), "2026-10-24");
});
