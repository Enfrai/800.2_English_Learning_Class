/** Real browser component tests in a disposable Next app; API responses are mocked. */
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, cp, symlink, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:net';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { chromium } from 'playwright';

const web = dirname(dirname(fileURLToPath(import.meta.url)));
const temp = await mkdtemp(join(tmpdir(), 'ako-enquiry-ui-'));
let server, browser, logs = '', passed = 0;
try {
  await mkdir(join(temp, 'app'));
  await cp(join(web, 'src/components/enquiries'), join(temp, 'app/enquiries'), { recursive: true });
  await symlink(join(web, 'node_modules'), join(temp, 'node_modules'));
  await cp(join(web, 'package.json'), join(temp, 'package.json'));
  await writeFile(join(temp, 'app/layout.tsx'), 'export default function Layout({children}:{children:React.ReactNode}) { return <html lang="en"><body>{children}</body></html>; }');
  await writeFile(join(temp, 'app/page.tsx'), 'import Form from "./enquiries/public-enquiry-form"; export default function Page(){return <Form/>;}');
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
  async function run(name, test) {
    const page = await browser.newPage({viewport:{width:360,height:800}});
    let calls = [];
    await page.route('**/api/user/enquiries', async route => { calls.push(route.request()); await route.fulfill({status:201,json:{message:'Thank you, the club will contact you'}}); });
    await page.goto(base);
    try { await test(page,calls); passed++; console.log(`PASS ${name}`); } finally { await page.close(); }
  }
  async function fill(page) {
    await page.getByLabel('Name (required)',{exact:true}).fill('Test Visitor');
    await page.getByLabel('Contact (required)',{exact:true}).fill('visitor@example.test');
    await page.getByRole('checkbox').check();
  }
  const send = page => page.getByRole('button',{name:'Send enquiry'}).click();
  await run('AC1 public success and clear', async(p,c)=>{await fill(p);await send(p);await p.getByRole('status').filter({hasText:'Thank you, the club will contact you'}).waitFor();assert.equal(c.length,1);assert.equal(c[0].headers().authorization,undefined);assert.equal(c[0].postDataJSON().consent,true);assert.equal(await p.getByLabel('Name (required)',{exact:true}).inputValue(),'');});
  await run('AC2 email error no request',async(p,c)=>{await fill(p);await p.getByLabel('Contact (required)',{exact:true}).fill('sam@');await send(p);await p.getByText('Please enter a valid email address',{exact:true}).waitFor();assert.equal(c.length,0);assert.equal(await p.locator('[name=contact]').evaluate(e=>e===document.activeElement),true);});
  await run('AC3 consent required',async(p,c)=>{await fill(p);await p.getByRole('checkbox').uncheck();await send(p);await p.getByText('Please consent to being contacted by the club',{exact:true}).waitFor();assert.equal(c.length,0);});
  await run('AC4 501 rejected 500 Unicode accepted',async(p,c)=>{await fill(p);await p.getByRole('textbox',{name:/Message/}).fill('😀'.repeat(501));await send(p);await p.getByText('Message must be 500 characters or fewer',{exact:true}).waitFor();assert.equal(c.length,0);await p.getByRole('textbox',{name:/Message/}).fill('😀'.repeat(500));await send(p);await p.getByText('Thank you, the club will contact you',{exact:true}).waitFor();assert.equal(c.length,1);});
  await run('phone and required name',async(p,c)=>{await fill(p);await p.getByLabel('Name (required)',{exact:true}).fill(' ');await send(p);assert.equal(c.length,0);await p.getByLabel('Name (required)',{exact:true}).fill('Test');await p.getByLabel('Email/Phone').selectOption('phone');await p.getByLabel('Contact (required)',{exact:true}).fill('+64 21 555 0101');await send(p);await p.getByText('Thank you, the club will contact you',{exact:true}).waitFor();assert.equal(c[0].postDataJSON().contact_type,'phone');});
  for (const [field, detail] of [
    ['contact', 'Please enter a valid email address'],
    ['name', 'Name must contain 1 to 150 characters'],
    ['message', 'Message must be 500 characters or fewer'],
    ['consent', 'Please consent to being contacted by the club'],
  ]) {
    await run(`server 422 restores ${field} focus after enabling`, async p => {
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      await p.route('**/api/user/enquiries', async route => {
        await gate;
        await route.fulfill({status:422,json:{detail}});
      });
      await fill(p); await send(p);
      assert.equal(await p.locator(`[name="${field}"]`).isDisabled(), true);
      release();
      await p.getByText(detail,{exact:true}).waitFor();
      await p.waitForFunction(name => {
        const input = document.querySelector(`[name="${name}"]`);
        return input && !input.matches(':disabled') && document.activeElement === input;
      }, field);
      assert.equal(await p.locator(`[name="${field}"]`).getAttribute('aria-invalid'), 'true');
      // The error remains available to assistive technology and the input stays editable.
      assert.ok(await p.locator(`[name="${field}"]`).getAttribute('aria-describedby'));
    });
  }
  await run('server failure sanitized',async(p)=>{await p.route('**/api/user/enquiries',r=>r.fulfill({status:500,json:{detail:'PRIVATE DATABASE ERROR'}}));await fill(p);await send(p);await p.getByText('Unable to send your enquiry. Please try again later.',{exact:true}).waitFor();assert.ok(!(await p.locator('body').innerText()).includes('PRIVATE'));});
  await run('network failure',async(p)=>{await p.route('**/api/user/enquiries',r=>r.abort());await fill(p);await send(p);await p.getByText('We could not confirm your submission. Please try again later.',{exact:true}).waitFor();});
  await run('duplicate submission and loading',async(p)=>{let requests=0, release;const gate=new Promise(r=>release=r);await p.route('**/api/user/enquiries',async r=>{requests++;await gate;await r.fulfill({status:201,json:{}});});await fill(p);await p.locator('form').evaluate(f=>{f.requestSubmit();f.requestSubmit();});await p.getByRole('button',{name:'Sending…'}).waitFor();assert.equal(await p.getByRole('button',{name:'Sending…'}).isDisabled(),true);release();await p.getByText('Thank you, the club will contact you',{exact:true}).waitFor();assert.equal(requests,1);});
  await run('mobile labels keyboard and no overflow',async(p)=>{assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);for(const name of ['name','contact','message','consent']) assert.equal(await p.locator(`[name=${name}]`).evaluate(e=>e.labels.length>0),true);await p.keyboard.press('Tab');assert.equal(await p.locator('[name=name]').evaluate(e=>e===document.activeElement),true);});
  console.log(`${passed} tests passed`);
} catch(error) { console.error(logs.slice(-2000)); throw error; }
finally { await browser?.close(); if(server && server.exitCode===null) {server.kill('SIGTERM');await once(server,'exit');} await rm(temp,{recursive:true,force:true}); }
