# server

## Running unit tests

Unit tests use pytest and a throwaway PostgreSQL database. They never use the
databases started by `compose.yaml`.

1. Start a test PostgreSQL server (Docker Desktop must be running):

   ```bash
   docker run -d --rm --name ako-test-postgres -e POSTGRES_PASSWORD=test \
     -p 127.0.0.1:55432:5432 postgres:17-alpine
   ```

2. Create a virtual environment for the service and install the test
   dependencies. The steps are the same for every service with a `tests`
   folder (`user`, `accessment`, `lesson`); the example uses the User service:

   ```bash
   cd server/services/user
   python3 -m venv .venv
   .venv/bin/pip install -r requirements-dev.txt
   ```

3. Run the tests:

   ```bash
   TEST_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:55432/postgres \
     .venv/bin/pytest -v
   ```

   Each run creates a database named `ako_test_<random>` and drops it at the
   end. The database in the URL is only used to create and drop it.

4. Stop the test server when finished: `docker stop ako-test-postgres`.

## Lessons and lesson files (US-006)

- **Where files are stored:** uploaded lesson files go to the Docker volume
  `lesson_files` (name set by `LESSON_FILES_VOLUME`), mounted at
  `/data/lesson-files` in both `lesson1` and `lesson2`. They are never written
  into the code folder or the zip. Each file is saved under a random name; the
  original name is kept in `lesson_materials.file_name` and used for downloads.
  Back up this volume together with the `lesson_data` database volume.
- **File rule:** PDF, DOCX, JPG or PNG, from 1 KB to 10 MB each. The rule is in
  `services/lesson/files.py` (`FileValidator`) and is repeated in the browser
  in `web/src/components/lessons/file-rule.ts`; change both together.
- **Upload size in Nginx:** `/api/lesson/` allows request bodies up to 11 MB
  (`client_max_body_size` in `nginx/nginx.conf`); every other route keeps 1 MB.
- **Test teacher accounts:** until US-001 adds teacher accounts, the User
  service creates `teacher1` and `teacher2` with the password in
  `TEST_TEACHER_PASSWORD` (default `TeacherPass123!`), next to the demo
  coordinator. Set `TEST_TEACHER_PASSWORD=` (empty) to start without them.
- **Existing lesson database:** US-006 adds one column. See
  `database/database-schema.md` for the one-line change, or start from a new
  lesson volume.

Run it:

```bash
cd server
docker compose up -d --build
```

Then open <http://localhost:8080>, log in as `teacher1` and choose **Lessons**.

To see where the files are on the running system:

```bash
docker compose exec lesson1 ls -R /data/lesson-files
```

## Teacher access to lesson materials

- **Sessions:** a session ends after 30 minutes without activity
  (`SESSION_IDLE_MINUTES` in `services/user/app.py`); every signed-in request
  moves the end forward. **Log out** calls `POST /api/user/logout`, which ends
  the session on the server, so a copied sessionid stops working.
- **Opening files:** PDF, JPG and PNG open in a new browser tab; DOCX files
  are downloaded. Files are fetched with the sign-in header, so a copied file
  address does not work for anyone who is not signed in. Downloads are sent
  with `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store`.
- **Visitors who are not signed in** get `401 Login required` from every
  lesson and file address, with no titles or file names, whether or not the
  lesson exists.
- **Māori content:** the lesson list and page show "Māori content – not yet
  reviewed" for a lesson flagged by US-008 until it is reviewed. Staff can
  still open its files; only learners are kept from unreviewed content.

