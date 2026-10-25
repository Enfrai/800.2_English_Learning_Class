# US-006 — Lesson library

Staff can create lessons with a title, date and one or more topic tags,
attach PDF/DOCX/JPG/JPEG/PNG materials, view/download other volunteers'
lessons, and edit/delete their own lessons. Coordinators can edit/delete
any lesson. All identities are checked with the User Service.

## Run

From the repository root:

```bash
docker compose -f server/compose.yaml up -d --build
```

Log in at <http://localhost:8080>, then choose **Lessons**.
The library, new lesson, detail and edit pages use the shared Ako UI kit.

## Storage and upgrade

- Both Lesson replicas mount the same `lesson_files` volume at
  `/var/lib/ako/materials`. Files survive container rebuilds.
- Never use `docker compose down -v` to upgrade existing data.
- Startup adds a missing `share_with_learners` column (default false) and
  legacy reviewer columns without resetting the database. PostgreSQL
  initialization is serialized with an advisory lock.
- Files have random internal names. Downloads keep the original filename.
- Deletion keeps database tombstones for references from class sessions.
  Download access stops immediately after commit; physical files are purged
  after the database change. A failed physical purge is logged and does not
  restore download access.
- Uploaded materials stay outside the source tree and code ZIP. Back up the
  file volume together with the Lesson database.

## Input rules and scope decisions

- Required: nonblank title (up to 255 Unicode characters), date and at least
  one topic tag (up to 100 characters per tag).
- The definitive tag list is not agreed in the story card. Staff enter
  comma-separated topics; existing tags are shown as suggestions.
- Materials are optional, and multiple attachments are supported.
- Each file is limited to **10,485,760 bytes**, inclusive. The UI describes
  both the familiar 10 MB label and the exact byte limit.
- JPEG is accepted with either `.jpg` or `.jpeg`. Types are checked using
  the extension and file signatures/container entries, not browser MIME alone.
- Each file's sharing checkbox starts off. Selecting it stores a preference;
  it does not provide public access or implement learner access (US-013).
- Adding/removing materials resets a reviewed Māori lesson to pending using
  the existing US-008 logic. Metadata edits and sharing preferences do not.
- A rejected file leaves form fields intact. If metadata was already saved
  before an upload failed, the UI says so. Retrying updates that same lesson
  rather than creating a duplicate.
- Search/copy are US-007; linking a lesson to a class session is US-014.

## API

The browser uses `/api/staff/lesson/`; the existing Next adapter validates
the HttpOnly cookie and Origin, then forwards a Bearer identity internally.
All file downloads remain authenticated.

| Method | Service path | Purpose |
| --- | --- | --- |
| GET | `/tags` | Existing topic suggestions |
| GET / POST | `/lessons` | List / create |
| GET / PUT / DELETE | `/lessons/{id}` | Read / update / soft-delete |
| POST | `/lessons/{id}/materials` | Multipart file upload |
| GET | `/materials/{id}/download` | Download with original name |
| PATCH | `/materials/{id}` | Change sharing preference |
| DELETE | `/materials/{id}` | Remove file |

Creation/update JSON:

```json
{
  "title": "Public transport",
  "lesson_date": "2026-10-25",
  "tags": ["transport", "shopping"],
  "description": "Optional teaching notes"
}
```

The old unauthenticated `POST /create` demo endpoint has been removed.
Clients must use the authenticated lesson endpoint; `created_by` is taken
from the login and cannot be supplied in the request.

## Tests

Install backend test dependencies into your local virtual environment:

```bash
python -m pip install -r server/services/lesson/requirements-dev.txt
python -m pytest server/services/lesson/tests/test_lessons.py server/services/lesson/tests/test_lesson_user_client.py server/services/lesson/tests/test_lesson_app.py -v
```

These tests use temporary SQLite databases/files and mocked User Service
responses, not production data. They cover AC1–AC6, role/ownership checks,
exact boundaries and invalid file content, original filenames, storage
collisions, upload rollback, sharing defaults, review resets, migration and
the authenticated application entry point.

Existing US-008 PostgreSQL tests remain in `tests/test_maori_review*.py`;
they require the isolated `TEST_DATABASE_URL` described in `server/README.md`.
The real gateway upload/review-reset test is in
`tests/system/test_review_flow.py`.

From `web/`:

```bash
npm ci
npm run test:lessons-unit
npm run build
npm run test:lessons-ui
node --test tests/lesson-session.test.mjs
```

UI tests run real rendered pages with mocked APIs. They use local Chrome by
default; set `BROWSER_CHANNEL=chromium` after installing Playwright Chromium
to use that browser instead. They check validation, retained form state,
upload retry, original-name download, sharing, ownership controls, editing,
confirmation/cancel, deletion and mobile layout. They do not replace the
real PostgreSQL and full system tests.
