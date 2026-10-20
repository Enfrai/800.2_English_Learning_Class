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
    print("+", " ".join(map(str, args)), flush=True)
    return subprocess.run(
        list(map(str, args)), check=check, text=True, capture_output=capture
    )


def sudo(*args):
    return run(*(([]) if os.geteuid() == 0 else ["sudo"]), *args)


def os_release():
    data = {}
    for line in Path("/etc/os-release").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k] = v.strip().strip('"')
    return data


def download(url, target):
    print("Downloading from", url)
    req = urllib.request.Request(url, headers={"User-Agent": "docker-bootstrap/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response, open(target, "wb") as out:
        shutil.copyfileobj(response, out)


def installed():
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
    check_and_install_docker()


if __name__ == "__main__":
    sys.exit(main())
