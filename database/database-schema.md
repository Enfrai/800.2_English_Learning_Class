# Ako database schema — SQLAlchemy create_all

Author: Shuohui Liu  
Date: 19 Oct 2026

Each service imports its own `models.Base` and calls `Base.metadata.create_all(bind=engine)` at FastAPI startup. No Alembic is used. The three databases contain 3, 4, and 5 business tables respectively.

**Development reset only:** `docker compose down -v` removes all Compose-managed volume data, then `docker compose up -d --build` recreates databases and tables. Verify that the volumes contain no data you need before doing this. `create_all` never changes an existing table's schema.

The User login endpoint preserves the demo credentials, adds five-failure temporary lockout and 30-minute session expiry, and returns a UUID user_id. The Lesson create endpoint requires a valid `created_by` UUID and optionally accepts `lesson_date`. The Accessment `/check` endpoint remains a stateless demo-only policy check, not real authorization.

Check tables:
```sh
docker compose exec postgres-user psql -U user_app -d userdb -c '\\dt'
docker compose exec postgres-access psql -U access_app -d accessdb -c '\\dt'
docker compose exec postgres-lesson psql -U lesson_app -d lessondb -c '\\dt'
```

The models define persistence only. User-session authentication middleware, cross-service UUID validation, QR check-in, lesson review enforcement and full learner/attendance APIs are not yet implemented.
