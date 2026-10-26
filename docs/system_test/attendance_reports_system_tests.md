# US-005: Attendance reports

## Entry point and roles

Sign in as a coordinator and choose **Attendance reports** in the staff menu.
The direct address is `http://localhost:8080/reports/attendance`.
Teachers, learners and visitors cannot access the page or export API.

## Behavior and explicit interpretation

- Start/end dates are inclusive. Equal dates produce a single-day report.
- Only actual dated class sessions become columns, in chronological order.
- The roster contains current active learners and historical learners referenced
  by attendance in the selected range. Same-name learners remain separate by UUID.
- A current Present record displays `Present`; explicit absent records and missing
  present records display `Absent`. This is a reporting convention, not advance
  enrolment. A learner added later can therefore show Absent for earlier classes.
  The convention is stated on the page and in the PDF. The story does not define
  historical enrolment, and this project has no enrolment or class groups.
- Latest US-015 corrections are reflected. Export never changes attendance or audits.
- PDF and CSV use the same matrix. Only names, class dates and statuses are exported.
  No contact details, first language, learner UUIDs or staff identities are included.
- PDFs are landscape A4 with six class dates per band, repeated table headings,
  wrapped names, range labels and page numbers. More dates continue in new bands;
  more learners continue across pages. Black-and-white printing stays readable.
- The bundled DejaVu Sans font preserves Māori macrons on local and Docker installs.
  Its redistribution license is included beside the unchanged font file.
- CSV is UTF-8 with BOM and standard quoting, with one row per learner and one
  column per date. Formula-like names receive a leading apostrophe for spreadsheet
  safety. The PDF keeps the entered name unchanged.
- A range with classes but no learners yields a valid header-only CSV and a PDF
  explaining that there are no learners. A range without classes yields the exact
  message `No classes found for these dates` and no downloadable file.
- Reversed dates yield `Start date must be before end date` and no export.
- Missing/unavailable historical learner data causes a retryable error, not a
  silently incomplete report. One authenticated roster request includes historical
  names; no per-learner network loop is needed.
- Files are built in memory and returned with attachment, no-store and nosniff
  headers. The staff adapter preserves binary bytes and download headers, uses the
  HttpOnly cookie as a server-side Bearer token, and checks Origin for POST.

The final library/club layout is still an open question for Julie in the story.
This implementation supplies a readable default without requiring that consultation
before the feature can be used.

## Deploy the branch

From the repository root:

```bash
git switch feature/v1.0/US_005
git pull --ff-only
docker compose -f server/compose.yaml up -d --build --force-recreate --wait web user1 user2 access1 access2
docker compose -f server/compose.yaml restart nginx
```

This feature adds no database migration. Keep existing volumes.

For Python local use, activate the project virtual environment and reinstall:

```bash
python -m pip install -r server/services/accessment/requirements-dev.txt
python -m pip install -r server/services/user/requirements-dev.txt
```

## Local automated checks

Backend report tests are SQLite-based and do not require PostgreSQL:

```bash
cd server/services/accessment
python -m pytest tests/test_attendance_reports.py tests/test_report_client.py -v
```

From the repository root, for the User-service report roster:

```bash
cd server/services/user
python -m pytest tests/test_report_roster.py -v
```

From the repository root, for web tests:

```bash
cd web
npm ci
npm run test:reports-unit
npm run build
node --test tests/report-session.test.mjs
npm run test:reports-ui
```

Browser tests default to installed Chrome. To use Playwright Chromium instead:

```bash
npx playwright install chromium
BROWSER_CHANNEL=chromium npm run test:reports-ui
```

On Windows PowerShell set `$env:BROWSER_CHANNEL='chromium'` before the last command.
The browser runner starts an isolated production Next server with mocked service
responses; its tests do not modify the running application's data.

## Isolated Docker checks

From the repository root:

```bash
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=accessment test-backend
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=user test-backend
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=reports-unit test-web
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=reports-ui test-web
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=api test-web
```

Run full multi-service tests, including `tests/system/test_attendance_reports.py`:

```bash
python tests/run_docker_tests.py --suite system
```

The real report system cases create only made-up learners/classes in the isolated
stack and verify current corrections, PDF/CSV downloads and role boundaries.
Do not point system tests at a database holding real learner data.

See `tests/docker/README.md` for complete setup and cleanup. Check each command's
exit code. Backend results are under `test-results/backend/` (log, XML and HTML);
web results are under `test-results/web/` (logs and summary JSON). The host runner
also writes `test-results/summary.json`. For a live container's output:

```bash
docker compose -f compose.test.yaml -p ako-tests logs test-backend test-web
```

## Acceptance and test mapping

| Criterion | Automated evidence |
| --- | --- |
| AC1: 3 classes, A4 PDF, each learner and status | `test_pdf_is_real_a4_with_each_name_status_and_date`; real system download case |
| AC2: no classes, exact message, no file | Backend PDF/CSV parametrized cases; browser empty-range case; real system empty-range case |
| AC3: reversed range, exact message, no export | Backend range validation, browser validation, real system reversed-range case |
| AC4: 12 classes/50 learners within 10 seconds, no clipped names | Timed backend HTTP export test; long-name PDF extraction; rendered multi-page visual review |
| AC5: spreadsheet CSV, rows and date columns | Matrix/CSV tests, binary adapter test and real system CSV download |
| Coordinator-only access | User and Accessment route tests, browser direct URL/navigation tests, real system teacher/anonymous case |
| Safe character handling | Macrons, same-name UUIDs, CSV quoting/formula tests, PDF escaped markup and long-name tests |
| Consistency and privacy | Single SELECT snapshot, one bulk roster call, latest corrections, no-write and minimal-fields tests |

Local unit/API/browser checks and the production web build are run during
implementation. Docker/PostgreSQL and real multi-service system tests require
the test stack and are not claimed as executed in the development tool environment.
