"""Fixed read-only queries over SSH. Target configuration belongs to the operator."""

import asyncio
import ipaddress
import json
from pathlib import Path
import re
import shlex
import subprocess


QUERIES = {
    "os_version": "SELECT name, version, major, minor FROM os_version;",
    "packages": "SELECT name, version, source FROM deb_packages;",
    "processes": "SELECT pid, name FROM processes;",
    "listening_ports": "SELECT pid, port, protocol, address FROM listening_ports;",
}
HOSTS_FILE = Path(__file__).resolve().parent.parent / "lab" / "hosts.json"


def load_hosts(path=HOSTS_FILE):
    hosts = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(hosts, dict) or not hosts:
        raise ValueError("inventory must contain hosts")
    for name, host in hosts.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", name):
            raise ValueError("invalid inventory host name")
        ipaddress.ip_address(host["address"])
        if not re.fullmatch(r"[a-z_][a-z0-9_-]*", host["user"]):
            raise ValueError("invalid SSH user")
        if not isinstance(host["key"], str) or not host["key"]:
            raise ValueError("missing SSH key path")
    return hosts


def query_host(host, query_id):
    command = [
        "ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=10", "-o", "IdentitiesOnly=yes",
        "-i", str(Path(host["key"]).expanduser()),
        f"{host['user']}@{host['address']}",
        shlex.join(["sudo", "-n", "osqueryi", "--json", QUERIES[query_id]]),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
        rows = json.loads(result.stdout)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("unexpected osquery response")
        return {"rows": rows, "error": None}
    except subprocess.TimeoutExpired:
        return {"rows": [], "error": "SSH query timed out"}
    except (subprocess.CalledProcessError, OSError):
        return {"rows": [], "error": "SSH/osquery failed; check operator-side connectivity and logs"}
    except (ValueError, UnicodeError):
        return {"rows": [], "error": "invalid osquery JSON response"}


async def collect(host_names, query_id, *, hosts=None, query_runner=query_host):
    hosts = load_hosts() if hosts is None else hosts
    if query_id not in QUERIES:
        raise ValueError("unknown query id; arbitrary SQL is not accepted")
    if not host_names or len(host_names) != len(set(host_names)):
        raise ValueError("select one or more unique hosts")
    if any(name not in hosts for name in host_names):
        raise ValueError("unknown inventory host")
    semaphore = asyncio.Semaphore(3)

    async def one(name):
        async with semaphore:
            return name, await asyncio.to_thread(query_runner, hosts[name], query_id)

    return {"query_id": query_id, "hosts": dict(await asyncio.gather(*(one(n) for n in host_names)))}
