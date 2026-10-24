# US-001 current implementation

The sections below preserve phase-by-phase contracts and test history. The current
lifecycle and browser integration are described in the final section; earlier
statements about pending phases refer to those historical checkpoints.

# US-001 Phase 1: login API contract

`POST /api/user/login` is routed by the existing gateway to `POST /login`.
The JSON request remains `{ "username": "...", "password": "..." }`.

- **200:** Existing `sessionid`, `expires_at`, `user_id` (UUID string), and
  `instance` fields are preserved. `role` (`teacher` or `coordinator`) and
  `display_name` come from the authenticated database user. Password hashes and
  internal failure counters are never returned.
- **401:** `{ "detail": "Username or password is incorrect" }` for incorrect
  credentials, unknown users, or inactive users.
- **423:** Returned immediately on the fifth consecutive wrong password and
  on further attempts before the lock expires. `detail` is an object containing
  `code: "account_locked"`, a readable `message`, UTC ISO-8601 `locked_until`,
  and integer `retry_after_seconds`. The `Retry-After` header contains the same
  seconds, rounded up. Further attempts do not extend the original lock.
- **422:** Existing request-validation behavior remains unchanged.

Successful login resets failures and clears an expired lock. Existing password
hashing, UUIDs, tables, and the single-session replacement behavior remain intact.
A correct password is accepted at the lock expiry boundary.

## Later phases

The frontend currently expects a string error detail and must be updated to
render the new lockout object. It still prefixes ordinary error messages.
Thus this backend phase alone does not satisfy the browser acceptance criteria.

`POST /activity` and `POST /logout` remain later-step endpoints. Cookie
transport is implemented in Step 3.1; sliding inactivity enforcement remains pending.
The existing 30-minute expiry is still only recorded at login in this phase.

## Tests

Install `server/services/user/requirements-dev.txt` in an isolated environment.
From the repository root run:

```sh
python -m pytest server/services/user/tests -q
```

Phase 1: `tests/test_login.py` contains 14 HTTP contract tests using mocked
persistence and a fixed clock. These tests do not connect to a database.

Phase 2: `tests/test_auth.py` contains 22 authentication/authorization cases using
isolated temporary SQLite databases, plus the Phase 2.1 regression below. These
tests execute real SQL against SQLite, never against development PostgreSQL.
Neither suite runs the application lifespan or demo seeding. Neither establishes
PostgreSQL commit durability, row-lock behavior, cross-replica correctness,
browser behavior, or login latency. Those require separate integration/E2E tests.


## Phase 2: authentication and authorization

`GET /api/user/session` (service route `/session`) accepts
`Authorization: Bearer <sessionid>` using the existing login token. It returns
only `user_id` (UUID string), `display_name`, and the current database `role`,
with `Cache-Control: no-store`. No tokens, hashes, or account lists are returned.
Missing/malformed credentials, unknown tokens, expiry (including equality),
revocation, deleted users, and inactive users yield HTTP 401 with
`{"detail": "Not authenticated"}` and `WWW-Authenticate: Bearer`.
Tokens in query strings and client-supplied identity/role headers are ignored.
Step 3.1 adds cookie transport alongside Bearer authentication, as detailed below.

`auth.get_current_user` is reusable through FastAPI `Depends`.
`auth.require_coordinator` and `auth.require_teacher` authorize their exact roles;
Coordinator does not implicitly inherit Teacher permissions. A valid session
with the wrong role receives HTTP 403 with
`{"detail": "You do not have permission"}`. Protected handlers must attach the
appropriate dependency before accessing protected data. No account CRUD or
production demonstration routes are added.

Validation is read-only: it never changes `expires_at`, `last_activity_at`, or
`revoked_at`. Therefore overlapping validation cannot undo revocation or extend
an expired session. An already authenticated in-flight request may finish after
revocation; later requests fail. There is no claim of cancelling in-flight work.
Phase 3's activity updates must independently check expiry/revocation atomically;
calling this dependency and then doing an unconditional refresh is unsafe.
The owning application supplies `app.state.session_factory`. Service replicas
must use the same User database and synchronized clocks. Database failures
propagate as server errors rather than being misreported as bad credentials.

Phase 2 tests use isolated temporary SQLite databases and the unchanged SQLAlchemy
models for session lookup, role enforcement, and overlap tests. They do not run
application startup or access development PostgreSQL. SQLite verifies actual SQL
execution but does not establish PostgreSQL isolation or multi-replica behavior.


## Phase 2.1: one database injection point

Login and authentication both use `Depends(auth.get_db)`, which obtains sessions
from `app.state.session_factory` and closes each session after the request. Login
still owns its `db.begin()` transaction and explicitly commits failed-attempt
tracking before returning an authentication error. Successful login commits at
the transaction-context exit, as before.

Tests can set `app.state.session_factory` once to a dedicated `sessionmaker` for
both endpoints, or override `auth.get_db` with a request-scoped dependency. Use a
fresh session per request; never share a Session between concurrent requests.
The Phase 2.1 regression logs in against the injected SQLite database, validates
the returned token, and verifies that the old token was replaced. The suite now
contains 37 cases: the original 36 plus this regression.

This is a request-handling injection point, not a startup override. The existing
lifespan still uses the configured engine for initialization. Current tests do
not run it. Future startup tests must configure an isolated database before
importing the application.

A User-service-local `ruff.toml` extends the existing server rules and classifies
`auth` and `models` as first-party imports. Shared lint/infrastructure files are
unchanged.

## Deferred review findings and proposed verification

- **F1 — Required before accepting Phase 3 session mutations:** provision a new,
  uniquely named PostgreSQL 17 test container with temporary storage and a random
  loopback-only host port. Do not attach development volumes or join its network.
  Use generated test-only credentials and an explicitly supplied test database
  URL, with no fallback to the application's development URL. Require checks of
  the test database name and container identity before fixture setup/cleanup.
  Initialize the unchanged models only inside that disposable database. Inject
  its session factory into both login and authentication. Exercise two separate
  application instances/engines against it for committed failures, concurrent
  logins, token replacement, UUID/timezone round trips, and revocation visibility.
  Add atomic refresh/logout race tests when Phase 3 implements those operations.
  PostgreSQL tests involving commits must use isolated fixtures rather than rely
  solely on an outer rollback. Any cleanup must target only the identified test
  resources. This is a proposal; no PostgreSQL container or database was created.
- **F2:** handle structured lockout responses and exact error text during frontend
  integration.
- **F4:** team decision required on supported Python versions, reconciling the
  CI example with Docker, and the backend dependency locking/install workflow.
  No runtime or dependency changes are made in Phase 2.1.
- **F7:** default demo Coordinator seeding is a deployment blocker outside local
  development. Agree an explicit development-only configuration before deployment;
  shared infrastructure changes require separate approval.
- **F8:** review timing-based account enumeration and dummy password verification
  as security hardening before public deployment.


## Phase 2.2: isolated PostgreSQL integration tests

Run the original 37 tests and 13 PostgreSQL integration cases together using:

```sh
python server/services/user/tests/run_postgres.py
```

The runner requires Docker and the existing development test dependencies. It
creates a PostgreSQL 17 Alpine container with a UUID-based name and ownership
label, generated password, a run-specific database name, tmpfs database storage,
and a random loopback-only port. It does not use Compose, development volumes,
or a development network. Credentials are passed through the child environment,
not printed or saved to the repository. The test fixture checks the full container
ID, name, ownership label, image, storage, port and database identity before
connecting. There is no fallback to the development DATABASE_URL. Cleanup checks
the same ownership identity before removing the created container and confirms
that it no longer exists. A failed identity check stops cleanup rather than
risk removing another resource. Cleanup identity checks use explicit exceptions
and remain enabled even under Python optimization.

Direct pytest runs without the runner's test environment skip the 13 PostgreSQL
cases; they must not be mistaken for a completed integration run.

Executed coverage:

- Five committed failures across both instances, ten-minute lock duration,
  rejection of the correct password while locked, and login after expiry.
- Successful login resets previously committed failures.
- Hash-only token persistence and validation from the other instance.
- Replacement login and committed revocation are visible to both instances.
- Expired, revoked and inactive-user sessions return 401.
- Concurrent batches of four, five and eight failed logins preserve counters
  and lockout; four successful concurrent logins leave exactly one valid token.
- Native UUID and timezone-aware timestamp round trips; the actual PostgreSQL
  partial unique index rejects a second unrevoked session but allows a revoked
  historical session.
- A real database CHECK violation after login's counter update and session delete
  rolls the transaction back: previous user/session state remains intact and the
  old token still validates.

The instances are separately loaded FastAPI applications with independent
SQLAlchemy engines and pools in one test process. Requests use TestClient, not
Nginx or separately deployed User containers. Real PostgreSQL executes all
integration SQL. Test users are unique per case; their records disappear with
the disposable container, without development-database cleanup.

Lock expiry is tested by setting the temporary account's lock deadline into the
past, not by waiting ten minutes. Revocation is committed through instance B's
engine because Phase 3's logout endpoint does not yet exist. The concurrency
checks exercise the present login/read-only validation implementation; they do
not validate future refresh/logout mutations, process crashes, network failures,
startup races, gateway routing, browser behavior or the three-second UI target.

Initial Phase 2.2 execution: 50 passed, no skips, with the existing Starlette/httpx
deprecation warning. The identity-checked test container was removed afterward.
F1's baseline PostgreSQL coverage is now present. Phase 3 still requires new
PostgreSQL tests for its atomic session mutations before those are accepted.


## Step 3.1: cookie authentication and login protection

A successful login now sets `ako_session` after its transaction commits. The
response body is unchanged, including `sessionid`, for API-client compatibility.
The cookie uses `HttpOnly`, `SameSite=Lax`, `Path=/`, no Domain attribute (host-only),
and `Max-Age=1800`. `Secure` is always enabled for HTTPS requests. Local HTTP uses
a non-Secure cookie in automatic mode. The database remains authoritative for
expiry; a browser retaining a cookie cannot revive an invalid session.
Keeping `sessionid` in the JSON response means that HttpOnly protects cookie
access, not the token in that login response. Frontend integration should rely
on the cookie rather than storing that response token in browser storage.

Optional environment settings, read when the User application is imported:

- `SESSION_PUBLIC_ORIGIN`: exact external origin, e.g. `https://ako.example`,
  with no path/query/fragment/userinfo. Use this behind HTTPS termination where
  the internal request URL differs from the browser-facing URL. An HTTPS value
  also enables Secure cookies even for an internal HTTP hop.
- `SESSION_COOKIE_SECURE`: `auto` (default) or `true` (force Secure). Disabling
  Secure for HTTPS via a `false` value is rejected at configuration time.

Without a configured public origin, the request's ASGI scheme/host determine the
expected origin. The application does not independently trust raw forwarded
headers. A deployment must configure its external origin or correctly restrict
proxy trust. No Compose or Nginx configuration was changed in this step; any
required deployment wiring remains subject to approval.

### Credential selection on protected endpoints

- Cookie-only and Bearer-only requests use the same hashed-token database lookup.
- If both are present, tokens must be identical. Different tokens return 401,
  even if one is expired or both belong to the same user. No fallback occurs.
- A malformed or duplicated Authorization header returns 401 even when the
  cookie is valid. Duplicate session-cookie values also return 401.
- Query-string tokens and client-supplied role/identity labels remain ignored.

Login authenticates the explicitly submitted username/password rather than an
existing session. It may replace an existing browser session after its Origin
check; it does not use Cookie/Bearer credentials to select the login identity.

### Origin protection

Login validates any supplied Origin against the configured/request origin.
A request carrying a session cookie or browser Fetch Metadata must supply a
matching Origin. Cross-origin, opaque (`null`), malformed, and duplicated origins
are rejected with 403 before login database access. Origin-less non-browser JSON
API login requests remain supported. The endpoint continues to accept JSON, not
form login bodies, and no permissive CORS policy is installed.

The reusable authentication dependency requires a matching Origin on unsafe
methods when a session cookie is present, including when an identical Bearer
token accompanies it. Bearer-only requests do not require Origin because the
browser does not attach this explicit credential automatically. This guard is
exercised through test-only routes; logout/activity endpoints are not added yet.
SameSite=Lax is defense in depth, not a replacement for the Origin check.

Successful and handled-error `/login` and `/session` responses receive
`Cache-Control: no-store` and `Pragma: no-cache`. `GET /session` neither updates
session timestamps nor renews the cookie. Unhandled database-failure responses
are generic server errors; uniform error-path hardening remains for Step 3.4.

### Verification and scope

The original 50 tests are retained. The PostgreSQL test helper explicitly omits
cookies for its existing Bearer API checks, preventing TestClient's new cookie
jar from unintentionally mixing credentials. New focused tests cover cookie
attributes, origin checks, credential conflicts, no-store responses, and cookie
read-only validation. New PostgreSQL cases cover cross-instance cookie use,
invalid-cookie rejection, and conflicting tokens from distinct valid identities.

Cookie flags are asserted at the HTTP-header level and secure mode is tested
with HTTPS TestClient requests; this is not a real browser or deployed TLS test.
No logout, activity refresh, sliding expiry, frontend provider or pages were
implemented. Steps 3.2 through 3.4 still require approval and their own tests.


## Completed core lifecycle and frontend integration

### Endpoints and transactions

- `POST /logout`: authenticated Cookie or Bearer session, HTTP 204 on successful
  revocation. Sets `revoked_at` and clears the host-only cookie with the same path,
  HttpOnly, SameSite and Secure policy. An already invalid session returns 401;
  if credential selection and Origin validation succeeded, its stale cookie is
  also cleared. A CSRF rejection never clears a cookie.
- `POST /activity`: explicit authenticated activity, no body required. Returns
  `{ "expires_at": "..." }`, updates `last_activity_at` and `expires_at` to server
  time and server time plus 30 minutes, and renews the cookie. No background
  endpoint implicitly extends a session.
- `GET /session`: unchanged identity JSON plus `X-Session-Expires-At`. Read-only.
- `GET /account-management/access`: Coordinator-only authorization boundary,
  returning only `{ "allowed": true }`. Teachers receive the exact 403 message.
  There are no account lists, account fields, or US-002 CRUD operations.

Expiry validation checks both the deadline and 30 minutes since last activity.
Equality at either boundary is expired. Logout and activity own their transactions
and lock the user row followed by the session row, matching login's order. They
check active status, revocation and current time after obtaining these locks.
Activity never sets revoked_at to NULL. If refresh wins a race, subsequent logout
revokes it; if logout wins, refresh fails. Replacement login deletes the old token
and a waiting refresh cannot restore it. A late HTTP response can leave an obsolete
cookie in a browser, but the database still rejects that token.

Origin validation applies to cookie-authenticated logout/activity, including a
matching Bearer+Cookie pair. Bearer-only API requests retain compatibility. Every
authentication endpoint and the account-access boundary has no-store headers;
unexpected User-service errors return generic no-store responses without SQL or
token details. HTTPS/public-origin configuration from Step 3.1 is unchanged.

### Frontend

Login preserves UUID strings, displays the exact incorrect-password text and the
local lockout retry time, and redirects according to the server-provided role.
Teacher navigation contains Home and Log out; Coordinator navigation additionally
contains Account management. The account-management page is a placeholder without
CRUD. No unrelated business-story links or features are implemented.

Next.js middleware checks protected routes against the User service before serving
them. It returns a 403 denial page for wrong roles and redirects unauthenticated
users to `/`. `USER_API_URL` defaults to `http://nginx/api/user`, using the existing
Compose gateway on the existing network; local tests supply a loopback test URL.
The backend destination is never derived from user-controlled request headers.
Authorization failures never render account-management content.

The browser shell validates its HttpOnly cookie, schedules expiry redirects,
submits activity only for trusted pointer/keyboard input, and passively checks
session status on polling/focus/tab restoration. BroadcastChannel synchronizes
logout and prompts passive validation after another tab's activity. It does not
store session tokens in localStorage. API response deadlines remain authoritative.

### Consolidated verification

Run the complete backend and isolated PostgreSQL suite with the existing runner.
To include browser acceptance checks, build the frontend first, then run with
`US001_BROWSER_TESTS=1` and Node.js on PATH. The browser runner requires the declared
Playwright package and installed Google Chrome. It starts only owned loopback
FastAPI and production Next.js processes and a temporary test proxy matching the
existing `/api/user/` gateway paths. The proxy's fixture-control routes exist only
in this test process and require a generated key. The production application has
no test-control routes. All controls target the identity-verified disposable DB.

Browser coverage includes role navigation, measured three-second Teacher login,
exact errors, five-failure lockout, direct-route denial, logout/token replay and
tab synchronization, explicit activity versus passive reads, and accelerated
idle expiry. The idle test advances browser time and expires the isolated test
record rather than waiting 30 real minutes. Separate PostgreSQL tests verify
actual timestamp predicates and session-write races. The test proxy does not
establish deployed Nginx/TLS behavior; that remains a deployment smoke test.

F4 runtime/dependency alignment remains a team decision. F7 known demo credentials
remain a blocker outside local development. F8 timing hardening remains for review
before public deployment. No shared infrastructure or database schema was changed.


### Final core verification record

- Backend: 111 passed, including 38 real PostgreSQL cases; one existing
  Starlette/httpx deprecation warning. Backend implementation was unchanged
  during subsequent frontend-only corrections.
- Production Next.js build and TypeScript validation passed.
- Final browser run: all eight scenarios passed against the standalone Next.js
  build and real FastAPI/PostgreSQL; Teacher login-to-home measured 217 ms.
- Ruff lint/format checks and git diff whitespace checks passed.
- Earlier browser failures identified denial-rewrite status loss and internal
  redirect-host handling; both were corrected and verified in the final run.
  The error-message test now targets the application's alert rather than an empty
  Material component live region.
- Every owned test container was removed after checking its identity. Development
  database resources and unrelated service implementations were untouched.

### Isolated Nginx integration verification

The approved Nginx correction now forwards `$http_host` in only the User API
and Web proxy locations, preserving the public Host and port. Other upstream
routing is unchanged.

A separate temporary Compose project ran PostgreSQL 17, two independent User
Service containers, Next.js Web and Nginx at `http://localhost:18080`. It used
its own network, generated credentials and tmpfs database storage. Its Nginx
configuration retained the project's User/Web routing and rate limits; only
unrelated Lesson and Accessment routes/upstreams were omitted.

- Nginx configuration validation passed.
- All eight browser scenarios passed through Nginx, covering AC1–AC5. Teacher
  login-to-visible-home measured 231 ms. Inactivity used accelerated browser
  time and an expired record in the isolated database, not a 30-minute wait.
- Cookie/Bearer validation, credential conflicts, explicit activity, passive
  checks, logout, persisted session hashing/revocation, replacement login and
  expired-session rejection passed. Both User replicas received gateway traffic;
  cross-replica session validation and revocation passed.
- Missing, malformed and mismatched Origin values were rejected for
  cookie-authenticated mutations. HTTP cookie attributes and no-store headers
  were verified.
- Temporary containers, network, images and database storage were removed after
  ownership checks. Original development containers retained their identities,
  configuration and start times; development databases were not accessed.

This is isolated integration verification, not deployment to the shared
`http://localhost:8080` development environment. Its running User/Web services
were not rebuilt or restarted, and its Nginx gateway was not reloaded.

Remaining public-deployment limitations:

- Without `SESSION_PUBLIC_ORIGIN`, Origin validation derives its expected origin
  from the request Host. A matching forged Host and Origin was accepted in the
  isolated test. Trusted-host enforcement and explicit public-origin/proxy-trust
  configuration require review before public deployment. Pinning the Origin
  alone does not provide a general Host allowlist for all routes or redirects.
- Real HTTPS gateway/browser verification remains outstanding. HTTPS TestClient
  checks do not establish deployed TLS termination, proxy trust or Secure-cookie
  behavior. The isolated Nginx run used HTTP only.
- Existing default demo credentials remain unsuitable for public deployment;
  the earlier runtime/dependency and timing-hardening review items still apply.

For frontend-only regression reruns, `run_postgres.py --browser-only` creates its
own isolated database and runs the browser checks without repeating backend tests.
