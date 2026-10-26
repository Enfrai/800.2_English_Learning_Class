import assert from "node:assert/strict";
import { after, test } from "node:test";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";
const folder=await mkdtemp(join(tmpdir(),"ako-us009-unit-"));
const source=await readFile(new URL("../src/lib/club-information.ts",import.meta.url),"utf8");
await writeFile(join(folder,"club.mjs"),ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText);
const api=await import(pathToFileURL(join(folder,"club.mjs")));
after(()=>rm(folder,{recursive:true,force:true}));
const schedule={confirmed:true,day:"Tuesday",time:"11:00 am to 1:00 pm",venue:"Māori community room",address:"42 Example Road, Example Town"};
const today="2026-10-26";

test("default sample data is clearly marked and has a usable contact method",()=>{
  const info=api.clubInformation({});assert.equal(info.sample,true);assert.equal(info.day,api.SAMPLE_SCHEDULE.day);assert.equal(info.contact.href,"/ask-about-classes");assert.equal(info.greeting,null);
});
for(const input of [null,undefined,[],"wrong",7,{schedule:null},{schedule:[]}])test(`malformed config safely falls back ${JSON.stringify(input)}`,()=>assert.equal(api.clubInformation(input).sample,true));
test("confirmed class details preserve entered macrons",()=>{
  const info=api.clubInformation({schedule});assert.equal(info.sample,false);assert.equal(info.venue,"Māori community room");assert.equal(info.day,"Tuesday");assert.equal(info.address,schedule.address);
});
test("unconfirmed actual details never leak into sample output",()=>{
  const info=api.clubInformation({schedule:{...schedule,confirmed:false,venue:"Private room"},contact:{approved:false,type:"phone",value:"+64 21 555 0101"}});
  assert.equal(JSON.stringify(info).includes("Private room"),false);assert.equal(JSON.stringify(info).includes("555"),false);
});
for(const field of ["day","time","venue","address"])test(`missing ${field} prevents partial publication`,()=>{
  const info=api.clubInformation({schedule:{...schedule,[field]:" "}});assert.equal(info.sample,true);assert.equal(info.venue,api.SAMPLE_SCHEDULE.venue);
});
test("approved email is linked only after permission",()=>{
  const contact={approved:true,type:"email",value:"classes@example.test"};assert.deepEqual(api.clubInformation({contact}).contact,{label:"Email",value:contact.value,href:"mailto:classes@example.test"});
  assert.equal(api.clubInformation({contact:{...contact,approved:false}}).contact.href,"/ask-about-classes");
});
test("approved phone is readable with a safe dial link",()=>{
  const value="+64 (21) 555-0101";assert.deepEqual(api.clubInformation({contact:{approved:true,type:"phone",value}}).contact,{label:"Phone",value,href:"tel:+64215550101"});
});
for(const value of ["sam@","name@example..test",".name@example.test","name..last@example.test","name@-example.test","javascript:alert(1)","name@example.test\nBCC:private@example.test"])test(`invalid contact is not published: ${value}`,()=>assert.equal(api.clubInformation({contact:{approved:true,type:"email",value}}).contact.href,"/ask-about-classes"));
test("email special characters cannot inject mailto options",()=>{
  const info=api.clubInformation({contact:{approved:true,type:"email",value:"name?subject=other@example.test"}});assert.equal(info.contact.href,"mailto:name%3Fsubject%3Dother@example.test");
});
for(const value of ["123","+64+21 5550101","1234567890123456","tel:1234567"])test(`invalid phone is not published: ${value}`,()=>assert.equal(api.clubInformation({contact:{approved:true,type:"phone",value}}).contact.href,"/ask-about-classes"));
test("reviewed greeting preserves Māori characters",()=>{
  const greeting={text:"Kia ora",reviewer:"Test Kaiārahi",review_date:today};assert.equal(api.clubInformation({greeting},today).greeting,"Kia ora");
});
for(const greeting of [{text:"Kia ora"},{text:"Kia ora",reviewer:" ",review_date:today},{text:"Kia ora",reviewer:"Test",review_date:"2026-02-30"},{text:"Kia ora",reviewer:"Test",review_date:"2026-10-27"},{text:"Kia ora",reviewer:"Test",review_date:"26 Oct 2026"}])test(`unreviewed or invalid review hides greeting ${JSON.stringify(greeting)}`,()=>assert.equal(api.clubInformation({greeting},today).greeting,null));
test("long sentences and oversized class text are rejected",()=>{
  assert.equal(api.clubInformation({schedule:{...schedule,venue:Array(16).fill("word").join(" ")}}).sample,true);
  assert.equal(api.clubInformation({schedule:{...schedule,address:"a".repeat(251)}}).sample,true);
});
test("plain English accepts fifteen words but rejects sixteen",()=>{
  assert.equal(api.wordCount("  one  two\nthree  "),3);assert.equal(api.shortSentences(Array(15).fill("word").join(" ")),true);assert.equal(api.shortSentences(Array(16).fill("word").join(" ")),false);assert.equal(api.shortSentences("Short sentence. Another short sentence!"),true);
});
test("all fixed public copy meets the sentence limit",()=>{
  for(const [key,text] of Object.entries(api.PUBLIC_COPY))assert.equal(api.shortSentences(text),true,key);
});
test("checked-in demo config contains no approved contact or greeting",async()=>{
  const config=JSON.parse(await readFile(new URL("../src/content/club.json",import.meta.url),"utf8"));const info=api.clubInformation(config,today);assert.equal(info.sample,true);assert.equal(info.greeting,null);assert.equal(info.contact.href,"/ask-about-classes");
});
