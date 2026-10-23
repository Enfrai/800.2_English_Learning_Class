/** Focused frontend runner: real Next.js rendering with test-only API responses, no database/Docker. */
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, rm, cp, access } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const web = dirname(dirname(fileURLToPath(import.meta.url)));
const mock = createServer((req, res) => {
  const role = req.headers.cookie?.includes("ui-coordinator") ? "coordinator"
    : req.headers.cookie?.includes("ui-teacher") ? "teacher" : null;
  const headers = { "Content-Type": "application/json", "Cache-Control": "no-store", "X-Session-Expires-At": new Date(Date.now() + 1800000).toISOString() };
  const allowed = role && (req.url === "/session" || role === "coordinator");
  res.writeHead(!role ? 401 : allowed ? 200 : 403, headers);
  res.end(JSON.stringify(req.url === "/session" && role
    ? { user_id: "00000000-0000-4000-8000-000000000001", display_name: "UI fixture", role }
    : { allowed: Boolean(allowed) }));
});
let next;
let temp;
let output = "";
try {
  await access(join(web, ".next/standalone/server.js"));
  mock.listen(0, "127.0.0.1");
  await once(mock, "listening");
  // Copy only generated output to a temporary runtime, keeping the repository build unchanged.
  temp = await mkdtemp(join(tmpdir(), "us002-ui-"));
  await cp(join(web, ".next/standalone"), temp, { recursive: true });
  await cp(join(web, ".next/static"), join(temp, ".next/static"), { recursive: true });
  const reservation = createServer();
  reservation.listen(0, "127.0.0.1");
  await once(reservation, "listening");
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  // Match the public localhost gateway; Next normalizes loopback-IP redirects.
  const base = `http://localhost:${port}`;
  next = spawn(process.execPath, [join(temp, "server.js")], {
    cwd: temp,
    env: { ...process.env, PORT: String(port), HOSTNAME: "127.0.0.1", NEXT_TELEMETRY_DISABLED: "1", USER_API_URL: `http://127.0.0.1:${mock.address().port}` },
    stdio: ["ignore", "pipe", "pipe"],
  });
  next.stdout.on("data", chunk => { output += chunk; });
  next.stderr.on("data", chunk => { output += chunk; });
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (next.exitCode !== null) throw new Error(`Next exited: ${output}`);
    try { ready = (await fetch(base)).ok; } catch { /* The child may still be binding its port. */ }
    if (ready) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (!ready) throw new Error(`Next readiness timeout: ${output}`);
  const tests = spawn(process.execPath, ["--test", "--test-concurrency=1", join(web, "tests/staff-ui.test.mjs")], {
    cwd: web, env: { ...process.env, US002_UI_BASE_URL: base }, stdio: "inherit",
  });
  process.exitCode = (await once(tests, "exit"))[0] ?? 1;
} finally {
  if (next && next.exitCode === null) {
    const stopped = once(next, "exit");
    next.kill("SIGTERM");
    await stopped;
  }
  mock.closeAllConnections();
  if (mock.listening) await new Promise(resolve => mock.close(resolve));
  if (temp) await rm(temp, { recursive: true, force: true });
}
