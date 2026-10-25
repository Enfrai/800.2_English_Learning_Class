import assert from "node:assert/strict";
import { after, test } from "node:test";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const folder = await mkdtemp(join(tmpdir(), "ako-us007-unit-"));
for (const name of ["api", "lessons-api"]) {
  const source = await readFile(new URL(`../src/lib/${name}.ts`, import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText.replaceAll('"./api"', '"./api.mjs"');
  await writeFile(join(folder, name + ".mjs"), output);
}
const api = await import(pathToFileURL(join(folder, "lessons-api.mjs")));
after(() => rm(folder, { recursive: true, force: true }));
const id = "22222222-2222-4222-8222-222222222222";
const input = { title: "Copy of Māori", lesson_date: "2026-10-26", tags: ["transport"], description: "Notes" };

test("combined search trims and encodes title keyword and exact tag", async t => {
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.equal(url, "/api/staff/lesson/lessons?q=M%C4%81ori+%25%26&tag=health+%26+travel");
    assert.equal(init.credentials, "same-origin");
    assert.equal(init.cache, "no-store");
    assert.equal(init.headers.has("Authorization"), false);
    return Response.json([]);
  });
  assert.deepEqual(await api.listLessons({ q: "  Māori %&  ", tag: " health & travel " }), []);
});
for (const filters of [{}, { q: " " }, { tag: "  " }]) test(`empty filters retain the collection URL ${JSON.stringify(filters)}`, async t => {
  t.mock.method(globalThis, "fetch", async url => { assert.equal(url, "/api/staff/lesson/lessons"); return Response.json([]); });
  await api.listLessons(filters);
});
test("opening a copy draft uses GET and never saves", async t => {
  const draft = { title: "Copy of Māori", lesson_date: null, tags: ["transport"], materials: [] };
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.equal(url, `/api/staff/lesson/lessons/${id}/copy`);
    assert.equal(init.method || "GET", "GET");
    assert.equal(init.body, undefined);
    return Response.json(draft);
  });
  assert.deepEqual(await api.getCopyDraft(id), draft);
});
test("saving a copy sends edited fields and the explicitly retained source materials", async t => {
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.equal(url, `/api/staff/lesson/lessons/${id}/copy`);
    assert.equal(init.method, "POST");
    assert.deepEqual(JSON.parse(init.body), { ...input, material_ids: ["material-id"] });
    return Response.json({ id: "copy" }, { status: 201 });
  });
  assert.equal((await api.copyLesson(id, input, ["material-id"])).id, "copy");
});
test("empty retained list removes materials only from the copy request", async t => {
  t.mock.method(globalThis, "fetch", async (_, init) => {
    assert.deepEqual(JSON.parse(init.body).material_ids, []);
    return Response.json({ id: "copy" }, { status: 201 });
  });
  await api.copyLesson(id, input, []);
});
test("copy date validation exposes the exact field error", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: { errors: { lesson_date: "Lesson date is required" } } }, { status: 422 }));
  await assert.rejects(api.copyLesson(id, input, []), error => error.fields.lesson_date === "Lesson date is required");
});
test("changed source gives a useful conflict message", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "Source materials changed. Reopen the copy draft." }, { status: 409 }));
  await assert.rejects(api.copyLesson(id, input, []), /Source materials changed/);
});
test("expired staff login is handled consistently", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 401 }));
  await assert.rejects(api.getCopyDraft(id), api.LoginRequiredError);
});
