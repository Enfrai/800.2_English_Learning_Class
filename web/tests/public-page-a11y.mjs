import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
const web=dirname(dirname(fileURLToPath(import.meta.url))),base=process.env.US009_BASE_URL;
if(!base)throw new Error("Run npm run test:public-a11y after npm run build");
const folder=process.env.AKO_TEST_REPORTS?join(process.env.AKO_TEST_REPORTS,"web"):resolve(web,"../test-results/web");await mkdir(folder,{recursive:true});
const summary=[];
const summaryPath=join(folder,"us009-accessibility-summary.json");
await writeFile(summaryPath,JSON.stringify({status:"running",results:[]}));
try {
for(const [name,path] of [["home","/"]]){
  const output=join(folder,`us009-${name}-lighthouse.json`);
  await writeFile(output,JSON.stringify({status:"running"}));
  const env={...process.env,...(process.env.BROWSER_CHANNEL==="chromium"?{CHROME_PATH:chromium.executablePath()}:{})};
  const child=spawn(process.execPath,[join(web,"node_modules/lighthouse/cli/index.js"),base+path,"--only-categories=accessibility","--form-factor=mobile","--output=json",`--output-path=${output}`,"--chrome-flags=--headless --no-sandbox --disable-dev-shm-usage","--quiet"],{cwd:web,env,stdio:"inherit"});
  assert.equal((await once(child,"exit"))[0],0,`Lighthouse failed: ${name}`);
  const report=JSON.parse(await readFile(output,"utf8")),score=Math.round(report.categories.accessibility.score*100);
  const failed=Object.values(report.audits).filter(a=>a.score===0).map(a=>({id:a.id,title:a.title}));
  summary.push({page:path,score,failed});console.log(`${name}: Lighthouse accessibility ${score}/100`);assert.ok(score>=90,JSON.stringify(failed));
}
await writeFile(summaryPath,JSON.stringify({status:"passed",results:summary},null,2)+"\n");
} catch (error) {
  await writeFile(summaryPath,JSON.stringify({status:"failed",results:summary,message:String(error)},null,2)+"\n");
  throw error;
}
