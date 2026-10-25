/** Verify the shared client keeps cookies and lesson file contracts after the merge. */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import ts from "typescript";
const source = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const api = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
for (const [url, expected] of [["/api/user/learners", "/api/user/learners"], ["/api/access/sessions/fixture/attendance", "/api/staff/access/sessions/fixture/attendance"], ["/api/lesson/lessons", "/api/staff/lesson/lessons"]]) {
  test(`cookie request routes ${url}`, async t => {
    t.mock.method(globalThis, "fetch", async (target, init) => {
      assert.equal(target, expected); assert.equal(init.credentials, "same-origin"); assert.equal(init.cache, "no-store");
      assert.equal(init.headers.has("Authorization"), false);
      return Response.json([]);
    });
    assert.equal((await api.apiRequest(url)).status, 200);
  });
}
test("multipart uses the browser boundary and unchanged body", async t => {
  const body = new FormData(); body.append("file", new Blob(["fiction"]), "fixture.pdf");
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.equal(init.body, body); assert.equal(init.headers.has("Content-Type"), false);
    return Response.json({});
  });
  await api.apiRequest("/api/lesson/lessons/fixture/materials", { method: "POST", body });
});
test("apiFile preserves binary download", async t => {
  const bytes = new Uint8Array([0, 255, 128, 65]);
  t.mock.method(globalThis, "fetch", async () => new Response(bytes));
  const result = await api.apiFile("/api/lesson/materials/fixture/download");
  assert.deepEqual(new Uint8Array(await result.blob.arrayBuffer()), bytes);
});
test("401 retains LoginRequiredError contract", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 401 }));
  await assert.rejects(api.apiRequest("/api/user/learners"), api.LoginRequiredError);
});
