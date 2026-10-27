# US-016: learner attendance history

Coordinator and Teacher open **Learners → History** beside a learner.
The history page displays the learner's name, newest class first, Present/Absent,
and a summary such as `Present 3 of 5`. Both roles have read-only access here.
Use the existing US-015 session attendance screen for coordinator corrections.
Learners and visitors cannot access the page or API.

## Counting rules

- Start and end dates are inclusive. Either may be blank for an open boundary.
- Include past dated sessions and closed sessions today in the club timezone.
  Future sessions and today's unfinished sessions are excluded.
- Include sessions from the learner's local creation date onwards. Preserve any
  explicit older attendance records, for imported or corrected historical data.
- With no eligible attendance records, show `No attendance recorded yet`.
- Once history exists, a missing Present record in an eligible session means
  Absent, matching the existing attendance/report model.
- Explicit Absent records count as recorded history. Never mix another learner's
  attendance into this learner's status or summary.
- Date filters affect both rows and totals. An empty filtered range has a
  separate `No class sessions in this date range` message.
- Read current attendance, so US-015 corrections appear on the next load.

These rules resolve details not specified in the story card. Historical records
before creation are preserved; unrelated old classes do not create false absences.
No schema migration, new learner fields or new permissions are needed.

## API

`GET /learners/{learner_id}/attendance-history` in the Accessment service accepts
optional ISO `start_date` and `end_date` query parameters. The browser uses
`/api/staff/access/learners/{learner_id}/attendance-history` through the existing
HttpOnly cookie adapter. The service validates staff identity and role, validates
the learner with the User service, then reads sessions and attendance in one
SELECT. Only learner ID and name accompany the history; contact data is omitted.

Responses: 200 history, 401 missing/expired login, 403 unsupported role, 404 unknown
learner, 422 invalid UUID/dates or reversed range, 503 unavailable learner data.
Responses are not cacheable. The history resource exposes no write endpoint.

## Automated tests

From `server/services/accessment`, after installing development dependencies:

```bash
python -m pytest tests/test_attendance_history.py -q
```

From `web`:

```bash
npm ci
npm run test:history-unit
npm run build
npm run test:history-session
npm run test:history-ui
```

Browser tests use local Chrome by default. For Playwright Chromium, install it
with `npx playwright install chromium`, then set `BROWSER_CHANNEL=chromium`.
UI tests use a temporary production Next server and generated/mock API fixtures.
Adapter tests exercise the real Next cookie proxy with a local upstream server.
They do not prove PostgreSQL persistence. `UI_SCREENSHOT_DIR` optionally saves
browser screenshots for review.

From the repository root, run the same selections in isolated Docker:

```bash
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=history-unit test-web
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=history-session test-web
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=history-ui test-web
python3 tests/run_docker_tests.py --suite backend
python3 tests/run_docker_tests.py --suite system
```

The system suite includes `tests/system/test_attendance_history.py`, which uses
real generated learners, dated sessions and US-015 corrections. Run it only
against a disposable test system. It verifies correction refresh, inclusive
filters, teacher read-only access, empty history and anonymous denial.

Inspect console exit codes and `test-results/web/summary.json`, `web/*.log`,
backend HTML/JUnit reports and `system/report.html`. Clean up Docker-only runs:

```bash
docker compose -f compose.test.yaml -p ako-tests down --remove-orphans
```

Docker was unavailable during implementation verification. The full container
system suite must be run separately in an environment with Docker.

## Recorded implementation checks (26 Oct 2026)

- Production Next build and TypeScript validation passed.
- History backend: 39 passed; frontend unit: 22 passed.
- History browser: 14 passed; real cookie adapter: 11 passed.
- Related backend history/report/check-in/client suites: 125 passed in total.
- Existing staff browser regression: 27 passed; report adapter: 12 passed.
- Docker helper tests: 4 passed. New Python files passed Ruff checks.
- The 360px browser check passed; axe WCAG A/AA reported no violations.
- Full PostgreSQL/Docker system tests were added but not executed here.
