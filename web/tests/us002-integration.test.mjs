/** Real gateway acceptance; the owning isolated runner supplies generated credentials and DB controls. */
import assert from "node:assert/strict";
import { before, after, test } from "node:test";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { chromium } from "playwright";

const base = process.env.US001_E2E_URL;
const password = process.env.US001_E2E_PASSWORD;
const controlPath = process.env.US002_TEST_CONTROL;
if (!base || !password || !controlPath || !process.env.US001_TEST_RUN_ID) throw new Error("Use the owned isolated gateway runner.");
let browser;
before(async () => { browser = await chromium.launch({ channel: "chrome", headless: true }); });
after(async () => { await browser?.close(); });
const field = (page, name) => page.locator(`input[name="${name}"]`);

// Controls are external test processes restricted to the uniquely owned DB, never production endpoints.
function record(username) {
  return JSON.parse(execFileSync("python3", [controlPath, "record", username], { encoding: "utf8" }));
}
async function loginApi(username, value = password) {
  return fetch(`${base}/api/user/login`, { method: "POST", headers: { "Content-Type": "application/json", Origin: base }, body: JSON.stringify({ username, password: value }) });
}
async function api(path, token, method = "GET", body) {
  return fetch(`${base}/api/user${path}`, { method, headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined });
}
async function openStaff(t) {
  const context = await browser.newContext(); t.after(() => context.close());
  const page = await context.newPage();
  await page.goto(base);
  await field(page, "username").fill("e2e_coordinator");
  await field(page, "password").fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("heading", { name: "Coordinator home", exact: true }).waitFor();
  await page.getByRole("link", { name: "Account management", exact: true }).click();
  await page.getByRole("heading", { name: "Teacher accounts", exact: true }).waitFor();
  return { page, context };
}
async function fill(page, username, value = password) {
  await field(page, "display_name").fill("Integration New Teacher");
  await field(page, "username").fill(username);
  await field(page, "temporary_password").fill(value);
}
async function create(page) { await page.getByRole("button", { name: "Create Teacher", exact: true }).click(); }
async function error(page, value) { await page.getByRole("alert").filter({ hasText: value }).waitFor(); }

// AC1 also verifies the successful frontend write becomes a real UUID-backed record.
test("AC1: Coordinator creates Teacher through the real browser and sees persisted account", async t => {
  const { page } = await openStaff(t);
  await fill(page, "e2e_created"); await create(page);
  await page.getByText("Teacher account created.", { exact: true }).waitFor();
  await page.getByText("Username: e2e_created", { exact: true }).waitFor();
  const row = record("e2e_created");
  assert.match(row.id, /^[0-9a-f-]{36}$/);
  assert.equal(row.role, "teacher"); assert.equal(row.is_active, true);
  assert.equal((await loginApi("e2e_created")).status, 200);
  assert.equal(await field(page, "temporary_password").inputValue(), "");
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  assert.equal(await page.getByRole("list", { name: "Teacher accounts" }).getByText("e2e_coordinator", { exact: true }).count(), 0);
});

test("AC2: duplicate username exact message, original account unchanged", async t => {
  const before = record("e2e_duplicate");
  const { page } = await openStaff(t);
  await fill(page, "e2e_duplicate"); await create(page);
  await error(page, "Username already taken");
  assert.deepEqual(record("e2e_duplicate"), before);
});

test("AC3: seven characters rejected by both frontend and real API", async t => {
  const { page, context } = await openStaff(t);
  await fill(page, "e2e_short", password.slice(0, 7)); await create(page);
  await error(page, "Password must be at least 8 characters");
  const cookie = (await context.cookies()).find(c => c.name === "ako_session");
  const response = await fetch(`${base}/api/user/staff`, { method: "POST", headers: { Cookie: `ako_session=${cookie.value}`, Origin: base, "Content-Type": "application/json" }, body: JSON.stringify({ username: "e2e_short", display_name: "Too short", temporary_password: password.slice(0, 7) }) });
  assert.equal(response.status, 422);
  assert.deepEqual(await response.json(), { detail: "Password must be at least 8 characters" });
  assert.equal(record("e2e_short"), null);
});

test("AC3: eight characters accepted through browser and usable for login", async t => {
  const { page } = await openStaff(t);
  await fill(page, "e2e_eight", password.slice(0, 8)); await create(page);
  await page.getByText("Teacher account created.", { exact: true }).waitFor();
  assert.equal((await loginApi("e2e_eight", password.slice(0, 8))).status, 200);
});

test("AC6: rename updates browser and database without changing UUID or username", async t => {
  const before = record("e2e_rename");
  const { page } = await openStaff(t);
  await page.getByRole("button", { name: "Edit e2e_rename", exact: true }).click();
  await field(page, "edit_display_name").fill("Renamed Integration Teacher");
  await page.getByRole("button", { name: "Save name", exact: true }).click();
  await page.getByRole("heading", { name: "Renamed Integration Teacher", exact: true }).waitFor();
  const after = record("e2e_rename");
  assert.equal(after.id, before.id); assert.equal(after.username, before.username);
  assert.equal(after.display_name, "Renamed Integration Teacher");
});

test("AC4: confirmed deactivation retains identity and revokes persisted session", async t => {
  const login = await loginApi("e2e_deactivate"); assert.equal(login.status, 200);
  const token = (await login.json()).sessionid;
  const before = record("e2e_deactivate");
  const { page } = await openStaff(t);
  await page.getByRole("button", { name: "Deactivate e2e_deactivate", exact: true }).click();
  await page.getByRole("button", { name: "Cancel deactivation", exact: true }).click();
  assert.equal(record("e2e_deactivate").is_active, true);
  await page.getByRole("button", { name: "Deactivate e2e_deactivate", exact: true }).click();
  await page.getByRole("button", { name: "Confirm deactivation", exact: true }).click();
  await page.getByText("Teacher account deactivated.", { exact: true }).waitFor();
  const row = page.getByRole("listitem").filter({ hasText: "Username: e2e_deactivate" });
  await row.getByText("Inactive", { exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Deactivate e2e_deactivate", exact: true }).count(), 0);
  const after = record("e2e_deactivate");
  assert.equal(after.id, before.id); assert.equal(after.username, before.username);
  assert.equal(after.display_name, before.display_name); assert.equal(after.is_active, false);
  assert.ok(after.sessions.some(s => s.token_hash === createHash("sha256").update(token).digest("hex") && s.revoked_at));
  assert.equal((await loginApi("e2e_deactivate")).status, 401);
  assert.equal((await api("/session", token)).status, 401);
  assert.equal((await api("/activity", token, "POST")).status, 401);
  assert.equal((await fetch(`${base}/api/user/session`, { headers: { Cookie: `ako_session=${token}` } })).status, 401);
});

test("Anonymous and Teacher cannot call any Staff API; Teacher page returns 403", async t => {
  const login = await loginApi("e2e_view"); const token = (await login.json()).sessionid;
  const target = record("e2e_view");
  for (const actor of [null, token]) {
    for (const [path, method, body] of [["/staff", "GET"], ["/staff", "POST", { username: "e2e_forbidden_create", display_name: "No", temporary_password: password }], [`/staff/${target.id}`, "PATCH", { display_name: "No" }], [`/staff/${target.id}/deactivate`, "POST"]]) {
      const response = await api(path, actor, method, body);
      assert.equal(response.status, actor ? 403 : 401);
      assert.equal(response.headers.get("cache-control"), "no-store");
    }
  }
  const context = await browser.newContext(); t.after(() => context.close());
  await context.addCookies([{ name: "ako_session", value: token, url: base, httpOnly: true, sameSite: "Lax" }]);
  const page = await context.newPage();
  assert.equal((await page.goto(`${base}/account-management`)).status(), 403);
  await page.getByText("You do not have permission", { exact: true }).waitFor();
});

test("Cookie attributes, Origin protection and no-store hold through actual Nginx", async t => {
  const { context } = await openStaff(t);
  const cookie = (await context.cookies()).find(c => c.name === "ako_session");
  assert.ok(cookie.httpOnly); assert.equal(cookie.sameSite, "Lax"); assert.equal(cookie.secure, false); assert.equal(cookie.path, "/");
  const before = record("e2e_csrf");
  for (const origin of [undefined, "http://evil.example", "null"]) {
    const response = await fetch(`${base}/api/user/staff/${before.id}/deactivate`, { method: "POST", headers: { Cookie: `ako_session=${cookie.value}`, ...(origin ? { Origin: origin } : {}) } });
    assert.equal(response.status, 403); assert.equal(response.headers.get("cache-control"), "no-store");
  }
  assert.deepEqual(record("e2e_csrf"), before);
  const response = await fetch(`${base}/api/user/staff`, { headers: { Cookie: `ako_session=${cookie.value}` } });
  assert.equal(response.status, 200); assert.equal(response.headers.get("cache-control"), "no-store");
  assert.ok((await response.json()).every(row => Object.keys(row).sort().join() === ["id", "username", "display_name", "role", "is_active"].sort().join()));
});

test("Two Coordinator clients racing through gateway create one username", async () => {
  const a = (await (await loginApi("e2e_coordinator")).json()).sessionid;
  const b = (await (await loginApi("e2e_coordinator_two")).json()).sessionid;
  const data = { username: "e2e_race", display_name: "Race Teacher", temporary_password: password };
  const responses = await Promise.all([api("/staff", a, "POST", data), api("/staff", b, "POST", data)]);
  assert.deepEqual(responses.map(r => r.status).sort(), [201, 409]);
  assert.equal(record("e2e_race").username, "e2e_race");
  // Repeated gateway checks are later correlated with both upstream IPs in Nginx logs.
  for (let i = 0; i < 4; i++) assert.equal((await api("/session", a)).status, 200);
});
