"""Run isolated backend and web suites including public-page accessibility checks.

Author: Shuohui Liu
Date: 19 Oct 2026
Updated: Sandhya Tiwari, 26 Oct 2026
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(os.getenv("AKO_TEST_ROOT", "/workspace"))
REPORTS = Path(os.getenv("AKO_TEST_REPORTS", "/reports"))


def run(name: str, args: list[str], cwd: Path, env: dict[str, str]) -> dict:
    """Keep a separate log while also streaming output to docker compose logs."""
    folder = REPORTS / sys.argv[1]
    folder.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    print(f"\n=== {name} ===", flush=True)
    try:
        with (folder / f"{name}.log").open("w") as log:
            process = subprocess.Popen(
                args,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            code = process.wait()
    except OSError as error:
        (folder / f"{name}.log").write_text(str(error))
        print(str(error), flush=True)
        code = 127
    return {
        "suite": name,
        "exit_code": code,
        "seconds": round(time.monotonic() - started, 2),
    }


def backend() -> list[dict]:
    """Create a run-owned integration DB; fixtures create their own transaction DBs."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    admin_url = make_url(os.environ["TEST_DATABASE_URL"])
    if (
        os.getenv("AKO_TEST_COMPOSE") != "1"
        or admin_url.host != "test-db"
        or admin_url.username != "ako_test"
        or admin_url.database != "postgres"
    ):
        raise RuntimeError("Backend runner requires the isolated Compose test database")
    suites = ["user", "accessment", "lesson"]
    selected = os.getenv("TEST_SUITE")
    if selected:
        if selected not in suites:
            raise ValueError("TEST_SUITE must be user, accessment or lesson")
        suites = [selected]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    name = f"ako_test_{uuid4().hex}"
    results = []
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        integration_url = admin_url.set(database=name).render_as_string(
            hide_password=False
        )
        for suite in suites:
            env = os.environ | {
                "AKO_COMPOSE_TEST_DATABASE_URL": integration_url,
                "PYTHONPATH": str(ROOT / "server/services" / suite),
            }
            results.append(
                run(
                    suite,
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-v",
                        "-ra",
                        "--junitxml",
                        str(REPORTS / "backend" / f"{suite}.xml"),
                        "--html",
                        str(REPORTS / "backend" / f"{suite}.html"),
                        "--self-contained-html",
                    ],
                    ROOT / "server/services" / suite,
                    env,
                )
            )
    finally:
        if created:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
    return results


def web() -> list[dict]:
    """Keep mocked UI tests separate from the real-system browser suite."""
    commands = {
        "api": [
            "node",
            "--test",
            "--test-concurrency=1",
            "tests/api-cookie.test.mjs",
            "tests/attendance-session.test.mjs",
            "tests/report-session.test.mjs",
            "tests/lesson-session.test.mjs",
        ],
        "staff-ui": ["node", "tests/run-staff-ui.mjs"],
        "materials-unit": ["npm", "run", "test:materials-unit"],
        "materials-ui": ["node", "tests/run-materials-ui.mjs"],
        "public-unit": ["npm", "run", "test:public-unit"],
        "public-ui": ["npm", "run", "test:public-ui"],
        "public-a11y": ["npm", "run", "test:public-a11y"],
        "checkin-unit": ["npm", "run", "test:checkin-unit"],
        "checkin-ui": ["node", "tests/run-checkin-ui.mjs"],
        "reports-unit": ["npm", "run", "test:reports-unit"],
        "reports-ui": ["node", "tests/run-reports-ui.mjs"],
        "sessions-unit": ["npm", "run", "test:sessions-unit"],
        "sessions-ui": ["node", "tests/run-sessions-ui.mjs"],
        "lessons-unit": ["npm", "run", "test:lessons-unit"],
        "lessons-ui": ["node", "tests/run-lessons-ui.mjs"],
        "public-enquiry": ["node", "tests/public-enquiry-form.mjs"],
        "coordinator-enquiries": ["node", "tests/coordinator-enquiries.mjs"],
        "csv-ui": ["node", "tests/run-csv-ui.mjs"],
    }
    selected = os.getenv("TEST_SUITE")
    if selected and selected not in commands:
        raise ValueError(f"TEST_SUITE must be one of: {', '.join(commands)}")
    return [
        run(name, command, ROOT / "web", os.environ.copy())
        for name, command in commands.items()
        if not selected or selected == name
    ]


def system() -> list[dict]:
    return [
        run(
            "system",
            [
                sys.executable,
                "-m",
                "pytest",
                "-v",
                "-ra",
                "--junitxml",
                str(REPORTS / "system/results.xml"),
                "--html",
                str(REPORTS / "system/report.html"),
                "--self-contained-html",
            ],
            ROOT / "tests/system",
            os.environ.copy(),
        )
    ]


def main() -> int:
    mode = sys.argv[1]
    folder = REPORTS / mode
    folder.mkdir(parents=True, exist_ok=True)
    # Invalidate old results before this run, so a setup failure cannot look green.
    summary = {"status": "running", "suites": []}
    summary_path = folder / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    try:
        results = {"backend": backend, "web": web, "system": system}[mode]()
        failed = any(result["exit_code"] for result in results)
        summary = {"status": "failed" if failed else "passed", "suites": results}
    except Exception as error:
        summary = {"status": "failed", "error": str(error), "suites": []}
        failed = True
        print(f"Test setup failed: {error}", file=sys.stderr, flush=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

