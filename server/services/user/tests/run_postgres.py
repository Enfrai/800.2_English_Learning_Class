"""Run the complete suite with an owned, disposable PostgreSQL 17 container."""

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

LABEL = "ako.us001.phase22"


def docker(*args: str) -> str:
    """
    Run the Docker command against the disposable test infrastructure.
    """
    return subprocess.check_output(["docker", *args], text=True).strip()


def verify_container(container_id: str, run_id: str) -> dict:
    """Fail closed before connecting or removing any container."""
    info = json.loads(docker("inspect", container_id))[0]
    checks = (
        info["Id"] == container_id,
        info["Name"] == f"/us001-pg17-{run_id}",
        info["Config"]["Labels"].get(LABEL) == run_id,
        info["Config"]["Image"] == "postgres:17-alpine",
        info["HostConfig"]["NetworkMode"] == "bridge",
        not any(m["Type"] in {"volume", "bind"} for m in info["Mounts"]),
        bool(info["HostConfig"]["Tmpfs"].get("/var/lib/postgresql/data")),
    )
    if not all(checks):
        raise RuntimeError("Test container identity or isolation check failed")
    return info


def main() -> int:
    """
    Parse command-line options and run the module’s documented command-line workflow.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-only", action="store_true")
    parser.add_argument("--test-file", action="append", default=[])
    args = parser.parse_args()
    test_dir = Path(__file__).resolve().parent
    targets = []
    for name in args.test_file:
        candidate = (test_dir / name).resolve()
        if (
            candidate.parent != test_dir
            or not candidate.name.startswith("test_")
            or not candidate.is_file()
        ):
            parser.error(
                "--test-file must name an existing test module in this directory"
            )
        targets.append(str(candidate))
    run_id = uuid4().hex
    name = f"us001-pg17-{run_id}"
    database = f"us001_test_{run_id}"
    password = secrets.token_hex(24)
    env = os.environ.copy()
    env.update(
        POSTGRES_USER="us001_test", POSTGRES_PASSWORD=password, POSTGRES_DB=database
    )
    container_id = ""
    try:
        container_id = subprocess.check_output(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--label",
                f"{LABEL}={run_id}",
                "--network",
                "bridge",
                "--tmpfs",
                "/var/lib/postgresql/data:rw",
                "-p",
                "127.0.0.1::5432",
                "-e",
                "POSTGRES_USER",
                "-e",
                "POSTGRES_PASSWORD",
                "-e",
                "POSTGRES_DB",
                "postgres:17-alpine",
            ],
            env=env,
            text=True,
        ).strip()
        info = verify_container(container_id, run_id)
        binding = info["NetworkSettings"]["Ports"]["5432/tcp"]
        if len(binding) != 1 or binding[0]["HostIp"] != "127.0.0.1":
            raise RuntimeError("Test port is not bound exclusively to loopback")
        port = binding[0]["HostPort"]
        print(
            f"Created isolated test container: {name} ({container_id[:12]})", flush=True
        )
        for _ in range(60):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    container_id,
                    "pg_isready",
                    "-U",
                    "us001_test",
                    "-d",
                    database,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Temporary PostgreSQL did not become ready")
        env.update(
            US001_TEST_RUN_ID=run_id,
            US001_TEST_CONTAINER_ID=container_id,
            US001_TEST_PG_URL=f"postgresql+psycopg://us001_test:{password}@127.0.0.1:{port}/{database}",
            PYTHONDONTWRITEBYTECODE="1",
        )
        result = (
            0
            if args.browser_only
            else subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    *(targets or [str(test_dir)]),
                    "-q",
                    "-p",
                    "no:cacheprovider",
                ],
                env=env,
            ).returncode
        )
        if result == 0 and (
            os.getenv("US001_BROWSER_TESTS") == "1" or args.browser_only
        ):
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("run_browser.py"))],
                env=env,
            ).returncode
        return result
    finally:
        if container_id:
            verify_container(container_id, run_id)
            docker("rm", "-f", container_id)
            remaining = docker(
                "ps", "-aq", "--no-trunc", "--filter", f"id={container_id}"
            )
            if remaining:
                raise RuntimeError("Owned test container still exists after cleanup")
            print(f"Verified cleanup of owned test container: {name}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
