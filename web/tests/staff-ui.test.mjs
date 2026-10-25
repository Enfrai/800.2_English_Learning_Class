/** Browser-level frontend tests with mocked APIs; these do not verify backend authorization or persistence. */
import assert from "node:assert/strict";
import { before, after, test } from "node:test";
import { chromium } from "playwright";

const base = process.env.US002_UI_BASE_URL;
if (!base) throw new Error("Run via tests/run-staff-ui.mjs after a production build.");
let browser;
before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || "chrome", headless: true }); });
after(async () => { await browser?.close(); });
const teacher = { id: "00000000-0000-4000-8000-000000000010", username: "teacher_one", display_name: "Teacher One", role: "teacher", is_active: true };
const coordinator = { ...teacher, id: "00000000-0000-4000-8000-000000000001", username: "coordinator_hidden", display_name: "Coordinator Hidden", role: "coordinator" };
const field = (page, name) => page.locator(`input[name="${name}"]`);

async function screen(t, options = {}) {
  const context = await browser.newContext({ viewport: options.viewport });
  t.after(() => context.close());
  if (options.role !== "anonymous") await context.addCookies([{ name: "ako_session", value: `ui-${options.role || "coordinator"}`, url: base, httpOnly: true, sameSite: "Lax" }]);
  const state = { rows: options.rows || [coordinator, { ...teacher }], requests: [], reads: 0, failure: null, postDelay: 0, expired: false, created: false };
  await context.route("**/api/user/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/user", "");
    const send = (status, data, headers = {}) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data), headers });
    if (path === "/session") return send(state.expired ? 401 : 200, { user_id: coordinator.id, display_name: "UI fixture", role: options.role || "coordinator" }, { "X-Session-Expires-At": new Date(Date.now() + 1800000).toISOString() });
    if (path === "/activity") return send(200, { expires_at: new Date(Date.now() + 1800000).toISOString() });
    if (!path.startsWith("/staff")) return send(404, {});
    if (request.method() === "GET") {
      state.reads++;
      if (options.listFailure) return send(options.listFailure, { detail: "Access lost" });
      if (options.loadDelay && state.reads === 1) await new Promise(resolve => setTimeout(resolve, options.loadDelay));
      if (options.failFirstLoad && state.reads === 1 || options.failRefresh && state.created) return send(500, { detail: "Internal SQL error must not be exposed" });
      return send(200, state.rows);
    }
    state.requests.push({ method: request.method(), path, body: request.postDataJSON(), headers: request.headers() });
    if (state.postDelay) await new Promise(resolve => setTimeout(resolve, state.postDelay));
    if (state.failure === "network") return route.abort("failed");
    if (state.failure) return send(state.failure.status, { detail: state.failure.detail });
    if (request.method() === "POST" && path === "/staff") {
      const data = request.postDataJSON();
      const row = { ...teacher, id: "00000000-0000-4000-8000-000000000020", username: data.username, display_name: data.display_name };
      state.rows.push(row); state.created = true;
      return send(201, row);
    }
    const row = state.rows.find(item => path.includes(item.id));
    if (!row) return send(404, {});
    if (request.method() === "PATCH") row.display_name = request.postDataJSON().display_name;
    else row.is_active = false;
    return send(200, row);
  });
  const page = await context.newPage();
  const response = await page.goto(`${base}/account-management`);
  // A 401 can redirect before the protected heading is ever painted.
  if ((!options.role || options.role === "coordinator") && options.listFailure !== 401) {
    await page.getByRole("heading", { name: "Account management", exact: true }).waitFor();
  }
  return { page, context, state, response };
}

async function fillCreate(page, password = "12345678") {
  await field(page, "display_name").fill("New Teacher");
  await field(page, "username").fill("new_teacher");
  await field(page, "temporary_password").fill(password);
}
async function create(page) { await page.getByRole("button", { name: "Create Teacher", exact: true }).click(); }
async function error(page, message) { await page.getByRole("alert").filter({ hasText: message }).waitFor(); }

test("Teachers and Coordinators are listed separately, including inactive state; mobile layout fits", async t => {
  const { page } = await screen(t, { viewport: { width: 390, height: 844 }, rows: [coordinator, teacher, { ...teacher, id: "inactive", username: "inactive", display_name: "Past Teacher", is_active: false }] });
  await page.getByRole("heading", { name: "Teacher One", exact: true }).waitFor();
  const teachers = page.getByRole("list", { name: "Teacher accounts" });
  const coordinators = page.getByRole("list", { name: "Coordinator accounts" });
  assert.equal(await teachers.getByText("Coordinator Hidden", { exact: true }).count(), 0);
  await coordinators.getByText("Coordinator Hidden", { exact: true }).waitFor();
  // Coordinators can be deactivated (AC5) but never renamed here.
  assert.equal(await page.getByRole("button", { name: "Edit coordinator_hidden", exact: true }).count(), 0);
  assert.equal(await page.getByRole("button", { name: "Deactivate inactive", exact: true }).count(), 0);
  await page.getByText("Inactive", { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
});

test("Create with eight characters, refresh list, clear password and avoid browser storage", async t => {
  const { page, state } = await screen(t);
  await fillCreate(page); await create(page);
  await page.getByRole("heading", { name: "New Teacher", exact: true }).waitFor();
  await page.getByText("Teacher account created.", { exact: true }).waitFor();
  assert.equal(await field(page, "temporary_password").inputValue(), "");
  assert.deepEqual(state.requests[0].body, { display_name: "New Teacher", username: "new_teacher", temporary_password: "12345678" });
  assert.ok(state.reads >= 2);
  assert.equal(state.requests[0].headers.origin, base);
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
});

for (const password of ["1234567", "😀😀😀😀😀😀😀"]) test("Reject seven characters without a write: " + password, async t => {
  const { page, state } = await screen(t);
  await fillCreate(page, password); await create(page);
  await error(page, "Password must be at least 8 characters");
  assert.equal(state.requests.length, 0);
});

for (const [status, detail] of [[409, "Username already taken"], [422, "Password must be at least 8 characters"]]) test("Render exact backend error: " + detail, async t => {
  const { page, state } = await screen(t); state.failure = { status, detail };
  await fillCreate(page); await create(page); await error(page, detail);
  assert.equal(await page.getByRole("heading", { name: "New Teacher", exact: true }).count(), 0);
  assert.equal(await field(page, "temporary_password").inputValue(), "");
});

test("Edit sends only display_name and refreshes the list", async t => {
  const { page, state } = await screen(t);
  await page.getByRole("button", { name: "Edit teacher_one", exact: true }).click();
  await field(page, "edit_display_name").fill("Updated Teacher");
  await page.getByRole("button", { name: "Save name", exact: true }).click();
  await page.getByRole("heading", { name: "Updated Teacher", exact: true }).waitFor();
  assert.deepEqual(state.requests[0].body, { display_name: "Updated Teacher" });
  assert.equal(state.requests[0].method, "PATCH");
  await page.getByText("Teacher name updated.", { exact: true }).waitFor();
});

test("Deactivation requires confirmation; cancel does not write; success removes action", async t => {
  const { page, state } = await screen(t);
  await page.getByRole("button", { name: "Deactivate teacher_one", exact: true }).click();
  await page.getByRole("button", { name: "Cancel deactivation", exact: true }).click();
  assert.equal(state.requests.length, 0);
  await page.getByRole("button", { name: "Deactivate teacher_one", exact: true }).click();
  await page.getByRole("button", { name: "Confirm deactivation", exact: true }).click();
  await page.getByText("Inactive", { exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Deactivate teacher_one", exact: true }).count(), 0);
  assert.equal(state.requests[0].path, `/staff/${teacher.id}/deactivate`);
  assert.equal(state.requests[0].body, null);
});

test("Teacher receives route denial and no Staff API request", async t => {
  const { page, response, state } = await screen(t, { role: "teacher" });
  assert.equal(response.status(), 403);
  await page.getByText("You do not have permission", { exact: true }).waitFor();
  assert.equal(state.reads, 0);
});

test("Anonymous browser returns to login", async t => {
  const { page, state } = await screen(t, { role: "anonymous" });
  await page.waitForURL(`${base}/`); assert.equal(state.reads, 0);
});

for (const status of [401, 403]) test("Staff API access loss: " + status, async t => {
  const { page, state } = await screen(t); state.failure = { status, detail: "Not allowed" };
  await fillCreate(page); await create(page);
  if (status === 401) await page.waitForURL(`${base}/`);
  else {
    await error(page, "You do not have permission");
    assert.equal(await page.getByRole("heading", { name: "Teacher One", exact: true }).count(), 0);
    assert.equal(await field(page, "temporary_password").count(), 0);
  }
});

test("API error allows retry without exposing internal details", async t => {
  const { page, state } = await screen(t); state.failure = { status: 500, detail: "secret database error" };
  await fillCreate(page); await create(page);
  await error(page, "Unable to complete the request. Please try again.");
  assert.equal(await page.getByText("secret database error").count(), 0);
  state.failure = null; await fillCreate(page); await create(page);
  await page.getByRole("heading", { name: "New Teacher", exact: true }).waitFor();
});

test("Repeated submit events produce one write while pending", async t => {
  const { page, state } = await screen(t); state.postDelay = 400;
  await fillCreate(page);
  await page.locator('form[aria-label="Add Teacher"]').evaluate(form => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  await page.getByRole("button", { name: "Saving…", exact: true }).waitFor();
  assert.equal(await page.locator('input[name="username"]').evaluate(el => el.disabled), true);
  await page.getByRole("heading", { name: "New Teacher", exact: true }).waitFor();
  assert.equal(state.requests.length, 1);
});

test("Loading then empty state", async t => {
  const { page } = await screen(t, { rows: [coordinator], loadDelay: 500 });
  await page.getByText("Loading Teacher accounts…", { exact: true }).waitFor();
  await page.getByText("No Teacher accounts yet.", { exact: true }).waitFor();
});

test("Failed list load offers retry", async t => {
  const { page } = await screen(t, { failFirstLoad: true });
  await error(page, "Unable to load Teacher accounts. Please try again.");
  await page.getByRole("button", { name: "Refresh list", exact: true }).click();
  await page.getByRole("heading", { name: "Teacher One", exact: true }).waitFor();
});

test("Failed post-save refresh preserves committed result and warns without repeating write", async t => {
  const { page, state } = await screen(t, { failRefresh: true });
  await fillCreate(page); await create(page);
  await page.getByRole("heading", { name: "New Teacher", exact: true }).waitFor();
  await error(page, "Changes saved, but the list could not be refreshed.");
  assert.equal(state.requests.length, 1);
});

test("Network write failure is reported and password cleared", async t => {
  const { page, state } = await screen(t); state.failure = "network";
  await fillCreate(page); await create(page);
  await error(page, "Unable to save changes. Refresh the list before trying again.");
  assert.equal(await field(page, "temporary_password").inputValue(), "");
});

for (const status of [401, 403]) test("Initial staff load handles access loss: " + status, async t => {
  const { page } = await screen(t, { listFailure: status });
  if (status === 401) await page.waitForURL(`${base}/`);
  else {
    await error(page, "You do not have permission");
    assert.equal(await page.getByRole("heading", { name: "Teacher One", exact: true }).count(), 0);
  }
});

test("SessionShell redirects an expired session while the staff form is open", async t => {
  const { page, state } = await screen(t);
  await fillCreate(page);
  state.expired = true;
  // Exercise the existing passive session check without waiting for its polling interval.
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForURL(`${base}/`);
  assert.equal(state.requests.length, 0);
});

test("AC5: deactivating the only active Coordinator is blocked with the agreed message", async t => {
  const { page, state } = await screen(t);
  await page.getByRole("button", { name: "Deactivate coordinator_hidden", exact: true }).click();
  await page.getByRole("heading", { name: "Deactivate Coordinator?", exact: true }).waitFor();
  state.failure = { status: 409, detail: "At least one coordinator must stay active" };
  await page.getByRole("button", { name: "Confirm deactivation", exact: true }).click();
  await error(page, "At least one coordinator must stay active");
  const coordinators = page.getByRole("list", { name: "Coordinator accounts" });
  await coordinators.getByText("Active", { exact: true }).waitFor();
  assert.equal(state.requests.length, 1);
  assert.equal(state.requests[0].path, `/staff/${coordinator.id}/deactivate`);
});

test("AC5: a Coordinator can be deactivated while another stays active", async t => {
  const second = { ...coordinator, id: "00000000-0000-4000-8000-000000000002", username: "coordinator_two", display_name: "Coordinator Two" };
  const { page } = await screen(t, { rows: [coordinator, second, { ...teacher }] });
  await page.getByRole("button", { name: "Deactivate coordinator_two", exact: true }).click();
  await page.getByRole("button", { name: "Confirm deactivation", exact: true }).click();
  await page.getByRole("status").filter({ hasText: "Coordinator account deactivated." }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Deactivate coordinator_two", exact: true }).count(), 0);
  await page.getByRole("button", { name: "Deactivate coordinator_hidden", exact: true }).waitFor();
});


// Exercise the real middleware and Staff layout for the newly integrated route.
for (const role of ["anonymous", "teacher", "coordinator"]) {
  test(`enquiries route protection: ${role}`, async t => {
    const context = await browser.newContext();
    t.after(() => context.close());
    if (role !== "anonymous") await context.addCookies([{name:"ako_session", value:`ui-${role}`, url:base, httpOnly:true, sameSite:"Lax"}]);
    let reads = 0;
    await context.route("**/api/user/**", route => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/user/session") return route.fulfill({json:{user_id:coordinator.id,display_name:"UI fixture",role},headers:{"X-Session-Expires-At":new Date(Date.now()+1800000).toISOString()}});
      if (path === "/api/user/enquiries") { reads++; return route.fulfill({json:[]}); }
      return route.fulfill({status:404,json:{}});
    });
    const page = await context.newPage();
    const response = await page.goto(`${base}/enquiries`);
    if (role === "anonymous") {
      assert.equal(new URL(page.url()).pathname, "/");
    } else if (role === "teacher") {
      assert.equal(response.status(), 403);
      await page.getByText("You do not have permission", {exact:true}).waitFor();
    } else {
      assert.equal(response.status(), 200);
      await page.getByText("No enquiries on this page.").waitFor();
      assert.equal(await page.getByRole("link", {name:"Enquiries",exact:true}).count(), 1);
    }
    assert.equal(reads, role === "coordinator" ? 1 : 0);
  });
}


test("Account management, login and learners share typography, controls and navigation", async t => {
  const { page, context } = await screen(t, { viewport: { width: 1280, height: 900 } });
  await page.getByRole("heading", { name: "Teacher One", exact: true }).waitFor();
  const appearance = async (selector) => page.locator(selector).first().evaluate(el => {
    const s = getComputedStyle(el);
    return { font: s.fontFamily, size: s.fontSize, color: s.color, background: s.backgroundColor, radius: s.borderRadius, border: s.borderTopWidth, minHeight: s.minHeight };
  });
  const accountHeading = await appearance("h1");
  const accountField = await appearance('input[name="username"]');
  const accountButton = await appearance('button[type="submit"]');
  const accountBar = await appearance("header.bar");
  assert.equal(await page.getByRole("link", { name: "Account management", exact: true }).getAttribute("aria-current"), "page");
  if (process.env.UI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.UI_SCREENSHOT_DIR}/accounts-desktop.png`, fullPage: true });
  await context.route("**/api/user/learners", route => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.goto(`${base}/learners`);
  await page.getByRole("heading", { name: "Learners", exact: true }).waitFor();
  assert.deepEqual(await appearance("h1"), accountHeading);
  assert.deepEqual(await appearance("header.bar"), accountBar);
  assert.deepEqual(await appearance("button.btn:not(.btn-secondary)"), accountButton);
  await page.getByRole("button", { name: "Add learner", exact: true }).click();
  assert.deepEqual(await appearance('input[type="text"]'), accountField);
  if (process.env.UI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.UI_SCREENSHOT_DIR}/learners-desktop.png`, fullPage: true });
  await page.goto(base);
  await page.getByLabel("Password", { exact: true }).waitFor();
  assert.deepEqual(await appearance("h1"), accountHeading);
  assert.deepEqual(await appearance('input[name="username"]'), accountField);
  assert.deepEqual(await appearance('button[type="submit"]'), accountButton);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  if (process.env.UI_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.UI_SCREENSHOT_DIR}/login-mobile.png`, fullPage: true });
});
