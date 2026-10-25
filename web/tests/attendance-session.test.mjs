/** Test the attendance and classroom cookie/Bearer adapter against a loopback stub.
 * Updated: Shuohui Liu, 26 Oct 2026
 */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { spawn } from 'node:child_process';
import { after, before, test } from 'node:test';

let upstream, app, base, seen = [], upstreamStatus = 200;
const token = 'test-only-cookie-token';
const path = '/api/staff/access/sessions/abcdef00-0000-0000-0000-000000000001/attendance';
before(async () => {
  upstream = createServer(async (req, res) => {
    let body = ''; for await (const chunk of req) body += chunk;
    seen.push({url:req.url, method:req.method, authorization:req.headers.authorization, cookie:req.headers.cookie, body});
    res.writeHead(upstreamStatus, {'Content-Type':'application/json'});
    res.end(JSON.stringify(upstreamStatus === 200 ? {records:[]} : {detail:'You do not have permission'}));
  }).listen(0,'127.0.0.1'); await once(upstream,'listening');
  const reservation = createServer().listen(0,'127.0.0.1'); await once(reservation,'listening');
  const port = reservation.address().port; await new Promise(r=>reservation.close(r));
  base = `http://127.0.0.1:${port}`;
  app = spawn(process.execPath,['.next/standalone/server.js'],{env:{...process.env,PORT:String(port),HOSTNAME:'127.0.0.1',ACCESS_API_URL:`http://127.0.0.1:${upstream.address().port}`,SESSION_PUBLIC_ORIGIN:base},stdio:'ignore'});
  for(let i=0;i<100;i++){try{if((await fetch(base)).ok)return;}catch{}await new Promise(r=>setTimeout(r,100));}
  throw new Error('Temporary Next server not ready');
});
after(async()=>{if(app && app.exitCode===null){app.kill();await once(app,'exit');}if(upstream)await new Promise(r=>upstream.close(r));});

test('anonymous denied without contacting Attendance',async()=>{seen=[];const r=await fetch(base+path);assert.equal(r.status,401);assert.equal(r.headers.get('cache-control'),'no-store');assert.equal(seen.length,0);});
test('cookie becomes Bearer only on the server',async()=>{seen=[];const r=await fetch(base+path,{headers:{Cookie:`ako_session=${token}`}});assert.equal(r.status,200);assert.equal(r.headers.get('cache-control'),'no-store');assert.equal(seen[0].authorization,`Bearer ${token}`);assert.equal(seen[0].cookie,undefined);assert.equal((await r.text()).includes(token),false);});
for(const origin of [undefined,'https://untrusted.example'])test(`mutation rejects ${origin?'foreign':'missing'} Origin`,async()=>{seen=[];const r=await fetch(base+path,{method:'POST',headers:{Cookie:`ako_session=${token}`,...(origin?{Origin:origin}:{})},body:'{}'});assert.equal(r.status,403);assert.equal(seen.length,0);});
test('same-origin mutation preserves request body',async()=>{seen=[];const r=await fetch(base+path,{method:'POST',headers:{Cookie:`ako_session=${token}`,Origin:base,'Content-Type':'application/json'},body:'{"learner_id":"fixture"}'});assert.equal(r.status,200);assert.equal(seen[0].body,'{"learner_id":"fixture"}');});
test('explicit browser Bearer does not override cookie identity',async()=>{seen=[];const r=await fetch(base+path,{headers:{Cookie:`ako_session=${token}`,Authorization:'Bearer another'}});assert.equal(r.status,401);assert.equal(seen.length,0);});
test('unrelated upstream paths cannot be proxied',async()=>{seen=[];const r=await fetch(base+'/api/staff/access/admin',{headers:{Cookie:`ako_session=${token}`}});assert.equal(r.status,404);assert.equal(seen.length,0);});
test('backend role denial remains 403 and no-store',async()=>{upstreamStatus=403;const r=await fetch(base+path,{headers:{Cookie:`ako_session=${token}`}});assert.equal(r.status,403);assert.equal(r.headers.get('cache-control'),'no-store');upstreamStatus=200;});

test('session list and classroom detail pass the cookie bridge',async()=>{
  for(const suffix of ['', '/abcdef00-0000-0000-0000-000000000001']){
    seen=[];
    const reply=await fetch(base+'/api/staff/access/sessions'+suffix,{headers:{Cookie:`ako_session=${token}`}});
    assert.equal(reply.status,200);assert.equal(seen[0].authorization,`Bearer ${token}`);
  }
});
test('class creation and lesson linking require same-origin writes',async()=>{
  for(const [suffix,method] of [['/today','POST'],['','POST'],['/abcdef00-0000-0000-0000-000000000001/lesson','PUT']]){
    seen=[];
    const url=base+'/api/staff/access/sessions'+suffix;
    assert.equal((await fetch(url,{method,headers:{Cookie:`ako_session=${token}`},body:'{}'})).status,403);
    assert.equal(seen.length,0);
    assert.equal((await fetch(url,{method,headers:{Cookie:`ako_session=${token}`,Origin:base},body:'{}'})).status,200);
  }
});
test('deleting a class preserves an empty 204 response',async()=>{
  upstreamStatus=204;
  try{
    const reply=await fetch(base+'/api/staff/access/sessions/abcdef00-0000-0000-0000-000000000001',{method:'DELETE',headers:{Cookie:`ako_session=${token}`,Origin:base}});
    assert.equal(reply.status,204);assert.equal(await reply.text(),'');
  }finally{upstreamStatus=200;}
});

test('class lesson selection uses the staff cookie bridge and same-origin protection',async()=>{
  const lessonPath=path.replace('/attendance','/lesson');
  seen=[];
  const denied=await fetch(base+lessonPath,{method:'PUT',headers:{Cookie:`ako_session=${token}`},body:'{}'});
  assert.equal(denied.status,403);assert.equal(seen.length,0);
  const response=await fetch(base+lessonPath,{method:'PUT',headers:{Cookie:`ako_session=${token}`,Origin:base,'Content-Type':'application/json'},body:'{"lesson_id":null}'});
  assert.equal(response.status,200);assert.equal(seen[0].authorization,`Bearer ${token}`);
  assert.equal(seen[0].body,'{"lesson_id":null}');
});
