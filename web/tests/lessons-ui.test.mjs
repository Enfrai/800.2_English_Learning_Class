import assert from "node:assert/strict";
import { before, after, test } from "node:test";
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

const base = process.env.US006_UI_BASE_URL;
if (!base) throw new Error("Run npm run test:lessons-ui after npm run build");
const id = "22222222-2222-4222-8222-222222222222";
const mid = "33333333-3333-4333-8333-333333333333";
const original = {
  id, title: "Te reo Māori transport", lesson_date: "2026-10-25",
  description: "Teaching notes", tags: ["transport"], created_by: "11111111-1111-4111-8111-111111111111",
  materials: [], can_edit: true, has_maori_content: false, review_status: "not_required", review_label: null,
};
const NOT_YET_REVIEWED = "Māori content – not yet reviewed";
const material = { id: mid, lesson_id: id, file_name: "Handout.pdf", file_size: 15, mime_type: "application/pdf", share_with_learners: false, created_at: "2026-10-25" };
let browser;
before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || "chrome", headless: true }); });
after(async () => { await browser?.close(); });

async function screen(t, options = {}) {
  const context = await browser.newContext({ viewport: options.mobile ? { width: 390, height: 844 } : { width: 1280, height: 900 } });
  t.after(() => context.close());
  await context.addCookies([{ name: "ako_session", value: options.coordinator ? "ui-coordinator" : "ui-author", url: base, httpOnly: true, sameSite: "Lax" }]);
  const state = { row: { ...structuredClone(original), materials: options.materials ? [structuredClone(material)] : [], can_edit: options.canEdit !== false }, created: 0, uploads: 0, deletes: 0, flags: [], failUpload: false, expired: false };
  if (options.review) Object.assign(state.row, options.review);
  await context.route("**/api/user/**", route => route.fulfill({ json: { user_id: original.created_by, display_name: "Test teacher", role: options.coordinator ? "coordinator" : "teacher" }, headers: { "X-Session-Expires-At": new Date(Date.now() + 1800000).toISOString() } }));
  await context.route("**/api/staff/lesson/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/staff/lesson/", "");
    const method = request.method();
    if (state.expired) return route.fulfill({ status: 401, json: { detail: "Login required" } });
    if (path === "tags") return route.fulfill({ json: [{ id: "tag", name: "health" }] });
    if (path === "lessons" && method === "GET") return route.fulfill({ json: state.row ? [state.row] : [] });
    if (path === "lessons" && method === "POST") {
      state.created++; state.row = { ...structuredClone(original), ...request.postDataJSON() };
      return route.fulfill({ status: 201, json: state.row });
    }
    if (path === `lessons/${id}`) {
      if (!state.row) return route.fulfill({ status: 404, json: { detail: "Lesson not found" } });
      if (method === "PUT") state.row = { ...state.row, ...request.postDataJSON() };
      if (method === "DELETE") { state.row = null; state.deletes++; return route.fulfill({ status: 204 }); }
      return route.fulfill({ json: state.row });
    }
    if (path === `lessons/${id}/maori-content` && method === "PUT") {
      const flagged = request.postDataJSON().has_maori_content;
      state.flags.push(flagged);
      Object.assign(state.row, { has_maori_content: flagged, review_status: flagged ? "pending" : "not_required", review_label: flagged ? NOT_YET_REVIEWED : null });
      return route.fulfill({ json: { lesson_id: id, has_maori_content: flagged } });
    }
    if (path === `lessons/${id}/materials`) {
      state.uploads++;
      if (state.failUpload) return route.fulfill({ status: 422, json: { detail: "The file content does not match its type" } });
      state.row.materials.push(structuredClone(material));
      return route.fulfill({ status: 201, json: material });
    }
    if (path === `materials/${mid}/download`) return route.fulfill({ body: "%PDF-test", contentType: "application/pdf", headers: { "Content-Disposition": 'attachment; filename="Handout.pdf"' } });
    if (path === `materials/${mid}` && method === "PATCH") {
      Object.assign(state.row.materials[0], request.postDataJSON());
      return route.fulfill({ json: state.row.materials[0] });
    }
    if (path === `materials/${mid}` && method === "DELETE") {
      state.row.materials = []; state.deletes++;
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  t.after(() => assert.deepEqual(errors, []));
  await page.goto(base + (options.path || "/lessons/new"));
  await page.getByRole("heading", { name: options.path?.includes("/edit") ? "Edit lesson" : options.path === "/lessons" ? "Lessons" : options.path === `/lessons/${id}` ? original.title : "New lesson", exact: true }).waitFor();
  return { page, state };
}
async function fill(page) {
  await page.getByLabel("Title", { exact: true }).fill("Māori health");
  await page.getByLabel("Lesson date", { exact: true }).fill("2026-10-25");
  await page.getByLabel("Topic tags", { exact: true }).fill("health, shopping");
}
const save = page => page.getByRole("button", { name: "Save lesson", exact: true }).click();
const attach = (page, name = "Handout.pdf", buffer = Buffer.from("%PDF-test")) => page.getByLabel("Add materials (optional)").setInputFiles({ name, mimeType: "application/octet-stream", buffer });

test("required fields show exact messages and do not save", async t => {
  const { page, state } = await screen(t);
  await save(page);
  await page.getByText("Title is required", { exact: true }).waitFor();
  await page.getByText("Lesson date is required", { exact: true }).waitFor();
  await page.getByText("At least one topic tag is required", { exact: true }).waitFor();
  assert.equal(state.created, 0);
  assert.equal(await page.getByLabel("Title", { exact: true }).evaluate(el => el === document.activeElement), true);
});
test("create a lesson and show its metadata", async t => {
  const { page, state } = await screen(t);
  await fill(page); await save(page);
  await page.getByRole("heading", { name: "Māori health", exact: true }).waitFor();
  assert.equal(state.created, 1);
  assert.deepEqual(state.row.tags, ["health", "shopping"]);
  await page.getByText("No materials attached yet.", { exact: true }).waitFor();
});
for (const [name, bytes] of [["bad.exe", Buffer.from("bad")], ["large.pdf", Buffer.alloc(10 * 1024 * 1024 + 1)]]) {
  test(`reject ${name} and retain form fields`, async t => {
    const { page, state } = await screen(t);
    await fill(page); await attach(page, name, bytes); await save(page);
    await page.getByRole("alert").filter({ hasText: "10 MB" }).waitFor();
    assert.equal(await page.getByLabel("Title", { exact: true }).inputValue(), "Māori health");
    assert.equal(state.created, 0); assert.equal(state.uploads, 0);
  });
}
test("upload, download original name and change sharing", async t => {
  const { page, state } = await screen(t);
  await fill(page); await attach(page);
  assert.equal(await page.getByRole("checkbox", { name: "Share Handout.pdf with learners" }).isChecked(), false);
  await save(page);
  await page.getByRole("heading", { name: "Māori health", exact: true }).waitFor();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Handout.pdf", exact: true }).click();
  assert.equal((await download).suggestedFilename(), "Handout.pdf");
  await page.getByRole("checkbox", { name: "Share Handout.pdf with learners" }).click();
  await page.getByText("Sharing preference saved", { exact: true }).waitFor();
  assert.equal(state.row.materials[0].share_with_learners, true);
});
test("upload failure retains saved draft and retry does not duplicate lesson", async t => {
  const { page, state } = await screen(t);
  state.failUpload = true;
  await fill(page); await attach(page); await save(page);
  await page.getByRole("alert").filter({ hasText: "Lesson details saved" }).waitFor();
  assert.equal(await page.getByLabel("Title", { exact: true }).inputValue(), "Māori health");
  assert.equal(state.created, 1);
  state.failUpload = false; await save(page);
  await page.getByRole("heading", { name: "Māori health", exact: true }).waitFor();
  assert.equal(state.created, 1);
  assert.equal(state.uploads, 2);
});
test("edit title preserves date and existing attachment", async t => {
  const { page, state } = await screen(t, { path: `/lessons/${id}/edit`, materials: true });
  await page.getByLabel("Title", { exact: true }).fill("Changed title");
  await save(page);
  await page.getByRole("heading", { name: "Changed title", exact: true }).waitFor();
  assert.equal(state.row.lesson_date, original.lesson_date);
  await page.getByRole("link", { name: "Handout.pdf", exact: true }).waitFor();
});
test("another teacher has view only controls", async t => {
  const { page } = await screen(t, { path: `/lessons/${id}`, materials: true, canEdit: false });
  assert.equal(await page.getByRole("link", { name: "Edit lesson", exact: true }).count(), 0);
  assert.equal(await page.getByRole("button", { name: "Delete lesson", exact: true }).count(), 0);
  await page.goto(base + `/lessons/${id}/edit`);
  await page.getByRole("alert").filter({ hasText: "permission" }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Save lesson", exact: true }).count(), 0);
});
test("coordinator can open another author's editing form", async t => {
  const { page } = await screen(t, { path: `/lessons/${id}/edit`, coordinator: true });
  await page.getByRole("button", { name: "Save lesson", exact: true }).waitFor();
});
test("delete requires confirmation and removes the lesson", async t => {
  const { page, state } = await screen(t, { path: `/lessons/${id}` });
  await page.getByRole("button", { name: "Delete lesson", exact: true }).click();
  await page.getByRole("button", { name: "Cancel deletion", exact: true }).click();
  assert.equal(state.deletes, 0);
  await page.getByRole("button", { name: "Delete lesson", exact: true }).click();
  await page.getByRole("button", { name: "Confirm deletion", exact: true }).click();
  await page.getByRole("heading", { name: "Lessons", exact: true }).waitFor();
  assert.equal(state.deletes, 1);
  await page.getByText("No lessons yet. Choose New lesson to start.", { exact: true }).waitFor();
});
test("remove material keeps the parent lesson", async t => {
  const { page, state } = await screen(t, { path: `/lessons/${id}`, materials: true });
  await page.getByRole("button", { name: "Remove Handout.pdf", exact: true }).click();
  await page.getByRole("button", { name: "Confirm deletion", exact: true }).click();
  await page.getByText("Material removed", { exact: true }).waitFor();
  assert.ok(state.row); assert.deepEqual(state.row.materials, []);
});
test("form fits mobile width and uses Ako controls", async t => {
  const { page } = await screen(t, { mobile: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.equal(await page.getByLabel("Title", { exact: true }).evaluate(el => getComputedStyle(el).fontSize), "18px");
  assert.equal(await page.locator("header.bar").evaluate(el => getComputedStyle(el).backgroundColor), "rgb(31, 78, 121)");
  if (process.env.UI_SCREENSHOT_DIR) {
    await mkdir(process.env.UI_SCREENSHOT_DIR, { recursive: true });
    await page.screenshot({ path: process.env.UI_SCREENSHOT_DIR + "/lesson-mobile.png", fullPage: true });
  }
});
test("list shows titles, dates, tags and edit permissions", async t => {
  const { page } = await screen(t, { path: "/lessons", canEdit: false });
  await page.getByRole("link", { name: original.title, exact: true }).waitFor();
  await page.getByText("View only", { exact: true }).waitFor();
  await page.getByRole("cell", { name: original.lesson_date, exact: true }).waitFor();
  if (process.env.UI_SCREENSHOT_DIR) {
    await mkdir(process.env.UI_SCREENSHOT_DIR, { recursive: true });
    await page.screenshot({ path: process.env.UI_SCREENSHOT_DIR + "/lessons-desktop.png", fullPage: true });
  }
});

test("long filenames wrap on mobile and queued files can be removed", async t => {
  const { page } = await screen(t, { mobile: true });
  const name = "x".repeat(200) + ".pdf";
  await attach(page, name);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.getByRole("button", { name: "Remove " + name, exact: true }).click();
  assert.equal(await page.getByRole("checkbox", { name: "Share " + name + " with learners", exact: true }).count(), 0);
});

// US-008: "Contains Māori content" tick box and the review pills (UI design 6.8, 6.10).
const reviewed = { has_maori_content: true, review_status: "reviewed", review_label: "Reviewed by Kiri Tāmaki, 14 Oct 2026" };
const pill = page => page.locator(".badge-review, .badge-reviewed");
test("ticking Contains Māori content shows the not yet reviewed pill", async t => {
  const { page, state } = await screen(t);
  await fill(page);
  await page.getByRole("checkbox", { name: "Contains Māori content", exact: true }).check();
  await save(page);
  await page.getByRole("heading", { name: "Māori health", exact: true }).waitFor();
  assert.deepEqual(state.flags, [true]);
  assert.equal(await pill(page).textContent(), NOT_YET_REVIEWED);
  assert.equal(await pill(page).getAttribute("class"), "badge badge-review");
});
test("saving without changing the tick does not touch the review", async t => {
  const { page, state } = await screen(t, { path: `/lessons/${id}/edit`, review: reviewed });
  assert.equal(await page.getByRole("checkbox", { name: "Contains Māori content", exact: true }).isChecked(), true);
  await page.getByText("Unticking removes the recorded review.", { exact: false }).waitFor();
  await save(page);
  await page.getByRole("heading", { name: original.title, exact: true }).waitFor();
  assert.deepEqual(state.flags, []);
});
test("unticking sends the change and removes the pill", async t => {
  const { page, state } = await screen(t, { path: `/lessons/${id}/edit`, review: { ...reviewed, review_status: "pending", review_label: NOT_YET_REVIEWED } });
  await page.getByRole("checkbox", { name: "Contains Māori content", exact: true }).uncheck();
  await save(page);
  await page.getByRole("heading", { name: original.title, exact: true }).waitFor();
  assert.deepEqual(state.flags, [false]);
  assert.equal(await pill(page).count(), 0);
});
for (const path of ["/lessons", `/lessons/${id}`]) {
  test(`reviewed lesson shows a green pill with macrons on ${path}`, async t => {
    const { page } = await screen(t, { path, review: reviewed });
    assert.equal(await pill(page).textContent(), "Reviewed by Kiri Tāmaki, 14 Oct 2026");
    assert.equal(await pill(page).getAttribute("class"), "badge badge-reviewed");
  });
}
