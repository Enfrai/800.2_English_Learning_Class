# Ako database schema — SQLAlchemy create_all

Author: Shuohui Liu  
Date: 19 Oct 2026  
Updated: Sandhya Tiwari, 23 Oct 2026 (US-006)

Each service imports its own `models.Base` and calls `Base.metadata.create_all(bind=engine)` at FastAPI startup. No Alembic is used. The three databases contain 3, 4, and 5 business tables respectively.

**Development reset only:** `docker compose down -v` removes all Compose-managed volume data, then `docker compose up -d --build` recreates databases and tables. Verify that the volumes contain no data you need before doing this. `create_all` never changes an existing table's schema.

The User login endpoint preserves the demo credentials, adds five-failure temporary lockout and 30-minute session expiry, and returns a UUID user_id. The Lesson service (US-006) checks the login with the User Service for every endpoint and takes the lesson author from that login, never from the request. It loads the seven agreed topic tags at start-up. The Accessment `/check` endpoint remains a stateless demo-only policy check, not real authorization.

Check tables:
```sh
docker compose exec postgres-user psql -U user_app -d userdb -c '\\dt'
docker compose exec postgres-access psql -U access_app -d accessdb -c '\\dt'
docker compose exec postgres-lesson psql -U lesson_app -d lessondb -c '\\dt'
```

## US-006 change to an existing lesson database

US-006 adds the column `lesson_materials.share_with_learners`. Because `create_all` does not change existing tables, a lesson database created before US-006 needs this once (a new database gets it automatically):

```sh
docker compose exec postgres-lesson psql -U lesson_app -d lessondb -c \
  "ALTER TABLE lesson_materials ADD COLUMN IF NOT EXISTS share_with_learners BOOLEAN NOT NULL DEFAULT false"
```

The models define persistence only. QR check-in, lesson review enforcement and the rest of the learner and attendance APIs are not yet implemented.
