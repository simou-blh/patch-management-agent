"""Observed-version verification module for the canary and fleet hosts.

Loaded by ``playbooks/verify.yml``. It compares observed installed package
versions against the approved plan using Debian version semantics, and runs the
configured service health checks. It is read-only: it never installs, removes,
or restarts anything.

The helpers are importable without Ansible so they can be unit-tested on any
platform.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import re
import socket
import subprocess

# --- Debian version helpers --------------------------------------------
# Copied from patch_agent/debversion.py: Ansible ships only this file to the
# target, so it must not import patch_agent. tests/test_library_isolation.py
# keeps the copy identical in behaviour.
from typing import NamedTuple

# [epoch:]upstream[-revision]. A colon is only valid in upstream after an epoch.
_SHAPE = re.compile(r"(?:([0-9]+):)?([0-9][A-Za-z0-9.+~:-]*)", re.ASCII)
_REVISION = re.compile(r"[A-Za-z0-9+.~]+", re.ASCII)


class DebianVersion(NamedTuple):
    epoch: int
    upstream: str
    revision: str


def parse_version(version: str) -> DebianVersion:
    """Split a Debian version, raising ValueError if it is not valid."""
    match = _SHAPE.fullmatch(version) if isinstance(version, str) else None
    if match is None:
        raise ValueError(f"invalid Debian version: {version!r}")
    epoch, rest = match.groups()
    if epoch is None and ":" in rest:
        raise ValueError(f"invalid Debian version (colon without epoch): {version!r}")
    upstream, hyphen, revision = rest.rpartition("-")
    if not hyphen:
        upstream, revision = rest, ""
    elif not upstream or not _REVISION.fullmatch(revision):
        raise ValueError(f"invalid Debian revision: {version!r}")
    return DebianVersion(int(epoch or 0), upstream, revision)


def _is_digit(char: str) -> bool:
    return "0" <= char <= "9"


def _order(char: str) -> int:
    """Sort weight of one non-digit character; '' is the end of the string."""
    if char == "":
        return 0
    if char == "~":
        return -1
    if char.isalpha():
        return ord(char)
    return ord(char) + 256


def _compare_part(left: str, right: str) -> int:
    """dpkg's verrevcmp: alternate non-digit and numeric runs."""
    i = j = 0
    while i < len(left) or j < len(right):
        while (i < len(left) and not _is_digit(left[i])) or (
            j < len(right) and not _is_digit(right[j])
        ):
            a = _order(left[i]) if i < len(left) else 0
            b = _order(right[j]) if j < len(right) else 0
            if a != b:
                return -1 if a < b else 1
            i += 1
            j += 1
        while i < len(left) and left[i] == "0":
            i += 1
        while j < len(right) and right[j] == "0":
            j += 1
        first_difference = 0
        while i < len(left) and _is_digit(left[i]) and j < len(right) and _is_digit(right[j]):
            if not first_difference:
                first_difference = ord(left[i]) - ord(right[j])
            i += 1
            j += 1
        if i < len(left) and _is_digit(left[i]):
            return 1
        if j < len(right) and _is_digit(right[j]):
            return -1
        if first_difference:
            return -1 if first_difference < 0 else 1
    return 0


def compare_versions(left: str, right: str) -> int:
    """Return -1, 0 or 1 like `dpkg --compare-versions` (left <, ==, > right)."""
    a, b = parse_version(left), parse_version(right)
    if a.epoch != b.epoch:
        return -1 if a.epoch < b.epoch else 1
    return _compare_part(a.upstream, b.upstream) or _compare_part(a.revision, b.revision)
# --- end Debian version helpers ----------------------------------------

_PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")
_ARCHITECTURE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SERVICE_NAME = re.compile(r"^[a-z0-9][a-z0-9@_.-]{0,63}$")


def validate_policy(policy):
    """Check the controller-supplied service policy without jsonschema.

    The full schema is validated by ``patch_agent.policies`` in CI; this guard
    only rejects shapes that would let an unconfigured service be restarted.
    """
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")
    if policy.get("restart_policy") != "configured-only":
        raise ValueError("restart policy must be configured-only")
    services = policy.get("services")
    packages = policy.get("packages")
    if not isinstance(services, dict) or not isinstance(packages, dict):
        raise ValueError("policy services and packages must be objects")
    for service in services:
        if not isinstance(service, str) or not _SERVICE_NAME.fullmatch(service):
            raise ValueError(f"invalid service name in policy: {service!r}")
    for package, entry in packages.items():
        listed = entry.get("services") if isinstance(entry, dict) else None
        if not isinstance(listed, list):
            raise ValueError(f"policy package {package} must list services")
        unknown = [service for service in listed if service not in services]
        if unknown:
            raise ValueError(
                f"package {package} references unconfigured services: {', '.join(map(str, unknown))}"
            )


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check(package, architecture, status, detail, data=None):
    return {
        "name": package,
        "architecture": architecture,
        "status": status,
        "detail": detail,
        "data": data or {},
    }


def _normalise_expectations(expectations):
    normalised = []
    seen = set()
    for item in expectations or []:
        if not isinstance(item, dict):
            raise ValueError("each verify expectation must be an object")
        name = item.get("name")
        architecture = item.get("architecture")
        expected_version = item.get("expected_version")
        if not isinstance(name, str) or not name:
            raise ValueError("verify expectation name must be a non-empty string")
        base, _, name_arch = name.partition(":")
        if not _PACKAGE_NAME.fullmatch(base):
            raise ValueError(f"invalid package name: {name!r}")
        if name_arch:
            if not _ARCHITECTURE.fullmatch(name_arch):
                raise ValueError(f"invalid architecture in {name!r}")
            if architecture and architecture != name_arch:
                raise ValueError(f"conflicting architectures for {name!r}")
            architecture = name_arch
        if architecture is not None and (
            not isinstance(architecture, str) or not _ARCHITECTURE.fullmatch(architecture)
        ):
            raise ValueError(f"invalid architecture for {name!r}")
        if not isinstance(expected_version, str) or not expected_version:
            raise ValueError(f"expected_version for {name!r} must be a non-empty string")
        try:
            parse_version(expected_version)
        except ValueError as exc:
            raise ValueError(f"invalid Debian version for {name!r}: {exc}") from exc
        key = f"{base}:{architecture}" if architecture else base
        if key in seen:
            raise ValueError(f"duplicate verify expectation for {key}")
        seen.add(key)
        normalised.append(
            {
                "name": base,
                "architecture": architecture,
                "expected_version": expected_version,
            }
        )
    return normalised


def parse_installed(text):
    """Parse fixed ``dpkg-query`` output into ``{name:arch: version}``."""
    installed = {}
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) != 3:
            continue
        binary, version, arch = (field.strip() for field in fields)
        if not binary or not version:
            continue
        name, _, explicit_arch = binary.partition(":")
        installed[f"{name}:{explicit_arch or arch or 'unknown'}"] = version
    return installed


def check_version(installed, name, architecture, expected_version):
    """Compare observed installed version against the approved version exactly."""
    if architecture:
        key = f"{name}:{architecture}"
        observed = installed.get(key)
    else:
        matches = [version for key, version in installed.items()
                   if key.partition(":")[0] == name]
        if len(matches) == 1:
            observed = matches[0]
        elif len(matches) > 1:
            observed = None  # ambiguous: specify architecture
        else:
            observed = None
    if observed is None:
        return _check(name, architecture, "error",
                      "Installed version could not be observed",
                      {"expected_version": expected_version, "observed_version": None})
    if compare_versions(observed, expected_version) == 0:
        return _check(name, architecture, "pass",
                      f"Observed version {observed} matches the approved version",
                      {"expected_version": expected_version, "observed_version": observed})
    return _check(name, architecture, "fail",
                  f"Observed version {observed} does not match approved {expected_version}",
                  {"expected_version": expected_version, "observed_version": observed})


def check_tcp_health(service, host, port, timeout_seconds):
    """Probe a TCP port without starting or restarting any service."""
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return {"service": service, "check": "tcp", "host": host, "port": port,
                    "status": "pass", "detail": f"tcp://{host}:{port} is reachable"}
    except OSError as exc:
        return {"service": service, "check": "tcp", "host": host, "port": port,
                "status": "fail", "detail": f"tcp://{host}:{port} unreachable: {type(exc).__name__}"}


def check_systemd_health(service, unit, deployment_unblocked, check_mode=True):
    """Query systemd unit status without starting or restarting anything."""
    if not deployment_unblocked or check_mode:
        return {"service": service, "check": "systemd", "unit": unit,
                "status": "skipped", "detail": "live health probes are blocked until deployment is unblocked"}
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
    except subprocess.TimeoutExpired:
        return {"service": service, "check": "systemd", "unit": unit,
                "status": "error", "detail": f"systemctl is-active {unit} timed out"}
    except OSError as exc:
        return {"service": service, "check": "systemd", "unit": unit,
                "status": "error", "detail": type(exc).__name__}
    status = "pass" if result.returncode == 0 else "fail"
    return {"service": service, "check": "systemd", "unit": unit,
            "status": status, "detail": f"systemd unit {unit} is {result.stdout.strip() or 'inactive'}"}


def check_http_health(service, url, expect_status, timeout_seconds):
    """Probe an HTTP endpoint without starting or restarting anything."""
    try:
        import urllib.request
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            actual = response.getcode()
        ok = actual == expect_status
        return {"service": service, "check": "http", "url": url,
                "status": "pass" if ok else "fail",
                "detail": f"HTTP {url} returned {actual}, expected {expect_status}"}
    except Exception as exc:  # noqa: BLE001 - report probe failure
        return {"service": service, "check": "http", "url": url,
                "status": "fail", "detail": f"HTTP {url} probe failed: {type(exc).__name__}"}


def run_health_checks(service, service_policy, deployment_unblocked, check_mode=True):
    """Run all configured health checks for a service."""
    checks = []
    for check in service_policy.get("health_checks", []):
        check_type = check.get("type")
        if check_type == "tcp":
            checks.append(check_tcp_health(
                service, check["host"], check["port"], check["timeout_seconds"]))
        elif check_type == "systemd":
            checks.append(check_systemd_health(
                service, check["unit"], deployment_unblocked, check_mode))
        elif check_type == "http":
            checks.append(check_http_health(
                service, check["url"], check["expect_status"], check["timeout_seconds"]))
        else:
            checks.append({"service": service, "check": check_type or "unknown",
                           "status": "error", "detail": f"unknown health check type: {check_type}"})
    return checks


def validate_verify_scope(expectations, installed, policy, deployment_unblocked, check_mode=True):
    """Validate versions and health checks without changing anything."""
    results = []
    for expectation in expectations:
        name = expectation["name"]
        architecture = expectation["architecture"]
        expected_version = expectation["expected_version"]

        version_check = check_version(installed, name, architecture, expected_version)
        services = policy.get("packages", {}).get(name, {}).get("services", [])
        health_results = []
        for service in services:
            service_policy = policy.get("services", {}).get(service, {})
            health_results.extend(run_health_checks(
                service, service_policy, deployment_unblocked, check_mode))

        overall = "pass" if version_check["status"] == "pass" and all(
            h["status"] in ("pass", "skipped") for h in health_results) else "fail"
        if version_check["status"] == "error":
            overall = "error"

        results.append({
            "name": name,
            "architecture": architecture,
            "status": overall,
            "detail": version_check["detail"],
            "expected_version": expected_version,
            "observed_version": version_check["data"].get("observed_version"),
            "version_check": version_check,
            "health_checks": health_results,
        })
    return results


def host_result(package_results, collected_at=None):
    packages = {}
    summary = {"total": 0, "passed": 0, "failed": 0, "error": 0}
    for result in package_results:
        packages[result["name"]] = result
        summary["total"] += 1
        status = result["status"]
        if status == "pass":
            summary["passed"] += 1
        elif status == "error":
            summary["error"] += 1
        else:
            summary["failed"] += 1
    return {
        "status": "failed" if summary["failed"] or summary["error"]
        else ("passed" if summary["total"] else "empty"),
        "collected_at": collected_at or _timestamp(),
        "packages": packages,
        "summary": summary,
        "error": None,
    }


def error_result(message, collected_at=None):
    return {
        "status": "error",
        "collected_at": collected_at or _timestamp(),
        "packages": {},
        "summary": {"total": 0, "passed": 0, "failed": 0, "error": 0},
        "error": {"code": "verify_error", "message": message},
    }


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "target": {"type": "str", "required": True},
            "expectations": {"type": "list", "elements": "dict", "default": []},
            "policy": {"type": "dict", "required": True},
            "deployment_unblocked": {"type": "bool", "default": False},
        },
        supports_check_mode=True,
    )
    collected_at = _timestamp()
    try:
        policy = module.params["policy"]
        validate_policy(policy)
        expectations = _normalise_expectations(module.params["expectations"])
        installed_text = subprocess.run(
            ["dpkg-query", "-W", "-f", "${binary:Package}\\t${Version}\\t${Architecture}\\n"],
            capture_output=True, text=True, check=True,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        ).stdout
        installed = parse_installed(installed_text)

        results = validate_verify_scope(
            expectations, installed, policy,
            module.params["deployment_unblocked"], module.check_mode,
        )
        module.exit_json(changed=False, **host_result(results, collected_at))
    except Exception as exc:  # noqa: BLE001 - never leak credentials
        module.exit_json(changed=False, **error_result(f"Verify failed ({type(exc).__name__})", collected_at))


if __name__ == "__main__":
    main()
