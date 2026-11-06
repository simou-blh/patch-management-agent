"""Fixed preflight checks and recovery preparation for one host.

Loaded by ``playbooks/preflight.yml``. It never changes package state: it reads
dpkg/apt state, probes APT lock files, optionally copies operator-listed
configuration paths into a backup root, and verifies operator-supplied recovery
artifacts.

The parsing and check helpers are importable without Ansible so they can be
unit-tested on any platform. They do not compare Debian versions; drift is an
exact comparison against the approved installed version.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess

DPKG_FORMAT = "${binary:Package}\t${Version}\t${Architecture}\n"

# "bash:" / "libc6:amd64:"
_POLICY_HEADER = re.compile(r"^(\S+):\s*$")
# " *** 5.2.15-2+b7 100" / "     5.2.15-2+b8 500"
_VERSION_LINE = re.compile(r"^\s+(?:\*\*\*\s+)?(\S+)\s+(-?\d+)\s*$")
# "        500 https://deb.debian.org/debian bookworm/main amd64 Packages"
_ORIGIN_LINE = re.compile(r"^\s+(-?\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+Packages\s*$")
_PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")
_ARCHITECTURE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_HOST_NAME = re.compile(r"^[a-z][a-z0-9-]{0,62}$")

REQUIRED_CHECKS = ("privileges", "disk", "apt_locks", "apt_health", "drift", "candidates")

DEFAULT_DISK_PATHS = ("/", "/var/cache/apt/archives")
DEFAULT_LOCK_PATHS = (
    "/var/lib/dpkg/lock-frontend",
    "/var/lib/dpkg/lock",
    "/var/lib/apt/lists/lock",
    "/var/cache/apt/archives/lock",
)


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check(check_id, status, detail, data=None):
    return {"id": check_id, "status": status, "detail": detail, "data": data or {}}


def _stamp(collected_at):
    value = collected_at.split(".")[0]
    return value.replace("-", "").replace(":", "")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_size(path, limit=None):
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        if item.is_symlink() or not item.is_file():
            continue
        total += item.stat().st_size
        if limit is not None and total > limit:
            return total
    return total


def check_privileges(euid):
    """Confirm the module runs with the privileges APT needs."""
    if euid == 0:
        return _check("privileges", "pass", "Running with root privileges")
    return _check(
        "privileges",
        "fail",
        "Root privileges are required for package-manager operations",
        {"euid": euid},
    )


def check_disk(paths, min_free_bytes, usage=None):
    """Confirm each configured path has at least ``min_free_bytes`` free."""
    usage = usage or shutil.disk_usage
    results = []
    for path in paths:
        try:
            total, _used, free = usage(path)
        except OSError as exc:
            results.append({"path": path, "status": "error", "detail": type(exc).__name__})
            continue
        ok = free >= min_free_bytes
        results.append(
            {
                "path": path,
                "status": "pass" if ok else "fail",
                "free_bytes": free,
                "total_bytes": total,
                "min_free_bytes": min_free_bytes,
            }
        )
    statuses = {result["status"] for result in results}
    if "fail" in statuses:
        status = "fail"
    elif "error" in statuses:
        status = "error"
    else:
        status = "pass"
    detail = f"Checked free space on {len(paths)} path(s) against {min_free_bytes} bytes"
    return _check("disk", status, detail, {"paths": results})


def _lock_held(path):
    """Return True when an APT/dpkg lock file is currently held."""
    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover - target hosts are Linux
        raise RuntimeError("fcntl is unavailable") from exc
    try:
        handle = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return False
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
        return False
    finally:
        os.close(handle)


def check_locks(paths, probe=None):
    """Confirm no APT/dpkg lock is held. ``probe`` is injectable for tests."""
    probe = probe or _lock_held
    results = []
    status = "pass"
    for path in paths:
        try:
            held = probe(path)
        except Exception as exc:  # noqa: BLE001 - report the lock probe failure
            results.append({"path": path, "status": "error", "detail": type(exc).__name__})
            if status != "fail":
                status = "error"
            continue
        if held:
            status = "fail"
            results.append({"path": path, "status": "fail", "detail": "lock is held"})
        else:
            results.append({"path": path, "status": "pass", "detail": "lock is free"})
    return _check("apt_locks", status, "Probed APT and dpkg lock files", {"locks": results})


def check_apt_health(audit_text, returncode):
    """Interpret ``dpkg --audit`` output without changing package state."""
    if returncode != 0:
        return _check(
            "apt_health",
            "error",
            f"dpkg --audit exited with status {returncode}",
        )
    lines = [line.strip() for line in audit_text.splitlines() if line.strip()]
    if lines:
        preview = " | ".join(line[:160] for line in lines[:5])
        return _check(
            "apt_health",
            "fail",
            f"dpkg --audit reported {len(lines)} issue(s): {preview}",
            {"issues": len(lines)},
        )
    return _check("apt_health", "pass", "dpkg --audit reported no issues")


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


def normalize_expectations(expectations):
    normalized = []
    seen = set()
    for item in expectations or []:
        if not isinstance(item, dict):
            raise ValueError("each expectation must be an object")
        name = item.get("name")
        expected = item.get("expected_installed")
        target = item.get("target_version")
        architecture = item.get("architecture")
        if not isinstance(name, str) or not name:
            raise ValueError("expectation name must be a non-empty string")
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
        for label, value in (("expected_installed", expected), ("target_version", target)):
            if not isinstance(value, str) or not value or any(char.isspace() for char in value):
                raise ValueError(f"{label} for {name!r} must be a non-empty version string")
        key = f"{base}:{architecture}" if architecture else base
        if key in seen:
            raise ValueError(f"duplicate expectation for {key}")
        seen.add(key)
        normalized.append(
            {
                "name": base,
                "architecture": architecture,
                "expected_installed": expected,
                "target_version": target,
            }
        )
    return normalized


def check_drift(installed, expectations):
    """Compare observed installed versions with the approved versions exactly."""
    if not expectations:
        return _check("drift", "skipped", "No approved package expectations were supplied")
    results = []
    failed = False
    for expectation in expectations:
        base = expectation["name"]
        architecture = expectation["architecture"]
        if architecture:
            key = f"{base}:{architecture}"
            observed = installed.get(key)
            detail = (
                "installed version matches the approved version"
                if observed is not None
                else "package is not installed"
            )
        else:
            matches = [key for key in installed if key.partition(":")[0] == base]
            if len(matches) > 1:
                key = None
                observed = None
                detail = "multiple installed architectures; specify architecture"
            elif matches:
                key = matches[0]
                observed = installed[key]
                detail = "installed version matches the approved version"
            else:
                key = None
                observed = None
                detail = "package is not installed"
        expected = expectation["expected_installed"]
        if observed is None:
            failed = True
            status = "fail"
        elif observed != expected:
            failed = True
            status = "fail"
            detail = "installed version differs from the approved version"
        else:
            status = "pass"
        results.append(
            {
                "name": base,
                "architecture": architecture,
                "expected_installed": expected,
                "observed_installed": observed,
                "status": status,
                "detail": detail,
            }
        )
    return _check(
        "drift",
        "fail" if failed else "pass",
        "Compared installed versions with the approved versions",
        {"packages": results},
    )


def _usable_origin(uri, suite_component):
    if uri.startswith("file:/") and not uri.startswith("file://"):
        uri = "file://" + uri[len("file:"):]
    return uri.startswith(("http://", "https://", "file://")) and "/" in suite_component


def parse_policy_versions(text):
    """Return ``{package: {version: {architecture, ...}}}`` for usable origins."""
    available = {}
    current = None
    in_table = False
    version = None
    for line in text.splitlines():
        header = _POLICY_HEADER.match(line)
        if header:
            current = header.group(1).partition(":")[0]
            available.setdefault(current, {})
            in_table = False
            version = None
            continue
        if current is None:
            continue
        if line.strip() == "Version table:":
            in_table = True
            continue
        if not in_table:
            continue
        match = _VERSION_LINE.match(line)
        if match:
            version = match.group(1)
            continue
        match = _ORIGIN_LINE.match(line)
        if match and version is not None:
            _, uri, suite_component, arch = match.groups()
            if _usable_origin(uri, suite_component):
                available[current].setdefault(version, set()).add(arch)
    return available


def _version_available(versions, target, architecture):
    arches = versions.get(target)
    if arches is None:
        return False
    if not architecture or architecture == "all":
        return True
    return architecture in arches or "all" in arches


def check_candidates(available, expectations):
    """Confirm every approved target version is still offered for its architecture."""
    if not expectations:
        return _check("candidates", "skipped", "No approved package expectations were supplied")
    results = []
    failed = False
    for expectation in expectations:
        name = expectation["name"]
        target = expectation["target_version"]
        architecture = expectation["architecture"]
        versions = available.get(name, {})
        ok = _version_available(versions, target, architecture)
        if not ok:
            failed = True
        results.append(
            {
                "name": name,
                "architecture": architecture,
                "target_version": target,
                "status": "pass" if ok else "fail",
                "available_versions": sorted(versions),
            }
        )
    return _check(
        "candidates",
        "fail" if failed else "pass",
        "Checked approved target versions against repository candidates",
        {"packages": results},
    )


def _backup_not_attempted(detail):
    return {"status": "not_attempted", "detail": detail, "files": []}


def _backup_failed(detail, files=None):
    return {"status": "failed", "detail": detail, "files": files or []}


def _manifest(source, backup):
    return {
        "source": str(source),
        "backup": str(backup),
        "sha256": _sha256(backup),
        "size": backup.stat().st_size,
    }


def backup_configs(paths, backup_root, host, collected_at, max_bytes):
    """Copy operator-listed absolute paths into a fixed backup root."""
    if not backup_root or not paths:
        return _backup_not_attempted(
            "No backup root or configuration paths were supplied; backup is not verified"
        )
    if not _HOST_NAME.fullmatch(host or ""):
        return _backup_failed("Host name is invalid for a backup path")
    root = Path(backup_root)
    if not root.is_absolute() or root == Path("/"):
        return _backup_failed("Backup root must be an absolute directory other than /")
    destination = root / host / _stamp(collected_at)
    files = []
    errors = []
    total = 0
    for raw in paths:
        source = Path(raw)
        if not source.is_absolute() or ".." in source.parts or len(source.parts) < 2:
            errors.append(f"{raw}: path must be absolute, non-root and without '..'")
            continue
        if source.is_symlink():
            errors.append(f"{raw}: symlinks are not backed up")
            continue
        if not source.exists():
            errors.append(f"{raw}: not found")
            continue
        size = _tree_size(source, limit=max_bytes)
        total += size
        if total > max_bytes:
            errors.append(f"{raw}: backup exceeds max_backup_bytes")
            continue
        target = destination / Path(*source.parts[1:])
        try:
            if source.is_dir():
                shutil.copytree(source, target, symlinks=True, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        except OSError as exc:
            errors.append(f"{raw}: {type(exc).__name__}")
            continue
        if source.is_dir():
            for copied in sorted(target.rglob("*")):
                if copied.is_symlink() or not copied.is_file():
                    continue
                files.append(_manifest(source / copied.relative_to(target), copied))
        else:
            files.append(_manifest(source, target))
    if errors:
        return _backup_failed("; ".join(errors)[:1000], files)
    return {
        "status": "verified",
        "detail": f"Backed up {len(files)} file(s) to {destination}",
        "files": files,
    }


def _recovery_not_attempted(detail):
    return {"status": "not_attempted", "detail": detail, "artifacts": []}


def _recovery_failed(detail, artifacts=None):
    return {"status": "failed", "detail": detail, "artifacts": artifacts or []}


def check_recovery_artifacts(artifact_dir, artifacts):
    """Verify operator-supplied recovery artifacts without downloading anything."""
    if not artifact_dir or not artifacts:
        return _recovery_not_attempted(
            "No recovery artifact directory or artifacts were supplied; artifacts are not verified"
        )
    root = Path(artifact_dir)
    if not root.is_absolute():
        return _recovery_failed("Recovery artifact directory must be absolute")
    if not root.is_dir():
        return _recovery_failed("Recovery artifact directory was not found")
    resolved_root = root.resolve()
    records = []
    errors = []
    for spec in artifacts:
        name = spec.get("name") if isinstance(spec, dict) else None
        if (
            not isinstance(name, str)
            or not name
            or Path(name).is_absolute()
            or ".." in Path(name).parts
        ):
            errors.append("artifact name must be a relative path without '..'")
            continue
        path = (resolved_root / name).resolve()
        if not path.is_relative_to(resolved_root):
            errors.append(f"{name}: escapes the artifact directory")
            continue
        if not path.is_file():
            errors.append(f"{name}: not found")
            continue
        digest = _sha256(path)
        expected = spec.get("sha256")
        if expected and digest != str(expected).lower():
            errors.append(f"{name}: checksum mismatch")
            continue
        records.append({"name": name, "sha256": digest, "size": path.stat().st_size})
    if errors:
        return _recovery_failed("; ".join(errors)[:1000], records)
    return {
        "status": "verified",
        "detail": f"Verified {len(records)} recovery artifact(s)",
        "artifacts": records,
    }


def deb_filename_glob(name, version):
    """Glob for the file ``apt-get download`` writes (epoch colon becomes %3a)."""
    return f"{name}_{version.replace(':', '%3a')}_*.deb"


def cache_previous_packages(artifact_dir, expectations, run=None):
    """Download the currently installed (previous) version of each package.

    ``apt-get download`` only writes a .deb into ``artifact_dir``; it never
    changes installed package state. Returns ``(artifact_specs, errors)`` that
    ``check_recovery_artifacts`` then verifies.
    """
    run = run or _run
    root = Path(artifact_dir) if artifact_dir else None
    if root is None or not root.is_absolute() or root == Path("/"):
        return [], ["recovery artifact directory must be an absolute non-root path"]
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    specs, errors = [], []
    for expectation in expectations:
        name, version = expectation["name"], expectation["expected_installed"]
        architecture = expectation["architecture"]
        package = f"{name}:{architecture}" if architecture else name
        result = run(["apt-get", "download", f"{package}={version}"], cwd=str(root), timeout=300)
        matches = sorted(root.glob(deb_filename_glob(name, version)))
        if result.returncode != 0 or not matches:
            errors.append(f"{package}={version}: previous package could not be downloaded")
            continue
        specs.extend({"name": match.name} for match in matches)
    return specs, errors


def host_record(checks, backup, recovery_artifacts, collected_at=None):
    """Derive ``ready`` only when every required check and preparation passes."""
    blocking = []
    present = {check["id"] for check in checks}
    for required in REQUIRED_CHECKS:
        if required not in present:
            blocking.append(f"missing:{required}")
    for check in checks:
        if check["status"] != "pass":
            blocking.append(check["id"])
    if backup["status"] != "verified":
        blocking.append("backup")
    if recovery_artifacts["status"] != "verified":
        blocking.append("recovery_artifacts")
    return {
        "status": "ready" if not blocking else "not_ready",
        "collected_at": collected_at or _timestamp(),
        "checks": checks,
        "backup": backup,
        "recovery_artifacts": recovery_artifacts,
        "blocking": blocking,
        "error": None,
    }


def error_record(code, message, collected_at=None):
    return {
        "status": "error",
        "collected_at": collected_at or _timestamp(),
        "checks": [],
        "backup": _backup_not_attempted("Preflight did not run"),
        "recovery_artifacts": _recovery_not_attempted("Preflight did not run"),
        "blocking": [code],
        "error": {"code": code, "message": message},
    }


def _run(command, timeout=120, cwd=None):
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={**os.environ, "LC_ALL": "C", "LANG": "C"},
    )


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "host_name": {"type": "str", "required": True},
            "expectations": {"type": "list", "elements": "dict", "default": []},
            "disk_paths": {"type": "list", "elements": "str", "default": list(DEFAULT_DISK_PATHS)},
            "min_free_bytes": {"type": "int", "default": 512 * 1024 * 1024},
            "lock_paths": {"type": "list", "elements": "str", "default": list(DEFAULT_LOCK_PATHS)},
            "backup_root": {"type": "str", "default": None},
            "config_paths": {"type": "list", "elements": "str", "default": []},
            "max_backup_bytes": {"type": "int", "default": 64 * 1024 * 1024},
            "recovery_artifact_dir": {"type": "str", "default": None},
            "recovery_artifacts": {"type": "list", "elements": "dict", "default": []},
            "cache_previous": {"type": "bool", "default": False},
        },
        supports_check_mode=True,
    )
    collected_at = _timestamp()
    changed = False
    try:
        expectations = normalize_expectations(module.params["expectations"])
        checks = [
            check_privileges(os.geteuid()),
            check_disk(module.params["disk_paths"], module.params["min_free_bytes"]),
            check_locks(module.params["lock_paths"]),
        ]

        audit = _run(["dpkg", "--audit"])
        checks.append(check_apt_health(audit.stdout, audit.returncode))

        installed = parse_installed(_run(["dpkg-query", "-W", "-f", DPKG_FORMAT]).stdout)
        checks.append(check_drift(installed, expectations))

        names = sorted({expectation["name"] for expectation in expectations})
        policy = _run(["apt-cache", "policy", *names]) if names else None
        checks.append(
            check_candidates(parse_policy_versions(policy.stdout if policy else ""), expectations)
        )

        if module.check_mode:
            backup = _backup_not_attempted("Check mode does not write configuration backups")
        else:
            backup = backup_configs(
                module.params["config_paths"],
                module.params["backup_root"],
                module.params["host_name"],
                collected_at,
                module.params["max_backup_bytes"],
            )
            changed = bool(backup["files"])

        artifact_specs = list(module.params["recovery_artifacts"])
        cache_errors = []
        if module.params["cache_previous"] and expectations:
            if module.check_mode:
                cache_errors.append("Check mode does not download previous packages")
            else:
                cached, cache_errors = cache_previous_packages(
                    module.params["recovery_artifact_dir"], expectations
                )
                changed = changed or bool(cached)
                known = {spec.get("name") for spec in artifact_specs if isinstance(spec, dict)}
                artifact_specs.extend(spec for spec in cached if spec["name"] not in known)
        recovery_artifacts = check_recovery_artifacts(
            module.params["recovery_artifact_dir"], artifact_specs
        )
        if cache_errors:
            recovery_artifacts = _recovery_failed(
                "; ".join(cache_errors)[:1000], recovery_artifacts["artifacts"]
            )
        record = host_record(checks, backup, recovery_artifacts, collected_at)
    except Exception as exc:  # noqa: BLE001 - never leak raw command output or credentials
        record = error_record(
            "preflight_error", f"Preflight failed ({type(exc).__name__})", collected_at
        )
    module.exit_json(changed=changed, **record)


if __name__ == "__main__":
    main()
