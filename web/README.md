# Next.js frontend

<!--
Describe the containerized Next.js login test and local development workflow.
Author: Shuohui Liu
Date: 19 Oct 2026
-->

This frontend tests the FastAPI User Service through the existing Nginx reverse proxy.

From the `fastapi-microservices` directory, run:

```bash
docker compose up -d --build
```

Open <http://localhost:8080>, then sign in with the demo credentials configured in the root `.env` (`DEMO_USERNAME` and `DEMO_PASSWORD`). The default demo username is `demo`.

The browser sends `POST /api/user/login` to Nginx, which forwards it to the User Service. The page displays success or error information but does not persist or display the session token.

The frontend runs in its own Node.js container. The host does not need Node.js for Docker-based deployment.

For local Next.js development, install Node.js and run `npm install` followed by `npm run dev` from this directory. Direct access to the development server on port 3000 will not proxy `/api/user/login`; use the Compose/Nginx entry point for integrated testing.
