/* Verify history cookie forwarding, date queries, authorization and path restrictions.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { once } from "node:events";
import { spawn } from "node:child_process";
import { before, after, test } from "node:test";
let upstream, app, base, calls = [], status = 200;
const path = "/api/staff/access/learners/11111111-1111-4111-8111-111111111111/attendance-history", token = "report-fixture-token";
const content = () => JSON.stringify({ learner: { id:"11111111-1111-4111-8111-111111111111", name:"Māia Example" }, sessions:[], present_count:0, total_count:0, has_records:false });
before(async () => {
  upstream = createServer(async (req, res) => {
    let body = ""; for await (const chunk of req) body += chunk;
    calls.push({ path: req.url, method: req.method, headers: req.headers, body });
    res.writeHead(status, { "Content-Type": "application/json" });
    res.end(status === 200 ? content() : JSON.stringify({ detail: "You do not have permission" }));
  }).listen(0, "127.0.0.1"); await once(upstream, "listening");
  const reservation = createServer().listen(0, "127.0.0.1"); await once(reservation, "listening");
  const port = reservation.address().port; await new Promise(resolve => reservation.close(resolve)); base = `http://127.0.0.1:${port}`;
  app = spawn(process.execPath, [".next/standalone/server.js"], { env: { ...process.env, PORT: String(port), HOSTNAME: "127.0.0.1", ACCESS_API_URL: `http://127.0.0.1:${upstream.address().port}`, SESSION_PUBLIC_ORIGIN: base }, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(base)).ok) return; } catch {} await new Promise(resolve => setTimeout(resolve, 100)); }
  throw new Error("Next server did not start");
});
after(async () => { if (app && app.exitCode === null) { app.kill(); await once(app, "exit"); } if (upstream) await new Promise(resolve => upstream.close(resolve)); });
async function read(headers={},suffix="") { return fetch(base+path+suffix,{headers}); }
test("anonymous history denied without upstream call",async()=>{calls=[];assert.equal((await read()).status,401);assert.equal(calls.length,0);});
test("duplicate session cookies denied",async()=>{calls=[];assert.equal((await read({Cookie:`ako_session=${token}; ako_session=other`})).status,401);assert.equal(calls.length,0);});
test("browser Bearer cannot replace cookie identity",async()=>{calls=[];assert.equal((await read({Cookie:`ako_session=${token}`,Authorization:"Bearer forged"})).status,401);assert.equal(calls.length,0);});
test("authenticated GET preserves dates and uses only server Bearer",async()=>{
  calls=[];const reply=await read({Cookie:`ako_session=${token}`} ,"?start_date=2026-10-20&end_date=2026-10-24");
  assert.equal(reply.status,200);assert.deepEqual(await reply.json(),JSON.parse(content()));assert.equal(reply.headers.get("cache-control"),"no-store");assert.equal(reply.headers.get("x-content-type-options"),"nosniff");
  assert.equal(calls[0].path,"/learners/11111111-1111-4111-8111-111111111111/attendance-history?start_date=2026-10-20&end_date=2026-10-24");assert.equal(calls[0].method,"GET");assert.equal(calls[0].headers.authorization,`Bearer ${token}`);assert.equal(calls[0].headers.cookie,undefined);
});
for(const code of [401,403,404,422,503])test(`history upstream ${code} is preserved`,async()=>{status=code;try{const reply=await read({Cookie:`ako_session=${token}`});assert.equal(reply.status,code);assert.equal(reply.headers.get("cache-control"),"no-store");}finally{status=200;}});
for(const suffix of ["/admin","/../../secret"])test(`history does not proxy unrelated path ${suffix}`,async()=>{calls=[];const reply=await read({Cookie:`ako_session=${token}`},suffix);assert.equal(reply.status,404);assert.equal(calls.length,0);});
