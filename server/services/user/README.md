# User Service administration

## Explicit first Coordinator initialization

Run `init_coordinator.py` only against a database you are authorized to administer,
after its existing schema has already been provisioned. It does not create tables,
run migrations or change schema. No database URL is assumed, even if `DATABASE_URL`
is set. The required argument names an environment variable containing the complete
`postgresql+psycopg` URL; do not put a real URL/password in source control or command
history. Populate that variable through your local secure configuration or hidden
shell input before running:

```sh
# From server/services/user, using the project's Python environment:
python init_coordinator.py --database-url-env AKO_BOOTSTRAP_DATABASE_URL \
  --username first_coordinator --display-name "Club Coordinator"
```

The script requires an interactive terminal and prompts twice without echo for a
password of at least eight characters. It does not accept a password argument or
piped password input and never prints the connection URL or password. Clear the
connection environment variable after use. Use only a disposable database when
running automated tests; never point the test runner at shared development data.

Behavior:

- No active Coordinator and available username: insert one Coordinator using the
  existing UUID model and PBKDF2 password hasher; exit 0.
- An active Coordinator already exists: no writes, password resets or account
  changes; report that initialization is already complete and exit 0.
- Username conflict (including inactive users): no account changes; exit 2.
- Existing inactive accounts are never reactivated or overwritten. A different
  username can create a new Coordinator only when none is active.
- Invalid input/noninteractive execution: exit 2 without writes. Database failure:
  rollback, sanitized message, exit 1. All successful writes commit together.
- Concurrent copies of this script serialize through a PostgreSQL transaction
  advisory lock. Run in a controlled setup window, not concurrently with application
  startup or other administrative account writers that do not share this lock.

The existing automatic demo-seeding lifespan is **unchanged**. The script imports
the established password function after explicitly selecting the URL, but does not
run FastAPI lifespan. It does not replace or disable demo seeding; a running local
installation with a demo Coordinator will normally produce the no-change result.
Default demo credentials are still a public-deployment blocker. Do not treat this
script as a password reset or account-recovery workflow.

## Staff Management

See `US002_API.md` for endpoint contracts, AC scope and verification boundaries.
AC5 remains **Deferred**; no Coordinator management API/UI is introduced here.
