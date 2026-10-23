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
   folder (`user`, `accessment`); the example uses the User service:

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
