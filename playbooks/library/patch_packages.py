"""Exact-version patching module for the canary host.

Loaded by ``playbooks/patch.yml``. It enforces the approved scope: only the
approved package at the approved version, only configured service restarts, and
never kernel/major upgrades. It runs in read-only simulate mode by default; the
apply path is gated behind ``deployment_unblocked`` and cannot be reached while
deployment stays blocked.

The helpers are importable without Ansible so they can be unit-tested on any
platform. They do not start services or change package state unless the
operator has unblocked live execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import re
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

KERNEL_PREFIXES = ("linux-", "kernel")

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
    """Validate and normalise approved patch expectations."""
    normalised = []
    seen = set()
    for item in expectations or []:
        if not isinstance(item, dict):
            raise ValueError("each patch expectation must be an object")
        name = item.get("name")
        action = item.get("action")
        architecture = item.get("architecture")
        expected_installed = item.get("expected_installed")
        target_version = item.get("target_version")
        if not isinstance(name, str) or not name:
            raise ValueError("patch expectation name must be a non-empty string")
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
        if action not in ("patch", "defer"):
            raise ValueError(f"action must be 'patch' or 'defer' for {name!r}")
        if action == "defer":
            if target_version is not None:
                raise ValueError(f"deferred package {name!r} must have a null target version")
            key = f"{base}:{architecture}" if architecture else base
            if key in seen:
                raise ValueError(f"duplicate patch expectation for {key}")
            seen.add(key)
            normalised.append(
                {
                    "name": base,
                    "architecture": architecture,
                    "action": "defer",
                    "expected_installed": None,
                    "target_version": None,
                }
            )
            continue
        for label, value in (("expected_installed", expected_installed), ("target_version", target_version)):
            if not isinstance(value, str) or not value or any(char.isspace() for char in value):
                raise ValueError(f"{label} for {name!r} must be a non-empty version string")
        try:
            parse_version(expected_installed)
            parse_version(target_version)
        except ValueError as exc:
            raise ValueError(f"invalid Debian version for {name!r}: {exc}") from exc
        if base.startswith(KERNEL_PREFIXES):
            raise ValueError(f"kernel package {name!r} is deferred in the MVP")
        key = f"{base}:{architecture}" if architecture else base
        if key in seen:
            raise ValueError(f"duplicate patch expectation for {key}")
        seen.add(key)
        normalised.append(
            {
                "name": base,
                "architecture": architecture,
                "action": "patch",
                "expected_installed": expected_installed,
                "target_version": target_version,
            }
        )
    return normalised


def _installed_version(installed, name, architecture):
    if architecture:
        return installed.get(f"{name}:{architecture}")
    matches = [version for key, version in installed.items()
               if key.partition(":")[0] == name]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return None  # ambiguous: caller must specify architecture
    return None


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


def _service_allowed(policy, package_name, service_name):
    entry = policy.get("packages", {}).get(package_name)
    if entry is None:
        return False
    return service_name in entry.get("services", [])


def validate_patch_scope(expectations, installed, candidates, policy):
    """Return per-package validation results without changing anything.

    ``candidates`` is ``{package_name: {version: {architecture, ...}}}`` from
    ``parse_policy_versions`` (preflight module) or the inspect evidence.
    """
    results = []
    for expectation in expectations:
        name = expectation["name"]
        architecture = expectation["architecture"]
        action = expectation["action"]
        if action == "defer":
            observed = _installed_version(installed, name, architecture)
            results.append(_check(
                name, architecture, "deferred",
                "Approved deferral; no package change will be made.",
                {"observed_installed": observed, "target_version": None, "service_restart": None},
            ))
            continue

        expected = expectation["expected_installed"]
        target = expectation["target_version"]
        observed = _installed_version(installed, name, architecture)

        if observed is None:
            results.append(_check(
                name, architecture, "failed",
                "Installed version could not be determined; aborting this package.",
                {"expected_installed": expected, "target_version": target,
                 "service_restart": None, "error": {"code": "installed_unknown", "message": "installed version not found"}},
            ))
            continue
        if observed != expected:
            results.append(_check(
                name, architecture, "failed",
                "Installed version differs from the approved expected version.",
                {"expected_installed": expected, "target_version": target,
                 "observed_installed": observed, "service_restart": None,
                 "error": {"code": "drift_detected", "message": f"installed {observed} != expected {expected}"}},
            ))
            continue
        available = candidates.get(name, {})
        if target not in available:
            results.append(_check(
                name, architecture, "failed",
                "Approved target version is not available in repository candidates.",
                {"expected_installed": expected, "target_version": target,
                 "observed_installed": observed, "service_restart": None,
                 "error": {"code": "version_unavailable", "message": f"target {target} not in candidates"}},
            ))
            continue

        services = policy.get("packages", {}).get(name, {}).get("services", [])
        restarts = []
        for service in services:
            if not _SERVICE_NAME.fullmatch(service):
                restarts.append({"service": service, "allowed": False,
                                 "detail": "service name does not match policy allowlist"})
                continue
            if _service_allowed(policy, name, service):
                restarts.append({"service": service, "allowed": True, "detail": "configured restart permitted"})
            else:
                restarts.append({"service": service, "allowed": False,
                                 "detail": "service not configured for this package"})

        results.append(_check(
            name, architecture, "validated",
            "Exact-version change is within the approved scope.",
            {"expected_installed": expected, "target_version": target,
             "observed_installed": observed, "service_restart": restarts,
             "error": None},
        ))
    return results


def apply_patch(name, architecture, target_version, services, deployment_unblocked, check_mode=True):
    """Install ``target_version`` for ``name`` only when unblocked and not in check mode.

    Returns ``(changed, installed_after, error)``.
    """
    if not deployment_unblocked:
        return False, None, {"code": "deployment_blocked", "message": "live execution is blocked by the foundation gate"}
    if check_mode:
        return False, None, None

    package_spec = f"{name}:{architecture}={target_version}" if architecture else f"{name}={target_version}"
    command = ["apt-get", "install", "--no-install-recommends", "-y", package_spec]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=300,
            env={**os.environ, "LC_ALL": "C", "LANG": "C", "DEBIAN_FRONTEND": "noninteractive"},
        )
    except subprocess.TimeoutExpired:
        return False, None, {"code": "patch_timeout", "message": f"apt install timed out for {name}={target_version}"}
    except OSError as exc:
        return False, None, {"code": "patch_command_failed", "message": type(exc).__name__}

    if result.returncode != 0:
        return False, None, {"code": "apt_install_failed",
                             "message": f"apt install {package_spec} exited {result.returncode}"}

    dpkg_format = "${binary:Package}\t${Version}\t${Architecture}\n"
    try:
        output = subprocess.run(
            ["dpkg-query", "-W", "-f", dpkg_format],
            capture_output=True, text=True, check=True,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        ).stdout
    except subprocess.CalledProcessError as exc:
        return True, None, {"code": "post_patch_query_failed", "message": type(exc).__name__}

    installed_after = _installed_version(parse_installed(output), name, architecture)
    return True, installed_after, None


def restart_service(service, deployment_unblocked, check_mode=True):
    """Restart ``service`` only when unblocked and not in check mode.

    Returns ``(restarted, error)``.
    """
    if not _SERVICE_NAME.fullmatch(service):
        return False, {"code": "invalid_service", "message": f"service name not allowed: {service}"}
    if not deployment_unblocked or check_mode:
        return False, None
    try:
        result = subprocess.run(
            ["systemctl", "restart", service],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
    except subprocess.TimeoutExpired:
        return False, {"code": "restart_timeout", "message": f"restart of {service} timed out"}
    except OSError as exc:
        return False, {"code": "restart_command_failed", "message": type(exc).__name__}
    if result.returncode != 0:
        return False, {"code": "restart_failed", "message": f"systemctl restart {service} exited {result.returncode}"}
    return True, None


def _package_record(entry, expectation, status, detail, installed_after, restarts, error):
    """Build one package record that matches ``schemas/patch.schema.json``."""
    data = entry["data"]
    return {
        "name": entry["name"],
        "architecture": entry["architecture"],
        "status": status,
        "detail": detail,
        "installed_before": data.get("observed_installed"),
        "installed_after": installed_after,
        "target_version": expectation["target_version"],
        "action": expectation["action"],
        "service_restart": restarts,
        "error": error,
    }


def execute_patch(validation, expectations, deployment_unblocked, check_mode=True):
    """Apply validated packages, then restart allowed services only after a change.

    Deferred and failed validations are reported unchanged. Nothing is installed
    or restarted unless deployment is unblocked and Ansible is not in check mode.
    """
    by_key = {(e["name"], e["architecture"]): e for e in expectations}
    results = []
    for entry in validation:
        expectation = by_key[(entry["name"], entry["architecture"])]
        observed = entry["data"].get("observed_installed")
        if entry["status"] in ("deferred", "failed"):
            results.append(_package_record(
                entry, expectation, entry["status"], entry["detail"], observed, [],
                entry["data"].get("error"),
            ))
            continue

        changed, installed_after, apply_error = apply_patch(
            entry["name"], entry["architecture"], expectation["target_version"], None,
            deployment_unblocked, check_mode,
        )
        if apply_error:
            results.append(_package_record(
                entry, expectation, "failed", f"Patch apply failed: {apply_error['message']}",
                installed_after if changed else observed, [], apply_error,
            ))
            continue
        if not changed:
            results.append(_package_record(
                entry, expectation, "skipped", "Check mode: no package change was made.",
                observed, [], None,
            ))
            continue
        if installed_after != expectation["target_version"]:
            error = {"code": "target_not_installed",
                     "message": f"installed {installed_after} != target {expectation['target_version']}"}
            results.append(_package_record(
                entry, expectation, "failed", "Package did not reach the approved version.",
                installed_after, [], error,
            ))
            continue

        restarts = []
        for restart in entry["data"].get("service_restart") or []:
            if not restart.get("allowed"):
                continue
            ok, err = restart_service(restart["service"], deployment_unblocked, check_mode)
            restarts.append({"service": restart["service"], "restarted": ok, "error": err})
        failed_restart = next((r["error"] for r in restarts if r["error"]), None)
        results.append(_package_record(
            entry, expectation, "failed" if failed_restart else "applied",
            "Service restart failed after patching." if failed_restart
            else f"Installed approved version {installed_after}.",
            installed_after, restarts, failed_restart,
        ))
    return results


def host_result(package_results, collected_at=None):
    """Aggregate per-package results into a host patch result."""
    packages = {}
    summary = {"total": 0, "applied": 0, "skipped": 0, "deferred": 0, "failed": 0}
    for result in package_results:
        name = result["name"]
        packages[name] = result
        summary["total"] += 1
        status = result["status"]
        if status == "applied":
            summary["applied"] += 1
        elif status == "skipped":
            summary["skipped"] += 1
        elif status == "deferred":
            summary["deferred"] += 1
        else:
            summary["failed"] += 1
    return {
        "status": "failed" if summary["failed"] else ("completed" if summary["total"] else "empty"),
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
        "summary": {"total": 0, "applied": 0, "skipped": 0, "deferred": 0, "failed": 0},
        "error": {"code": "patch_error", "message": message},
    }


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "target": {"type": "str", "required": True},
            "expectations": {"type": "list", "elements": "dict", "default": []},
            "candidates": {"type": "dict", "default": {}},
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

        validation = validate_patch_scope(expectations, installed, module.params["candidates"], policy)
        results = execute_patch(validation, expectations,
                                module.params["deployment_unblocked"], module.check_mode)

        module.exit_json(changed=False, **host_result(results, collected_at))
    except Exception as exc:  # noqa: BLE001 - never leak credentials
        module.exit_json(changed=False, **error_result(f"Patch failed ({type(exc).__name__})", collected_at))


if __name__ == "__main__":
    main()
