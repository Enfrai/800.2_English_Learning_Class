# Browser system tests

Automated versions of the system test cases in the Test Plan (section 5).
They drive a real browser against a running Ako system. The manual scripts
that testers follow and sign off are in `docs/system_test/`.

| File | Cases |
| --- | --- |
| `test_attendance_history.py` | US-016 current history, inclusive date filters, correction refresh and role boundaries |
| `test_club_information.py` | US-009 anonymous class information, 360px readability, short sentences and HTTP 404/home navigation |
| `test_checkin_management.py` | US-011 real QR open/sign-in/live attendance/close and anonymous management denial |
| `test_attendance_reports.py` | US-005 PDF/CSV downloads, current corrections, date validation and role boundaries through real services |
| `test_learners_page.py` | ST-11, and the Learners page parts of NT-05, NT-06, NT-07, NT-08, NT-10 |
| `test_attendance_page.py` | ST-01, US-004 AC1 to AC5, and the attendance page parts of NT-01, NT-06, NT-07, NT-10 |
| `test_corrections_page.py` | ST-04, ST-05 and the correction parts of NT-06 (US-015), with a new teacher account for each teacher test |
| `test_sign_in_page.py` | ST-14 from opening to closing check-in on the class page, with the materials page (US-011, 012, 013); US-012 AC1 to AC6; the sign-in parts of NT-06 and NT-11, on a 360 px phone |
| `test_review_flow.py` | ST-09 and the US-008 review rules through the API: the checks a page cannot reach (missing Origin, logged out, a teacher flagging another teacher's lesson) |
| `test_review_pages.py` | ST-09 on the lesson pages, US-008 AC1 to AC5, and the review parts of NT-06 and NT-10 |

## Recommended: isolated Docker tests

From the repository root, run `python3 tests/run_docker_tests.py --suite system`,
or `docker compose -f compose.test.yaml -p ako-tests run --build --rm test-system`.
See [Docker testing instructions](../docker/README.md) for all suites, reports
and cleanup. This mode uses temporary databases, bundled Chromium and no host
ports. The manual steps below are for a host-installed Python/browser only.

## Running the tests manually

1. Start Ako with throwaway database volumes, so test learners never mix
   with your own data (Test Plan section 3):

   ```bash
   cd server
   export USER_DATA_VOLUME=ako-systest_user_data
   export ACCESS_DATA_VOLUME=ako-systest_access_data
   export LESSON_DATA_VOLUME=ako-systest_lesson_data
   export LESSON_FILES_VOLUME=ako-systest_lesson_files
   docker compose up -d --build
   ```

2. Install the test dependencies once:

   ```bash
   cd tests/system
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/playwright install chromium
   ```

   To use the Google Chrome already on the computer instead, skip
   `playwright install` and set `BROWSER_CHANNEL=chrome` when running.

3. Run the tests from `tests/system`:

   ```bash
   .venv/bin/pytest -v
   ```

4. Remove the throwaway system and its data (from `server`, with the same
   variables exported):

   ```bash
   docker compose down
   docker volume rm ako-systest_user_data ako-systest_access_data \
     ako-systest_lesson_data ako-systest_lesson_files
   ```

Notes:

- The tests log in as the demo coordinator. A new login ends the previous
  demo session, so a browser where you are logged in as demo is logged out.
  Tests that need a teacher create a new teacher account (US-002) each time.
- The accessibility check loads axe-core from cdnjs, so it needs internet.
- `test_sign_in_page.py` clears `signin_failures` on the throwaway database
  before each test: every test request comes from this computer's address,
  which has a limit of 50 wrong names in 10 minutes.
- The attendance, sign-in and correction tests set up class sessions with
  `docker compose exec` on the running system (and the correction tests
  record last week's ticks the same way), so Docker must be on the same
  computer. Set `COMPOSE_FILE` if the system was started from another
  compose file.
- There is one class session per date (US-014). Tests share today's
  session, so present counts are checked as a rise from the number present
  when the test started. Each test that needs a past class gets a new one,
  on the first date at or before the one it asks for that has no class.
  The tests never delete attendance.
- Each test adds its own learners with a random suffix, so the tests run in
  any order and do not need an empty database.

