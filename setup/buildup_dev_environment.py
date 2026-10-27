"""
Idempotent Docker bootstrap for Windows or macOS.
Author: Shuohui Liu
Date: 18 Oct 2026
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

PACKAGES = [
    "docker-ce",
    "docker-ce-cli",
    "containerd.io",
    "docker-buildx-plugin",
    "docker-compose-plugin",
]


def run(*args, check=True, capture=False):
    """
    Execute a subprocess with the requested exit-code and output-capture policy.
    """
    print("+", " ".join(map(str, args)), flush=True)
    return subprocess.run(
        list(map(str, args)), check=check, text=True, capture_output=capture
    )


def sudo(*args):
    """
    Run the command with elevated privileges when the current user is not root.
    """
    return run(*(([]) if os.geteuid() == 0 else ["sudo"]), *args)


def os_release():
    """
    Read operating-system identification fields from /etc/os-release.
    """
    data = {}
    for line in Path("/etc/os-release").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k] = v.strip().strip('"')
    return data


def download(url, target):
    """
    Download the requested resource into the target file.
    """
    print("Downloading from", url)
    req = urllib.request.Request(url, headers={"User-Agent": "docker-bootstrap/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response, open(target, "wb") as out:
        shutil.copyfileobj(response, out)


def installed():
    """
    Check whether Docker CLI or Docker Desktop is already installed.
    """
    if shutil.which("docker"):
        result = run("docker", "--version", check=False, capture=True)
        if result.returncode == 0:
            print("Already installed:", result.stdout.strip())
            return True
    if sys.platform == "darwin" and Path("/Applications/Docker.app").exists():
        print("Docker Desktop application already exists.")
        return True
    if sys.platform == "win32":
        path = (
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "Docker/Docker/Docker Desktop.exe"
        )
        if path.exists():
            print("Docker Desktop application already exists.")
            return True
    return False


def mac_install():
    """
    Install Docker Desktop on a supported macOS architecture.
    """
    version = platform.mac_ver()[0]
    arch = platform.machine()
    print("macOS", version, arch)
    if arch not in ("arm64", "x86_64"):
        raise RuntimeError("Unsupported Mac architecture")
    if shutil.which("brew"):
        run("brew", "install", "--cask", "docker")
        return
    url = f"https://desktop.docker.com/mac/main/{arch}/Docker.dmg"
    with tempfile.TemporaryDirectory() as folder:
        dmg = Path(folder) / "Docker.dmg"
        download(url, dmg)
        mount = Path(folder) / "mounted"
        mount.mkdir()
        run("hdiutil", "attach", dmg, "-nobrowse", "-mountpoint", mount)
        try:
            run("sudo", str(mount / "Docker.app/Contents/MacOS/install"))
        finally:
            run("hdiutil", "detach", mount, check=False)
    print("Start Docker Desktop from Applications and accept its license agreement.")


def windows_install():
    """
    Install Docker Desktop on Windows using winget or the vendor installer.
    """
    if platform.machine().lower() not in ("amd64", "x86_64", "arm64"):
        raise RuntimeError("Unsupported Windows architecture")
    print("Windows:", platform.version(), platform.machine())
    if shutil.which("winget"):
        run(
            "winget",
            "install",
            "--id",
            "Docker.DockerDesktop",
            "--exact",
            "--source",
            "winget",
            "--accept-source-agreements",
            "--accept-package-agreements",
        )
    else:
        arch = "arm64" if platform.machine().lower() == "arm64" else "amd64"
        url = f"https://desktop.docker.com/win/main/{arch}/Docker%20Desktop%20Installer.exe"
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "Docker Desktop Installer.exe"
            download(url, exe)
            run(exe, "install", "--user")
    print(
        "Start Docker Desktop, ensure WSL 2 is configured, and accept its license agreement."
    )


def check_and_install_docker():
    """
    Check for Docker and install it only when the configured confirmation allows it.
    """
    parser = argparse.ArgumentParser(description="Install Docker if missing")
    parser.add_argument(
        "--yes", action="store_true", help="Proceed without confirmation"
    )
    args = parser.parse_args()
    print("System:", platform.platform(), "| architecture:", platform.machine())
    if installed():
        return 0
    if not args.yes and input(
        "Docker is missing. Install it? [y/N] "
    ).strip().lower() not in ("y", "yes"):
        print("Cancelled")
        return 0
    try:
        if sys.platform == "darwin":
            mac_install()
        elif sys.platform == "win32":
            windows_install()
        else:
            raise RuntimeError(f"Unsupported OS: {sys.platform}")

        print("Installer finished. Docker Desktop may need to be started manually.")

        if shutil.which("docker"):
            run("docker", "--version", check=False)
            run("docker", "info", check=False)
        return 0
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


def main():
    """
    Parse command-line options and run the module’s documented command-line workflow.
    """
    check_and_install_docker()


if __name__ == "__main__":
    sys.exit(main())
"""Check/install Docker and Python 3.12, then prepare project dependencies.

Author: Shuohui Liu
Date: 19 Oct 2026
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REQUIREMENTS = (
    Path("server/services/user/requirements.txt"),
    Path("server/services/accessment/requirements.txt"),
    Path("server/services/lesson/requirements.txt"),
)


def run(*args, check=True, capture=False):
    """
    Execute a subprocess with the requested exit-code and output-capture policy.
    """
    print("+", " ".join(map(str, args)), flush=True)
    return subprocess.run(
        list(map(str, args)), check=check, text=True, capture_output=capture
    )


def confirm(question, assume_yes=False):
    """
    Read affirmative user consent unless the caller already approved the operation.
    """
    return assume_yes or input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def download(url, target):
    """
    Download the requested resource into the target file.
    """
    print("Downloading from", url)
    req = urllib.request.Request(url, headers={"User-Agent": "dev-bootstrap/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response, open(target, "wb") as out:
        shutil.copyfileobj(response, out)


def docker_installed():
    """
    Check whether Docker CLI or Docker Desktop is already installed.
    """
    if shutil.which("docker"):
        result = run("docker", "--version", check=False, capture=True)
        if result.returncode == 0:
            print("Docker installed:", result.stdout.strip())
            return True
    if sys.platform == "darwin" and Path("/Applications/Docker.app").exists():
        print("Docker Desktop application already exists.")
        return True
    if sys.platform == "win32":
        path = (
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "Docker/Docker/Docker Desktop.exe"
        )
        if path.exists():
            print("Docker Desktop application already exists.")
            return True
    return False


def mac_install_docker():
    """
    Install Docker Desktop on macOS using Homebrew or the disk-image installer.
    """
    arch = platform.machine()
    if arch not in ("arm64", "x86_64"):
        raise RuntimeError("Unsupported Mac architecture")
    if shutil.which("brew"):
        run("brew", "install", "--cask", "docker")
        return
    url = f"https://desktop.docker.com/mac/main/{arch}/Docker.dmg"
    with tempfile.TemporaryDirectory() as folder:
        dmg = Path(folder) / "Docker.dmg"
        download(url, dmg)
        mount = Path(folder) / "mounted"
        mount.mkdir()
        run("hdiutil", "attach", dmg, "-nobrowse", "-mountpoint", mount)
        try:
            run("sudo", str(mount / "Docker.app/Contents/MacOS/install"))
        finally:
            run("hdiutil", "detach", mount, check=False)
    print("Start Docker Desktop and accept its license agreement.")


def windows_install_docker():
    """
    Install Docker Desktop on Windows using winget or the vendor installer.
    """
    if platform.machine().lower() not in ("amd64", "x86_64", "arm64"):
        raise RuntimeError("Unsupported Windows architecture")
    if shutil.which("winget"):
        run(
            "winget",
            "install",
            "--id",
            "Docker.DockerDesktop",
            "--exact",
            "--source",
            "winget",
            "--accept-source-agreements",
            "--accept-package-agreements",
        )
    else:
        arch = "arm64" if platform.machine().lower() == "arm64" else "amd64"
        url = f"https://desktop.docker.com/win/main/{arch}/Docker%20Desktop%20Installer.exe"
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "Docker Desktop Installer.exe"
            download(url, exe)
            run(exe, "install", "--user")
    print("Start Docker Desktop and ensure WSL 2 is configured.")


def check_and_install_docker(assume_yes):
    """
    Check for Docker and install it only when the configured confirmation allows it.
    """
    if docker_installed():
        return
    if not confirm("Docker is missing. Install it?", assume_yes):
        print("Docker installation skipped.")
        return
    if sys.platform == "darwin":
        mac_install_docker()
    elif sys.platform == "win32":
        windows_install_docker()
    else:
        raise RuntimeError(f"Unsupported OS: {sys.platform}")
    print("Docker installer finished. Docker Desktop may need to be started manually.")


def python312_command():
    """Return an invocation of Python 3.12, excluding other Python versions."""
    candidates = []
    if sys.platform == "win32":
        if shutil.which("py"):
            candidates.append(("py", "-3.12"))
        if shutil.which("python3.12"):
            candidates.append(("python3.12",))
        if shutil.which("python"):
            candidates.append(("python",))
    else:
        if shutil.which("python3.12"):
            candidates.append(("python3.12",))
        if sys.platform == "darwin":
            for prefix in ("/opt/homebrew", "/usr/local"):
                path = Path(prefix) / "opt/python@3.12/bin/python3.12"
                if path.exists():
                    candidates.append((str(path),))
    for command in candidates:
        result = subprocess.run(
            [*command, "-c", "import sys; print(sys.version_info[:2] == (3, 12))"],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip() == "True":
            return command
    return None


def install_python312():
    """
    Install Python 3.12 using the supported operating-system package manager.
    """
    if sys.platform == "darwin":
        if not shutil.which("brew"):
            raise RuntimeError(
                "Homebrew is required for automatic Python 3.12 installation on macOS. "
                "Install Homebrew from https://brew.sh/ or install Python 3.12 "
                "from https://www.python.org/downloads/ and rerun this script."
            )
        run("brew", "install", "python@3.12")
    elif sys.platform == "win32":
        if not shutil.which("winget"):
            raise RuntimeError(
                "winget is required for automatic Python 3.12 installation on Windows. "
                "Install App Installer or Python 3.12 from "
                "https://www.python.org/downloads/ and rerun this script."
            )
        run(
            "winget",
            "install",
            "--id",
            "Python.Python.3.12",
            "--exact",
            "--source",
            "winget",
            "--accept-source-agreements",
            "--accept-package-agreements",
        )
    else:
        raise RuntimeError(f"Unsupported OS: {sys.platform}")


def check_and_install_python312(assume_yes):
    """
    Find Python 3.12 and optionally install it after confirmation.
    """
    command = python312_command()
    if command:
        print("Python 3.12 found:", " ".join(command))
        return command
    if not confirm("Python 3.12 is missing. Install it?", assume_yes):
        print("Python 3.12 installation skipped; cannot prepare virtual environment.")
        return None
    install_python312()
    command = python312_command()
    if command is None:
        raise RuntimeError(
            "Python 3.12 installer finished but Python was not found. "
            "Open a new terminal and rerun this script (Windows may require PATH refresh)."
        )
    print("Python 3.12 installed:", " ".join(command))
    return command


def setup_python_environment(python_command, project_root):
    """
    Create or reuse the project Python 3.12 environment and install service
    dependencies.
    """
    missing = [str(p) for p in REQUIREMENTS if not (project_root / p).is_file()]
    if missing:
        raise RuntimeError(
            f"Requirements not found under {project_root}: {', '.join(missing)}. "
            "Run this script from the project root or pass --project-root."
        )

    venv_dir = project_root / ".venv"
    venv_python = venv_dir / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    if venv_python.exists():
        version = subprocess.run(
            [
                str(venv_python),
                "-c",
                "import sys; print(sys.version_info[:2] == (3, 12))",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if version.returncode != 0 or version.stdout.strip() != "True":
            raise RuntimeError(
                f"Existing {venv_dir} is not a working Python 3.12 environment. "
                "Move/remove it manually before rerunning to avoid losing installed packages."
            )
        print("Using existing virtual environment:", venv_dir)
    else:
        if venv_dir.exists():
            raise RuntimeError(
                f"{venv_dir} exists but is incomplete. Check it manually."
            )
        run(*python_command, "-m", "venv", venv_dir)

    for requirements in REQUIREMENTS:
        run(venv_python, "-m", "pip", "install", "-r", project_root / requirements)

    if sys.platform == "win32":
        print(
            f"Virtual environment ready. Activate with: {venv_dir}\\Scripts\\activate"
        )
    else:
        print(
            f"Virtual environment ready. Activate with: source {venv_dir}/bin/activate"
        )


def main():
    """
    Parse command-line options and run the module’s documented command-line workflow.
    """
    parser = argparse.ArgumentParser(
        description="Check/install Docker and Python 3.12; create a venv and install service requirements."
    )
    parser.add_argument(
        "--yes", action="store_true", help="Approve installations without prompting"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Directory containing server/services/ and .venv (default: current directory)",
    )
    args = parser.parse_args()
    if sys.platform not in ("darwin", "win32"):
        print("ERROR: Only macOS and Windows are supported.", file=sys.stderr)
        return 1
    print("System:", platform.platform(), "| architecture:", platform.machine())
    try:
        check_and_install_docker(args.yes)
        python_command = check_and_install_python312(args.yes)
        if python_command:
            setup_python_environment(python_command, args.project_root.resolve())
        return 0
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
