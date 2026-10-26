/* Verify staff QR requests, safe errors and a black-and-white A4 print sheet.
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
const folder = await mkdtemp(join(tmpdir(), "ako-us011-unit-"));
for (const name of ["api", "checkin-management-api"]) {
  const source = await readFile(new URL(`../src/lib/${name}.ts`, import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText.replaceAll('"./api"', '"./api.mjs"');
  await writeFile(join(folder, name + ".mjs"), output);
}
const api = await import(pathToFileURL(join(folder, "checkin-management-api.mjs")));
after(() => rm(folder, { recursive:true,force:true }));
for(const [method,invoke] of [["GET",api.getWindow],["POST",api.openWindow],["DELETE",api.closeWindow]])test(`${method} uses cookie bridge and no client Bearer`,async t=>{
  t.mock.method(globalThis,"fetch",async(url,init)=>{
    assert.equal(url,"/api/staff/access/sessions/class-id/check-in");assert.equal(init.method,method);assert.equal(init.credentials,"same-origin");assert.equal(init.cache,"no-store");assert.equal(init.headers.has("Authorization"),false);
    return Response.json({state:"open"});
  });assert.equal((await invoke("class-id")).state,"open");
});
for(const [status,detail,message] of [[403,"private","You do not have permission"],[404,"private","Class session not found"],[409,"Check-in can only open for today's active class","Check-in can only open for today's active class"],[503,"private upstream details","Check-in could not be updated. Please try again."]])test(`HTTP ${status} has safe useful text`,async t=>{
  t.mock.method(globalThis,"fetch",async()=>Response.json({detail},{status}));await assert.rejects(api.openWindow("id"),e=>e instanceof api.CheckinError&&e.message===message);
});
test("expired session retains shared login handling",async t=>{
  t.mock.method(globalThis,"fetch",async()=>new Response(null,{status:401}));await assert.rejects(api.getWindow("id"),api.LoginRequiredError);
});
test("path ids cannot escape the fixed route",async t=>{
  t.mock.method(globalThis,"fetch",async url=>{assert.ok(url.includes("id%2F..%2Fadmin/check-in"));return Response.json({});});await api.getWindow("id/../admin");
});
const open={state:"open",session_date:"2026-10-26",sign_in_url:"http://192.168.1.20:8080/sign-in/token",qr_svg:'<svg xmlns="http://www.w3.org/2000/svg"></svg>'};
test("print sheet uses A4, 110mm code, black-and-white and date",()=>{
  const html=api.printDocument(open);assert.ok(html.includes("size: A4"));assert.ok(html.includes("width:110mm; height:110mm"));assert.ok(html.includes("color: #000; background:#fff"));assert.ok(html.includes("Class date: 2026-10-26"));assert.ok(html.includes(encodeURIComponent(open.qr_svg)));
});
test("print sheet escapes text and URLs rather than inserting markup",()=>{
  const html=api.printDocument({...open,session_date:'<script>bad</script>',sign_in_url:'https://example.test/?x="<bad>&y=1'});
  assert.equal(html.includes('<script>bad</script>'),false);assert.ok(html.includes('&lt;script&gt;'));assert.ok(html.includes('&quot;'));
});
for(const state of ["closed","expired","not-open"])test(`printing ${state} is refused`,()=>assert.throws(()=>api.printDocument({...open,state}),api.CheckinError));
