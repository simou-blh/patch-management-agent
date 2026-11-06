"""Fixed read-only inspection module for evidence-contract v1 host records.

This module is loaded by ``playbooks/inspect.yml``. It runs only two read-only
commands on the target (``dpkg-query`` and ``apt-cache policy``) and returns one
host record shaped like ``schemas/evidence.schema.json``.

The parsing helpers are deliberately importable without Ansible so they can be
unit-tested on any platform. They do not compare or order versions: assessment
must use Debian version semantics (``patch_agent.debversion``).
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import re
import subprocess

DPKG_FORMAT = (
    "${binary:Package}\t${Version}\t${source:Package}\t"
    "${source:Version}\t${Architecture}\t${db:Status-Abbrev}\n"
)

# " *** 1.0-1 100" / "     1.0-2 500"
_VERSION_LINE = re.compile(r"^\s+(?:\*\*\*\s+)?(\S+)\s+(-?\d+)\s*$")
# "        500 https://deb.debian.org/debian bookworm/main amd64 Packages"
_ORIGIN_LINE = re.compile(r"^\s+(-?\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+Packages\s*$")
# "bash:" / "libc6:amd64:"
_POLICY_HEADER = re.compile(r"^(\S+):\s*$")


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _source(name, version):
    if name and version:
        return {"name": name, "version": version}
    return None


def parse_dpkg_query(text):
    """Parse fixed ``dpkg-query`` output into installed package records.

    Only packages whose current dpkg state is ``installed`` are kept. Keys are
    architecture-qualified (``curl:amd64``) to keep multiarch packages separate.
    """
    packages = {}
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) != 6:
            continue
        binary, version, source_name, source_version, arch, status = fields
        status = status.strip()
        if len(status) < 2 or status[1] != "i":
            continue
        if not binary or not version:
            continue
        if ":" in binary:
            name, _, explicit_arch = binary.partition(":")
            arch = explicit_arch or arch
        else:
            name = binary
        packages[f"{name}:{arch or 'all'}"] = {
            "installed": version,
            "source": _source(source_name, source_version),
            "candidates": [],
        }
    return packages


def _normalize_uri(uri):
    # apt-cache policy prints local repositories as file:/path; the contract
    # requires a file:// URI.
    if uri.startswith("file:/") and not uri.startswith("file://"):
        return "file://" + uri[len("file:"):]
    return uri


def _origin(uri, suite_component):
    if "/" not in suite_component:
        return None
    suite, _, component = suite_component.partition("/")
    if not suite or not component:
        return None
    uri = _normalize_uri(uri)
    if not uri.startswith(("http://", "https://", "file://")):
        return None
    return {"uri": uri, "suite": suite, "component": component}


def parse_apt_policy(text):
    """Parse ``apt-cache policy`` output.

    Returns ``{binary_name: {version: [origin, ...]}}``. Each internal origin
    carries an ``_arch`` field used only to filter candidates per package; it is
    removed before the record is returned. Versions with no supported origin are
    dropped because evidence-contract v1 requires at least one origin.
    """
    result = {}
    current = None
    in_table = False
    version = None
    versions = None
    for line in text.splitlines():
        header = _POLICY_HEADER.match(line)
        if header:
            current = header.group(1).split(":")[0]
            versions = {}
            result[current] = versions
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
            versions.setdefault(version, [])
            continue
        match = _ORIGIN_LINE.match(line)
        if match and version is not None:
            _, uri, suite_component, arch = match.groups()
            origin = _origin(uri, suite_component)
            if origin is not None:
                origin["_arch"] = arch
                versions[version].append(origin)
    return result


def _candidates(versions, arch):
    candidates = []
    for version, origins in versions.items():
        filtered = []
        seen = set()
        for origin in origins:
            origin_arch = origin.get("_arch")
            if arch and arch != "all" and origin_arch not in (arch, "all"):
                continue
            key = (origin["uri"], origin["suite"], origin["component"])
            if key in seen:
                continue
            seen.add(key)
            filtered.append(
                {"uri": origin["uri"], "suite": origin["suite"], "component": origin["component"]}
            )
        if not filtered:
            continue
        filtered.sort(key=lambda item: (item["uri"], item["suite"], item["component"]))
        candidates.append({"version": version, "source": None, "origins": filtered})
    # Deterministic string order only; assessment uses Debian version ordering.
    candidates.sort(key=lambda item: item["version"])
    return candidates


def apply_policy(packages, policy_text):
    """Attach available candidates to parsed installed packages in place."""
    policy = parse_apt_policy(policy_text)
    for key, package in packages.items():
        name, _, arch = key.partition(":")
        package["candidates"] = _candidates(policy.get(name, {}), arch)
    return packages


def collect(installed_text, policy_text):
    """Build the package map for one host from fixed command output."""
    return apply_policy(parse_dpkg_query(installed_text), policy_text)


def host_record(installed_text, policy_text, collected_at=None):
    return {
        "status": "ok",
        "collected_at": collected_at or _timestamp(),
        "packages": collect(installed_text, policy_text),
        "error": None,
    }


def error_record(code, message, collected_at=None):
    return {
        "status": "error",
        "collected_at": collected_at or _timestamp(),
        "packages": {},
        "error": {"code": code, "message": message},
    }


def _run(command, timeout=120):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
        env={**os.environ, "LC_ALL": "C", "LANG": "C"},
    ).stdout


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    try:
        installed_text = _run(["dpkg-query", "-W", "-f", DPKG_FORMAT])
        packages = parse_dpkg_query(installed_text)
        if not packages:
            record = error_record("inspection_empty", "No installed packages were observed")
        else:
            names = sorted({key.partition(":")[0] for key in packages})
            policy_text = _run(["apt-cache", "policy", *names])
            apply_policy(packages, policy_text)
            record = {
                "status": "ok",
                "collected_at": _timestamp(),
                "packages": packages,
                "error": None,
            }
    except subprocess.TimeoutExpired:
        record = error_record("inspection_timeout", "Package inspection timed out")
    except subprocess.CalledProcessError:
        record = error_record(
            "inspection_command_failed", "Package inspection command failed"
        )
    except Exception as exc:  # noqa: BLE001 - never leak raw command output/credentials
        record = error_record(
            "inspection_error", f"Package inspection failed ({type(exc).__name__})"
        )
    module.exit_json(changed=False, **record)


if __name__ == "__main__":
    main()
