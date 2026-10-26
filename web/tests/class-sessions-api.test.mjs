/* Verify class-session requests, cookie boundaries and field errors.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

import assert from "node:assert/strict";
import { after, test } from "node:test";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";
const folder = await mkdtemp(join(tmpdir(), "ako-us014-unit-"));
for (const name of ["api", "class-sessions-api"]) {
  const source = await readFile(new URL(`../src/lib/${name}.ts`, import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText.replaceAll('"./api"', '"./api.mjs"');
  await writeFile(join(folder, name + ".mjs"), output);
}
const api = await import(pathToFileURL(join(folder, "class-sessions-api.mjs")));
after(() => rm(folder, { recursive: true, force: true }));
const id = "22222222-2222-4222-8222-222222222222";
const lesson = "33333333-3333-4333-8333-333333333333";
for (const [name, method, path, body, invoke] of [
  ["list", "GET", "", undefined, () => api.listClassSessions()],
  ["detail", "GET", `/${id}`, undefined, () => api.getClassSession(id)],
  ["start today", "POST", "/today", undefined, () => api.startToday()],
  ["dated class", "POST", "", { session_date: "2026-10-24" }, () => api.createClassSession("2026-10-24")],
  ["link lesson", "PUT", `/${id}/lesson`, { lesson_id: lesson }, () => api.linkClassLesson(id, lesson)],
  ["unlink lesson", "PUT", `/${id}/lesson`, { lesson_id: null }, () => api.linkClassLesson(id, null)],
  ["delete", "DELETE", `/${id}`, undefined, () => api.deleteClassSession(id)],
]) test(name + " uses the authenticated adapter", async t => {
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.equal(url, "/api/staff/access/sessions" + path);
    assert.equal(init.method || "GET", method);
    assert.equal(init.credentials, "same-origin"); assert.equal(init.cache, "no-store");
    assert.equal(init.headers.has("Authorization"), false);
    assert.deepEqual(init.body ? JSON.parse(init.body) : undefined, body);
    return method === "DELETE" ? new Response(null, { status: 204 }) : Response.json({ id });
  });
  await invoke();
});
for (const status of [403, 404, 409, 503]) test(`HTTP ${status} becomes a meaningful error`, async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: status === 409 ? "This session has attendance and cannot be deleted" : "Class session not found" }, { status }));
  await assert.rejects(api.deleteClassSession(id), error => error instanceof api.ClassSessionError && error.status === status && (status !== 409 || error.message === "This session has attendance and cannot be deleted"));
});
test("future date error retains field and exact message", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: { field: "session_date", message: "Date cannot be in the future" } }, { status: 422 }));
  await assert.rejects(api.createClassSession("2099-01-01"), error => error.field === "session_date" && error.message === "Date cannot be in the future");
});
test("expired login keeps the shared LoginRequiredError", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 401 }));
  await assert.rejects(api.listClassSessions(), api.LoginRequiredError);
});
test("unstructured upstream failures receive safe text", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response("bad gateway", { status: 502 }));
  await assert.rejects(api.startToday(), /The class could not be updated/);
});
test("encoded ids cannot inject a new route", async t => {
  t.mock.method(globalThis, "fetch", async url => { assert.equal(url, "/api/staff/access/sessions/a%2Fb%3Fx"); return Response.json({}); });
  await api.getClassSession("a/b?x");
});
