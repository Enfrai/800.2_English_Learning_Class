"""Check failure propagation, report capture and isolated cleanup without Docker.

Author: Shuohui Liu
Date: 19 Oct 2026
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def load_runner():
    """
    Import the Docker test runner without starting its command-line entry point.
    """
    spec = importlib.util.spec_from_file_location(
        "docker_test_runner", Path(__file__).with_name("run.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_child_failure_is_logged_with_its_real_exit_code(tmp_path, monkeypatch):
    """
    Verify that child failure is logged with its real exit code.
    """
    runner = load_runner()
    monkeypatch.setattr(runner, "REPORTS", tmp_path)
    monkeypatch.setattr(sys, "argv", ["run.py", "web"])
    result = runner.run(
        "failing",
        [sys.executable, "-c", "print('assertion failed'); raise SystemExit(7)"],
        tmp_path,
        os.environ.copy(),
    )
    assert result["exit_code"] == 7
    assert "assertion failed" in (tmp_path / "web/failing.log").read_text()


def test_setup_failure_replaces_old_success_summary(tmp_path, monkeypatch):
    """
    Verify that setup failure replaces old success summary.
    """
    runner = load_runner()
    monkeypatch.setattr(runner, "REPORTS", tmp_path)
    monkeypatch.setattr(sys, "argv", ["run.py", "web"])
    monkeypatch.setenv("TEST_SUITE", "does-not-exist")
    folder = tmp_path / "web"
    folder.mkdir()
    (folder / "summary.json").write_text('{"status":"passed"}')
    assert runner.main() == 1
    assert json.loads((folder / "summary.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("keep", [False, True])
def test_host_runner_continues_after_failure_and_only_cleans_its_project(
    tmp_path, keep
):
    """
    Verify that host runner continues after failure and only cleans its project.
    """
    root = Path(__file__).resolve().parents[2]
    target = tmp_path / "repo/tests"
    target.mkdir(parents=True)
    shutil.copy(root / "tests/run_docker_tests.py", target)
    binary = tmp_path / "bin"
    binary.mkdir()
    calls = tmp_path / "calls.jsonl"
    docker = binary / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        "import sys,json,os\n"
        "with open(os.environ['CALL_LOG'],'a') as f:\n"
        " f.write(json.dumps(sys.argv[1:])+'\\n')\n"
        "sys.exit(1 if 'run' in sys.argv and 'test-backend' in sys.argv else 0)\n"
    )
    docker.chmod(0o755)
    result = subprocess.run(
        [
            sys.executable,
            str(target / "run_docker_tests.py"),
            *(["--keep"] if keep else []),
        ],
        env=os.environ
        | {
            "PATH": str(binary) + os.pathsep + os.environ["PATH"],
            "CALL_LOG": str(calls),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    recorded = [json.loads(line) for line in calls.read_text().splitlines()]
    assert len([args for args in recorded if "run" in args]) == 3
    assert bool([args for args in recorded if "down" in args]) is not keep
    for args in recorded:
        if "-p" in args:
            assert args[args.index("-p") + 1].startswith("ako-tests-")
    summary = json.loads((tmp_path / "repo/test-results/summary.json").read_text())
    assert summary["status"] == "failed"
    assert [item["exit_code"] for item in summary["suites"]] == [1, 0, 0]
