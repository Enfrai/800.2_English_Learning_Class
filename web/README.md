# ELC Web — Next.js + Material 3

<!--
Describe the containerized Next.js login test and local development workflow.
Author: Shuohui Liu
Date: 19 Oct 2026
-->

This web application tests the FastAPI User Service through the existing Nginx reverse proxy.

From the `fastapi-microservices` directory, run:

```bash
docker compose up -d --build
```

Open <http://localhost:8080>, then sign in with the demo credentials configured in the root `.env` (`DEMO_USERNAME` and `DEMO_PASSWORD`). The default demo username is `demo`.

The browser sends `POST /api/user/login` to Nginx, which forwards it to the User Service. The page displays success or error information but does not persist or display the session token.

The frontend runs in its own Node.js container. The host does not need Node.js for Docker-based deployment.

For local Next.js development, install Node.js and run `npm install` followed by `npm run dev` from this directory. Direct access to the development server on port 3000 will not proxy `/api/user/login`; use the Compose/Nginx entry point for integrated testing.

## UI components

The login screen uses Material Design 3 components from `@material/web` with
`@lit/react` adapters in `src/components/material.tsx`. Import these adapters for
new screens. Material Web is in maintenance mode; see its upstream README.
The login screen loads on the client (`ssr: false`) because these components use
browser APIs. Theme tokens and layout are in `src/app/(auth)/globals.css`.

## Logged-in pages

Pages for logged-in staff live in `src/app/(staff)` and use the Ako UI kit
(`docs/system_design/ako-ui-kit`), copied to `src/styles/ako`. Use the kit's
classes and change the kit first, then copy the CSS again. The login page and
the staff pages have separate root layouts, so the Material styles and the kit
styles never load on the same page.

Login uses the User service's HttpOnly cookie (see "US-001 authentication"
below). `SessionShell` with `layout="kit"` draws the navy menu bar for these
pages; the (auth) pages keep its default panel layout.

| Page | Path | Story |
| --- | --- | --- |
| Learners | `/learners` | US-003 |

Use `npm ci` for reproducible installs and `npm run build` for validation.
The Compose service is named `web`; its build context is `./web`.


## US-001 authentication

Login uses the User service's HttpOnly cookie. `/teacher`, `/coordinator` and
`/account-management` are protected by server-side middleware and a browser session
shell. Account management now provides the US-002 Teacher-management interface.
The server-only `USER_API_URL`, `ACCESS_API_URL` and `LESSON_API_URL` default to
the services' internal Compose names (`http://user-service:8000`,
`http://access-service:8000`, `http://lesson-service:8000`). Server-side calls do
not go through Nginx: they would all come from the web container's one address
and share one rate limit for every user. For separate local servers, set them to
each service's base URL. The browser still uses same-origin `/api/...` through
the gateway, where Nginx rate-limits each browser, including `/api/staff/*`.

After `npm ci`, run `npm run build`. For full isolated backend/browser verification:

```sh
# From repository root, with backend test dependencies, Docker, Node and Chrome:
US001_BROWSER_TESTS=1 python server/services/user/tests/run_postgres.py
```

The runner supplies temporary URLs, generated credentials and the isolated
PostgreSQL database; `npm run test:e2e` alone requires that test environment.
Browser tests use Playwright with the installed Google Chrome channel. No
credentials or tokens are written into browser storage or test source files.


## US-002 Staff Management — Phase 2

`/account-management` reuses the existing Coordinator middleware and SessionShell.
The screen shows Teacher accounts from `GET /api/user/staff`, with name,
username and Active/Inactive state. It creates Teachers, edits only display names,
and requires confirmation before soft deactivation. Coordinator accounts are listed
separately with Deactivate only (AC5): the only active Coordinator cannot be
deactivated ("At least one coordinator must stay active"). No delete action is provided.

Requests use same-origin cookies and no-store caching. The browser supplies Origin;
the frontend does not construct tokens or override CSRF checks. The backend remains
the authority for permissions, password length and username uniqueness. A 401
returns to login; a 403 removes staff content and displays the permission error.
Temporary passwords stay in form memory only and are cleared after API submission.

Validation preserves the exact duplicate-username and minimum-password messages.
A synchronous pending guard prevents duplicate writes before React updates disabled
controls. Successful responses update the list immediately and trigger a passive
refresh. If that refresh fails, the committed result remains visible with a warning;
the frontend never automatically retries a write. Network failure can leave a write's
outcome uncertain, so users are told to refresh before retrying.

Focused frontend checks (Node and installed Google Chrome required):

```sh
npm run build
npm run test:staff-ui
```

The test runner starts a temporary loopback Next.js runtime and a test-only session
API, then intercepts browser Staff requests with Playwright fixtures. It uses
`localhost` to match the public gateway hostname and avoid Next's loopback-IP redirect
normalization. No real backend, PostgreSQL, Docker or existing manual-test environment
is used. Owned child processes and temporary runtime files are removed afterward.
These tests verify frontend behavior, not real API authorization or persistence.

Coverage includes Teacher-only lists, loading/empty/error/retry states, mobile layout,
create and password boundaries (including Unicode), exact backend errors, rename,
deactivation confirmation/cancellation, pending-write suppression, 401/403 handling,
Teacher/anonymous route denial and session expiry through unchanged SessionShell.
Real API/database/gateway acceptance was completed in Phase 3, as recorded below.
AC4 lesson and attendance historical-page visibility remains **Pending Joint Verification**.
Existing trusted-host/public-origin and deployed HTTPS limitations remain outstanding.

### US-002 Phase 3 verification

The focused frontend suite passed 21/21. A separate isolated deployment with
PostgreSQL 17, two independent User Service replicas, Next.js Web and Nginx
passed all nine real-browser/API scenarios in `tests/us002-integration.test.mjs` and all eight
US-001 browser regressions. The real test module requires the owned isolated runner
to supply its URL, generated account password, run identifier and external DB-control
script; it must not be pointed at a development database or gateway. Its controls
are test processes, not application HTTP endpoints, and never modify shared data.

See `../server/services/user/US002_API.md` for the complete verification record,
isolation/cleanup evidence and remaining acceptance limits. AC4 historical-page
visibility remains **Pending Joint Verification**; AC5 was added later (see `US002_API.md`). HTTP integration
success does not resolve the documented trusted-host/public-origin or HTTPS risks.


## US-011 QR check-in

The class detail page provides Teacher/Coordinator QR window controls. The
Attendance page refreshes live attendance every three seconds. Both use the
existing server-only cookie adapter. `npm run test:checkin-unit` checks requests
and print output; after `npm run build`, `npm run test:checkin-ui` starts an
isolated browser suite. See `docs/system_test/qr_checkin_system_tests.md` at the
repository root for phone/LAN setup, printing and Docker tests.

## Public class information (US-009)

The homepage now presents public class details before the existing enquiry and
staff login forms. Staff can use `/#staff-login` directly. Edit
`src/content/club.json` and rebuild to publish approved information. The default
schedule is explicitly labelled as sample data.

Run `npm run test:public-unit`, `npm run build`, `npm run test:public-ui` and
`npm run test:public-a11y`. See [content approval and testing](../docs/system_test/club_information_system_tests.md).
