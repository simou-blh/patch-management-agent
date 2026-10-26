"""Read-only checks. Default checks tools; --live also checks Docker, Ansible and osquery."""

import argparse
import asyncio
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from patch_agent.osquery import collect, load_hosts  # noqa: E402


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
        result = asyncio.run(collect(list(load_hosts()), "os_version"))
        for name, host in result["hosts"].items():
            debian12 = bool(host["rows"]) and all(
                str(row.get("major")) == "12" and "Debian" in row.get("name", "")
                for row in host["rows"])
            print(f"{'OK' if debian12 else 'FAIL'} {name}: Debian 12 osquery evidence")
            failed |= not debian12
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
