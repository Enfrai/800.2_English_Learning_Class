# US-007 — Find and copy lessons

## Scope and decisions

Teachers and coordinators can search the shared staff library and copy any
available lesson. Learners and visitors cannot access these routes. The UI uses
`web/src/styles/ako` and the existing lesson editor. No new dependency or database
migration is required.

Search accepts `q` (up to 255 characters) and `tag` (up to 100). Keyword search is
case-insensitive and matches titles or topic tags only. It does not read notes,
filenames or attachment contents. Tag selection is exact. Combining both filters
uses AND; blank filters list all available lessons. SQL wildcard characters are
literal user input. Deleted lessons are excluded. The UI waits 250 ms after
changes and ignores older requests that finish after a newer search.

Opening **Copy as new lesson** makes no database or file changes. It opens
`/lessons/new?copyFrom=<source UUID>` with:

- `Copy of ...` as title (truncated to the existing 255-character limit).
- An empty, required date; the user chooses the new date before saving.
- The source tags, teaching notes and materials.
- An option to omit individual source files without deleting them from the source.
- A notice when the copy contains Māori content.

Saving creates a new lesson owned by the current staff member and records the
existing `lessons.source_lesson_id` reference. Source editing permissions do not
change. Files get new random keys and metadata rows, so deleting either lesson
does not break the other's files. Original download names are retained. Copied
files start with learner sharing off. A Māori-content copy starts pending review;
reviewer details and previous approval are never inherited. Non-Māori copies use
`not_required`. These sharing/review choices resolve details not specified by the
US-007 card conservatively using US-006/US-008/US-013.

The source row is locked while saving, matching US-006's edit/delete locking.
Foreign/deleted material IDs, missing/changed files and unsafe paths reject the
copy. Database/file failures roll back new metadata and remove files created by
that attempt; a cleanup failure is logged. Source content is never overwritten.
Cancelling an unsaved draft creates nothing. Retrying a failed additional upload
updates the already saved copy rather than creating it again.

## Manual test

From the repository root:

```sh
git switch temp/1.0_US_007
git pull --ff-only
docker compose -f server/compose.yaml up -d --build --force-recreate --wait web lesson1 lesson2
docker compose -f server/compose.yaml restart nginx
```

Open <http://localhost:8080/lessons> after logging in as Teacher or Coordinator.
The existing `temp/v1.0_US_007` branch was the implementation baseline; changes
are submitted on the requested `temp/1.0_US_007` branch.

1. Create ten lessons; give only two the exact `transport` tag.
2. Select that tag. Only the two matching rows should appear.
3. Type a title keyword using different capitalization. Results should appear
   within two seconds. Add a tag to check combined filtering.
4. Search for a nonexistent word. Check **No lessons found** and the creation link.
5. Open another teacher's lesson and choose **Copy as new lesson**.
6. Verify title prefix, tags, notes, materials and blank date. Save without a
   date; check **Lesson date is required**, retained fields and no new record.
7. Set a date, edit the title and save. Verify the original stayed unchanged.
8. Download a copied attachment; check its original filename. Delete the source
   as its author/coordinator and check that the copied file still downloads.
9. Repeat copying and cancel it. No new lesson should appear.
10. Check the copy on a 360px screen: controls fit, and the results table scrolls
    within its region rather than squeezing words into single-letter columns.

## Automated tests

Install each service's `requirements-dev.txt` in a virtual environment first.
From the repository root:

```sh
python -m pytest server/services/lesson/tests/test_lesson_search_copy.py server/services/lesson/tests/test_lessons.py server/services/lesson/tests/test_lesson_app.py server/services/lesson/tests/test_lesson_user_client.py -q
python -m pytest tests/docker/test_runner.py -q
cd web
npm ci
npm run test:lessons-unit
npm run build
node --test tests/lesson-session.test.mjs
npm run test:lessons-ui
```

The new feature backend tests use temporary SQLite databases with mocked staff
identity. SQLite's `lower()` is supplied a Unicode-aware implementation for
these isolated tests. The existing PostgreSQL suites remain separate and need
`TEST_DATABASE_URL`; no production database is used. Browser tests run a
production Next server with mocked APIs and local Chrome. For installed
Playwright Chromium, set `BROWSER_CHANNEL=chromium`.

The existing independent Docker runner now includes `lessons-unit` and
`lessons-ui`. Run these from the repository root with Docker Desktop running:

```sh
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=lesson test-backend
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=lessons-unit test-web
docker compose -f compose.test.yaml -p ako-tests run --build --rm -e TEST_SUITE=lessons-ui test-web
```

Reports and logs appear under `test-results/backend/` and `test-results/web/`.
The helper `python3.14 tests/run_docker_tests.py` also runs these suites as part of
the full test stack. See `tests/docker/README.md` for isolation and cleanup.

## Acceptance mapping

| Criterion | Tests |
| --- | --- |
| AC1: two tagged lessons out of ten | Backend exact-tag/near-match tests and browser tag selection |
| AC2: title keyword in any case within two seconds | Case variants, Unicode, literal wildcard tests; bounded API and browser timings |
| AC3: no match and new-lesson link | Empty result API; exact UI text and working creation link |
| AC4: independent unsaved draft | No rows/files on GET/cancel, title/tags/notes/materials/date, new ownership and independent storage |
| AC5: empty date rejected with nothing saved | Backend field validation/count and browser focused date error |
| Permissions and failures | Anonymous access, own/other/coordinator copies, unchanged source permissions, missing/deleted source, foreign material IDs, rollback/collision/path safety |
| Related rules | Sharing defaults, Māori review reset, macrons, upload retry, stale search responses and mobile Ako styles |

Local verification covers these unit/API/browser tests and the production build.
A full Docker/PostgreSQL end-to-end run is not implied by mocked tests.
