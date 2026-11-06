"""Recovery module for failed patch targets.

Loaded by ``playbooks/recover.yml``. It captures diagnostics, attempts bounded
APT repair and previous-package/config restoration (simulated first and refused
if APT would remove anything), in read-only mode by default, and reports whether manual intervention is required. The apply path
is gated behind ``deployment_unblocked`` and cannot be reached while deployment
stays blocked.

The helpers are importable without Ansible so they can be unit-tested on any
platform.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import re
import subprocess

_PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")
_ARCHITECTURE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalise_previous_packages(previous_packages):
    normalised = []
    seen = set()
    for item in previous_packages or []:
        if not isinstance(item, dict):
            raise ValueError("each previous package entry must be an object")
        name = item.get("name")
        version = item.get("previous_version")
        architecture = item.get("architecture")
        if not isinstance(name, str) or not name:
            raise ValueError("previous package name must be a non-empty string")
        if not _PACKAGE_NAME.fullmatch(name):
            raise ValueError(f"invalid package name: {name!r}")
        if not isinstance(version, str) or not version:
            raise ValueError(f"previous_version for {name!r} must be a non-empty string")
        if architecture is not None and (
            not isinstance(architecture, str) or not _ARCHITECTURE.fullmatch(architecture)
        ):
            raise ValueError(f"invalid architecture for {name!r}")
        key = f"{name}:{architecture}" if architecture else name
        if key in seen:
            raise ValueError(f"duplicate previous package entry for {key}")
        seen.add(key)
        normalised.append(
            {"name": name, "previous_version": version, "architecture": architecture}
        )
    return normalised


def _normalise_config_paths(config_paths):
    normalised = []
    seen = set()
    for path in config_paths or []:
        if not isinstance(path, str) or not path:
            raise ValueError("config path must be a non-empty string")
        if not path.startswith("/") or ".." in path.split("/"):
            raise ValueError(f"config path must be absolute without '..': {path!r}")
        if path in seen:
            raise ValueError(f"duplicate config path: {path!r}")
        seen.add(path)
        normalised.append(path)
    return normalised


def capture_diagnostics():
    """Read-only diagnostics: dpkg --audit, apt-cache policy, service status."""
    diagnostics = {"dpkg_audit": None, "apt_policy": None, "service_status": None}

    try:
        result = subprocess.run(
            ["dpkg", "--audit"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
        diagnostics["dpkg_audit"] = {
            "returncode": result.returncode,
            "output": result.stdout[:4000],
            "issues": len([line for line in result.stdout.splitlines() if line.strip()]),
        }
    except subprocess.TimeoutExpired:
        diagnostics["dpkg_audit"] = {
            "returncode": -1, "output": "", "issues": 0,
            "error": "dpkg --audit timed out",
        }
    except OSError as exc:
        diagnostics["dpkg_audit"] = {
            "returncode": -1, "output": "", "issues": 0,
            "error": type(exc).__name__,
        }

    try:
        result = subprocess.run(
            ["apt-cache", "policy"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
        diagnostics["apt_policy"] = {
            "returncode": result.returncode,
            "output": result.stdout[:4000],
        }
    except subprocess.TimeoutExpired:
        diagnostics["apt_policy"] = {
            "returncode": -1, "output": "",
            "error": "apt-cache policy timed out",
        }
    except OSError as exc:
        diagnostics["apt_policy"] = {
            "returncode": -1, "output": "",
            "error": type(exc).__name__,
        }

    try:
        result = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--state=failed"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
        diagnostics["service_status"] = {
            "returncode": result.returncode,
            "output": result.stdout[:4000],
        }
    except subprocess.TimeoutExpired:
        diagnostics["service_status"] = {
            "returncode": -1, "output": "",
            "error": "systemctl list-units timed out",
        }
    except OSError as exc:
        diagnostics["service_status"] = {
            "returncode": -1, "output": "",
            "error": type(exc).__name__,
        }

    return diagnostics


_APT_ENV = {"LC_ALL": "C", "LANG": "C", "DEBIAN_FRONTEND": "noninteractive"}
_KEEP_CONFIG = ["-o", "Dpkg::Options::=--force-confold"]


def _apt(args, timeout=300):
    return subprocess.run(
        ["apt-get", *args], capture_output=True, text=True, timeout=timeout,
        env={**os.environ, **_APT_ENV},
    )


def planned_removals(simulation_output):
    """Return package names that an ``apt-get -s`` run would remove."""
    removals = []
    for line in simulation_output.splitlines():
        if line.startswith("Remv "):
            fields = line.split()
            if len(fields) > 1:
                removals.append(fields[1])
    return removals


def _bounded_apt(args):
    """Simulate ``apt-get args``; run it for real only if nothing is removed.

    Returns ``(attempted, result, detail)``.
    """
    try:
        simulation = _apt([*args, "-s"])
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, "failed", f"APT simulation failed: {type(exc).__name__}"
    if simulation.returncode != 0:
        return False, "failed", f"APT simulation exited {simulation.returncode}: {simulation.stderr[-500:]}"
    removals = planned_removals(simulation.stdout)
    if removals:
        return False, "failed", "refused: would remove " + ", ".join(removals[:20])
    try:
        result = _apt([*args, "-y", *_KEEP_CONFIG])
    except subprocess.TimeoutExpired:
        return True, "failed", "APT command timed out"
    except OSError as exc:
        return True, "failed", type(exc).__name__
    if result.returncode != 0:
        return True, "failed", f"APT exited {result.returncode}: {result.stderr[-500:]}"
    return True, "succeeded", result.stdout[-2000:] or "APT completed"


def _installed(name, architecture):
    package = f"{name}:{architecture}" if architecture else name
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f", "${Version}", package],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def bounded_apt_repair(deployment_unblocked, check_mode=True):
    """Repair interrupted/broken dpkg state with ``apt-get install -f``.

    Bounded: the repair is simulated first and refused if it would remove any
    package, so it can only finish configuring or install missing dependencies.
    """
    if not deployment_unblocked or check_mode:
        return {"attempted": False, "command": "apt-get install -f -s",
                "dry_run": True, "result": "not_attempted",
                "detail": "live repair is blocked until deployment is unblocked"}
    attempted, result, detail = _bounded_apt(["install", "-f"])
    return {"attempted": attempted, "command": "apt-get install -f -y",
            "dry_run": False, "result": result, "detail": detail}


def restore_previous_package(name, previous_version, architecture, deployment_unblocked, check_mode=True):
    """Downgrade to the approved previous version and verify it is installed."""
    base = f"{name}:{architecture}" if architecture else name
    package_spec = f"{base}={previous_version}"

    def record(attempted, result, detail):
        return {"name": name, "previous_version": previous_version,
                "architecture": architecture, "attempted": attempted,
                "result": result, "detail": detail}

    if not deployment_unblocked or check_mode:
        return record(False, "not_attempted",
                      "live restoration is blocked until deployment is unblocked")
    attempted, result, detail = _bounded_apt(
        ["install", "--no-install-recommends", "--allow-downgrades", package_spec])
    if result != "succeeded":
        return record(attempted, result, detail)
    observed = _installed(name, architecture)
    if observed != previous_version:
        return record(True, "failed", f"after restore {base} is {observed}, expected {previous_version}")
    return record(True, "succeeded", f"{base} restored to {previous_version}")


def restore_config_backup(config_path, backup_path, deployment_unblocked, check_mode=True):
    """Restore a backed-up configuration file and confirm the bytes match."""
    if not deployment_unblocked or check_mode:
        return {"path": config_path, "attempted": False,
                "result": "not_attempted",
                "detail": "live restoration is blocked until deployment is unblocked"}
    if not backup_path or not os.path.isfile(backup_path):
        return {"path": config_path, "attempted": False, "result": "failed",
                "detail": "no configuration backup is available"}
    import filecmp
    import shutil
    try:
        shutil.copy2(backup_path, config_path)
        if not filecmp.cmp(backup_path, config_path, shallow=False):
            raise OSError("restored file differs from backup")
    except OSError as exc:
        return {"path": config_path, "attempted": True,
                "result": "failed", "detail": f"{type(exc).__name__}: {exc}"[:500]}
    return {"path": config_path, "attempted": True, "result": "succeeded",
            "detail": f"restored {config_path} from {backup_path}"}


def host_result(diagnostics, repair, previous_restorations, config_restorations,
                manual_intervention, collected_at=None):
    recovery_status = "manual_required" if manual_intervention else (
        "failed" if (repair["result"] == "failed" or
                     any(r["result"] == "failed" for r in previous_restorations) or
                     any(r["result"] == "failed" for r in config_restorations))
        else "succeeded"
    )
    return {
        "status": recovery_status,
        "collected_at": collected_at or _timestamp(),
        "diagnostics": diagnostics,
        "repair": repair,
        "restoration": {
            "previous_packages": previous_restorations,
            "config_backups": config_restorations,
        },
        "manual_intervention": manual_intervention,
        "error": None,
    }


def error_result(message, collected_at=None):
    return {
        "status": "error",
        "collected_at": collected_at or _timestamp(),
        "diagnostics": {"dpkg_audit": {}, "apt_policy": {}, "service_status": {}},
        "repair": {"attempted": False, "command": "not run", "dry_run": True,
                   "result": "not_attempted", "detail": message},
        "restoration": {"previous_packages": [], "config_backups": []},
        "manual_intervention": True,
        "error": {"code": "recover_error", "message": message},
    }


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "target": {"type": "str", "required": True},
            "previous_packages": {"type": "list", "elements": "dict", "default": []},
            "config_paths": {"type": "list", "elements": "str", "default": []},
            "backup_root": {"type": "str", "default": None},
            "deployment_unblocked": {"type": "bool", "default": False},
        },
        supports_check_mode=True,
    )
    collected_at = _timestamp()
    try:
        previous = _normalise_previous_packages(module.params["previous_packages"])
        config_paths = _normalise_config_paths(module.params["config_paths"])

        diagnostics = capture_diagnostics()
        repair = bounded_apt_repair(
            module.params["deployment_unblocked"], module.check_mode,
        )

        previous_restorations = []
        for entry in previous:
            previous_restorations.append(restore_previous_package(
                entry["name"], entry["previous_version"], entry["architecture"],
                module.params["deployment_unblocked"], module.check_mode,
            ))

        config_restorations = []
        backup_root = module.params["backup_root"]
        for config_path in config_paths:
            backup_path = None
            if backup_root:
                from pathlib import Path
                backup_path = str(Path(backup_root) / Path(*Path(config_path).parts[1:]))
            config_restorations.append(restore_config_backup(
                config_path, backup_path,
                module.params["deployment_unblocked"], module.check_mode,
            ))

        manual = (
            repair["result"] == "failed" or
            any(r["result"] == "failed" for r in previous_restorations) or
            any(r["result"] == "failed" for r in config_restorations) or
            diagnostics["dpkg_audit"] is not None and
            diagnostics["dpkg_audit"].get("issues", 0) > 0
        )

        # Report a change whenever a live APT run or file restore was attempted.
        changed = repair["attempted"] or any(
            r["attempted"] for r in previous_restorations + config_restorations)
        module.exit_json(changed=changed, **host_result(
            diagnostics, repair, previous_restorations, config_restorations,
            manual, collected_at,
        ))
    except Exception as exc:  # noqa: BLE001 - never leak credentials
        module.exit_json(changed=False, **error_result(
            f"Recovery failed ({type(exc).__name__})", collected_at))


if __name__ == "__main__":
    main()
