/* Verify report downloads, authentication, error messages and file validation.
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
const folder = await mkdtemp(join(tmpdir(), "ako-us005-unit-"));
for (const name of ["api", "attendance-reports-api"]) {
  const source = await readFile(new URL(`../src/lib/${name}.ts`, import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText.replaceAll('"./api"', '"./api.mjs"');
  await writeFile(join(folder, name + ".mjs"), output);
}
const api = await import(pathToFileURL(join(folder, "attendance-reports-api.mjs")));
after(() => rm(folder, { recursive: true, force: true }));
for (const format of ["pdf", "csv"]) test(`${format} posts through the cookie adapter and returns a deterministic filename`, async t => {
  const bytes = format === "pdf" ? "%PDF-1.7 fixture" : "Learner name,2026-10-24\r\nMāia Test,Present\r\n";
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.equal(url, "/api/staff/access/reports/attendance"); assert.equal(init.method, "POST");
    assert.equal(init.credentials, "same-origin"); assert.equal(init.cache, "no-store");
    assert.equal(init.headers.Authorization, undefined);
    assert.deepEqual(JSON.parse(init.body), { start_date: "2026-10-24", end_date: "2026-10-26", format });
    return new Response(bytes, { headers: { "Content-Type": format === "pdf" ? "application/pdf" : "text/csv; charset=utf-8" } });
  });
  const result = await api.downloadAttendance("2026-10-24", "2026-10-26", format);
  assert.equal(result.filename, `ako-attendance-2026-10-24-2026-10-26.${format}`);
  assert.equal(await result.blob.text(), bytes);
});
for (const [status, detail, expected, field] of [
  [403, "internal", "You do not have permission"],
  [404, "internal", "No classes found for these dates"],
  [422, { field: "end_date", message: "Start date must be before end date" }, "Start date must be before end date", "end_date"],
  [422, { field: "start_date", message: "Start date is required" }, "Start date is required", "start_date"],
  [422, [{ msg: "invalid" }], "The report could not be downloaded. Please try again."],
  [500, "private database details", "The report could not be downloaded. Please try again."],
  [503, "private upstream details", "The report could not be downloaded. Please try again."],
]) test(`HTTP ${status} exposes a useful safe message ${field || ""}`, async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail }, { status }));
  await assert.rejects(api.downloadAttendance("2026-10-24", "2026-10-26", "pdf"), error => error instanceof api.ReportError && error.message === expected && error.field === field && error.status === status);
});
test("expired login keeps shared login-required behavior", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 401 }));
  await assert.rejects(api.downloadAttendance("x", "y", "csv"), api.LoginRequiredError);
});
test("network failure is retryable", async t => {
  t.mock.method(globalThis, "fetch", async () => { throw new Error("offline"); });
  await assert.rejects(api.downloadAttendance("x", "y", "csv"));
});
for (const [body, type] of [["<html>bad gateway</html>", "text/html"], ["", "application/pdf"]]) test(`reject a false-success file ${type}`, async t => {
  t.mock.method(globalThis, "fetch", async () => new Response(body, { headers: { "Content-Type": type } }));
  await assert.rejects(api.downloadAttendance("x", "y", "pdf"), api.ReportError);
});
test("non-JSON backend failure is safely handled", async t => {
  t.mock.method(globalThis, "fetch", async () => new Response("Bad gateway", { status: 502 }));
  await assert.rejects(api.downloadAttendance("x", "y", "pdf"), api.ReportError);
});
