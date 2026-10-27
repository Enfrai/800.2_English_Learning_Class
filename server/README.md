# server

## Running unit tests

Unit tests use pytest and a throwaway PostgreSQL database. They never use the
databases started by `compose.yaml`.

1. Start a test PostgreSQL server (Docker Desktop must be running):

   ```bash
   docker run -d --rm --name ako-test-postgres -e POSTGRES_PASSWORD=test \
     -p 127.0.0.1:55432:5432 postgres:17-alpine
   ```

2. Create a virtual environment for the service and install the test
   dependencies. The steps are the same for every service with a `tests`
   folder (`user`, `accessment`, `lesson`); the example uses the User service:

   ```bash
   cd server/services/user
   python3.14 -m venv .venv
   .venv/bin/pip install -r requirements-dev.txt
   ```

3. Run the tests:

   ```bash
   TEST_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:55432/postgres \
     .venv/bin/pytest -v
   ```

   Each run creates a database named `ako_test_<random>` and drops it at the
   end. The database in the URL is only used to create and drop it.

4. Stop the test server when finished: `docker stop ako-test-postgres`.

## Internal service key

The Accessment Service looks up a learner by name for QR sign-in (US-012)
without a login. It proves itself to the User Service with `INTERNAL_API_KEY`,
which `compose.yaml` passes to `user1`, `user2`, `access1` and `access2`.
The default `local_internal_key` is for local development only; set a long
random value in the environment anywhere else. Nginx refuses
`/api/user/internal/` from outside, so the lookup is reachable only between
services.


## Class sessions (US-014)

Staff use `/sessions` to create or reopen today's class, create a past class,
choose its lesson and enter Attendance. Class dates are unique and use the
club's `Pacific/Auckland` date by default. Empty classes can be deleted after
confirmation; any attendance blocks deletion. The startup upgrade is additive
and refuses legacy duplicate dates instead of removing data.

See [class-session operation and tests](../docs/system_test/class_sessions_system_tests.md)
for local/Chrome checks and the PostgreSQL concurrency/Docker suites.


## US-005 attendance reports

Coordinators open **Attendance reports** in the staff menu, or
`http://localhost:8080/reports/attendance`. Select inclusive start/end dates
and download an A4 landscape PDF or UTF-8 CSV. Teachers cannot view or export
reports. Outputs use actual class dates and current attendance, including
corrections. No database migration is needed.

The Accessment service now needs ReportLab; reinstall its requirements for
local Python use. Its bundled licensed DejaVu Sans font preserves Māori
macrons without an OS font installation. Rebuild `web`, `user1`, `user2`,
`access1` and `access2` for Docker use, then restart Nginx.
See [report behavior, tests and commands](../docs/system_test/attendance_reports_system_tests.md).


## US-011 classroom QR check-in

Teacher and Coordinator users open today's class in **Class sessions**, then
choose **Open check-in**. The detail page shows the code, link and expiry, with
**Print QR code** and **Close check-in**. The Attendance page refreshes every
three seconds and links back through **Manage QR check-in**. Codes expire after
four hours or at club midnight and cannot open for other dates or closed classes.

For phone scanning configure `CHECKIN_PUBLIC_ORIGIN`, `CHECKIN_TOKEN_SECRET`
and, for LAN access, `AKO_BIND_ADDRESS` in `server/.env`. Rebuild/recreate the
Compose services to apply the settings and the new `qrcode` dependency. Existing
volumes and schema stay in place. See [QR check-in operation and tests](../docs/system_test/qr_checkin_system_tests.md).
