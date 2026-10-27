# Development environment setup

Python 3.14 is the supported project runtime. Docker application images and
isolated test runners use the same minor version.

## Optional bootstrap on macOS and Windows

Run from the repository root using an existing Python interpreter:

```sh
python3 setup/buildup_dev_environment.py
```

Windows:

```powershell
py setup/buildup_dev_environment.py
```

The script checks Docker, finds Python 3.14 or asks to install it, creates the
root `.venv`, and installs all three services' runtime requirements.
macOS automatic Python installation uses Homebrew (`python@3.14`).
Windows uses winget (`Python.Python.3.14`).
Restart the terminal if a newly installed interpreter is not yet discoverable.
Docker Desktop must still be started before container commands.

Use `--project-root /path/to/checkout` when running elsewhere. Use `--yes`
only when you intend to approve the script's installation prompts.
Linux users install Python 3.14 and Docker using their platform tools instead.

Existing environments are checked before package installation. An environment
using another Python version is preserved and rejected. Move it aside manually,
then create a fresh Python 3.14 environment; do not reuse its site-packages.

## Manual Python environment

From the repository root on macOS/Linux:

```sh
python3.14 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install -r server/services/user/requirements-dev.txt
python -m pip install -r server/services/accessment/requirements-dev.txt
python -m pip install -r server/services/lesson/requirements-dev.txt
```

Windows:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
python --version
python -m pip install -r server/services/user/requirements-dev.txt
python -m pip install -r server/services/accessment/requirements-dev.txt
python -m pip install -r server/services/lesson/requirements-dev.txt
```

Select the new `.venv` interpreter in your editor. The root `.python-version`
records 3.14 for compatible version managers.

## Bootstrap regression checks

These checks mock installers and never install Docker/Python or modify a real
environment:

```sh
python3.14 -m unittest discover -s setup/tests -v
```

On Windows use `py -3.14 -m unittest discover -s setup/tests -v`.

See the [root README](../README.md) for the complete Docker startup, configuration,
tests, clean image rebuild, logs and backup instructions.
