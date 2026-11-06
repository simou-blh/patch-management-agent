"""Read-only checks. Default checks tools; --live also checks Docker, Ansible, osquery, SSH and Semaphore."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from patch_agent.osquery import collect, load_hosts  # noqa: E402

DEFAULT_SEMAPHORE_URL = "http://localhost:3000"
TIMEOUT_SECONDS = 10


def check_semaphore(base_url=None, token=None, opener=urllib.request.urlopen):
    """Ping the local Semaphore API; authenticate only when a token is provided.

    The token stays in the operator environment, is never printed and is never a
    tool argument. Auth is skipped, not failed, when no token is set.
    """
    url = (base_url or os.environ.get("SEMAPHORE_URL") or DEFAULT_SEMAPHORE_URL).rstrip("/")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        print("FAIL semaphore: SEMAPHORE_URL must be an http(s) URL with a host")
        return False
    if parsed.username is not None or parsed.password is not None:
        print("FAIL semaphore: SEMAPHORE_URL must not embed credentials")
        return False
    try:
        with opener(f"{url}/api/ping", timeout=TIMEOUT_SECONDS) as response:
            ok = getattr(response, "status", 0) == 200
        print(f"{'OK' if ok else 'FAIL'} semaphore ping: {url}")
        if not ok:
            return False
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"FAIL semaphore ping: {type(exc).__name__}")
        return False

    token = token if token is not None else os.environ.get("SEMAPHORE_API_TOKEN")
    if not token:
        print("SKIP semaphore auth: SEMAPHORE_API_TOKEN not set")
        return True
    request = urllib.request.Request(
        f"{url}/api/projects", headers={"Authorization": f"Bearer {token}"})
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            ok = getattr(response, "status", 0) == 200
            payload = json.loads(response.read().decode("utf-8")) if ok else []
        count = len(payload) if isinstance(payload, list) else "?"
        print(f"{'OK' if ok else 'FAIL'} semaphore auth: {count} project(s) visible")
        return ok
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"FAIL semaphore auth: {type(exc).__name__}")
        return False


def check_ssh(hosts=None, runner=subprocess.run):
    """Batch-mode SSH authentication to each configured host, without osquery."""
    hosts = load_hosts() if hosts is None else hosts
    failed = False
    for name, host in hosts.items():
        command = [
            "ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=10", "-o", "IdentitiesOnly=yes",
            "-i", str(Path(host["key"]).expanduser()),
            f"{host['user']}@{host['address']}", "true",
        ]
        try:
            result = runner(command, capture_output=True, text=True, timeout=20)
            ok = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        print(f"{'OK' if ok else 'FAIL'} ssh {name}")
        failed |= not ok
    return not failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    failed = False
    print(f"Python: {sys.version.split()[0]}")
    if sys.version_info < (3, 12):
        failed = True
    for command in ("git", "ssh", "uv", "opencode", "docker", "ansible", "ansible-playbook"):
        path = shutil.which(command)
        print(f"{'OK' if path else 'MISSING'} {command}: {path or 'not on PATH'}")
        failed |= path is None
    if args.live:
        for command in (["docker", "info"], ["ansible", "all", "-m", "ping"]):
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                print(f"{'OK' if result.returncode == 0 else 'FAIL'} {' '.join(command)}")
                failed |= result.returncode != 0
            except (OSError, subprocess.TimeoutExpired):
                print(f"FAIL {' '.join(command)}")
                failed = True
        failed |= not check_ssh()
        result = asyncio.run(collect(list(load_hosts()), "os_version"))
        for name, host in result["hosts"].items():
            debian12 = bool(host["rows"]) and all(
                str(row.get("major")) == "12" and "Debian" in row.get("name", "")
                for row in host["rows"])
            print(f"{'OK' if debian12 else 'FAIL'} {name}: Debian 12 osquery evidence")
            failed |= not debian12
        failed |= not check_semaphore()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
