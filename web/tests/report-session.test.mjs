/* Verify binary report forwarding, cookie identity and same-origin enforcement.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { once } from "node:events";
import { spawn } from "node:child_process";
import { before, after, test } from "node:test";
let upstream, app, base, calls = [], status = 200, format = "pdf";
const path = "/api/staff/access/reports/attendance", token = "report-fixture-token";
const content = () => format === "pdf" ? Buffer.from([37,80,68,70,45,49,46,55,10,0,255,128]) : Buffer.from("\ufeffLearner name,2026-10-26\r\nMāia Test,Present\r\n");
before(async () => {
  upstream = createServer(async (req, res) => {
    let body = ""; for await (const chunk of req) body += chunk;
    calls.push({ path: req.url, method: req.method, headers: req.headers, body });
    res.writeHead(status, { "Content-Type": status === 200 ? format === "pdf" ? "application/pdf" : "text/csv; charset=utf-8" : "application/json", "Content-Disposition": `attachment; filename=fixture.${format}` });
    res.end(status === 200 ? content() : JSON.stringify({ detail: "You do not have permission" }));
  }).listen(0, "127.0.0.1"); await once(upstream, "listening");
  const reservation = createServer().listen(0, "127.0.0.1"); await once(reservation, "listening");
  const port = reservation.address().port; await new Promise(resolve => reservation.close(resolve)); base = `http://127.0.0.1:${port}`;
  app = spawn(process.execPath, [".next/standalone/server.js"], { env: { ...process.env, PORT: String(port), HOSTNAME: "127.0.0.1", ACCESS_API_URL: `http://127.0.0.1:${upstream.address().port}`, SESSION_PUBLIC_ORIGIN: base }, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(base)).ok) return; } catch {} await new Promise(resolve => setTimeout(resolve, 100)); }
  throw new Error("Next server did not start");
});
after(async () => { if (app && app.exitCode === null) { app.kill(); await once(app, "exit"); } if (upstream) await new Promise(resolve => upstream.close(resolve)); });
async function download(headers = {}) { return fetch(base+path, { method: "POST", headers, body: JSON.stringify({ start_date: "2026-10-24", end_date: "2026-10-26", format }) }); }
test("anonymous cannot request a report", async () => { calls=[]; assert.equal((await download()).status,401); assert.equal(calls.length,0); });
for (const origin of [undefined,"https://untrusted.example"]) test(`deny ${origin || "missing"} Origin`, async () => {
  calls=[]; assert.equal((await download({ Cookie:`ako_session=${token}`, ...(origin?{Origin:origin}:{}) })).status,403); assert.equal(calls.length,0);
});
test("browser Bearer cannot replace cookie identity",async()=>{
  calls=[]; assert.equal((await download({ Cookie:`ako_session=${token}`, Authorization:"Bearer attacker",Origin:base })).status,401); assert.equal(calls.length,0);
});
for (const type of ["pdf","csv"]) test(`${type} bytes and download headers survive proxying`,async()=>{
  calls=[]; format=type;
  const reply=await download({ Cookie:`ako_session=${token}`,Origin:base,"Content-Type":"application/json" });
  assert.equal(reply.status,200); assert.deepEqual(Buffer.from(await reply.arrayBuffer()),content());
  assert.equal(reply.headers.get("content-disposition"),`attachment; filename=fixture.${type}`);
  assert.equal(reply.headers.get("cache-control"),"no-store"); assert.equal(reply.headers.get("x-content-type-options"),"nosniff");
  assert.equal(calls[0].path,"/reports/attendance"); assert.equal(calls[0].method,"POST"); assert.equal(calls[0].headers.authorization,`Bearer ${token}`); assert.equal(calls[0].headers.cookie,undefined);
  assert.equal(JSON.parse(calls[0].body).format,type);
});
for (const code of [401,403,404,422,503]) test(`upstream ${code} is preserved`,async()=>{
  status=code; try { const reply=await download({ Cookie:`ako_session=${token}`,Origin:base });assert.equal(reply.status,code);assert.equal(reply.headers.get("cache-control"),"no-store"); } finally {status=200;}
});
test("report path cannot proxy unrelated upstream resources",async()=>{
  calls=[]; const reply=await fetch(base+path+"/admin",{headers:{Cookie:`ako_session=${token}`}});assert.equal(reply.status,404);assert.equal(calls.length,0);
});
