# US-002 Staff Management — Phase 1

Scope: backend AC1, AC2, AC3, AC4 and AC6. AC5 is **Deferred**. This phase has
no frontend changes, Coordinator bootstrap script, role assignment, Coordinator
mutation, schema migration or shared infrastructure changes.

## API contract

Paths below are User-service paths; the existing gateway prefixes `/api/user`.
Every endpoint requires an active Coordinator session using existing Cookie or
Bearer authentication. Cookie writes require a matching Origin. Staff responses,
including handled errors, use `Cache-Control: no-store` and `Pragma: no-cache`.

| Method/path | Request | Success |
| --- | --- | --- |
| `GET /staff` | None | 200; list of active/inactive Teacher and Coordinator accounts |
| `POST /staff` | `display_name`, `username`, `temporary_password` | 201; new Teacher |
| `PATCH /staff/{user_id}` | `display_name` only | 200; updated Teacher |
| `POST /staff/{user_id}/deactivate` | No body, or empty object | 200; inactive Teacher |

Account responses contain only `id` (UUID string), `username`, `display_name`,
`role`, and `is_active`. Password hashes, passwords, sessions and email addresses
are not returned. The list is ordered by username, then UUID.

Create and rename reject unknown body fields, including role/privilege fields.
Deactivation also rejects nonempty mutation objects. The server fixes newly
created accounts to `role="teacher"`. Names/usernames must be nonblank and fit
existing column limits (150/100 characters respectively); names and usernames
are not silently normalized. Username uniqueness retains existing PostgreSQL
case-sensitive semantics and includes inactive accounts.

| Failure | HTTP status / detail |
| --- | --- |
| Missing/invalid/inactive/expired/revoked authentication | 401, existing US-001 contract |
| Teacher attempting any Staff API | 403, `You do not have permission` |
| Attempt to rename or deactivate any Coordinator | 403, `Only Teacher accounts can be modified` |
| Missing target | 404, `Staff account not found` |
| Existing username, including concurrent creation | 409, `Username already taken` |
| Temporary password shorter than 8 characters | 422, `Password must be at least 8 characters` |
| Other invalid input/UUID/extra fields | 422, standard FastAPI validation response |
| Cookie Origin/CSRF rejection | 403, existing US-001 contract |
| Unexpected database failure | 500, generic existing error response; transaction rolled back |

Coordinator target rejection is a scope boundary, not AC5 implementation. There
is no active-Coordinator count or last-Coordinator protection workflow.

## Authentication, transactions and concurrency

The routes reuse `require_coordinator` and `get_session_token` without modifying
US-001 authentication or session core behavior. An operation Session delegates
to the existing `get_db` generator and therefore uses the same injectable
`app.state.session_factory`; it is separate from the authentication dependency's
read-only Session so that writes own an explicit transaction.

Writes lock actor/target users in UUID order and then revalidate the actor's
current session and database-derived role. A request waiting on a user lock must
not continue after its actor's session has been revoked. All user locks precede
session mutations, matching existing login/activity/logout lock ordering.

Creation hashes the temporary password with the existing PBKDF2 implementation
before acquiring locks. PostgreSQL's username unique constraint arbitrates races;
only that constraint is translated to the duplicate-username response. Other
integrity failures are not mislabeled. The current model creates the constraint
as `users_username_key`; any separately managed schema with a renamed constraint
requires compatibility review rather than a silent schema change.

Deactivation updates `is_active` and `updated_at`, and revokes all unrevoked target
sessions in the same transaction. It never deletes the user or sessions. Repeated
deactivation does not rewrite existing revocation timestamps. UUID, username,
display name and cross-service historical references are preserved. No Lesson or
Accessment tables or code are touched. Their owners must still verify that
historical pages do not filter out records whose authors have become inactive.

## Executed Phase 1 verification

Focused command (using the existing project test environment):

```sh
python tests/run_postgres.py \
  --test-file test_staff.py \
  --test-file test_auth.py \
  --test-file test_login.py
```

Result: **80 passed**, including **43 new Staff tests against PostgreSQL 17** and
37 directly affected US-001 authentication/login tests. The isolated runner
verified its uniquely owned tmpfs container before use and removal. No shared
or manual-test database was used. The two application instances use independent
engines/session factories against the same disposable database; they are not two
running service containers or a Nginx/browser deployment test.

Coverage includes create/list and password hashing, password boundaries, duplicate
and concurrent creation by separate Coordinators, anonymous/Teacher denial,
forbidden field changes, rename, soft deactivation, login/session/activity denial,
Coordinator target rejection, Cookie/Origin protection, actual PostgreSQL error
rollback, deactivation winning concurrent login/activity, and actor revocation
while a write waits for its user lock.

Full end-to-end regression was deliberately not run in Phase 1. AC1/AC2/AC3/AC6
have backend verification only; AC4 verifies account/session behavior and retained
account identity, while Lesson/attendance historical visibility remains pending
cross-service acceptance. AC5 remains Deferred. The existing Starlette/httpx
TestClient deprecation warning remains; no dependency upgrade was attempted.

The inherited trusted-host/public-origin and deployed HTTPS limitations recorded
in `US001_API.md` remain unresolved and are not changed by this phase.

## Phase 3 integration and acceptance record

The explicit Coordinator bootstrap script is now implemented; see the User-service
`README.md`. Existing automatic demo seeding, authentication core, UUID models,
shared schema and infrastructure files remain unchanged. AC5 is still **Deferred**.

Executed verification:

- Full backend suite: **166 passed** (111 US-001, 43 Staff, 12 bootstrap), with one
  pre-existing Starlette/httpx TestClient deprecation warning. The PostgreSQL cases
  used an identity-verified disposable PostgreSQL 17 container with tmpfs storage.
- Bootstrap verification includes UUID/password hashing, no DDL, no-op repeat,
  username conflicts, preservation of inactive accounts, concurrent invocation,
  rollback, explicit connection selection, rejection of piped input, and a real
  pseudo-terminal check that password input is not echoed.
- Focused frontend suite: **21 passed**, using mocked APIs (not persistence tests).
- Actual Nginx/browser suite: **17 passed**: eight US-001 regressions plus nine
  US-002 scenarios. Teacher login-to-visible-home measured **223 ms**.
- Standalone TypeScript check and Next.js production builds passed. Ruff lint and
  formatting passed for all 16 authentication/Staff/test Python files in scope;
  unrelated legacy models were not reformatted. Git whitespace check passed.

The real integration stack was a separate temporary Compose project with
PostgreSQL 17, two User Service containers, Web and Nginx, on
`http://localhost:18081` because the pre-existing manual-test gateway occupied
18080. The database had no host port; storage was tmpfs and the network was unique.
Both replicas were verified to use only that database, and Nginx logs showed
traffic to both upstream IPs. The temporary Nginx copy preserved User/Web routing,
rate limits and `$http_host`; unrelated Lesson/Accessment routes were omitted.

The initial Web image build stalled downloading dependencies. A temporary build
context reused the existing dependency-install cache with identical dependencies
and lockfile, then restored the current package scripts and built current source.
No repository Dockerfile, Compose file or Nginx configuration was edited. The final
Web image used the project's Node 24 Alpine builder/runtime structure.

Actual gateway tests verified Teacher creation/list display, duplicate username
and exact error text, seven/eight-character boundaries, rename, deactivation
confirmation, retained UUID/account identity, login refusal, persisted revocation
and old Cookie/Bearer/activity rejection. Anonymous and Teacher access were denied;
HTTP cookie attributes, Origin checks, no-store responses and concurrent duplicate
creation by two Coordinator clients were verified.

Acceptance status:

| AC | Result |
| --- | --- |
| AC1 | Passed through browser, real API and persisted PostgreSQL account |
| AC2 | Passed; exact duplicate message and unchanged original account |
| AC3 | Passed; seven rejected by UI/API, eight accepted and usable for login |
| AC4 | Account/session/identity checks passed; lesson and attendance historical-page visibility is **Pending Joint Verification** with those modules' owners |
| AC5 | **Deferred**, not implemented or claimed passed |
| AC6 | Passed; name updated in browser/database, UUID and username retained |

Remaining deployment limits:

- A mismatched Origin was rejected with 403. A matching forged Host and Origin
  was still accepted (200) under the inherited default configuration. Trusted-host
  enforcement and explicit public-origin/proxy-trust configuration remain required
  before public deployment; no security-policy change was made in this phase.
- Real HTTPS/TLS termination and Secure-cookie behavior remain unverified by the
  HTTP gateway run; existing HTTPS TestClient checks are not deployment evidence.
- Default demo seeding remains unchanged and unsuitable for public deployment.
  Bootstrap must run in a controlled setup window, not alongside other account
  initializers that do not share its transaction advisory lock.

Results were reported before cleanup. No failed scenario required manual inspection.
Only this run's five containers, network, unique images, tmpfs database and runtime
secret/configuration files were removed after ownership checks. All **24 pre-existing
containers** retained IDs, images, configurations, mounts, start times and restart
counts, including the user's still-running manual-test environment. No development
database was connected to or modified. This is isolated acceptance, not deployment
to the shared development environment. No commit/push/merge/rebase was performed.
