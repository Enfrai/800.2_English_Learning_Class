import assert from "node:assert/strict";
import { after, test } from "node:test";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const folder = await mkdtemp(join(tmpdir(), "us006-client-"));
for (const name of ["api", "lessons-api"]) {
  const source = await readFile(new URL(`../src/lib/${name}.ts`, import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText.replaceAll('"./api"', '"./api.mjs"');
  await writeFile(join(folder, name + ".mjs"), compiled);
}
const api = await import(pathToFileURL(join(folder, "lessons-api.mjs")));
after(() => rm(folder, { recursive: true, force: true }));
const id = "11111111-1111-4111-8111-111111111111";
const input = { title: "Māori", lesson_date: "2026-10-25", tags: ["health"], description: "" };

for (const [name, method, path, invoke] of [
  ["list", "GET", "/lessons", () => api.listLessons()],
  ["tags", "GET", "/tags", () => api.listTags()],
  ["detail", "GET", `/lessons/${id}`, () => api.getLesson(id)],
  ["create", "POST", "/lessons", () => api.saveLesson(null, input)],
  ["edit", "PUT", `/lessons/${id}`, () => api.saveLesson(id, input)],
  ["delete", "DELETE", `/lessons/${id}`, () => api.deleteLesson(id)],
  ["remove", "DELETE", `/materials/${id}`, () => api.deleteMaterial(id)],
  ["share", "PATCH", `/materials/${id}`, () => api.shareMaterial(id, true)],
]) {
  test(`client ${name} uses the protected adapter and cookies`, async t => {
    t.mock.method(globalThis, "fetch", async (url, init) => {
      assert.equal(url, "/api/staff/lesson" + path);
      assert.equal(init.method || "GET", method);
      assert.equal(init.credentials, "same-origin");
      assert.equal(init.cache, "no-store");
      assert.equal(init.headers.has("Authorization"), false);
      if (name === "create" || name === "edit") assert.deepEqual(JSON.parse(init.body), input);
      if (name === "share") assert.deepEqual(JSON.parse(init.body), { share_with_learners: true });
      return method === "DELETE" ? new Response(null, { status: 204 }) : Response.json([]);
    });
    await invoke();
  });
}
test("multipart keeps the browser boundary, original filename and sharing preference", async t => {
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.equal(init.headers.has("Content-Type"), false);
    assert.equal(init.body.get("file").name, "Māori.pdf");
    assert.equal(init.body.get("share_with_learners"), "false");
    return Response.json({ id });
  });
  await api.uploadMaterial(id, new File(["%PDF-test"], "Māori.pdf"), false);
});
for (const [status, text] of [[403, "permission"], [404, "no longer"], [413, "10 MB"], [500, "Unable"]]) {
  test(`client maps ${status} safely`, async t => {
    t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "private database internals" }, { status }));
    await assert.rejects(api.listLessons(), error => error instanceof api.LessonError && error.message.includes(text) && !error.message.includes("internals"));
  });
}
test("field validation maps exact messages", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: { errors: { title: "Title is required" } } }, { status: 422 }));
  await assert.rejects(api.saveLesson(null, input), error => error.fields.title === "Title is required");
});
test("expired session retains the shared login-required error", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 401 }));
  await assert.rejects(api.listLessons(), api.LoginRequiredError);
});
test("download points to the cookie adapter", () => assert.equal(api.materialUrl(id), `/api/staff/lesson/materials/${id}/download`));
