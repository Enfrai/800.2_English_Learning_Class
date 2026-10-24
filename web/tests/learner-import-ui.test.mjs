/** Learners/SessionShell integration with mocked API; backend role tests remain separate. */
import assert from "node:assert/strict";
import { before, after, test } from "node:test";
import { chromium } from "playwright";
let browser;
const base=process.env.US017_UI_URL;
if(!base)throw new Error("Run node tests/run-csv-ui.mjs");
before(async()=>{browser=await chromium.launch({channel:"chrome",headless:true});});
after(async()=>{await browser?.close();});
const learner={id:"00000000-0000-4000-8000-000000000001",first_name:"Fiction",family_name:"Existing",first_language:null,contact:null,is_active:true};
async function open(t,role="coordinator",importStatus=200,refreshFails=false){
 const context=await browser.newContext();t.after(()=>context.close());const page=await context.newPage();
 let imported=false,reads=0,uploads=0;
 await page.route("**/api/user/**",async route=>{
  const request=route.request(),path=new URL(request.url()).pathname;
  if(path.endsWith("/session"))return route.fulfill({status:role?200:401,headers:{"X-Session-Expires-At":new Date(Date.now()+1800000).toISOString()},json:{user_id:learner.id,display_name:"Fixture",role}});
  if(path.endsWith("/activity"))return route.fulfill({json:{expires_at:new Date(Date.now()+1800000).toISOString()}});
  if(path.endsWith("/learners/import")){uploads++;imported=importStatus===200;return route.fulfill({status:importStatus,json:importStatus===200?{imported_count:1,duplicates:[],errors:[]}:{detail:"Denied"}});}
  if(path.endsWith("/learners")){reads++;return route.fulfill({status:imported&&refreshFails?500:200,json:imported?[learner,{...learner,id:"00000000-0000-4000-8000-000000000002",family_name:"Imported"}]:[learner]});}
  return route.fulfill({status:404,json:{}});
 });
 await page.goto(`${base}/test-learners`);
 return {page,stats:()=>({reads,uploads})};
}
async function upload(page){
 await page.getByRole("button",{name:"Import CSV",exact:true}).click();
 await page.getByLabel("CSV file",{exact:true}).setInputFiles({name:"fiction.csv",mimeType:"text/csv",buffer:Buffer.from("first_name,family_name,first_language,contact\nFiction,Imported,,\n")});
 await page.getByRole("button",{name:"Import learners",exact:true}).click();
}
test("Coordinator can toggle import and refresh list after successful import",async t=>{
 const {page,stats}=await open(t);await page.getByRole("cell",{name:"Fiction Existing",exact:true}).waitFor();
 await upload(page);await page.getByText("1 learners imported",{exact:true}).waitFor();await page.getByRole("cell",{name:"Fiction Imported",exact:true}).waitFor();
 assert.ok(stats().reads >= 2);assert.equal(stats().uploads,1);
 await page.getByRole("button",{name:"Close CSV import",exact:true}).click();assert.equal(await page.getByLabel("CSV file",{exact:true}).count(),0);
});
test("Teacher retains list, add and edit without import entry",async t=>{
 const {page,stats}=await open(t,"teacher");await page.getByRole("cell",{name:"Fiction Existing",exact:true}).waitFor();
 assert.equal(await page.getByRole("button",{name:"Import CSV",exact:true}).count(),0);
 await page.getByRole("button",{name:"Add learner",exact:true}).click();await page.getByRole("heading",{name:"Add learner",exact:true}).waitFor();
 await page.getByRole("button",{name:"Cancel",exact:true}).click();await page.getByRole("button",{name:"Edit Fiction Existing",exact:true}).click();
 await page.getByRole("heading",{name:"Edit learner",exact:true}).waitFor();assert.equal(await page.getByLabel("First name",{exact:true}).inputValue(),"Fiction");assert.equal(stats().uploads,0);
});
test("Anonymous session redirects before mounting learners or import",async t=>{
 const {page,stats}=await open(t,null);await page.waitForURL(`${base}/`);assert.deepEqual(stats(),{reads:0,uploads:0});
});
test("Import 403 blocks form without refreshing list",async t=>{
 const {page,stats}=await open(t,"coordinator",403);await upload(page);await page.getByText("You do not have permission",{exact:true}).waitFor();assert.equal(stats().uploads,1);assert.equal(await page.getByRole("button",{name:"Import learners",exact:true}).isDisabled(),true);
});
test("Refresh failure preserves import success and offers list retry",async t=>{
 const {page,stats}=await open(t,"coordinator",200,true);await upload(page);await page.getByText("1 learners imported",{exact:true}).waitFor();await page.getByRole("button",{name:"Try again",exact:true}).waitFor();assert.ok(stats().reads >= 2);assert.equal(stats().uploads,1);
});
