# US-014 — Manage class sessions

## Feature and entry points

Teacher and Coordinator accounts use **Class sessions** in the existing staff
navigation, or open <http://localhost:8080/sessions> after login. The list offers
**Start today's class** and **New class session**. A classroom opens at
`/sessions/<UUID>`, with lesson selection, a confirmed deletion action, and an
**Attendance** link to `/sessions/<UUID>/attendance`. Attendance now has a return
link to its classroom. The existing shared Ako styles are used throughout.

- One session is permitted per club date. PostgreSQL and SQLite use the unique
  index `uq_class_sessions_date`; repeated or concurrent starts return the same
  session rather than changing its owner or linked lesson.
- Today is calculated by the Accessment service using `CLUB_TIMEZONE`, default
  `Pacific/Auckland`. Browser date validation uses the backend's date.
- New dates can be today or earlier. A future date returns **Date cannot be in
  the future**. An empty date returns **Class date is required**.
- The list is ordered newest first and includes the current linked lesson title.
  Dates with no lesson show **No lesson linked**. A deleted lesson shows
  **Lesson unavailable**, retaining the classroom and attendance.
- Both staff roles can link, replace or unlink any saved lesson. Linking changes
  only the Accessment association; it never edits or copies the lesson itself.
- Any present or absent attendance record prevents deletion with **This session
  has attendance and cannot be deleted**. An empty classroom needs confirmation;
  deleting it also removes its empty lesson link and QR windows, not the lesson.
- Attendance writes, past-attendance corrections and deletion lock the same
  classroom row. Foreign keys provide a second barrier against unsafe deletion.
- Existing US-015 restrictions still apply: Teachers cannot change past
  attendance; Coordinators use its correction workflow. Session dates cannot be
  edited through this feature.

The QR generation workflow remains US-011. No extra learner accounts, class
groups, enrolment or timetable are introduced.

## Start the app

From the repository root:

```sh
git switch temp/1.0_US_014
git pull --ff-only
docker compose -f server/compose.yaml up -d --build --force-recreate --wait web access1 access2
docker compose -f server/compose.yaml restart nginx
```

Both Accessment instances run an additive startup upgrade under PostgreSQL
transaction advisory lock 800014. It creates `session_lesson_links` and adds the
unique class-date index without resetting existing data. No volume deletion is
needed. The authenticated Lesson API defaults to `http://nginx/api/lesson` and
can be configured with `LESSON_API_URL` on Accessment.

If the pre-existing database contains duplicate dates, startup lists the
conflicting dates and refuses the upgrade. It never guesses which attendance
to keep, deletes records or silently merges classes. Inspect safely with:

```sql
SELECT session_date, COUNT(*)
FROM class_sessions
GROUP BY session_date
HAVING COUNT(*) > 1;
```

Resolve legacy duplicate sessions while preserving attendance and audit history,
then restart. This manual data decision is deliberately outside automatic DDL.

## Local unit and browser tests

Install service test dependencies in your virtual environment, then run from the
repository root:

```sh
python -m pip install -r server/services/accessment/requirements-dev.txt
python -m pytest server/services/accessment/tests/test_class_sessions.py server/services/accessment/tests/test_lesson_client.py server/services/accessment/tests/test_user_client.py -q
python -m pytest tests/docker/test_runner.py -q
cd web
npm ci
npm run test:sessions-unit
npm run build
node --test tests/attendance-session.test.mjs
npm run test:sessions-ui
```

These feature API/unit tests use temporary SQLite databases with foreign keys
and mocked Lesson/User boundaries. Their cloned test schema omits the existing
PostgreSQL-only interval constraint and audit DDL; they do not establish the
behavior of PostgreSQL locks. Browser tests run an isolated production Next
server with mocked API replies, using local Chrome by default. Set
`BROWSER_CHANNEL=chromium` for an installed Playwright Chromium.

## PostgreSQL concurrency and Docker suites

The new `test_class_sessions_postgres.py` uses the existing isolated PostgreSQL
fixture and tests two API replicas starting a class at once, plus deletion
waiting for a committed attendance write. With `TEST_DATABASE_URL` set to a test
PostgreSQL server that allows disposable database creation:

```sh
cd server/services/accessment
python -m pytest tests/test_class_sessions_postgres.py -q
```

The fixture creates and drops a uniquely named test database. It does not modify
the database named in that URL. These tests use synchronization events rather
than timing guesses to coordinate the writer and deletion request.

The independent Docker test stack includes all Accessment tests and the new
`sessions-unit` and `sessions-ui` browser groups. From the repository root:

```sh
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=accessment test-backend
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=sessions-unit test-web
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=sessions-ui test-web
```

Inspect process exit codes and `test-results/backend/accessment.html`,
`test-results/backend/accessment.xml`, `test-results/backend/accessment.log`,
`test-results/web/summary.json`, and the `sessions-*.log` files. The full helper
`python3 tests/run_docker_tests.py` also includes these groups. See
`tests/docker/README.md` for cleanup and isolation.

## Acceptance checklist

| Criterion | Coverage |
| --- | --- |
| AC1: Start today, open within two seconds | Real API timing; browser creation and navigation |
| AC2: One session per date | Repeated starts, unique-index rejection, concurrent SQLite requests, PostgreSQL replica test |
| AC3: Save a linked lesson without changing it | Link/replace/unlink, authenticated upstream requests, unchanged lesson source; browser selection and failure recovery |
| AC4: List newest first with date/title | Three dated sessions, current titles/macrons, missing lesson; browser refresh |
| AC5: Block deletion with attendance | Present and absent cases, actual app attendance integration, confirmed deletion and concurrency tests |
| AC6: Reject future dates | API and browser exact messages, invalid/missing date checks, zero new records |
| Permissions | Teacher/Coordinator allowed; anonymous/nonstaff denied; same-origin adapter writes; historical attendance remains protected |
| Upgrades and usability | Idempotent upgrade, preserved rows, duplicate-date refusal, 360px Ako layouts, service retries and Attendance return navigation |

The local unit/API/browser suites and production build were verified during
implementation. PostgreSQL concurrency and the full Docker stack require their
own run; mocked/SQLite checks do not imply that those suites were executed.
