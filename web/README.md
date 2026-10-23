# ELC Web — Next.js + Material 3

<!--
Describe the containerized Next.js login test and local development workflow.
Author: Shuohui Liu
Date: 19 Oct 2026
-->

This web application tests the FastAPI User Service through the existing Nginx reverse proxy.

From the `fastapi-microservices` directory, run:

```bash
docker compose up -d --build
```

Open <http://localhost:8080>, then sign in with the demo credentials configured in the root `.env` (`DEMO_USERNAME` and `DEMO_PASSWORD`). The default demo username is `demo`.

The browser sends `POST /api/user/login` to Nginx, which forwards it to the User Service. The page displays success or error information but does not persist or display the session token.

The frontend runs in its own Node.js container. The host does not need Node.js for Docker-based deployment.

For local Next.js development, install Node.js and run `npm install` followed by `npm run dev` from this directory. Direct access to the development server on port 3000 will not proxy `/api/user/login`; use the Compose/Nginx entry point for integrated testing.

## UI components

The login screen uses Material Design 3 components from `@material/web` with
`@lit/react` adapters in `src/components/material.tsx`. Import these adapters for
new screens. Material Web is in maintenance mode; see its upstream README.
The login screen loads on the client (`ssr: false`) because these components use
browser APIs. Theme tokens and layout are in `src/app/globals.css`.

Use `npm ci` for reproducible installs and `npm run build` for validation.
The Compose service is named `web`; its build context is `./web`.


## US-001 authentication

Login uses the User service's HttpOnly cookie. `/teacher`, `/coordinator` and
`/account-management` are protected by server-side middleware and a browser session
shell. Account management is a permissions placeholder, not US-002 CRUD.
The server-only `USER_API_URL` defaults to `http://nginx/api/user` for existing
Compose networking. For separate local servers, set it to the User-service base
URL. The browser still uses same-origin `/api/user/*` through the gateway.

After `npm ci`, run `npm run build`. For full isolated backend/browser verification:

```sh
# From repository root, with backend test dependencies, Docker, Node and Chrome:
US001_BROWSER_TESTS=1 python server/services/user/tests/run_postgres.py
```

The runner supplies temporary URLs, generated credentials and the isolated
PostgreSQL database; `npm run test:e2e` alone requires that test environment.
Browser tests use Playwright with the installed Google Chrome channel. No
credentials or tokens are written into browser storage or test source files.
