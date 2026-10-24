"""Production Next.js + FastAPI browser checks on the owned test PostgreSQL.

The ephemeral proxy mirrors the existing gateway paths. It is test-only and
exposes fixture controls only with a per-run random key; no production routes
or Compose resources are altered.
"""

import http.client
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from sqlalchemy import create_engine, select

from test_postgres import postgres_url


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(url: str, process: subprocess.Popen) -> None:
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Test server exited before becoming ready")
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("Test server readiness timed out")


def main() -> int:
    url = (
        postgres_url.__wrapped__()
    )  # Same identity/port/DB verification as integration tests.
    service = Path(__file__).resolve().parents[1]
    web = service.parents[2] / "web"
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js must be on PATH for browser verification")
    sys.path.insert(0, str(service))
    os.environ["DATABASE_URL"] = url
    import app

    engine = create_engine(url)
    app.Base.metadata.create_all(engine)
    password, key = secrets.token_urlsafe(24), secrets.token_hex(24)
    names = [
        f"e2e_{n}"
        for n in (
            "teacher",
            "coordinator",
            "lock",
            "forbidden",
            "tabs",
            "activity",
            "idle",
        )
    ]
    with engine.begin() as db:
        for name in names:
            db.execute(
                app.users.insert().values(
                    username=name,
                    display_name=name,
                    role="coordinator" if name == "e2e_coordinator" else "teacher",
                    password_hash=app.password_hash(password, os.urandom(16)),
                )
            )
    backend_port, web_port = free_port(), free_port()

    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            self.forward()

        def do_POST(self) -> None:
            if self.path.startswith("/__test/"):
                self.control()
            else:
                self.forward()

        def control(self) -> None:
            if self.headers.get("X-Test-Key") != key:
                self.send_error(403)
                return
            data = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
            )
            username = data.get("username")
            if username not in names:
                self.send_error(400)
                return
            with engine.begin() as db:
                user_id = db.execute(
                    select(app.users.c.id).where(app.users.c.username == username)
                ).scalar_one()
                query = app.user_sessions.c.user_id == user_id
                now = datetime.now(UTC)
                if self.path == "/__test/expire":
                    db.execute(
                        app.user_sessions.update()
                        .where(query)
                        .values(
                            created_at=now - timedelta(hours=1),
                            expires_at=now - timedelta(seconds=1),
                        )
                    )
                elif self.path == "/__test/age":
                    db.execute(
                        app.user_sessions.update()
                        .where(query)
                        .values(
                            created_at=now - timedelta(hours=1),
                            last_activity_at=now - timedelta(minutes=20),
                            expires_at=now + timedelta(minutes=10),
                        )
                    )
                elif self.path != "/__test/inspect":
                    self.send_error(404)
                    return
                row = (
                    db.execute(
                        select(
                            app.user_sessions.c.last_activity_at,
                            app.user_sessions.c.expires_at,
                            app.user_sessions.c.revoked_at,
                        ).where(query)
                    )
                    .mappings()
                    .one()
                )
                body = json.dumps(dict(row), default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def forward(self) -> None:
            is_api = self.path.startswith("/api/user/")
            path = self.path[len("/api/user") :] if is_api else self.path
            connection = http.client.HTTPConnection(
                "127.0.0.1", backend_port if is_api else web_port, timeout=15
            )
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                headers = {
                    k: v
                    for k, v in self.headers.items()
                    if k.lower() not in {"connection", "transfer-encoding"}
                }
                connection.request(self.command, path, body=body, headers=headers)
                response = connection.getresponse()
                content = response.read()
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in {
                        "content-length",
                        "transfer-encoding",
                        "connection",
                    }:
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            finally:
                connection.close()

    proxy = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
    origin = f"http://127.0.0.1:{proxy.server_port}"
    env = os.environ.copy()
    env.update(
        DATABASE_URL=url,
        USER_API_URL=f"http://127.0.0.1:{backend_port}",
        SESSION_PUBLIC_ORIGIN=origin,
        US001_E2E_URL=origin,
        US001_E2E_PASSWORD=password,
        US001_E2E_KEY=key,
        NEXT_TELEMETRY_DISABLED="1",
    )
    processes = []
    started = False
    try:
        with tempfile.TemporaryDirectory(prefix="us001-browser-") as logs:
            with (
                open(Path(logs) / "backend.log", "w+") as backend_log,
                open(Path(logs) / "web.log", "w+") as web_log,
            ):
                backend = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app:app",
                        "--app-dir",
                        str(service),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(backend_port),
                        "--lifespan",
                        "off",
                    ],
                    env=env,
                    stdout=backend_log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(backend)
                standalone = web / ".next/standalone"
                shutil.copytree(
                    web / ".next/static",
                    standalone / ".next/static",
                    dirs_exist_ok=True,
                )
                frontend_env = {**env, "HOSTNAME": "127.0.0.1", "PORT": str(web_port)}
                frontend = subprocess.Popen(
                    [node, str(standalone / "server.js")],
                    cwd=web,
                    env=frontend_env,
                    stdout=web_log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(frontend)
                wait_ready(f"http://127.0.0.1:{backend_port}/health", backend)
                wait_ready(f"http://127.0.0.1:{web_port}/", frontend)
                Thread(target=proxy.serve_forever, daemon=True).start()
                started = True
                result = subprocess.run(
                    [node, "--test", "--test-concurrency=1", "tests/us001.test.mjs"],
                    cwd=web,
                    env=env,
                )
                if result.returncode:
                    web_log.seek(0)
                    print(web_log.read()[-3000:])
                return result.returncode
    finally:
        if started:
            proxy.shutdown()
        proxy.server_close()
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        engine.dispose()
        app.engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
