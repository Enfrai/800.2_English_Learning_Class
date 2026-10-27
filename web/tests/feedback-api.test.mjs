/* Verify feedback validation and the public API request and error contract.
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

const folder = await mkdtemp(join(tmpdir(), "ako-feedback-unit-"));
const source = await readFile(new URL("../src/lib/feedback-api.ts", import.meta.url), "utf8");
await writeFile(join(folder, "api.mjs"), ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText);
const api = await import(pathToFileURL(join(folder, "api.mjs")));
after(() => rm(folder, { recursive: true, force: true }));
const valid = { title: "Test", email: "user@example.test", description: "Māori feedback" };
const success = "Thank you. Your feedback has been submitted.";

test("required fields and valid Unicode length boundaries", () => {
  assert.deepEqual(Object.keys(api.validateFeedback({ title: " ", email: "", description: "" })), ["title", "email", "description"]);
  assert.deepEqual(api.validateFeedback({ ...valid, title: "ā".repeat(200), description: "中".repeat(5000) }), {});
});
for (const [field, value] of [
  ["title", "x".repeat(201)], ["title", "a\r\nBcc: victim@example.test"],
  ["email", "bad"], ["email", ".a@example.test"], ["email", "a..b@example.test"],
  ["email", "a@-bad.test"], ["email", "a@localhost"], ["email", "a@example.test;other@example.test"],
  ["email", "a@example.test\r\nBcc: other@example.test"],
  ["description", "x".repeat(5001)], ["description", "bad\x00text"],
]) test(`invalid ${field}: ${value.slice(0, 20)}`, () => {
  assert.ok(api.validateFeedback({ ...valid, [field]: value })[field]);
});
test("same-origin JSON submission trims input and exposes no recipients", async t => {
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.equal(url, "/api/user/feedback");
    assert.equal(init.credentials, "same-origin"); assert.equal(init.cache, "no-store");
    assert.equal(init.method, "POST");
    assert.deepEqual(init.headers, { "Content-Type": "application/json" });
    assert.deepEqual(JSON.parse(init.body), valid);
    return Response.json({ message: success });
  });
  assert.equal(await api.submitFeedback({ ...valid, title: " Test ", email: " user@example.test " }), success);
});
for (const status of [400, 401, 403, 422, 429, 500, 502, 503]) test(`HTTP ${status} fails without retry or private upstream details`, async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => { calls++; return Response.json({ detail: "SMTP secret" }, { status }); });
  await assert.rejects(api.submitFeedback(valid), error => error instanceof api.FeedbackError && !error.message.includes("secret"));
  assert.equal(calls, 1);
});
test("network error is not automatically retried", async t => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => { calls++; throw Error("network failed"); });
  await assert.rejects(api.submitFeedback(valid), /Unable to confirm delivery/);
  assert.equal(calls, 1);
});
for (const body of [null, {}, { message: "untrusted" }]) test("unconfirmed successful response is not treated as delivered", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json(body));
  await assert.rejects(api.submitFeedback(valid), api.FeedbackError);
});
test("invalid JSON is not a successful receipt", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response("<html>error</html>"));
  await assert.rejects(api.submitFeedback(valid), api.FeedbackError);
});
