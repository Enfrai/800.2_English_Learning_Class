import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';
const folder = await mkdtemp(join(tmpdir(), 'ako-us013-unit-'));
const source = await readFile(new URL('../src/lib/materials-api.ts',import.meta.url),'utf8');
await writeFile(join(folder,'materials.mjs'),ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText);
const api = await import(pathToFileURL(join(folder,'materials.mjs')));
after(()=>rm(folder,{recursive:true,force:true}));
test('materials use the learner cookie and disable cache without staff authorization',async t=>{
  const data={session_date:'2026-10-26',materials:[{id:'file',file_name:'Māori.pdf',file_size:10}],message:''};
  t.mock.method(globalThis,'fetch',async (url,init)=>{
    assert.equal(url,'/api/access/learner/materials');
    assert.equal(init.credentials,'same-origin');assert.equal(init.cache,'no-store');
    assert.equal(init.headers,undefined);
    return Response.json(data);
  });
  assert.deepEqual(await api.getMaterials(),data);
});
test('expired or absent grant asks for a new sign-in',async t=>{
  t.mock.method(globalThis,'fetch',async()=>Response.json({detail:'expired'},{status:401}));
  await assert.rejects(api.getMaterials(),api.SignInRequired);
});
for(const status of [403,404,500,503]) test(`HTTP ${status} displays a retryable error`,async t=>{
  t.mock.method(globalThis,'fetch',async()=>new Response(null,{status}));
  await assert.rejects(api.getMaterials(),/Materials are not available/);
});
test('network failure is passed to retry UI',async t=>{
  t.mock.method(globalThis,'fetch',async()=>{throw new Error('offline')});
  await assert.rejects(api.getMaterials(),/offline/);
});
test('download encodes the material id and never contains a grant',()=>{
  assert.equal(api.materialDownload('a/b?x'),'/api/access/learner/materials/a%2Fb%3Fx/download');
});
