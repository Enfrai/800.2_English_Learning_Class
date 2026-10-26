# US-011: Open check-in with a QR code

## User workflow

1. A Teacher or Coordinator opens **Class sessions** and starts today's class.
2. In its detail page, choose **Open check-in** in **QR check-in**.
3. Show the code/link on screen, or choose **Print QR code** for an A4 sheet.
4. Learners scan it and use the existing US-012 name sign-in page, with no account.
5. Open **Attendance**. The list refreshes every three seconds and shows Present
   with the recorded time. The Attendance page links back via **Manage QR check-in**.
6. Choose **Close check-in**. Previously issued codes immediately stop accepting
   sign-ins. Windows also expire at four hours or the end of that club day,
   whichever happens first. Historical/future or closed classes cannot open.

The screen follows the existing Ako tokens and controls. The printable document
is separate from the staff page: portrait A4, black on white, class date, readable
link and a 110 mm square code image including its quiet zone. No navigation,
learner list or staff identity prints. The larger image keeps the actual QR
pattern above the required 80 mm width for the generated sign-in links.

## Phone access and Docker

The default public address is `http://localhost:8080`, suitable for testing on
that computer. A phone cannot use the computer's localhost address. Copy
`server/.env.example` to `server/.env` if needed, keep any existing values,
and set the computer's LAN address, for example:

```dotenv
AKO_BIND_ADDRESS=0.0.0.0
CHECKIN_PUBLIC_ORIGIN=http://192.168.1.20:8080
CHECKIN_TOKEN_SECRET=replace_with_one_shared_random_secret
```

Generate a secret with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Both Accessment replicas must use the same secret and public origin. The phone
and computer should be on the same reachable Wi-Fi network. Use HTTPS as the
public origin when the deployment serves HTTPS. The bind-address default remains
127.0.0.1 unless configured. This feature needs no paid QR service or app.

From the repository root:

```bash
git switch feature/v1.0/US_011
git pull --ff-only
docker compose -f server/compose.yaml up -d --build --force-recreate --wait
```

Keep existing database volumes. No schema migration is added. Local Python
installs must reinstall the Accessment requirements for `qrcode`.

## API and persistence

Staff use `/api/staff/access/sessions/{id}/check-in` through the cookie bridge:

| Method | Operation |
| --- | --- |
| GET | Current state and, only while open, the sign-in URL and QR SVG |
| POST | Open today's window, or reuse the existing live window without extending it |
| DELETE | Close all unclosed windows for this session; safe to repeat |

States are `not-open`, `open`, `closed`, `expired` and `unavailable`.
All staff roles are checked before querying a classroom. The adapter requires a
single HttpOnly session cookie and a matching Origin for changes; browser Bearer
headers cannot override the cookie. Responses are no-store and nosniff.

A fresh cryptographically random UUID seeds a new window. A domain-separated
HMAC using the shared secret produces an unguessable, URL-safe 256-bit token.
Only its SHA-256 hash is stored in the existing `checkin_windows` table. Either
replica can recover the display URL from the window ID and secret, so page
refreshes, restarts and duplicate Open clicks preserve the code and expiry.
Different windows/classes get different tokens. URLs contain tokens, not dates.

Changing the secret leaves old codes unverifiable for staff display. Existing
learner links still follow the stored hash, closure and expiry rules. Staff see
`unavailable` and can close/reopen to issue a fresh displayable code. Legacy
manually inserted windows behave the same way. Secrets are not stored in the DB.

Open, close, deletion and successful sign-in acquire the same classroom row lock.
A sign-in rechecks its window after acquiring that lock and after the name lookup.
Closed/expired windows cannot write attendance or issue a material grant, even
when the browser already loaded the form. A sign-in committed before Close is
retained; closing never removes existing attendance or US-013 access grants.
Expiry is checked on each request and does not need a scheduled worker.
The existing wrong-name throttle and duplicate-sign-in checks remain in effect.

## Local tests

Activate the Python virtual environment and install dependencies from the root:

```bash
python -m pip install -r server/services/accessment/requirements-dev.txt
cd server/services/accessment
python -m pytest tests/test_checkin_management.py -v
```

Web tests from the root:

```bash
cd web
npm ci
npm run test:checkin-unit
npm run build
node --test tests/attendance-session.test.mjs
npm run test:checkin-ui
```

The browser runner uses an isolated production Next server and mocked services.
It defaults to installed Chrome. For Playwright Chromium, install it with
`npx playwright install chromium` and set `BROWSER_CHANNEL=chromium` (PowerShell:
`$env:BROWSER_CHANNEL='chromium'`). These checks do not modify application data.

## Isolated Docker tests and results

From the repository root:

```bash
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=accessment test-backend
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=checkin-unit test-web
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=checkin-ui test-web
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=api test-web
python tests/run_docker_tests.py --suite system
```

The backend suite includes two real PostgreSQL concurrency cases in
`test_checkin_management_postgres.py`. The system group includes
`tests/system/test_checkin_management.py`, exercising real QR opening, anonymous
name sign-in, automatic staff attendance and immediate closure through Nginx.
The isolated test stack sets its public origin to `http://nginx`, reachable from
its test browser. Use made-up learners and disposable databases only.

Inspect command exit codes, `test-results/backend/` logs/XML/HTML,
`test-results/web/` logs and summary JSON, and the host runner's
`test-results/summary.json`. Full report/cleanup instructions remain in
`tests/docker/README.md`.

## Acceptance coverage

| Criterion | Evidence |
| --- | --- |
| AC1: code/link in 2 seconds, unique per session | Timed API and browser tests; per-class token isolation; repeated-open test |
| AC2: link identifies one session with long random token | Token/hash and scope tests; decoded real generated QR |
| AC3: readable A4 code at least 8 cm, class date | Print-document tests; real browser iframe geometry; A4 PDF render and QR decoding review |
| AC4: immediate close | Public endpoint and prefetched/slow-lookup sign-in tests; close UI test; PostgreSQL lock test |
| AC5: automatic four-hour expiry | Exact-boundary API tests, club-midnight test, browser expiry test |
| AC6: Present and time within 10 seconds | Browser checkbox/count update within the deadline; real-service system case |
| No regressions | Existing class, material-grant and report tests; wrong-name throttling; safe retry, stale-response and non-overlapping slow-refresh tests |

Local unit/API/browser checks, production web build and Ruff are run during
implementation. Actual QR images are decoded and the A4 print sheet is rendered
and inspected. Docker/PostgreSQL/full-stack cases are provided but require their
runtime; they are not claimed as executed in the development tool environment.
