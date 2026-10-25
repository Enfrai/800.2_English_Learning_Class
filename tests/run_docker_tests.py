"""Run isolated Docker test suites, keep a summary, and clean up only this run.

Author: Shuohui Liu
Date: 19 Oct 2026
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite", choices=["all", "backend", "web", "system"], default="all"
    )
    parser.add_argument(
        "--keep", action="store_true", help="Keep test services for debugging"
    )
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = f"ako-tests-{uuid4().hex[:10]}"
    command = [
        "docker",
        "compose",
        "-f",
        str(root / "compose.test.yaml"),
        "-p",
        project,
    ]
    suites = ["backend", "web", "system"] if options.suite == "all" else [options.suite]
    reports = root / "test-results"
    reports.mkdir(exist_ok=True)
    summary = {"project": project, "status": "running", "suites": []}
    path = reports / "summary.json"
    path.write_text(json.dumps(summary, indent=2) + "\n")
    failed = False
    try:
        subprocess.run(
            ["docker", "info"], cwd=root, check=True, stdout=subprocess.DEVNULL
        )
        build = subprocess.run(
            command + ["build", *[f"test-{s}" for s in suites]], cwd=root
        )
        if build.returncode:
            raise RuntimeError(f"Image build failed with exit code {build.returncode}")
        for suite in suites:
            result = subprocess.run(
                command + ["run", "--rm", f"test-{suite}"], cwd=root
            )
            summary["suites"].append({"suite": suite, "exit_code": result.returncode})
            failed |= result.returncode != 0
            path.write_text(json.dumps(summary, indent=2) + "\n")
    except (
        OSError,
        subprocess.CalledProcessError,
        RuntimeError,
        KeyboardInterrupt,
    ) as error:
        failed = True
        summary["error"] = str(error)
        print(f"Tests interrupted or unable to start: {error}", file=sys.stderr)
    finally:
        if not options.keep:
            try:
                cleanup = subprocess.run(
                    command + ["down", "--remove-orphans"], cwd=root
                )
                if cleanup.returncode:
                    failed = True
                    summary["cleanup_error"] = cleanup.returncode
            except OSError as error:
                failed = True
                summary["cleanup_error"] = str(error)
        summary["status"] = "failed" if failed else "passed"
        path.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Results: {path}\nStatus: {summary['status']}\nTest project: {project}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
