"""Sequential fleet rollout coordinator for canary-then-fleet patching.

Loaded by ``playbooks/rollout.yml``. It decides, per host in sequence, whether
to proceed to the next host or stop and recover the failed host. Recovery only
ever touches the failed/modified host; later fleet hosts are never reached
after a failure.

The helpers are importable without Ansible so they can be unit-tested on any
platform. The module never installs, restarts, or changes anything itself.
"""

from __future__ import annotations

from datetime import datetime, timezone

_HOST_NAME = __import__("re").compile(r"^[a-z][a-z0-9-]{0,62}$")


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_rollout_scope(targets, canary):
    """Validate and order rollout targets: canary first, then remaining hosts.

    Returns the ordered target list. Raises ValueError for invalid scope.
    """
    if not isinstance(targets, list) or not targets:
        raise ValueError("rollout targets must be a non-empty list")
    if len(targets) != len(set(targets)):
        raise ValueError("rollout targets must be unique")
    for target in targets:
        if not isinstance(target, str) or not _HOST_NAME.fullmatch(target):
            raise ValueError(f"invalid rollout target: {target!r}")
    if canary not in targets:
        raise ValueError("canary must be one of the rollout targets")
    ordered = [canary] + [t for t in targets if t != canary]
    return ordered


def blocking_steps(preflight_status, patch_status, verify_status):
    """Return the stages that did not succeed, in execution order."""
    blocking = []
    if preflight_status != "ready":
        blocking.append("preflight")
    if patch_status not in ("completed", "skipped", "empty"):
        blocking.append("patch")
    if verify_status != "passed":
        blocking.append("verify")
    return blocking


def host_sequence_decision(preflight_status, patch_status, verify_status):
    """Decide the next action for one host based on step results.

    Returns one of: ``'proceed'``, ``'recover'``.
    """
    return "recover" if blocking_steps(preflight_status, patch_status, verify_status) else "proceed"


def rollout_should_stop(host_results):
    """Return True when the rollout must stop (a host needs recovery)."""
    for result in host_results:
        if result.get("action") == "recover":
            return True
    return False


def step_result(name, status, detail, data=None):
    return {"step": name, "status": status, "detail": detail, "data": data or {}}


def host_rollout_result(target, preflight, patch, verify, recover, action,
                        collected_at=None, error=None):
    """Aggregate one host's rollout outcome."""
    return {
        "target": target,
        "collected_at": collected_at or _timestamp(),
        "preflight": preflight,
        "patch": patch,
        "verify": verify,
        "recover": recover,
        "action": action,
        "blocking": blocking_steps(preflight, patch, verify) if action == "recover" else [],
        "error": error,
    }


def rollout_result(targets, canary, hosts, collected_at=None):
    """Aggregate the full rollout outcome."""
    total = len(hosts)
    completed = sum(1 for h in hosts.values() if h["action"] == "proceed")
    failed = sum(1 for h in hosts.values() if h["action"] == "recover")
    stopped_early = rollout_should_stop(list(hosts.values()))
    return {
        "schema_version": 1,
        "collected_at": collected_at or _timestamp(),
        "targets": targets,
        "canary": canary,
        "hosts": hosts,
        "summary": {
            "total": total,
            "completed": completed,
            "failed": failed,
            "stopped_early": stopped_early,
        },
        "error": None,
    }


def error_result(message, collected_at=None):
    return {
        "schema_version": 1,
        "collected_at": collected_at or _timestamp(),
        "targets": [],
        "canary": None,
        "hosts": {},
        "summary": {"total": 0, "completed": 0, "failed": 0, "stopped_early": True},
        "error": {"code": "rollout_error", "message": message},
    }


def main():
    from ansible.module_utils.basic import AnsibleModule

    module = AnsibleModule(
        argument_spec={
            "target": {"type": "str", "required": True},
            "preflight_status": {"type": "str", "required": True},
            "patch_status": {"type": "str", "required": True},
            "verify_status": {"type": "str", "required": True},
            "recover_result": {"type": "dict", "default": {}},
            "is_last_host": {"type": "bool", "default": False},
        },
        supports_check_mode=True,
    )
    collected_at = _timestamp()
    try:
        action = host_sequence_decision(
            module.params["preflight_status"],
            module.params["patch_status"],
            module.params["verify_status"],
        )
        record = host_rollout_result(
            module.params["target"],
            module.params["preflight_status"],
            module.params["patch_status"],
            module.params["verify_status"],
            module.params["recover_result"],
            action,
            collected_at,
        )
        module.exit_json(changed=False, **record)
    except Exception as exc:  # noqa: BLE001 - never leak credentials
        module.exit_json(changed=False, **error_result(
            f"Rollout coordination failed ({type(exc).__name__})", collected_at))


if __name__ == "__main__":
    main()
