"""Verify Python 3.14 bootstrap discovery, installation and safe venv reuse.

Author: Shuohui Liu
Date: 24 Oct 2026
"""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "buildup_dev_environment.py"
SPEC = importlib.util.spec_from_file_location("ako_dev_bootstrap", SCRIPT)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def project(self, folder):
        root = Path(folder)
        for requirement in bootstrap.REQUIREMENTS:
            path = root / requirement
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        return root

    def test_import_does_not_run_an_installer(self):
        with patch("subprocess.run") as run:
            SPEC.loader.exec_module(bootstrap)
        run.assert_not_called()

    def test_help_reaches_python_setup_entry_point(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Python 3.14", result.stdout)
        self.assertIn("--project-root", result.stdout)

    def test_mac_discovers_versioned_interpreter(self):
        with (
            patch.object(bootstrap.sys, "platform", "darwin"),
            patch.object(bootstrap.shutil, "which", return_value="/bin/python3.14"),
            patch.object(bootstrap.subprocess, "run") as run,
        ):
            run.return_value = SimpleNamespace(returncode=0, stdout="True\n")
            self.assertEqual(bootstrap.python314_command(), ("python3.14",))
            self.assertIn("(3, 14)", run.call_args.args[0][-1])

    def test_windows_prefers_explicit_launcher_version(self):
        with (
            patch.object(bootstrap.sys, "platform", "win32"),
            patch.object(bootstrap.shutil, "which", return_value="available"),
            patch.object(bootstrap.subprocess, "run") as run,
        ):
            run.return_value = SimpleNamespace(returncode=0, stdout="True\n")
            self.assertEqual(bootstrap.python314_command(), ("py", "-3.14"))

    def test_discovery_rejects_wrong_or_broken_interpreters(self):
        with (
            patch.object(bootstrap.sys, "platform", "win32"),
            patch.object(bootstrap.shutil, "which", return_value="available"),
            patch.object(bootstrap.subprocess, "run") as run,
        ):
            run.side_effect = [
                SimpleNamespace(returncode=0, stdout="False\n"),
                SimpleNamespace(returncode=1, stdout=""),
                SimpleNamespace(returncode=0, stdout="False\n"),
            ]
            self.assertIsNone(bootstrap.python314_command())

    def test_mac_installer_selects_versioned_formula(self):
        with (
            patch.object(bootstrap.sys, "platform", "darwin"),
            patch.object(bootstrap.shutil, "which", return_value="/bin/brew"),
            patch.object(bootstrap, "run") as run,
        ):
            bootstrap.install_python314()
        run.assert_called_once_with("brew", "install", "python@3.14")

    def test_windows_installer_selects_versioned_package(self):
        with (
            patch.object(bootstrap.sys, "platform", "win32"),
            patch.object(bootstrap.shutil, "which", return_value="winget"),
            patch.object(bootstrap, "run") as run,
        ):
            bootstrap.install_python314()
        self.assertIn("Python.Python.3.14", run.call_args.args)

    def test_declined_install_does_not_mutate_environment(self):
        with (
            patch.object(bootstrap, "python314_command", return_value=None),
            patch.object(bootstrap, "confirm", return_value=False),
            patch.object(bootstrap, "install_python314") as install,
        ):
            self.assertIsNone(bootstrap.check_and_install_python314(False))
        install.assert_not_called()

    def test_old_venv_is_preserved_and_pip_never_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.project(folder)
            interpreter = root / ".venv/bin/python"
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text("existing interpreter marker")
            with (
                patch.object(bootstrap.sys, "platform", "darwin"),
                patch.object(
                    bootstrap.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=0, stdout="False\n"),
                ),
                patch.object(bootstrap, "run") as run,
            ):
                with self.assertRaisesRegex(RuntimeError, "Python 3.14"):
                    bootstrap.setup_python_environment(("python3.14",), root)
            run.assert_not_called()
            self.assertEqual(interpreter.read_text(), "existing interpreter marker")

    def test_missing_requirements_does_not_create_a_venv(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bootstrap, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "Requirements not found"):
                    bootstrap.setup_python_environment(("python3.14",), Path(folder))
            run.assert_not_called()

    def test_new_venv_uses_selected_python_and_all_service_dependencies(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.project(folder)
            with (
                patch.object(bootstrap.sys, "platform", "darwin"),
                patch.object(bootstrap, "run") as run,
            ):
                bootstrap.setup_python_environment(("python3.14",), root)
            self.assertEqual(
                run.call_args_list[0].args,
                ("python3.14", "-m", "venv", root / ".venv"),
            )
            self.assertEqual(run.call_count, 1 + len(bootstrap.REQUIREMENTS))
            self.assertEqual(
                [call.args[-1] for call in run.call_args_list[1:]],
                [root / path for path in bootstrap.REQUIREMENTS],
            )

    def test_main_prepares_both_docker_and_python(self):
        with (
            patch.object(bootstrap.sys, "platform", "darwin"),
            patch.object(bootstrap.sys, "argv", [str(SCRIPT)]),
            patch.object(bootstrap, "check_and_install_docker") as docker,
            patch.object(
                bootstrap, "check_and_install_python314", return_value=("python3.14",)
            ) as python,
            patch.object(bootstrap, "setup_python_environment") as setup,
        ):
            self.assertEqual(bootstrap.main(), 0)
        docker.assert_called_once_with(False)
        python.assert_called_once_with(False)
        setup.assert_called_once_with(("python3.14",), Path.cwd().resolve())


if __name__ == "__main__":
    unittest.main()
