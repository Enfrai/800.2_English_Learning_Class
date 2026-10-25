/** Test the server-only cookie/Bearer adapter against an owned loopback stub. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { spawn } from 'node:child_process';
import { after, before, test } from 'node:test';

let upstream, app, base, seen = [], upstreamStatus = 200;
const token = 'test-only-cookie-token';
const path = '/api/staff/lesson/lessons/abcdef00-0000-0000-0000-000000000001/materials';
before(async () => {
  upstream = createServer(async (req, res) => {
    const chunks=[]; for await (const chunk of req) chunks.push(chunk);
    const bytes=Buffer.concat(chunks); const body=bytes.toString();
    seen.push({url:req.url, method:req.method, authorization:req.headers.authorization, cookie:req.headers.cookie, body,bytes,contentType:req.headers["content-type"]});
    res.writeHead(upstreamStatus, {'Content-Type':'application/json','Content-Disposition':'attachment; filename=fixture.pdf'});
    res.end(JSON.stringify(upstreamStatus === 200 ? {records:[]} : {detail:'You do not have permission'}));
  }).listen(0,'127.0.0.1'); await once(upstream,'listening');
  const reservation = createServer().listen(0,'127.0.0.1'); await once(reservation,'listening');
  const port = reservation.address().port; await new Promise(r=>reservation.close(r));
  base = `http://127.0.0.1:${port}`;
  app = spawn(process.execPath,['.next/standalone/server.js'],{env:{...process.env,PORT:String(port),HOSTNAME:'127.0.0.1',LESSON_API_URL:`http://127.0.0.1:${upstream.address().port}`,SESSION_PUBLIC_ORIGIN:base},stdio:'ignore'});
  for(let i=0;i<100;i++){try{if((await fetch(base)).ok)return;}catch{}await new Promise(r=>setTimeout(r,100));}
  throw new Error('Temporary Next server not ready');
});
after(async()=>{if(app && app.exitCode===null){app.kill();await once(app,'exit');}if(upstream)await new Promise(r=>upstream.close(r));});

test('anonymous denied without contacting Lesson',async()=>{seen=[];const r=await fetch(base+path);assert.equal(r.status,401);assert.equal(r.headers.get('cache-control'),'no-store');assert.equal(seen.length,0);});
test('cookie becomes Bearer only on the server',async()=>{seen=[];const r=await fetch(base+path,{headers:{Cookie:`ako_session=${token}`}});assert.equal(r.status,200);assert.equal(r.headers.get('cache-control'),'no-store');assert.equal(seen[0].authorization,`Bearer ${token}`);assert.equal(seen[0].cookie,undefined);assert.equal((await r.text()).includes(token),false);});
for(const origin of [undefined,'https://untrusted.example'])test(`mutation rejects ${origin?'foreign':'missing'} Origin`,async()=>{seen=[];const r=await fetch(base+path,{method:'POST',headers:{Cookie:`ako_session=${token}`,...(origin?{Origin:origin}:{})},body:'{}'});assert.equal(r.status,403);assert.equal(seen.length,0);});
test('same-origin mutation preserves request body',async()=>{seen=[];const r=await fetch(base+path,{method:'POST',headers:{Cookie:`ako_session=${token}`,Origin:base,'Content-Type':'application/json'},body:'{"learner_id":"fixture"}'});assert.equal(r.status,200);assert.equal(seen[0].body,'{"learner_id":"fixture"}');});
test('explicit browser Bearer does not override cookie identity',async()=>{seen=[];const r=await fetch(base+path,{headers:{Cookie:`ako_session=${token}`,Authorization:'Bearer another'}});assert.equal(r.status,401);assert.equal(seen.length,0);});
test('unrelated upstream paths cannot be proxied',async()=>{seen=[];const r=await fetch(base+'/api/staff/lesson/admin',{headers:{Cookie:`ako_session=${token}`}});assert.equal(r.status,404);assert.equal(seen.length,0);});
test('backend role denial remains 403 and no-store',async()=>{upstreamStatus=403;const r=await fetch(base+path,{headers:{Cookie:`ako_session=${token}`}});assert.equal(r.status,403);assert.equal(r.headers.get('cache-control'),'no-store');upstreamStatus=200;});

 test('multipart upload preserves binary bytes and boundary',async()=>{
 seen=[];const body=Buffer.from([0,255,128,13,10,65]);
 const r=await fetch(base+path,{method:'POST',headers:{Cookie:`ako_session=${token}`,Origin:base,'Content-Type':'multipart/form-data; boundary=fixture'},body});
 assert.equal(r.status,200);assert.deepEqual(seen[0].bytes,body);assert.equal(seen[0].contentType,'multipart/form-data; boundary=fixture');
 });
 test('download disposition is retained',async()=>{const r=await fetch(base+'/api/staff/lesson/materials/abcdef00-0000-0000-0000-000000000001/download',{headers:{Cookie:`ako_session=${token}`}});assert.equal(r.status,200);assert.equal(r.headers.get('content-disposition'),'attachment; filename=fixture.pdf');});
 test('delete 204 keeps an empty body',async()=>{upstreamStatus=204;try{const r=await fetch(base+'/api/staff/lesson/lessons/abcdef00-0000-0000-0000-000000000001',{method:'DELETE',headers:{Cookie:`ako_session=${token}`,Origin:base}});assert.equal(r.status,204);assert.equal(await r.text(),'');}finally{upstreamStatus=200;}});

test('oversized adapter request is rejected before reaching Lesson',async()=>{
 seen=[];
 const response=await fetch(base+path,{method:'POST',headers:{Cookie:`ako_session=${token}`,Origin:base,'Content-Type':'application/octet-stream'},body:Buffer.alloc(11*1024*1024+1)});
 assert.equal(response.status,413);assert.equal(seen.length,0);
});

test('search query parameters pass through the cookie adapter unchanged',async()=>{
  seen=[];
  const response=await fetch(base+'/api/staff/lesson/lessons?q=M%C4%81ori%25&tag=transport',{headers:{Cookie:`ako_session=${token}`}});
  assert.equal(response.status,200);
  assert.equal(seen[0].url,'/lessons?q=M%C4%81ori%25&tag=transport');
});
test('copy draft and save keep staff authentication and same-origin write protection',async()=>{
  const copyPath=path.replace('/materials','/copy');
  seen=[];
  assert.equal((await fetch(base+copyPath)).status,401);
  assert.equal(seen.length,0);
  assert.equal((await fetch(base+copyPath,{headers:{Cookie:`ako_session=${token}`}})).status,200);
  assert.equal(seen[0].method,'GET');
  seen=[];
  assert.equal((await fetch(base+copyPath,{method:'POST',headers:{Cookie:`ako_session=${token}`,Origin:'https://untrusted.example'},body:'{}'})).status,403);
  assert.equal(seen.length,0);
  const body='{"title":"Copy of lesson","lesson_date":"2026-10-26","tags":["health"],"material_ids":[]}';
  const saved=await fetch(base+copyPath,{method:'POST',headers:{Cookie:`ako_session=${token}`,Origin:base,'Content-Type':'application/json'},body});
  assert.equal(saved.status,200);assert.equal(seen[0].body,body);
  assert.equal(seen[0].authorization,`Bearer ${token}`);
});
