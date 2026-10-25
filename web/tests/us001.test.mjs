import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { chromium } from "playwright";

const base = process.env.US001_E2E_URL;
const password = process.env.US001_E2E_PASSWORD;
if (!base || !password || !process.env.US001_TEST_RUN_ID) throw new Error("Run via the isolated PostgreSQL/browser runner.");
let browser;
before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || "chrome", headless: true }); });
after(async () => { await browser?.close(); });

async function open(t) {
  const context = await browser.newContext();
  t.after(() => context.close());
  const page = await context.newPage();
  await page.goto(base);
  await page.locator('input[name="username"]').waitFor();
  return { context, page };
}
async function fill(page, username, value = password) {
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(value);
}
async function login(page, username = "e2e_teacher", heading = "Teacher home") {
  await fill(page, username);
  const start = performance.now();
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("heading", { name: heading, exact: true }).waitFor();
  return performance.now() - start;
}
async function control(action, username) {
  const response = await fetch(`${base}/__test/${action}`, { method: "POST", headers: { "X-Test-Key": process.env.US001_E2E_KEY, "Content-Type": "application/json" }, body: JSON.stringify({ username }) });
  assert.equal(response.status, 200);
  return response.json();
}

test("AC1: Teacher home and Teacher-only menu within three seconds", async (t) => {
  const { context, page } = await open(t);
  const elapsed = await login(page);
  console.log(`AC1 measured login-to-visible-home: ${Math.round(elapsed)} ms`);
  assert.ok(elapsed <= 3000, `Login took ${elapsed} ms`);
  assert.equal(await page.locator("nav").getAttribute("aria-label"), "Teacher menu");
  assert.equal(await page.getByRole("link", { name: "Account management" }).count(), 0);
  const cookie = (await context.cookies()).find(c => c.name === "ako_session");
  assert.ok(cookie.httpOnly);
  assert.equal(cookie.sameSite, "Lax");
  assert.equal(await page.evaluate(() => document.cookie.includes("ako_session")), false);
});

test("Coordinator redirect and menu", async (t) => {
  const { page } = await open(t);
  await login(page, "e2e_coordinator", "Coordinator home");
  assert.equal(await page.locator("nav").getAttribute("aria-label"), "Coordinator menu");
  await page.getByRole("link", { name: "Account management" }).click();
  await page.getByRole("heading", { name: "Account management" }).waitFor();
});

test("AC2: exact incorrect-password text and login URL", async (t) => {
  const { page } = await open(t);
  await fill(page, "e2e_teacher", "incorrect");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.locator("p.msg.msg-error").waitFor();
  assert.equal(await page.locator("p.msg.msg-error").textContent(), "Username or password is incorrect");
  assert.equal(new URL(page.url()).pathname, "/");
});

test("AC3: fifth failure shows retry time", async (t) => {
  const { page } = await open(t);
  for (let i = 0; i < 5; i++) {
    await fill(page, "e2e_lock", "incorrect");
    const completed = page.waitForResponse(r => r.url().endsWith("/api/user/login"));
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    const response = await completed;
    assert.equal(response.status(), i === 4 ? 423 : 401);
    await page.getByRole("button", { name: "Sign in", exact: true }).waitFor();
  }
  await page.getByText(/Account temporarily locked\. Please try again at/).waitFor();
  assert.equal(new URL(page.url()).pathname, "/");
});

test("AC4: direct account management is 403 with no account data", async (t) => {
  const { page } = await open(t);
  await login(page, "e2e_forbidden");
  const response = await page.goto(`${base}/account-management`);
  assert.equal(response.status(), 403);
  await page.getByText("You do not have permission", { exact: true }).waitFor();
  const html = await response.text();
  assert.ok(!html.includes("e2e_coordinator"));
  assert.equal(await page.getByRole("heading", { name: "Account management" }).count(), 0);
  const access = await page.request.get(`${base}/api/user/account-management/access`);
  assert.equal(access.status(), 403);
  assert.deepEqual(await access.json(), { detail: "You do not have permission" });
});

test("AC5: logout clears cookie, rejects replay and redirects other tabs", async (t) => {
  const { context, page } = await open(t);
  await login(page, "e2e_tabs");
  const token = (await context.cookies()).find(c => c.name === "ako_session").value;
  const second = await context.newPage();
  await second.goto(`${base}/teacher`);
  await second.getByRole("heading", { name: "Teacher home" }).waitFor();
  await page.getByRole("button", { name: "Log out", exact: true }).click();
  await page.waitForURL(`${base}/`);
  await second.waitForURL(`${base}/`);
  assert.equal((await context.cookies()).some(c => c.name === "ako_session"), false);
  const replay = await fetch(`${base}/api/user/session`, { headers: { Authorization: `Bearer ${token}` } });
  assert.equal(replay.status, 401);
  await page.goto(`${base}/teacher`);
  await page.waitForURL(`${base}/`);
});

test("AC5: passive checks do not refresh; explicit input refreshes", async (t) => {
  const { page } = await open(t);
  await login(page, "e2e_activity");
  const before = await control("age", "e2e_activity");
  await page.evaluate(async () => { await fetch("/api/user/session"); await fetch("/api/user/session"); });
  assert.deepEqual(await control("inspect", "e2e_activity"), before);
  const activity = page.waitForResponse(r => r.url().endsWith("/api/user/activity"));
  await page.getByRole("heading", { name: "Teacher home" }).click();
  assert.equal((await activity).status(), 200);
  const after = await control("inspect", "e2e_activity");
  assert.ok(Date.parse(after.expires_at) > Date.parse(before.expires_at));
});

test("AC5: accelerated idle timer returns to login; expired token rejected", async (t) => {
  const { page } = await open(t);
  await page.clock.install();
  await login(page, "e2e_idle");
  await control("expire", "e2e_idle");
  await page.clock.fastForward(30 * 60 * 1000 + 1000);
  await page.waitForURL(`${base}/`);
  const result = await page.request.get(`${base}/api/user/session`);
  assert.equal(result.status(), 401);
});

// Merge regression: dev's learner page must work with a cookie-only US-001 login.
test("Cookie login reaches Learners and preserves create/edit APIs", async (t) => {
  const { page } = await open(t);
  await login(page);
  assert.equal(await page.evaluate(() => localStorage.getItem("ako.sessionid")), null);
  await page.getByRole("link", { name: "Learners", exact: true }).click();
  await page.getByRole("heading", { name: "Learners", exact: true }).waitFor();
  await page.getByRole("button", { name: "Add learner", exact: true }).click();
  await page.getByLabel("First name", { exact: true }).fill("Merge");
  await page.getByLabel("Family name", { exact: true }).fill("Cookie Test");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByText("Learner saved", { exact: true }).waitFor();
  const me = await page.request.get(`${base}/api/user/me`);
  assert.equal(me.status(), 200);
  assert.equal((await me.json()).role, "teacher");
  await page.getByRole("button", { name: "Log out", exact: true }).click();
  await page.getByRole("button", { name: "Sign in", exact: true }).waitFor();
  assert.equal((await page.request.get(`${base}/api/user/learners`)).status(), 401);
});
