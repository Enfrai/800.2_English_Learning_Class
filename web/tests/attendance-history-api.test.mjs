/* Verify history request encoding, cookie transport, counts and safe errors.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */
import assert from "node:assert/strict";
import { after, test } from "node:test";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";
const folder=await mkdtemp(join(tmpdir(),"ako-history-unit-"));
for(const name of ["api","attendance-history-api"]){
  const source=await readFile(new URL(`../src/lib/${name}.ts`,import.meta.url),"utf8");
  await writeFile(join(folder,name+".mjs"),ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText.replaceAll('"./api"','"./api.mjs"'));
}
const api=await import(pathToFileURL(join(folder,"attendance-history-api.mjs")));
after(()=>rm(folder,{recursive:true,force:true}));
const id="11111111-1111-4111-8111-111111111111";
const fixture={learner:{id,name:"Māia Example"},sessions:[{session_id:"x",session_date:"2026-10-24",status:"Present"}],present_count:1,total_count:1,has_records:true,start_date:null,end_date:null};
for(const [start,end,query] of [["","",""],["2026-10-24","","?start_date=2026-10-24"],["","2026-10-25","?end_date=2026-10-25"],["2026-10-24","2026-10-25","?start_date=2026-10-24&end_date=2026-10-25"]])test(`GET history with inclusive optional dates ${query}`,async t=>{
  t.mock.method(globalThis,"fetch",async(url,init)=>{assert.equal(url,`/api/staff/access/learners/${id}/attendance-history${query}`);assert.equal(init.credentials,"same-origin");assert.equal(init.cache,"no-store");assert.equal(init.headers.has("Authorization"),false);assert.equal(init.body,undefined);return Response.json(fixture);});
  assert.deepEqual(await api.getAttendanceHistory(id,start,end),fixture);
});
for(const [status,message,field] of [[403,"You do not have permission"],[404,"Learner not found"],[422,"Start date must be before end date","end_date"]])test(`safe HTTP ${status}`,async t=>{
  t.mock.method(globalThis,"fetch",async()=>Response.json({detail:field?{field,message:"private text"}:"private text"},{status}));
  await assert.rejects(api.getAttendanceHistory(id),e=>e instanceof api.HistoryError&&e.message===message&&e.field===field);
});
test("expired session uses shared login error",async t=>{t.mock.method(globalThis,"fetch",async()=>new Response(null,{status:401}));await assert.rejects(api.getAttendanceHistory(id),api.LoginRequiredError);});
for(const status of [422,500,502,503])test(`generic HTTP ${status} does not reveal internals`,async t=>{t.mock.method(globalThis,"fetch",async()=>Response.json({detail:"private"},{status}));await assert.rejects(api.getAttendanceHistory(id),e=>!e.message.includes("private"));});
for(const change of [{present_count:3},{total_count:9},{learner:{id:"other",name:"Wrong"}},{sessions:[{session_id:"x",session_date:"bad",status:"Present"}]},{sessions:[{session_id:"x",session_date:"2026-10-24",status:"unknown"}]},{sessions:null},{has_records:null}])test(`reject malformed history ${JSON.stringify(change)}`,async t=>{t.mock.method(globalThis,"fetch",async()=>Response.json({...fixture,...change}));await assert.rejects(api.getAttendanceHistory(id));});
test("network failure is retryable",async t=>{t.mock.method(globalThis,"fetch",async()=>{throw Error("network");});await assert.rejects(api.getAttendanceHistory(id));});
test("non JSON answer is rejected",async t=>{t.mock.method(globalThis,"fetch",async()=>new Response("bad gateway"));await assert.rejects(api.getAttendanceHistory(id));});
test("identifier is encoded as one path segment",async t=>{t.mock.method(globalThis,"fetch",async url=>{assert.ok(url.includes("a%2Fb%3Fc/attendance-history"));return new Response(null,{status:404});});await assert.rejects(api.getAttendanceHistory("a/b?c"));});
