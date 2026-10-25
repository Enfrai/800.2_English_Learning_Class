# US-013 — Learner lesson materials

Learners have no account. A successful US-012 sign-in creates a random, HttpOnly,
SameSite=Lax `ako_materials` cookie lasting 24 hours. Only its SHA-256 hash,
class session reference and issue/expiry times are stored. Reloading does not
extend access. A closed check-in window does not revoke an existing material
grant. The grant cannot authenticate staff endpoints.

## Run the feature

From the repository root:

```sh
git switch temp/1.0_US_013
docker compose -f server/compose.yaml up -d --build --force-recreate --wait web access1 access2 lesson1 lesson2
docker compose -f server/compose.yaml restart nginx
```

No volume reset is needed. Accessment creates the two new tables on startup;
PostgreSQL initialization is serialized across replicas. Existing records stay
in place. Both Lesson replicas share the existing material file volume and
receive the same `INTERNAL_API_KEY` as Accessment. For HTTPS deployments set
`COOKIE_SECURE=true` on both Accessment replicas. `LESSON_SERVICE_URL` defaults
to the internal Docker alias `http://lesson-service:8000`.

1. In Lessons, upload files and tick **Share with learners** for each public file.
2. Open an existing class's Attendance page and choose its **Class lesson**.
3. Open that class's valid QR sign-in link; sign in with a made-up learner.
4. The success page shows the material list. **Lesson materials** opens the
   dedicated `/materials` page, which can be revisited on the same browser.
5. Each **Download** link preserves the original name.

US-011 owns opening/printing classroom QR codes; this branch's existing
Attendance QR button is still marked Later. US-013 consumes valid US-012
check-in links and does not implement the separate US-011 workflow. Similarly,
class creation remains US-014; this change supplies the missing lesson
association for existing sessions.

## Automated verification

These feature unit/API tests use isolated temporary SQLite databases and mock
service boundaries. They do not need Docker, a running app or real learner data:

```sh
cd server/services/accessment
python -m pytest tests/test_learner_materials.py -q
```

In another shell, from the repository root:

```sh
cd server/services/lesson
python -m pytest tests/test_shared_materials.py tests/test_lessons.py tests/test_lesson_app.py tests/test_lesson_user_client.py -q
```

Install each service's `requirements-dev.txt` first in a virtual environment.
The existing broader Accessment suite still needs `TEST_DATABASE_URL` pointing
at a PostgreSQL server; its fixture creates and drops an isolated test database.

Frontend unit tests and Chrome tests:

```sh
cd web
npm ci
npm run test:materials-unit
npm run build
npm run test:materials-ui
node --test tests/attendance-session.test.mjs
```

Chrome must be installed. The browser runner uses local Chrome by default;
`BROWSER_CHANNEL=chromium` uses a Playwright Chromium installation instead.
The UI harness starts an isolated production Next server with a mock Accessment
service, then closes the server and removes its temporary files.

## Acceptance coverage

| Criterion | Automated coverage |
| --- | --- |
| AC1: shared files and original names | Two shared files; both download names; Unicode names; browser download |
| AC2: no sign-in means no metadata or files | Missing/invalid cookie, server redirect, direct-download redirect, no staff access |
| AC3: share only selected files | Private file omitted and direct download refused; unsharing revokes old links |
| AC4: unreviewed Māori content | Pending/rejected hide all files; reviewed allows access; success is independent of materials |
| AC5: no linked lesson | Empty list and exact message; no Lesson request; attendance remains saved |
| AC6: 24-hour access | 20 hours valid; just before 24 valid; exactly 24 expired; refresh does not renew |
| Additional boundaries | Missing/deleted files and lessons, path traversal, wrong lesson, service failure, invalid internal key, grant rollback, 360px layout |

## API boundaries

- Public Accessment `GET /learner/materials` returns the signed-in class date,
  shared files and a state message. Missing/expired grants return 401.
- Public Accessment `GET /learner/materials/{id}/download` verifies the grant
  again. It redirects to `/sign-in` when the grant is missing/expired.
- Staff `GET/PUT /sessions/{id}/lesson` reads/changes the linked lesson.
  The existing Next cookie-to-Bearer adapter enforces same-origin writes.
- Internal Lesson `GET /internal/lessons/{id}/shared-materials` and
  `GET /internal/lessons/{id}/shared-materials/{material_id}` require the
  internal key. Nginx refuses external `/api/lesson/internal/` requests.
- Listing and downloading independently recheck deletion, sharing, lesson
  scope and Māori review status. No learner list, identity or storage key is
  returned. Learner responses are `no-store` and `nosniff`.

A lesson with zero shared files uses **No materials for today**. Māori content
is hidden unless reviewed, using **Materials will be added soon**. These
sharing rules still require the Kaiārahi consultation noted in the stories;
copyright checking is an open requirements question, not an implemented flow.
