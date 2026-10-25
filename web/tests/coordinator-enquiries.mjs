/** Real browser component tests in a disposable Next app; API responses are mocked. */
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, cp, readFile, symlink, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:net';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { chromium } from 'playwright';

const web = dirname(dirname(fileURLToPath(import.meta.url)));
const temp = await mkdtemp(join(tmpdir(), 'ako-enquiry-list-'));
let server, browser, logs = '', passed = 0;
try {
  await mkdir(join(temp, 'app'));
  await mkdir(join(temp, 'lib'));
  await writeFile(join(temp, 'app/session-context.tsx'), (await readFile(join(web, 'src/components/session-context.tsx'), 'utf8')).replace('@/lib/session', '../lib/session'));
  await cp(join(web, 'src/lib/session.ts'), join(temp, 'lib/session.ts'));
  await cp(join(web, 'src/components/enquiries'), join(temp, 'app/enquiries'), { recursive: true });
  await symlink(join(web, 'node_modules'), join(temp, 'node_modules'));
  await cp(join(web, 'package.json'), join(temp, 'package.json'));
  await writeFile(join(temp, 'app/layout.tsx'), 'export default function Layout({children}:{children:React.ReactNode}) { return <html lang="en"><body>{children}</body></html>; }');
  await writeFile(join(temp, 'app/page.tsx'), `"use client";
import {useEffect, useState} from "react";
import Form from "./enquiries/coordinator-enquiries";
import {SessionContext} from "./session-context";
export default function Page(){
 const [session,setSession]=useState<any>(null);
 useEffect(()=>{setSession((window as any).__session);(window as any).__setSession=setSession;},[]);
 return <SessionContext.Provider value={session}><Form/></SessionContext.Provider>;
}`);
  const reservation = createServer().listen(0, '127.0.0.1');
  await once(reservation, 'listening');
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  server = spawn(process.execPath, [join(web, 'node_modules/next/dist/bin/next'), 'dev', temp, '--hostname', '127.0.0.1', '--port', String(port)], { env: {...process.env, NEXT_TELEMETRY_DISABLED:'1'}, stdio:['ignore','pipe','pipe'] });
  server.stdout.on('data', x => logs += x); server.stderr.on('data', x => logs += x);
  const base = `http://127.0.0.1:${port}`;
  let ready = false;
  for(let i=0;i<90;i++) { try { if((await fetch(base)).ok) {ready=true;break;} } catch {} await new Promise(r=>setTimeout(r,500)); }
  assert.ok(ready, logs);
  browser = await chromium.launch({ channel:'chrome', headless:true });
  const record = (i=1) => ({id:String(i),name:`Visitor ${i}`,contact:`visitor${i}@example.test`,message:'Hello',created_at:'2026-10-24T01:00:00Z'});
  async function run(name, test, token='coordinator') {
    const page = await browser.newPage({viewport:{width:360,height:800}});
    await page.addInitScript(role=>{window.__session=role?{user_id:role,role,display_name:role,expiresAt:Date.now()+1800000}:null;},token);
    if(token) await page.context().addCookies([{name:'ako_session',value:'test-cookie',url:base,httpOnly:true,sameSite:'Lax'}]);
    try { await test(page); passed++; console.log(`PASS ${name}`); } finally { await page.close(); }
  }
  const mock = (page, handler) => page.route('**/api/user/enquiries?*', handler);
  const listReady = page => page.getByRole('list',{name:'Enquiries'}).waitFor();
  await run('Coordinator list fields and server ordering',async p=>{
    await mock(p,r=>{assert.equal(r.request().headers().authorization,undefined);assert.ok(r.request().headers().cookie.includes('ako_session=test-cookie'));return r.fulfill({json:[record(2),record(1)]});});
    await p.goto(base);await listReady(p);assert.deepEqual(await p.locator('li h2').allTextContents(),['Visitor 2','Visitor 1']);
    assert.equal(await p.locator('time').first().getAttribute('datetime'),'2026-10-24T01:00:00Z');
    assert.ok((await p.locator('body').innerText()).includes('visitor2@example.test'));
  });
  await run('Anonymous makes no private request',async p=>{let calls=0;await mock(p,r=>{calls++;return r.fulfill({json:[]});});await p.goto(base);await p.getByRole('link',{name:'Log in',exact:true}).waitFor();assert.equal(calls,0);assert.equal(await p.locator('li').count(),0);},null);
  await run('Teacher 403 body never displayed',async p=>{await mock(p,r=>r.fulfill({status:403,json:[record()]}));await p.goto(base);await p.getByText('You do not have permission',{exact:true}).waitFor();assert.equal(await p.locator('li').count(),0);assert.ok(!(await p.locator('body').innerText()).includes('visitor1'));},'teacher');
  await run('401 clears private data without reading HttpOnly credentials',async p=>{await mock(p,r=>r.fulfill({status:401,json:[record()]}));await p.goto(base);await p.getByRole('link',{name:'Log in',exact:true}).waitFor();assert.equal(await p.locator('li').count(),0);});
  await run('pagination and empty last page',async p=>{await mock(p,r=>{const u=new URL(r.request().url());assert.equal(u.searchParams.get('limit'),'20');return r.fulfill({json:u.searchParams.get('offset')==='0'?Array.from({length:20},(_,i)=>record(i)):[]});});await p.goto(base);await listReady(p);await p.getByRole('button',{name:'Next',exact:true}).click();await p.getByText('No enquiries on this page.').waitFor();assert.equal(await p.getByRole('button',{name:'Next',exact:true}).isDisabled(),true);await p.getByRole('button',{name:'Previous',exact:true}).click();await listReady(p);assert.equal(await p.locator('li').count(),20);});
  await run('empty first page',async p=>{await mock(p,r=>r.fulfill({json:[]}));await p.goto(base);await p.getByText('No enquiries on this page.').waitFor();assert.equal(await p.getByRole('button',{name:'Previous',exact:true}).isDisabled(),true);});
  await run('500 sanitized and retry',async p=>{let n=0;await mock(p,r=>r.fulfill(++n===1?{status:500,json:{detail:'PRIVATE'}}:{json:[record()]}));await p.goto(base);await p.getByRole('button',{name:'Retry'}).waitFor();assert.ok(!(await p.locator('body').innerText()).includes('PRIVATE'));await p.getByRole('button',{name:'Retry'}).click();await listReady(p);});
  await run('network failure',async p=>{await mock(p,r=>r.abort());await p.goto(base);await p.getByRole('button',{name:'Retry'}).waitFor();});
  await run('malformed data rejected',async p=>{await mock(p,r=>r.fulfill({json:[{...record(),created_at:'invalid'}]}));await p.goto(base);await p.getByRole('button',{name:'Retry'}).waitFor();assert.equal(await p.locator('li').count(),0);});
  await run('revoked access removes old data',async p=>{let n=0;await mock(p,r=>r.fulfill(++n===1?{json:[record()]}:{status:403,json:{}}));await p.goto(base);await listReady(p);await p.getByRole('button',{name:'Refresh'}).click();await p.getByText('You do not have permission',{exact:true}).waitFor();assert.ok(!(await p.locator('body').innerText()).includes('visitor1'));});
  await run('account change during request rejects stale response',async p=>{let release;const gate=new Promise(r=>release=r);await mock(p,async r=>{await gate;await r.fulfill({json:[record()]});});await p.goto(base);await p.getByText('Loading enquiries…').waitFor();await p.evaluate(()=>window.__setSession(null));release();await p.getByRole('link',{name:'Log in',exact:true}).waitFor();assert.equal(await p.locator('li').count(),0);});
  await run('mobile and HTML content remains text',async p=>{await mock(p,r=>r.fulfill({json:[{...record(),message:'<img src=x onerror=alert(1)>',contact:'x'.repeat(255)}]}));await p.goto(base);await listReady(p);assert.equal(await p.locator('li img').count(),0);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.equal(await p.getByRole('navigation',{name:'Enquiry pages'}).count(),1);});
  console.log(`${passed} tests passed`);
} catch(error) { console.error(logs.slice(-2000)); throw error; }
finally { await browser?.close(); if(server && server.exitCode===null) {server.kill('SIGTERM');await once(server,'exit');} await rm(temp,{recursive:true,force:true}); }
