/** Real browser component tests; every import endpoint is mocked. */
import assert from "node:assert/strict";
import { before, after, test } from "node:test";
import { chromium } from "playwright";
const base=process.env.US017_UI_URL;
if(!base)throw new Error("Run with node tests/run-csv-ui.mjs");
let browser;
before(async()=>{browser=await chromium.launch({channel:"chrome",headless:true});});
after(async()=>{await browser?.close();});
const header="first_name,family_name,first_language,contact\r\n";
const result={imported_count:10,message:"10 learners imported",duplicates:[],errors:[]};
async function open(t,status=200,body=result){
 const context=await browser.newContext();t.after(()=>context.close());
 await context.addCookies([{name:"ako_session",value:"mock-only",url:base,httpOnly:true,sameSite:"Lax"}]);
 const page=await context.newPage(); const requests=[];
 await page.route("**/api/user/learners/import",async route=>{requests.push(route.request());await route.fulfill({status,contentType:"application/json",body:JSON.stringify(body)});});
 await page.goto(`${base}/test-csv`);
 return {page,requests};
}
async function select(page,name="learners.csv",buffer=Buffer.from(header+"Fiction,Example,,\r\n")){
 await page.getByLabel("CSV file",{exact:true}).setInputFiles({name,mimeType:"text/csv",buffer});
}
async function submit(page){await page.getByRole("button",{name:"Import learners",exact:true}).click();}

test("AC1: multipart cookie upload and exact success message",async t=>{
 const {page,requests}=await open(t);await select(page);await submit(page);
 await page.getByText("10 learners imported",{exact:true}).waitFor();
 assert.equal(requests.length,1);const r=requests[0];
 assert.match(r.headers()["content-type"],/^multipart\/form-data; boundary=/);
 assert.match(r.postData(),/name="file"; filename="learners.csv"/);
 assert.equal(r.headers()["origin"],base);
 assert.equal((await r.allHeaders()).cookie,"ako_session=mock-only");
 assert.equal(r.headers().authorization,undefined);
 assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
 assert.equal(await page.getByLabel("CSV file",{exact:true}).inputValue(),"");
});
test("AC2–AC4: duplicate names and rejected row numbers/messages",async t=>{
 const {page}=await open(t,200,{...result,imported_count:1,duplicates:[{row_number:3,first_name:"Āria",family_name:"Example",source:"database",first_row_number:null},{row_number:5,first_name:"Fiction",family_name:"Example",source:"file",first_row_number:2}],errors:[{row_number:4,field:"first_name",message:"First name is required"},{row_number:6,field:"family_name",message:"Name must be 100 characters or fewer"}]});
 await select(page);await submit(page);
 for(const text of ["1 learners imported","Row 3: Āria Example — Already exists","Row 4: First name is required","Row 6: Name must be 100 characters or fewer","Row 5: Fiction Example — Duplicate in file (row 2)"])await page.getByText(text,{exact:true}).waitFor();
});
for(const [name,buffer,message] of [["file.txt",Buffer.from(header),"File must be a CSV file (.csv)"],["file.csv",Buffer.alloc(1048577),"CSV file must be 1,048,576 bytes or fewer"]])test(`AC5: rejects ${name}/${buffer.length} locally`,async t=>{
 const {page,requests}=await open(t);await select(page,name,buffer);await submit(page);await page.getByRole("alert").filter({hasText:message}).waitFor();assert.equal(requests.length,0);
});
test("Inclusive 1 MiB boundary and uppercase extension",async t=>{const {page,requests}=await open(t);await select(page,"FILE.CSV",Buffer.alloc(1048576));await submit(page);await page.getByText("10 learners imported",{exact:true}).waitFor();assert.equal(requests.length,1);});
test("Missing file focuses accessible picker",async t=>{const {page,requests}=await open(t);await submit(page);await page.getByText("Choose a CSV file",{exact:true}).waitFor();assert.equal(await page.getByLabel("CSV file",{exact:true}).evaluate(el=>el===document.activeElement),true);assert.equal(requests.length,0);});
for(const [status,detail,message] of [[403,"secret","You do not have permission"],[413,"gateway","CSV file must be 1,048,576 bytes or fewer"],[422,"CSV file must use UTF-8 encoding","CSV file must use UTF-8 encoding"],[422,[{input:"private"}],"Invalid CSV file. Check the template and UTF-8 encoding."],[500,"Unable to import learners. No learners were imported.","Unable to import learners. No learners were imported."],[500,"SQL secret","Unable to confirm the import. Check the learner list before retrying."]])test(`HTTP ${status}: ${typeof detail}`,async t=>{
 const {page}=await open(t,status,{detail});await select(page);await submit(page);await page.getByRole("alert").filter({hasText:message}).waitFor();assert.equal(await page.getByText("SQL secret",{exact:true}).count(),0);
 if(status===403)assert.equal(await page.getByRole("button",{name:"Import learners",exact:true}).isDisabled(),true);
});
test("401 clears state and redirects to login",async t=>{const {page}=await open(t,401,{});await select(page);await submit(page);await page.waitForURL(`${base}/`);});
test("Pending request blocks same-tick duplicate submits",async t=>{
 const {page}=await open(t);let calls=0,release;const gate=new Promise(resolve=>release=resolve);
 await page.route("**/api/user/learners/import",async route=>{calls++;await gate;await route.fulfill({json:result});});
 await select(page);await page.locator("form").evaluate(form=>{form.requestSubmit();form.requestSubmit();});
 await page.getByText("Uploading CSV…",{exact:true}).waitFor();assert.equal(await page.getByLabel("CSV file",{exact:true}).isDisabled(),true);
 release();await page.getByText("10 learners imported",{exact:true}).waitFor();assert.equal(calls,1);
});
test("Network failure never claims rollback or retries",async t=>{const {page}=await open(t);await page.route("**/api/user/learners/import",route=>route.abort());await select(page);await submit(page);await page.getByText("Unable to confirm the import. Check the learner list before retrying.",{exact:true}).waitFor();});
test("Template is exact UTF-8 header; mobile layout fits",async t=>{
 const {page}=await open(t);const link=page.getByRole("link",{name:"Download CSV template"});
 const href=await link.getAttribute("href");assert.equal(decodeURIComponent(href.split(",").slice(1).join(",")),header);
 assert.equal(await link.getAttribute("download"),"learners-template.csv");
 await page.setViewportSize({width:360,height:800});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
});
test("Malformed successful response is not presented as success",async t=>{const {page}=await open(t,200,{imported_count:10});await select(page);await submit(page);await page.getByRole("alert").waitFor();assert.equal(await page.getByText("10 learners imported",{exact:true}).count(),0);});
