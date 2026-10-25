import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

const base = process.env.US006_UI_BASE_URL;
if (!base) throw new Error("Run npm run test:lessons-ui after npm run build");
const id = "22222222-2222-4222-8222-222222222222";
const copyId = "44444444-4444-4444-8444-444444444444";
const mid = "33333333-3333-4333-8333-333333333333";
const source = { id, title: "Te reo Māori transport", lesson_date: "2025-10-01", tags: ["transport", "health"], description: "Teaching notes", created_by: "11111111-1111-4111-8111-111111111111", can_edit: false, review_label: null,
  materials: [{ id: mid, lesson_id: id, file_name: "Māori handout.pdf", file_size: 12, mime_type: "application/pdf", share_with_learners: true, created_at: "2025-10-01" }] };
let browser;
before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || "chrome", headless: true }); });
after(async () => { await browser?.close(); });

async function screen(t, options = {}) {
  const context = await browser.newContext({ viewport: options.mobile ? { width: 360, height: 800 } : { width: 1280, height: 900 } });
  t.after(() => context.close());
  await context.addCookies([{ name: "ako_session", value: options.coordinator ? "ui-coordinator" : "ui-other", url: base, httpOnly: true, sameSite: "Lax" }]);
  const state = { rows: options.ten ? Array.from({ length: 10 }, (_, index) => ({ ...structuredClone(source), id: index ? `22222222-2222-4222-8222-${String(index).padStart(12, "0")}` : id, title: index ? `Lesson ${index}` : source.title, tags: index < 2 ? ["transport"] : ["shopping"] })) : [structuredClone(source)], copied: null, copies: 0, uploads: 0, edits: 0, failUpload: false, missing: false, conflict: false, searchFail: false, slowOld: false, queries: [] };
  await context.route("**/api/user/**", route => route.fulfill({ json: { user_id: source.created_by, display_name: "Test teacher", role: options.coordinator ? "coordinator" : "teacher" }, headers: { "X-Session-Expires-At": new Date(Date.now() + 1800000).toISOString() } }));
  await context.route("**/api/staff/lesson/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/staff/lesson/", "");
    const method = request.method();
    if (path === "tags") return route.fulfill({ json: ["transport", "health", "shopping"].map(name => ({ id: name, name })) });
    if (path === "lessons" && method === "GET") {
      const q = url.searchParams.get("q") || "", tag = url.searchParams.get("tag") || "";
      state.queries.push({ q, tag });
      if (state.searchFail) return route.fulfill({ status: 503, json: { detail: "Unavailable" } });
      if (state.slowOld && q === "old") await new Promise(resolve => setTimeout(resolve, 800));
      const rows = state.rows.filter(row => (!tag || row.tags.includes(tag)) && (!q || row.title.toLowerCase().includes(q.toLowerCase()) || row.tags.some(topic => topic.toLowerCase().includes(q.toLowerCase()))));
      return route.fulfill({ json: rows });
    }
    if (path === `lessons/${id}/copy`) {
      if (state.missing) return route.fulfill({ status: 404, json: { detail: "Lesson not found" } });
      if (method === "GET") return route.fulfill({ json: { source_lesson_id: id, title: "Copy of " + source.title, lesson_date: null, tags: source.tags, description: source.description, materials: source.materials.map(item => ({ ...item, share_with_learners: false })), has_maori_content: true } });
      if (state.conflict) return route.fulfill({ status: 409, json: { detail: "Source materials changed. Reopen the copy draft." } });
      state.copies++;
      const body = request.postDataJSON();
      state.copied = { ...structuredClone(source), ...body, id: copyId, can_edit: true, materials: source.materials.filter(item => body.material_ids.includes(item.id)).map(item => ({ ...item, share_with_learners: false })), review_label: "Māori content – not yet reviewed" };
      return route.fulfill({ status: 201, json: state.copied });
    }
    if (path === `lessons/${id}`) return route.fulfill({ json: source });
    if (path === `lessons/${copyId}`) {
      if (method === "PUT") { state.edits++; Object.assign(state.copied, request.postDataJSON()); }
      return route.fulfill({ json: state.copied });
    }
    if (path === `lessons/${copyId}/materials`) {
      state.uploads++;
      if (state.failUpload) return route.fulfill({ status: 422, json: { detail: "The file content does not match its type" } });
      return route.fulfill({ status: 201, json: { ...source.materials[0], file_name: "Extra.pdf" } });
    }
    if (path === `materials/${mid}/download`) return route.fulfill({ body: "%PDF-test", contentType: "application/pdf", headers: { "Content-Disposition": 'attachment; filename="Māori handout.pdf"' } });
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  t.after(() => assert.deepEqual(errors, []));
  return { page, state, context };
}
const openDraft = async page => {
  await page.goto(base + `/lessons/new?copyFrom=${id}`);
  await page.getByRole("heading", { name: "Copy lesson", exact: true }).waitFor();
};
const save = page => page.getByRole("button", { name: "Save lesson", exact: true }).click();

test("tag selection shows only two of ten lessons, combined search and clear restore results", async t => {
  const { page } = await screen(t, { ten: true });
  await page.goto(base + "/lessons"); await page.getByText("10 lessons found", { exact: true }).waitFor();
  await page.getByLabel("Topic tag", { exact: true }).selectOption("transport");
  await page.getByText("2 lessons found", { exact: true }).waitFor();
  await page.getByLabel("Search lessons", { exact: true }).fill("MĀORI");
  await page.getByText("1 lesson found", { exact: true }).waitFor();
  await page.getByRole("link", { name: source.title, exact: true }).waitFor();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await page.getByText("10 lessons found", { exact: true }).waitFor();
});
test("keyword results appear within two seconds after typing", async t => {
  const { page } = await screen(t);
  await page.goto(base + "/lessons"); await page.getByText("1 lesson found", { exact: true }).waitFor();
  const response = page.waitForResponse(reply => reply.url().includes("q=TRANSPORT"));
  const started = Date.now(); await page.getByLabel("Search lessons", { exact: true }).fill("TRANSPORT");
  await response;
  await page.getByRole("status").filter({ hasText: /^1 lesson found$/ }).waitFor();
  assert.ok(Date.now() - started < 2000);
});
test("no match shows exact text and a working creation link", async t => {
  const { page } = await screen(t);
  await page.goto(base + "/lessons"); await page.getByLabel("Search lessons", { exact: true }).fill("notfound");
  await page.getByText("No lessons found", { exact: true }).waitFor();
  await page.getByRole("link", { name: "Create a new lesson" }).click();
  await page.getByRole("heading", { name: "New lesson", exact: true }).waitFor();
});
test("late older search responses cannot overwrite the newest result", async t => {
  const { page, state } = await screen(t); state.slowOld = true;
  await page.goto(base + "/lessons");
  await page.getByLabel("Search lessons", { exact: true }).fill("old");
  await page.waitForRequest(request => request.url().includes("q=old"));
  await page.getByLabel("Search lessons", { exact: true }).fill("transport");
  await page.getByRole("link", { name: source.title, exact: true }).waitFor();
  await page.waitForTimeout(900);
  assert.equal(await page.getByText("No lessons found", { exact: true }).count(), 0);
});
test("search service failures recover on Refresh", async t => {
  const { page, state } = await screen(t); state.searchFail = true;
  await page.goto(base + "/lessons"); await page.getByRole("alert").filter({ hasText: "Unable to complete" }).waitFor();
  state.searchFail = false; await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await page.getByRole("link", { name: source.title, exact: true }).waitFor();
});
test("another teacher can copy a view-only lesson from the list", async t => {
  const { page, state } = await screen(t);
  await page.goto(base + "/lessons");
  await page.getByText("View only", { exact: true }).waitFor();
  await page.getByRole("link", { name: "Copy as new lesson: " + source.title, exact: true }).click();
  await page.getByRole("heading", { name: "Copy lesson", exact: true }).waitFor();
  assert.equal(state.copies, 0);
});
test("copy opens unsaved with prefixed title, empty date, tags, notes and materials", async t => {
  const { page, state } = await screen(t); await openDraft(page);
  assert.equal(await page.getByLabel("Title", { exact: true }).inputValue(), "Copy of " + source.title);
  assert.equal(await page.getByLabel("Lesson date", { exact: true }).inputValue(), "");
  assert.equal(await page.getByLabel("Topic tags", { exact: true }).inputValue(), "transport, health");
  assert.equal(await page.getByLabel("Teaching notes (optional)").inputValue(), source.description);
  await page.getByRole("link", { name: "Māori handout.pdf", exact: true }).waitFor();
  await page.getByText("This copy contains Māori content and will need a new review.").waitFor();
  assert.equal(state.copies, 0);
});
test("saving without a date preserves the draft and does not POST", async t => {
  const { page, state } = await screen(t); await openDraft(page); await save(page);
  await page.getByText("Lesson date is required", { exact: true }).waitFor();
  assert.equal(state.copies, 0);
  assert.equal(await page.getByLabel("Lesson date", { exact: true }).evaluate(element => element === document.activeElement), true);
  assert.equal(await page.getByLabel("Title", { exact: true }).inputValue(), "Copy of " + source.title);
});
test("saving creates one edited copy and keeps original metadata", async t => {
  const { page, state } = await screen(t); await openDraft(page);
  await page.getByLabel("Title", { exact: true }).fill("New Māori lesson");
  await page.getByLabel("Lesson date", { exact: true }).fill("2026-10-26"); await save(page);
  await page.getByRole("heading", { name: "New Māori lesson", exact: true }).waitFor();
  assert.equal(state.copies, 1); assert.equal(state.copied.lesson_date, "2026-10-26");
  assert.equal(state.copied.materials[0].share_with_learners, false);
  assert.equal(state.rows[0].title, source.title);
});
test("Cancel returns to the original without creating anything", async t => {
  const { page, state } = await screen(t); await openDraft(page);
  await page.getByRole("link", { name: "Cancel", exact: true }).click();
  await page.getByRole("heading", { name: source.title, exact: true }).waitFor();
  await page.getByRole("link", { name: "Copy as new lesson", exact: true }).waitFor();
  assert.equal(state.copies, 0);
});
test("removing copied material affects only the draft", async t => {
  const { page, state } = await screen(t); await openDraft(page);
  await page.getByRole("button", { name: "Remove copied Māori handout.pdf", exact: true }).click();
  await page.getByLabel("Lesson date", { exact: true }).fill("2026-10-26"); await save(page);
  await page.waitForURL(`**/lessons/${copyId}`);
  assert.deepEqual(state.copied.materials, []); assert.equal(state.rows[0].materials.length, 1);
});
test("retrying an additional upload edits the saved copy without duplicating it", async t => {
  const { page, state } = await screen(t); state.failUpload = true; await openDraft(page);
  await page.getByLabel("Lesson date", { exact: true }).fill("2026-10-26");
  await page.getByLabel("Add materials (optional)").setInputFiles({ name: "Extra.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-test") });
  await save(page); await page.getByText(/Lesson details saved. Some uploads could not be confirmed/).waitFor();
  state.failUpload = false; await save(page); await page.waitForURL(`**/lessons/${copyId}`);
  assert.equal(state.copies, 1); assert.equal(state.edits, 1); assert.equal(state.uploads, 2);
});
test("deleted source shows an error and no save form", async t => {
  const { page, state } = await screen(t); state.missing = true;
  await page.goto(base + `/lessons/new?copyFrom=${id}`);
  await page.getByText("This lesson or material is no longer available", { exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Save lesson", exact: true }).count(), 0);
});
test("changed source keeps entered values and explains reopening the draft", async t => {
  const { page, state } = await screen(t); state.conflict = true; await openDraft(page);
  await page.getByLabel("Lesson date", { exact: true }).fill("2026-10-26"); await save(page);
  await page.getByText("Source materials changed. Reopen the copy draft.", { exact: true }).waitFor();
  assert.equal(await page.getByLabel("Lesson date", { exact: true }).inputValue(), "2026-10-26");
  assert.equal(state.copies, 0);
});
test("copy form fits 360px with existing Ako colours and readable controls", async t => {
  const { page } = await screen(t, { mobile: true }); await openDraft(page);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.equal(await page.getByLabel("Title", { exact: true }).evaluate(element => getComputedStyle(element).fontSize), "18px");
  assert.equal(await page.locator("header.bar").evaluate(element => getComputedStyle(element).backgroundColor), "rgb(31, 78, 121)");
  if (process.env.UI_SCREENSHOT_DIR) {
    await mkdir(process.env.UI_SCREENSHOT_DIR, { recursive: true });
    await page.screenshot({ path: process.env.UI_SCREENSHOT_DIR + "/us007-copy-mobile.png", fullPage: true });
  }
});
test("search and filter controls fit a 360px phone", async t => {
  const { page } = await screen(t, { mobile: true }); await page.goto(base + "/lessons");
  await page.getByText("1 lesson found", { exact: true }).waitFor();
  assert.equal(await page.getByLabel("Search lessons", { exact: true }).evaluate(element => getComputedStyle(element).fontSize), "18px");
  assert.ok((await page.getByLabel("Search lessons", { exact: true }).boundingBox()).height >= 44);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  if (process.env.UI_SCREENSHOT_DIR) {
    await mkdir(process.env.UI_SCREENSHOT_DIR, { recursive: true });
    await page.screenshot({ path: process.env.UI_SCREENSHOT_DIR + "/us007-search-mobile.png", fullPage: true });
  }
});
