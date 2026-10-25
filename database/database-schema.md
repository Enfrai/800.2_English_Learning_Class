# Ako database schema — SQLAlchemy create_all

Author: Shuohui Liu  
Date: 19 Oct 2026  
Updated: Sandhya Tiwari, 23 Oct 2026 (US-006)

Each service imports its own `models.Base`. The Lesson Service calls `prepare_schema` at startup; it serializes PostgreSQL initialization and adds missing US-006 sharing and US-008 reviewer columns without dropping records. No Alembic is used. Each service owns its database tables; the feature sections below describe additive schema changes.

**Development reset only:** `docker compose down -v` removes all Compose-managed volume data, then `docker compose up -d --build` recreates databases and tables. Verify that the volumes contain no data you need before doing this. `create_all` never changes an existing table's schema.

The User login endpoint preserves the demo credentials, adds five-failure temporary lockout and 30-minute session expiry, and returns a UUID user_id. The Lesson service (US-006) checks the login with the User Service for every endpoint and takes the lesson author from that login, never from the request. Topic tags are entered by staff; the definitive tag list is still open in the requirements. The Accessment `/check` endpoint remains a stateless demo-only policy check, not real authorization.

Check tables:
```sh
docker compose exec postgres-user psql -U user_app -d userdb -c '\\dt'
docker compose exec postgres-access psql -U access_app -d accessdb -c '\\dt'
docker compose exec postgres-lesson psql -U lesson_app -d lessondb -c '\\dt'
```

## US-006 change to an existing lesson database

US-006 adds the column `lesson_materials.share_with_learners`. The Lesson Service now adds this column automatically and idempotently on startup. No database reset is required. The equivalent manual operation is:

```sh
docker compose exec postgres-lesson psql -U lesson_app -d lessondb -c \
  "ALTER TABLE lesson_materials ADD COLUMN IF NOT EXISTS share_with_learners BOOLEAN NOT NULL DEFAULT false"
```

## US-008 change to an existing lesson database

US-008 adds `lessons.reviewer_name` and `lessons.review_date`, so the label can show "Reviewed by [name], [date]". The Lesson Service now adds these columns automatically on startup. The equivalent manual operation is:

```sh
docker compose exec postgres-lesson psql -U lesson_app -d lessondb -c \
  "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS reviewer_name VARCHAR(150), ADD COLUMN IF NOT EXISTS review_date DATE"
```

## US-015 change to an existing accessment database

US-015 makes the attendance change log append-only: a trigger refuses any `UPDATE`, `DELETE` or `TRUNCATE` on `attendance_audits` (Test Plan UT-35). A new database gets it automatically. An accessment database created before US-015 needs this once; running it again does no harm:

```sh
docker compose exec -T postgres-access psql -U access_app -d accessdb <<'SQL'
CREATE OR REPLACE FUNCTION refuse_attendance_audit_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'attendance_audits is append-only';
END
$$;
CREATE OR REPLACE TRIGGER attendance_audits_append_only
BEFORE UPDATE OR DELETE ON attendance_audits
FOR EACH ROW EXECUTE FUNCTION refuse_attendance_audit_change();
CREATE OR REPLACE TRIGGER attendance_audits_no_truncate
BEFORE TRUNCATE ON attendance_audits
FOR EACH STATEMENT EXECUTE FUNCTION refuse_attendance_audit_change();
SQL
```

US-006 now implements authenticated lesson CRUD, topic tags, attachment upload/download/removal and sharing metadata. Review enforcement remains in US-008. Uploaded files are stored in the shared `lesson_files` volume, outside the code submission.

## US-013 additive accessment tables

`session_lesson_links` associates an existing classroom session with one Lesson
Service lesson. `session_id` is the primary key and a foreign key to
`class_sessions.id`; nullable `lesson_id` is a UUID cross-service reference.

`learner_material_grants` contains `token_hash` VARCHAR(64) primary key,
`session_id` UUID foreign key to `class_sessions.id`, and non-null timezone-aware
`issued_at` and `expires_at` timestamps. `expires_at` is indexed. Grants last
exactly 24 hours and contain no learner/device identity. Expired grants are
removed when a new sign-in issues a grant. Only the browser receives the raw
random token; the database stores its hash.

Both tables are created automatically on Accessment startup without modifying
existing tables. PostgreSQL initialization uses transaction advisory lock
800013 so both replicas can start safely. File sharing/review metadata remains
in the Lesson database, and Accessment calls key-protected internal Lesson
endpoints rather than reading another service's database.
