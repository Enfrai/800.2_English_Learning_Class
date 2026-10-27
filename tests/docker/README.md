# Isolated Docker tests

<!--
Describe test execution, isolation, reports and troubleshooting.
Author: Shuohui Liu
Date: 19 Oct 2026
-->

Run these commands from the **repository root**, with Docker Desktop running.
The test stack uses its own Compose project/network, PostgreSQL 17 instances,
and temporary database storage. It has no published ports and does not mount
the Docker socket or any development database volume. Your usual app can keep
running on port 8080.

The backend test image uses Python 3.14 to match the service Dockerfiles.
The web test image uses Node.js 24 and installs the Chromium version matching
the project's Playwright dependency. Chrome is not needed on the host.

## Recommended: run all supported suites

Only Python's standard library and Docker are required on the host:

```bash
python3 tests/run_docker_tests.py
```

Windows:

```powershell
py tests/run_docker_tests.py
```

The helper builds the required images, runs backend, web and system suites
sequentially, records each exit code, and cleans up its uniquely named test
project even when tests fail. It continues to the other suites after an
individual test runner returns failure. Build failures stop the run.
Its process exit code is 0 only when the requested suites and cleanup succeed.

Run one group:

```bash
python3 tests/run_docker_tests.py --suite backend
python3 tests/run_docker_tests.py --suite web
python3 tests/run_docker_tests.py --suite system
```

Add `--keep` to leave application services running for troubleshooting. The
helper prints the unique project name. Do not run two helpers concurrently
against the same checkout: their reports use the same output directory.

## Docker-only commands

No local Python, Node.js, browser or PostgreSQL installation is required:

```bash
docker compose -f compose.test.yaml -p ako-tests run --build --rm test-backend
docker compose -f compose.test.yaml -p ako-tests run --build --rm test-web
docker compose -f compose.test.yaml -p ako-tests run --build --rm test-system
docker compose -f compose.test.yaml -p ako-tests down --remove-orphans
```

Each `run` command returns the test runner's exit code. Unlike the Python helper,
shells may continue after a failed command: inspect every command's result.
Dependencies remain running until `down`; their databases are tmpfs and are
discarded when the database containers stop. To start fresh for another system
test run, run `down` first.

Run a subset:

```bash
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=user test-backend
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=staff-ui test-web
```

Backend selections: `user`, `accessment`, `lesson`.
Web selections: `api`, `staff-ui`, `public-enquiry`,
`coordinator-enquiries`, `csv-ui`, `lessons-unit`, `lessons-ui`,
`materials-unit`, `materials-ui`, `sessions-unit`, `sessions-ui`, `reports-unit`, `reports-ui`, `checkin-unit`, `checkin-ui`, `public-unit`, `public-ui`, `public-a11y`.

## Coverage

| Group | What it runs |
| --- | --- |
| Backend | pytest in all three service directories, including the User Service's real PostgreSQL/cross-replica tests |
| Web | API cookie/adapter tests, staff UI and style parity, public enquiry, coordinator enquiry, CSV upload/import UI, lesson search/copy, learner materials and class-session and attendance-report unit/browser tests, including binary report adapters |
| System | The existing `tests/system/` suite against real Nginx, Next.js, two replicas of each API, and three isolated application databases |

Mocked web tests verify frontend behavior; they do not prove backend
authorization or persistence. System tests exercise real services.
The historical `us001.test.mjs` and `us002-integration.test.mjs` use specialized
fixture/control runners and are not invoked by this Compose configuration;
do not run those files directly or claim they are included in the web group.
Existing pytest skips remain visible in logs/XML/HTML, including the system
test for material-upload review reset that is marked unimplemented upstream.

## Results

Reports are written to `test-results/` on your host and retained after cleanup:

| Path | Contents |
| --- | --- |
| `summary.json` | Overall result/exit codes from the Python helper |
| `backend/summary.json` | User, Accessment and Lesson process results |
| `backend/user.html`, `accessment.html`, `lesson.html` | Detailed pytest reports; open in a browser |
| `backend/*.xml` | JUnit XML for CI |
| `backend/*.log` | Complete pytest output |
| `web/summary.json` and `web/*.log` | Web suite statuses and complete output |
| `web/*-desktop.png`, `web/login-mobile.png` | UI style comparison screenshots |
| `system/report.html`, `system/results.xml`, `system/system.log` | Full system test results |
| `system/failures/*.png` and `*.zip` | Screenshot and Playwright trace for failing tests that use the shared page fixture |

Open `test-results/system/report.html` in your browser. A trace can be inspected
with a local Playwright trace viewer; reports may contain test account data.
Passing tests show `PASSED`; assertions show `FAILED`; fixture/startup failures
show `ERROR`; `SKIPPED` means that case was not executed. A successful suite
may still contain explicitly skipped cases.

Reports are overwritten by the next run of the same group. Check the current
`summary.json` before reading an older HTML file: build/setup failures can
leave HTML reports from a previous run.

## Logs and troubleshooting

The runners stream test output directly to your terminal. In another terminal:

```bash
docker compose -f compose.test.yaml -p ako-tests ps -a
docker compose -f compose.test.yaml -p ako-tests logs --tail=100 nginx web user1 access1 lesson1
```

For helper runs, add the printed project name:

```bash
docker compose -f compose.test.yaml -p ako-tests-EXAMPLE logs --tail=100
docker compose -f compose.test.yaml -p ako-tests-EXAMPLE down --remove-orphans
```

The first build downloads Python/npm dependencies, browser binaries and images.
Later builds reuse Docker's cache. To rebuild without cache:

```bash
docker compose -f compose.test.yaml -p ako-tests build --no-cache test-backend test-web test-system
```

Do not combine this file with `server/compose.yaml`. Its isolation is intentional.
System setup uses a guarded direct connection to the **test** Accessment
database instead of invoking Docker inside a test container. Authentication
uses shared HttpOnly cookies and native Ako form selectors.
Accessibility checks use the locally installed axe-core asset inside the
system image, so tests do not depend on a public CDN at runtime.


US-005 report commands: `TEST_SUITE=reports-unit` or `TEST_SUITE=reports-ui`
with `test-web`. Backend runs include report roster and PDF/CSV tests. The
system group includes real multi-service report downloads.

US-011 adds `TEST_SUITE=checkin-unit` and `TEST_SUITE=checkin-ui` for `test-web`,
QR endpoint cookie-bridge checks in `api`, PostgreSQL window-lock tests in
`accessment`, and real QR/sign-in/live-attendance cases in the system group.

US-009 adds public content unit tests, public homepage browser tests and a
Lighthouse accessibility audit. Select `TEST_SUITE=public-unit`, `public-ui` or
`public-a11y` with `test-web`. The default web suite includes all three.
Audit reports are `test-results/web/us009-home-lighthouse.json` and
`test-results/web/us009-accessibility-summary.json`. All audit dependencies are
installed in the image; no public script CDN is required.

US-016 adds `TEST_SUITE=history-unit`, `history-session` and `history-ui`
with `test-web`. The default web group includes all three. Backend includes
history aggregation and permission tests. The system group includes real
learner history and correction refresh checks. See
[history test instructions](../../docs/system_test/attendance_history_system_tests.md).
