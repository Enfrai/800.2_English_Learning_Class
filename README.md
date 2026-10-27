# Ako English Learning Class

Ako helps an English conversation club manage learner records, class sessions,
attendance and reusable lessons. Visitors can view class information and send
enquiries. Learners can check in by QR code and access shared lesson materials
without an account.

## Documentation

- **[User manual](docs/manual/Ako_User_Manual.md)**: role-based instructions,
  every feature, operation steps, validation messages and current limitations.
- [User manual in Word](docs/manual/Ako_User_Manual.docx)
- [QR sign-in walkthrough and validation checklist](docs/manual/Ako_User_Manual.md#77-verify-qr-sign-in-step-by-step)
- [Requirements and user stories](docs/system_analysis/)
- [System design and Ako UI kit](docs/system_design/)
- [Database design and schema notes](database/)
- [Docker tests and result files](tests/docker/README.md)
- [Browser system tests](tests/system/README.md)
- [Manual acceptance test scripts](docs/system_test/)

## Features and roles

| Area | Features | Who uses it |
| --- | --- | --- |
| Accounts | Role-based login/logout, idle expiry, teacher account creation, name editing and deactivation | Staff; account administration is coordinator-only |
| Learners | Add/edit records, duplicate-name confirmation, CSV import | Both staff roles; CSV import is coordinator-only |
| Classes and attendance | One session per date, lesson association, manual attendance, QR check-in and live updates | Both staff roles |
| Attendance follow-up | Past attendance corrections and audit history, learner history, printable PDF and CSV reports | Both roles can view history; corrections and reports are coordinator-only |
| Lessons | Create/edit/delete, attachments, search, topic filters, copying and learner sharing | Both roles; teachers edit their own lessons |
| Cultural review | Māori content flag and recorded review | Authors/coordinators flag; coordinators record reviews |
| Public pages | Class information, enquiries and separate staff login | Visitors; enquiry listing is coordinator-only |
| Learner materials | Shared files after successful QR sign-in, with 24-hour browser access | Learners; no login required |

There is one club list and no advance enrolment, class groups or learner accounts.
The current public schedule is sample content until approved.

## Architecture and repository layout

The browser connects to Nginx on port **8080**. Nginx routes pages to Next.js
and API traffic to FastAPI services. There are two replicas of each API and
one PostgreSQL database per service. Uploaded lesson files use a shared volume.

| Path | Purpose |
| --- | --- |
| `web/` | Next.js 15, React 19, Material Web and the shared Ako styles |
| `server/compose.yaml` | Local application stack, project name `ako-server` |
| `server/nginx/` | Gateway routing, API rate limits and load balancing |
| `server/services/user/` | Authentication, staff, learners, imports and enquiries |
| `server/services/accessment/` | Classes, attendance, corrections, reports, QR and material grants |
| `server/services/lesson/` | Lessons, files, copying and cultural review |
| `database/` | Database design and schema documentation |
| `setup/` | Optional host environment bootstrap |
| `tests/` and `compose.test.yaml` | Isolated automated test stack and runners |
| `docs/` | Requirements, project, design and test documents |
| `docs/manual/` | English user manual in Markdown and Word |

The directory name `accessment` is retained to match the implementation.

## Prerequisites

For the recommended application setup:

- Git and access to this repository.
- Docker Engine with the Compose v2 plugin, or Docker Desktop on macOS/Windows.
  Start Docker Desktop and wait for its engine to be ready before running
  container commands. On Linux, start the Docker daemon.
- A current desktop browser and internet access for the first image/build download.
- Port 8080 available on the host.

Host Python, Node.js and PostgreSQL are **not required to run the application
in Docker**. The images use Python **3.14**, Node.js **24**, PostgreSQL **17**
and Nginx **1.28**. Local tests/development require their own tools, described below.
Docker CLI commands such as `docker --version` can run without an engine;
building and starting containers require a running engine.

Check Docker:

```sh
docker --version
docker compose version
docker info
```

## Quick start

### 1. Clone the release branch

From a terminal:

```sh
git clone --branch feature/v1.0/pre_release https://github.com/Enfrai/800.2_English_Learning_Class.git
cd 800.2_English_Learning_Class
cd server
```

All application lifecycle commands below run from **`server/`**.
If you already have a checkout, preserve uncommitted work before switching branches.

### 2. Create the local configuration

macOS/Linux:

```sh
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Review `server/.env` before starting. The shipped values are for local demonstration.
Choose private passwords and shared keys before enabling access from another computer.
Do not commit `.env`.

| Setting | Purpose |
| --- | --- |
| `USER_DB_PASSWORD`, `ACCESS_DB_PASSWORD`, `LESSON_DB_PASSWORD` | Database initialization passwords; keep existing values when reusing volumes |
| `DEMO_USERNAME`, `DEMO_PASSWORD` | Coordinator seeded when that username does not already exist |
| `INTERNAL_API_KEY` | Add this setting to `.env`; shared internal authentication key, defaulting to a local-only value |
| `CHECKIN_TOKEN_SECRET` | Shared QR token secret for both Accessment replicas |
| `CHECKIN_PUBLIC_ORIGIN` | Browser-reachable origin used in QR links; default `http://localhost:8080` |
| `AKO_BIND_ADDRESS` | Gateway bind address; default `127.0.0.1` |
| `COOKIE_SECURE` | `false` for local HTTP; `true` only when the external entry point uses HTTPS |
| `LESSON_SERVICE_URL` | Internal lesson URL; keep `http://lesson-service:8000` in this Compose stack |
| `USER_DATA_VOLUME`, `ACCESS_DATA_VOLUME`, `LESSON_DATA_VOLUME`, `LESSON_FILES_VOLUME` | Optional volume name overrides, for deliberately separate datasets |

To generate a key without installing host Python, use:

```sh
docker run --rm python:3.14-slim python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Generate separate values for `INTERNAL_API_KEY` and `CHECKIN_TOKEN_SECRET`.
Keep each setting consistent across replicas; Compose supplies it to the services.

### 3. Build and start

```sh
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

The first build downloads dependencies and may take several minutes.
Wait for the API/database health checks and the web server to become ready.

### 4. Open the application

Open **http://localhost:8080**.

For an unchanged local demo configuration, use:

- Username: `demo`
- Password: `DemoPass123!`

The initial account is a **Coordinator**. Create teacher accounts under
**Account management**. The coordinator username and password come from `.env`
on first creation; editing those settings does **not** reset an existing account.
The page links **Class Information**, **Ask About Classes** and **Staff Login**
open separate content.

Check the gateway and APIs:

```sh
curl http://localhost:8080/health
curl http://localhost:8080/api/user/health
curl http://localhost:8080/api/access/health
curl http://localhost:8080/api/lesson/health
```

On Windows PowerShell, use `curl.exe` for these examples.
A healthy gateway alone does not prove every service is healthy.

## Approved public information

The public page reads `web/src/content/club.json`. A maintainer can enter the
approved day, time, venue and address, then set `schedule.confirmed` to true.
Set an approved contact type/value and `contact.approved` to true to publish it.
A te reo greeting requires its text, reviewer and a valid non-future review date.
Keep public wording short and use only club-approved details.

After editing, run from `server/`:

```sh
docker compose up -d --build web
docker compose restart nginx
```

Verify `/class-information` while logged out. The enquiry link remains the fallback
when no approved contact is configured.

## Day-to-day operation

Run from `server/`:

```sh
docker compose ps
docker compose logs -f --tail=100
docker compose logs --tail=100 web user1 access1 lesson1 nginx
docker compose stop
docker compose start
docker compose down
```

`stop` keeps the containers; `start` resumes them. `down` removes containers and
the network but keeps persistent volumes. After `down`, use
`docker compose up -d`, not `start`.

After pulling source changes:

```sh
docker compose up -d --build
docker compose restart nginx
```

To rebuild selected components:

```sh
docker compose up -d --build web user1 user2 access1 access2 lesson1 lesson2
docker compose restart nginx
```

For a clean image build, without deleting application data:

```sh
docker compose build --no-cache
docker compose up -d
docker compose restart nginx
```

Do not use `docker compose down -v` as a build cleanup command: it removes the
stack's data volumes, including uploaded files. Back up required data before any reset.

## Phone access and QR codes

`localhost` on a phone means the phone itself. For a real phone demo:

1. Put the computer and phone on the same reachable Wi-Fi network.
2. Find the computer's LAN address, for example `192.168.1.20`.
3. In `server/.env`, set `AKO_BIND_ADDRESS=0.0.0.0` and
   `CHECKIN_PUBLIC_ORIGIN=http://192.168.1.20:8080`.
4. Set private internal and QR secrets. Allow inbound TCP 8080 in the host firewall
   for the intended local network.
5. From `server/`, run `docker compose up -d --build`, then
   `docker compose restart nginx`.
6. On the phone, open `http://192.168.1.20:8080/class-information`.
   If it loads, staff can open today's class, choose **Open check-in**, and scan.

Use one consistent hostname when signing in and returning to materials:
browser cookies do not transfer between `localhost` and a LAN IP.
Changing the QR secret or public origin requires issuing suitable new codes.
Closing QR check-in does not remove an already issued 24-hour material grant.
See the [manual's QR instructions](docs/manual/Ako_User_Manual.md#7-qr-check-in-and-learner-materials).
For a complete real-phone check, follow the [step-by-step walkthrough](docs/manual/Ako_User_Manual.md#77-verify-qr-sign-in-step-by-step)
and [additional validation cases](docs/manual/Ako_User_Manual.md#78-additional-validation-cases-and-results).
Use a new test learner who has not already been marked Present.

## Local development tools

Docker is the supported full-system route above. A host-only Next.js process
on port 3000 does not replace Nginx or the three API services.

For frontend dependency installation and a production build, from the repository root:

```sh
cd web
npm ci
npm run build
```

Use Node.js 24 to match Docker. `npm run dev` starts the development server on
port 3000; integrated API use additionally needs working service URLs and gateway
routing. Server-side `USER_API_URL`, `ACCESS_API_URL` and `LESSON_API_URL` must
point to reachable API base URLs, not browser-facing `/api/...` paths.

For Python development, use a virtual environment and install each service's
requirements. Python 3.14 matches the current images; the optional
`setup/buildup_dev_environment.py` still provisions Python 3.12 on macOS/Windows.
It is not required for Docker and does not establish parity with the container runtime.

Example using Python 3.14, from the repository root:

```sh
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r server/services/user/requirements-dev.txt
python -m pip install -r server/services/accessment/requirements-dev.txt
python -m pip install -r server/services/lesson/requirements-dev.txt
```

On Windows, create the environment with `py -3.14 -m venv .venv`, then activate
using `.venv\Scripts\Activate.ps1`. If activation is restricted, call
`.venv\Scripts\python.exe` directly. Each API also needs its own PostgreSQL
`DATABASE_URL`; cross-service calls require consistent internal keys and URLs.
Run Uvicorn from that service directory, for example
`python -m uvicorn app:app --host 127.0.0.1 --port 8001` in
`server/services/user/`. This is an individual API development command,
not a complete application startup.

## Testing and results

### Recommended isolated Docker run

From the **repository root**, with the Docker engine running:

```sh
python3 tests/run_docker_tests.py
```

Windows:

```powershell
py tests/run_docker_tests.py
```

Or use Docker only, without host Python:

```sh
docker compose -f compose.test.yaml -p ako-tests run --build --rm test-backend
docker compose -f compose.test.yaml -p ako-tests run --build --rm test-web
docker compose -f compose.test.yaml -p ako-tests run --build --rm test-system
docker compose -f compose.test.yaml -p ako-tests down --remove-orphans
```

The helper runs all supported groups, records exit codes and cleans its unique
test project. The explicit Docker commands require checking every command's
exit code and running cleanup yourself. The test stack uses separate databases
and no published ports. Do not combine it with `server/compose.yaml`.

Run one group with `python3 tests/run_docker_tests.py --suite backend`,
`--suite web` or `--suite system`. Add `--keep` for debugging.
Do not run multiple helpers concurrently in the same checkout.

| Result path | What to inspect |
| --- | --- |
| `test-results/summary.json` | Current helper exit codes and overall result |
| `test-results/backend/*.html`, `*.xml`, `*.log` | Service test reports and logs |
| `test-results/web/summary.json`, `*.log` | Frontend test results |
| `test-results/system/report.html` | Browser system report |
| `test-results/system/failures/` | Failure screenshots and traces, when recorded |

Open HTML reports in a browser. `SKIPPED` means not executed, even when the
suite exits successfully. A failed build can leave older HTML files, so check
the current summary first. Reports may be overwritten by the next run.

### Host browser and service tests

Host Chrome tests remain supported. Use a disposable deployment and follow
[the browser test instructions](tests/system/README.md); set
`BROWSER_CHANNEL=chrome` to use installed Google Chrome. These tests create
records and may end the demo account's existing session. Never point them at
a dataset you need to preserve.

For the complete User Service suite, activate the test environment above and run
from the repository root:

```sh
python server/services/user/tests/run_postgres.py
```

This runner creates and verifies its own disposable PostgreSQL container.
Supplying only `TEST_DATABASE_URL` does not enable its guarded cross-replica tests.

For Accessment and Lesson pytest tests, start the throwaway PostgreSQL server described in
[server testing instructions](server/README.md), install the service's
`requirements-dev.txt`, and run pytest from that service directory with
`TEST_DATABASE_URL` set. A PostgreSQL-capable test role must be able to create
and drop the generated test databases.

The [Docker testing guide](tests/docker/README.md) documents suite selections,
coverage limits and specialized authentication runners.

## Data, initialization and backups

PostgreSQL data and lesson uploads persist in four named Docker volumes.
The three database volume names retain the legacy `fastapi-microservices_...`
prefix; this is intentional compatibility, not the current project name.
Inspect the actual names with `docker volume ls` and the Compose configuration.
Avoid sharing the same explicit volumes between separate development/test stacks.

Startup creates tables and applies the implemented additive schema upgrades.
Back up data before an upgrade. Legacy duplicate class dates are refused rather
than silently deleted. Design documents are references; the running services
own schema initialization.

For backup, pause writes and take consistent dumps of all three databases plus
the uploaded file volume. From `server/`, database dump examples are:

```sh
docker compose exec -T postgres-user pg_dump -U user_app -d userdb -Fc -f /tmp/userdb.dump
docker compose cp postgres-user:/tmp/userdb.dump ./userdb.dump
docker compose exec -T postgres-access pg_dump -U access_app -d accessdb -Fc -f /tmp/accessdb.dump
docker compose cp postgres-access:/tmp/accessdb.dump ./accessdb.dump
docker compose exec -T postgres-lesson pg_dump -U lesson_app -d lessondb -Fc -f /tmp/lessondb.dump
docker compose cp postgres-lesson:/tmp/lessondb.dump ./lessondb.dump
```

Back up the complete `lesson_files` volume using your Docker volume backup tool.
Keep files and database dumps together; neither alone is a complete restore.
Store backups outside the source checkout, restrict access, and test restoring
to a separate environment before replacing working data.

An explicit coordinator bootstrap utility is available for an initialized
User database with no active coordinator:

```sh
docker compose exec user1 python init_coordinator.py --database-url-env DATABASE_URL --username club_admin --display-name "Club Coordinator"
```

It prompts for a password in a real terminal and refuses to change an existing
active coordinator. It is not a password reset or general account editor.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Cannot connect to Docker | Start Docker Desktop/daemon; check `docker info` and the active Docker context |
| Port 8080 already allocated | Stop the conflicting application or deliberately change the published port and QR origin together |
| Build dependency download fails | Check network/proxy access; retry the build and inspect the first failing package/image |
| `package-lock.json` missing | Restore the tracked lockfile; `npm ci` and the Docker build need it |
| Page/API returns 502 or 503 | Check `docker compose ps`, then web/API/database logs; restart Nginx after recreating upstream containers |
| 403 on a staff page | Verify role and login, use one consistent origin, and inspect API logs; teachers cannot open coordinator-only features |
| Login works on one host but not another | Use the same hostname/IP; verify HTTP versus HTTPS and `COOKIE_SECURE` |
| Demo password changed in `.env` but login still fails | Existing accounts are not overwritten; use the original credentials or an agreed recovery procedure |
| QR opens on laptop but not phone | Configure LAN bind/origin, allow firewall access, and test the LAN URL on the phone first |
| Already signed in but no materials | Reuse the browser that completed QR sign-in; if manually marked or its cookie was lost, ask the teacher for the handout |
| File rejected | Lessons accept PDF/DOCX/JPG/JPEG/PNG up to 10 MiB each; imports require UTF-8 CSV up to 1 MiB |
| Write failed or response was lost | Refresh and inspect saved data before retrying to avoid duplicate or partial operations |

Current workflow limitations and safe user actions are documented in the
[user manual](docs/manual/Ako_User_Manual.md#10-troubleshooting-and-current-limitations).

## Contributing

Use a feature branch, preserve the shared Ako styles in `web/src/lib/` and
`web/src/styles/ako/`, and keep authorization checks on the server.
Add relevant tests for behavior changes. Update both manual formats whenever
a user workflow changes. Do not commit secrets, personal learner data, local
environments, generated test results or uploaded lesson files.
Use made-up data for development, demonstrations and tests.

Report defects in [GitHub Issues](https://github.com/Enfrai/800.2_English_Learning_Class/issues)
with the role, page, steps, expected/actual result and sanitized logs.
Include the commit and browser version; do not include passwords or session tokens.

## License

The repository is licensed under the [Apache License 2.0](LICENSE).
