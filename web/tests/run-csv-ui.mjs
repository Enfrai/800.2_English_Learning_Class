/** Isolated component harness: temporary Next app, mocked API, no production routes changed. */
import { mkdtemp, cp, mkdir, writeFile, symlink, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "node:net";
import { spawn } from "node:child_process";
import { once } from "node:events";
const web = dirname(dirname(fileURLToPath(import.meta.url)));
const temp = await mkdtemp(join(tmpdir(), "us017-ui-"));
let server;
let output = "";
async function command(args) {
  const child = spawn(process.execPath, args, {cwd: temp, env: process.env, stdio: "inherit"});
  const [code] = await once(child, "exit");
  if (code !== 0) throw new Error(`Verification failed (${code})`);
}
try {
  for (const file of ["package.json", "tsconfig.json", "next-env.d.ts"]) await cp(join(web,file), join(temp,file));
  await symlink(join(web,"node_modules"),join(temp,"node_modules"),"dir");
  await mkdir(join(temp,"src/app"),{recursive:true});
  await mkdir(join(temp,"src/components/learners"),{recursive:true});
  await cp(join(web,"src/components"),join(temp,"src/components"),{recursive:true});
  await cp(join(web,"src/lib"),join(temp,"src/lib"),{recursive:true});
  await cp(join(web,"src/styles"),join(temp,"src/styles"),{recursive:true});
  await writeFile(join(temp,"src/app/layout.tsx"),'import "@/styles/ako/tokens.css"; import "@/styles/ako/components.css"; export default function Layout({children}:{children:React.ReactNode}) {return <html lang="en"><body><main className="page">{children}</main></body></html>}');
  await writeFile(join(temp,"src/app/page.tsx"),'export default function Page(){return <h1>Sign in</h1>}');
  await mkdir(join(temp,"src/app/test-csv"));
  await writeFile(join(temp,"src/app/test-csv/page.tsx"),'import CsvUpload from "@/components/learners/csv-upload"; export default function Page(){return <CsvUpload/>}');
  await mkdir(join(temp,"src/app/test-learners"));
  await writeFile(join(temp,"src/app/test-learners/page.tsx"),'import LearnersScreen from "@/components/learners/learners-screen"; import SessionShell from "@/components/session-shell"; export default function Page(){return <SessionShell layout="kit"><LearnersScreen/></SessionShell>}');
  const reservation = createServer().listen(0,"127.0.0.1"); await once(reservation,"listening");
  const port = reservation.address().port; await new Promise(resolve=>reservation.close(resolve));
  server = spawn(process.execPath,[join(web,"node_modules/next/dist/bin/next"),"dev","--hostname","127.0.0.1","--port",String(port)],{cwd:temp,env:{...process.env,NEXT_TELEMETRY_DISABLED:"1"},stdio:["ignore","pipe","pipe"]});
  server.stdout.on("data",chunk=>output+=chunk); server.stderr.on("data",chunk=>output+=chunk);
  const base=`http://127.0.0.1:${port}`;
  let ready=false;
  for(let i=0;i<120;i++) {
    if(server.exitCode!==null) throw new Error(output);
    try{ready=(await fetch(`${base}/test-csv`)).ok;}catch{}
    if(ready)break;
    await new Promise(resolve=>setTimeout(resolve,250));
  }
  if(!ready)throw new Error(output);
  const tests=spawn(process.execPath,["--test","--test-concurrency=1",join(web,"tests/csv-upload.test.mjs"),join(web,"tests/learner-import-ui.test.mjs")],{cwd:web,env:{...process.env,US017_UI_URL:base},stdio:"inherit"});
  const [code]=await once(tests,"exit");
  if(code!==0)throw new Error(`Browser tests failed (${code})`);
  await command([join(web,"node_modules/typescript/bin/tsc"),"--noEmit","--incremental","false"]);
  console.log("Isolated component TypeScript check passed");
} finally {
  if(server && server.exitCode===null){const stopped=once(server,"exit");server.kill("SIGTERM");await stopped;}
  await rm(temp,{recursive:true,force:true});
}
