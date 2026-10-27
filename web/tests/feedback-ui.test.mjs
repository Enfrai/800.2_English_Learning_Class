/* Verify the feedback entry on all layout types and accessible form interactions.
 * Author: Shuohui Liu
 * Date: 24 Oct 2026
 */

import assert from "node:assert/strict";
import { before, after, test } from "node:test";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";

const base = process.env.FEEDBACK_BASE_URL;
if (!base) throw Error("Use tests/run-feedback-ui.mjs");
let browser;
before(async () => { browser = await chromium.launch({ channel: process.env.BROWSER_EXECUTABLE_PATH ? undefined : process.env.BROWSER_CHANNEL || "chrome", executablePath: process.env.BROWSER_EXECUTABLE_PATH, headless: true }); });
after(async () => { await browser?.close(); });

async function pageFor(t, mobile = false) {
  const context = await browser.newContext({ viewport: mobile ? { width: 360, height: 740 } : { width: 1280, height: 900 } });
  await context.addCookies([{ name: "ako_session", value: "ui-coordinator", url: base }]);
  const page = await context.newPage();
  t.after(() => context.close());
  return page;
}
async function fill(page) {
  await page.getByLabel("Title", { exact: true }).fill("Calendar issue");
  await page.getByLabel("Email", { exact: true }).fill("visitor@example.test");
  await page.getByLabel("Description", { exact: true }).fill("The date picker is not opening.");
}
for (const path of ["/", "/class-information", "/ask-about-classes", "/feedback", "/sessions", "/learners", "/lessons", "/reports/attendance", "/enquiries", "/account-management", "/sign-in/invalid", "/materials", "/not-a-real-page"]) {
  test(`feedback icon is visible and bottom-right on ${path}`, async t => {
    const page = await pageFor(t);
    await page.goto(base + path, { waitUntil: "domcontentloaded" });
    const entry = page.getByRole("link", { name: "Send feedback", exact: true });
    await entry.waitFor();
    const bounds = await entry.boundingBox();
    assert.ok(bounds.width >= 44 && bounds.height >= 44);
    assert.ok(Math.abs(1280 - (bounds.x + bounds.width) - 16) <= 2);
    assert.ok(Math.abs(900 - (bounds.y + bounds.height) - 16) <= 2);
    assert.equal(await entry.getAttribute("href"), "/feedback");
  });
}
test("keyboard entry opens the public form without requiring login", async t => {
  const page = await pageFor(t);
  await page.context().clearCookies();
  await page.goto(base + "/class-information");
  await page.getByRole("link", { name: "Send feedback" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("heading", { name: "Feedback", exact: true }).waitFor();
  assert.ok(await page.getByRole("button", { name: "Submit feedback" }).isVisible());
});
test("required fields and invalid email are blocked before posting", async t => {
  const page = await pageFor(t);
  let requests = 0;
  await page.route("**/api/user/feedback", route => { requests++; return route.fulfill({ json: { message: "unexpected" } }); });
  await page.goto(base + "/feedback");
  await page.getByRole("button", { name: "Submit feedback" }).click();
  assert.equal(await page.locator("form").getByRole("alert").count(), 3);
  assert.equal(await page.locator(":focus").getAttribute("name"), "title");
  await fill(page);
  await page.getByLabel("Email", { exact: true }).fill("wrong");
  await page.getByRole("button", { name: "Submit feedback" }).click();
  await page.getByText("Please enter a valid email address", { exact: true }).waitFor();
  assert.equal(requests, 0);
});
test("one pending write, successful status and cleared fields", async t => {
  const page = await pageFor(t);
  let requests = 0;
  await page.route("**/api/user/feedback", async route => {
    requests++;
    assert.deepEqual(route.request().postDataJSON(), { title: "Calendar issue", email: "visitor@example.test", description: "The date picker is not opening." });
    await new Promise(resolve => setTimeout(resolve, 200));
    await route.fulfill({ json: { message: "Thank you. Your feedback has been submitted." } });
  });
  await page.goto(base + "/feedback");
  await fill(page);
  await page.locator("form").evaluate(form => { form.requestSubmit(); form.requestSubmit(); });
  await page.getByText("Thank you. Your feedback has been submitted.", { exact: true }).waitFor();
  assert.equal(requests, 1);
  assert.equal(await page.getByLabel("Title", { exact: true }).inputValue(), "");
  assert.equal(await page.getByLabel("Email", { exact: true }).inputValue(), "");
});
for (const status of [429, 502, 503]) test(`HTTP ${status} retains entered fields and allows later retry`, async t => {
  const page = await pageFor(t);
  await page.route("**/api/user/feedback", route => route.fulfill({ status, json: { detail: "private SMTP details" } }));
  await page.goto(base + "/feedback");
  await fill(page);
  await page.getByRole("button", { name: "Submit feedback" }).click();
  await page.locator("form").getByRole("alert").waitFor();
  assert.equal(await page.getByLabel("Title", { exact: true }).inputValue(), "Calendar issue");
  assert.equal(await page.getByLabel("Email", { exact: true }).inputValue(), "visitor@example.test");
  assert.ok(!await page.locator("form").getByRole("alert").innerText().then(value => value.includes("private")));
  assert.equal(await page.getByRole("button", { name: "Submit feedback" }).isDisabled(), false);
});
test("mobile layout, print hiding and accessibility", async t => {
  const page = await pageFor(t, true);
  await page.goto(base + "/feedback");
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.addScriptTag({ content: await readFile(new URL("../node_modules/axe-core/axe.min.js", import.meta.url), "utf8") });
  const results = await page.evaluate(async () => window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] } }));
  assert.deepEqual(results.violations.map(v => v.id), []);
  await page.emulateMedia({ media: "print" });
  assert.equal(await page.getByRole("link", { name: "Send feedback" }).isVisible(), false);
});
