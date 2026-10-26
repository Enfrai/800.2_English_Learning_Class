/* Verify classroom lifecycle, QR panel compatibility and attendance navigation.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */
import assert from "node:assert/strict";
import { before, after, test } from "node:test";
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
const base = process.env.US014_UI_BASE_URL;
if (!base) throw new Error("Run npm run test:sessions-ui after npm run build");
const sid = "22222222-2222-4222-8222-222222222222", lid = "33333333-3333-4333-8333-333333333333", today = "2026-10-26";
const original = { id: sid, session_date: today, lesson_id: null, lesson_title: null, lesson_unavailable: false, attendance_count: 0, present_count: 0, can_delete: true };
let browser;
before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || "chrome", headless: true }); });
after(async () => { await browser?.close(); });
async function screen(t, options = {}) {
  const context = await browser.newContext({ viewport: options.mobile ? { width: 360, height: 800 } : { width: 1280, height: 900 } });
  t.after(() => context.close());
  if (!options.anonymous) await context.addCookies([{ name: "ako_session", value: options.coordinator ? "ui-coordinator" : "ui-teacher", url: base, httpOnly: true, sameSite: "Lax" }]);
  const state = { rows: options.empty ? [] : [{ ...original, ...(options.recorded ? { attendance_count: 1, present_count: 1, can_delete: false } : {}) }], starts: 0, creations: 0, links: 0, deletes: 0, failList: false, failSave: false, deletedLesson: false, blockDelete: false, listCalls: 0 };
  await context.route("**/api/user/**", route => route.fulfill({ json: route.request().url().endsWith("/learners") ? [] : { user_id: sid, display_name: "Test teacher", role: options.coordinator ? "coordinator" : "teacher", expires_at: new Date(Date.now() + 1800000).toISOString() }, headers: { "X-Session-Expires-At": new Date(Date.now() + 1800000).toISOString() } }));
  await context.route("**/api/staff/lesson/lessons", route => route.fulfill({ json: [{ id: lid, title: "Te reo Māori transport", materials: [], tags: ["transport"] }] }));
  await context.route("**/api/staff/access/sessions**", async route => {
    const req = route.request(), path = new URL(req.url()).pathname.replace("/api/staff/access/sessions", ""), method = req.method();
    const reply = (json, status = 200) => route.fulfill({ json, status });
    if (path === "" && method === "GET") { state.listCalls++; return state.failList ? reply({ detail: "Class list unavailable" }, 503) : reply({ today, sessions: state.rows }); }
    if ((path === "/today" || path === "") && method === "POST") {
      const day = path === "/today" ? today : req.postDataJSON().session_date; state.starts++;
      if (day > today) return reply({ detail: { field: "session_date", message: "Date cannot be in the future" } }, 422);
      const old = state.rows.find(item => item.session_date === day);
      if (old) return reply({ id: old.id, session_date: day, created: false });
      state.creations++; state.rows.push({ ...original, session_date: day }); return reply({ id: sid, session_date: day, created: true });
    }
    if (path === `/${sid}` && method === "GET") return state.rows.length ? reply({ today, ...state.rows[0] }) : reply({ detail: "Class session not found" }, 404);
    if (path === `/${sid}/lesson` && method === "PUT") {
      state.links++;
      if (state.failSave) return reply({ detail: "The lesson could not be checked. Please try again." }, 503);
      if (state.deletedLesson) return reply({ detail: "Lesson is no longer available" }, 404);
      const chosen = req.postDataJSON().lesson_id; Object.assign(state.rows[0], { lesson_id: chosen, lesson_title: chosen ? "Te reo Māori transport" : null, lesson_unavailable: false }); return reply(state.rows[0]);
    }
    if (path === `/${sid}` && method === "DELETE") {
      if (state.blockDelete || state.rows[0].attendance_count) return reply({ detail: "This session has attendance and cannot be deleted" }, 409);
      state.deletes++; state.rows = []; return route.fulfill({ status: 204 });
    }
    if (path === `/${sid}/check-in`) return reply({ state: "not-open", session_date: today, can_open: true, opened_at: null, expires_at: null, sign_in_url: null, qr_svg: null });
    if (path === `/${sid}/attendance`) return reply({ session_date: state.rows[0].session_date, editable: true, present_count: 0, records: [], corrected_learner_ids: [] });
    return reply({ detail: "Class session not found" }, 404);
  });
  const page = await context.newPage(), errors = [];
  page.on("pageerror", error => errors.push(error.message)); t.after(() => assert.deepEqual(errors, []));
  return { page, state };
}
const button = (page, name) => page.getByRole("button", { name, exact: true });
const go = (page, path = "/sessions") => page.goto(base + path);
const detail = async page => { await go(page, `/sessions/${sid}`); await button(page, "Save lesson").waitFor(); };
const text = (page, value) => page.getByText(value, { exact: true }).waitFor();
const selectLesson = (page, value) => page.getByLabel("Lesson", { exact: true }).selectOption(value);

test("navigation opens the class list and empty state", async t => {
  const { page } = await screen(t, { empty: true }); await go(page, "/teacher"); await page.getByRole("link", { name: "Class sessions", exact: true }).click();
  await text(page, "No class sessions yet. Start today's class to begin.");
});
test("Start today creates a classroom and opens it within two seconds", async t => {
  const { page, state } = await screen(t, { empty: true }); await go(page); const started = Date.now();
  await button(page, "Start today's class").click(); await button(page, "Save lesson").waitFor(); assert.ok(Date.now() - started < 2000); assert.equal(state.creations, 1);
});
test("starting an existing class reuses its id", async t => {
  const { page, state } = await screen(t); await go(page); await button(page, "Start today's class").click(); await page.waitForURL(`**/sessions/${sid}`);
  assert.equal(state.creations, 0); assert.equal(state.rows.length, 1);
});
test("date is required and future dates never submit", async t => {
  const { page, state } = await screen(t); await go(page); await button(page, "New class session").click(); await button(page, "Create or open class").click(); await text(page, "Class date is required");
  await page.getByLabel("Class date", { exact: true }).fill("2099-01-01"); await button(page, "Create or open class").click(); await text(page, "Date cannot be in the future"); assert.equal(state.starts, 0);
});
test("a past date opens with the historical attendance rule", async t => {
  const { page, state } = await screen(t, { empty: true }); await go(page); await button(page, "New class session").click();
  await page.getByLabel("Class date", { exact: true }).fill("2026-10-20"); await button(page, "Create or open class").click(); await text(page, "Only a coordinator can correct past attendance"); assert.equal(state.rows[0].session_date, "2026-10-20");
});
test("lesson can be linked and unlinked", async t => {
  const { page, state } = await screen(t); await detail(page); await selectLesson(page, lid); await button(page, "Save lesson").click(); await text(page, "Lesson saved for this class."); assert.equal(state.rows[0].lesson_id, lid);
  await selectLesson(page, ""); await button(page, "Save lesson").click(); await text(page, "Lesson saved for this class."); assert.equal(state.rows[0].lesson_id, null);
});
test("failed linking preserves selection without false success", async t => {
  const { page, state } = await screen(t); state.failSave = true; await detail(page); await selectLesson(page, lid); await button(page, "Save lesson").click();
  await text(page, "The lesson could not be checked. Please try again."); assert.equal(await page.getByLabel("Lesson", { exact: true }).inputValue(), lid); assert.equal(await page.getByText("Lesson saved for this class.", { exact: true }).count(), 0);
});
test("deleted lesson gives a clear error", async t => {
  const { page, state } = await screen(t); state.deletedLesson = true; await detail(page); await selectLesson(page, lid); await button(page, "Save lesson").click(); await text(page, "Lesson is no longer available"); assert.equal(state.rows[0].lesson_id, null);
});
test("attendance opens from class detail and returns", async t => {
  const { page } = await screen(t); await detail(page); await page.getByRole("link", { name: "Attendance", exact: true }).click(); await page.getByRole("heading", { name: "Attendance", exact: true }).waitFor();
  await page.getByRole("link", { name: "Back to class session", exact: true }).click(); await page.getByRole("heading", { name: "Class session", exact: true }).waitFor();
});
test("delete needs confirmation and cancel does nothing", async t => {
  const { page, state } = await screen(t); await detail(page); await button(page, "Delete session").click(); await button(page, "Cancel deletion").click(); assert.equal(state.deletes, 0);
  await button(page, "Delete session").click(); await button(page, "Confirm deletion").click(); await page.waitForURL("**/sessions"); assert.equal(state.deletes, 1);
});
test("recorded attendance disables deletion with an explanation", async t => {
  const { page } = await screen(t, { recorded: true }); await detail(page); assert.equal(await button(page, "Delete session").isDisabled(), true); await text(page, "This session has attendance and cannot be deleted");
});
test("a concurrent attendance write blocks confirmed deletion", async t => {
  const { page, state } = await screen(t); await detail(page); await button(page, "Delete session").click(); state.blockDelete = true; await button(page, "Confirm deletion").click(); await text(page, "This session has attendance and cannot be deleted"); assert.equal(state.deletes, 0);
});
test("list retains lesson titles after refresh", async t => {
  const { page, state } = await screen(t); Object.assign(state.rows[0], { lesson_title: "Te reo Māori transport", lesson_id: lid }); await go(page); await page.getByRole("cell", { name: "Te reo Māori transport", exact: true }).waitFor();
  await button(page, "Refresh").click(); await page.getByRole("cell", { name: "Te reo Māori transport", exact: true }).waitFor(); assert.ok(state.listCalls >= 2);
});
test("list service failure can be retried", async t => {
  const { page, state } = await screen(t); state.failList = true; await go(page); await text(page, "Class list unavailable"); state.failList = false; await button(page, "Refresh").click(); await page.getByRole("link", { name: "Open class", exact: true }).waitFor();
});
test("coordinator uses the same navigation", async t => {
  const { page } = await screen(t, { coordinator: true }); await go(page, "/coordinator"); await page.getByRole("link", { name: "Class sessions", exact: true }).click(); await button(page, "Start today's class").click(); await button(page, "Save lesson").waitFor();
});
test("class list and date form fit 360px with Ako styles", async t => {
  const { page } = await screen(t, { mobile: true }); await go(page); await button(page, "New class session").click(); await page.getByLabel("Class date", { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true); assert.equal(await page.getByLabel("Class date", { exact: true }).evaluate(el => getComputedStyle(el).fontSize), "18px"); assert.equal(await page.locator("header.bar").evaluate(el => getComputedStyle(el).backgroundColor), "rgb(31, 78, 121)");
  if (process.env.UI_SCREENSHOT_DIR) { await mkdir(process.env.UI_SCREENSHOT_DIR, { recursive: true }); await page.screenshot({ path: process.env.UI_SCREENSHOT_DIR + "/sessions-mobile.png", fullPage: true }); }
});
test("class detail fits 360px with macrons", async t => {
  const { page } = await screen(t, { mobile: true }); await detail(page); await selectLesson(page, lid); await button(page, "Save lesson").click(); await text(page, "Lesson saved for this class."); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  if (process.env.UI_SCREENSHOT_DIR) { await mkdir(process.env.UI_SCREENSHOT_DIR, { recursive: true }); await page.screenshot({ path: process.env.UI_SCREENSHOT_DIR + "/session-detail-mobile.png", fullPage: true }); }
});
test("anonymous visitors cannot open staff classrooms", async t => {
  const { page } = await screen(t, { anonymous: true }); await go(page); await page.waitForURL(base + "/"); assert.equal(await button(page, "Start today's class").count(), 0);
});
