import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp,rm,cp,access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join,dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const web=dirname(dirname(fileURLToPath(import.meta.url)));
const mock=createServer((req,res)=>{
  if(req.url === '/session') {
    res.writeHead(200,{'Content-Type':'application/json','X-Session-Expires-At':new Date(Date.now()+1800000).toISOString()});
    return res.end(JSON.stringify({user_id:'11111111-1111-4111-8111-111111111111',display_name:'Test teacher',role:'teacher'}));
  }
  const valid=req.headers.cookie?.includes('ako_materials=valid');
  res.writeHead(valid?200:401,{'Content-Type':'application/json','Cache-Control':'no-store'});
  res.end(JSON.stringify(valid?{session_date:'2026-10-26',materials:[],message:'No materials for today'}:{detail:'Sign in again'}));
});
let app,temporary,output='';
try {
  await access(join(web,'.next/standalone/server.js'));
  mock.listen(0,'127.0.0.1');await once(mock,'listening');
  temporary=await mkdtemp(join(tmpdir(),'ako-us013-ui-'));
  await cp(join(web,'.next/standalone'),temporary,{recursive:true});
  await cp(join(web,'.next/static'),join(temporary,'.next/static'),{recursive:true});
  const reservation=createServer().listen(0,'127.0.0.1');await once(reservation,'listening');
  const port=reservation.address().port;await new Promise(resolve=>reservation.close(resolve));
  app=spawn(process.execPath,[join(temporary,'server.js')],{cwd:temporary,env:{...process.env,HOSTNAME:'127.0.0.1',PORT:String(port),ACCESS_API_URL:`http://127.0.0.1:${mock.address().port}`,USER_API_URL:`http://127.0.0.1:${mock.address().port}`},stdio:['ignore','pipe','pipe']});
  app.stdout.on('data',chunk=>output+=chunk);app.stderr.on('data',chunk=>output+=chunk);
  const base=`http://localhost:${port}`;
  let ready=false;
  for(let attempt=0;attempt<100;attempt++){
    if(app.exitCode!==null)throw new Error(output);
    try{ready=(await fetch(base+'/sign-in')).ok}catch{}
    if(ready)break;
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  if(!ready)throw new Error(output);
  const tests=spawn(process.execPath,['--test','--test-concurrency=1',join(web,'tests/materials-ui.test.mjs')],{cwd:web,env:{...process.env,US013_UI_BASE_URL:base},stdio:'inherit'});
  process.exitCode=(await once(tests,'exit'))[0]??1;
} finally {
  if(app&&app.exitCode===null){const done=once(app,'exit');app.kill();await done;}
  mock.closeAllConnections();if(mock.listening)await new Promise(resolve=>mock.close(resolve));
  if(temporary)await rm(temporary,{recursive:true,force:true});
}
