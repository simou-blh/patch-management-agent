# Foundation interfaces

The interfaces below are starter contracts. The schema files define the current
implemented subset; they must be extended to cover the complete `mvp.md` report
before live execution is enabled.

## Fleet MCP

- `inventory_catalog()` returns the operator-configured host names and fixed query IDs.
- `query_fleet(hosts, query_id)` returns `{query_id, hosts: {name: {rows, error}}}`.
- IDs: `os_version`, `packages`, `processes`, `listening_ports`. SQL is fixed in code.
- Unknown hosts/queries, duplicate selections and empty selections fail before SSH.
- Known-host checks, batch authentication and per-host timeouts are mandatory.
- Inventory is stored in `lab/hosts.json`; keep it synchronized with `inventory.ini`.

## Plan and approval MCP

The proposed [versioned evidence contract](evidence-contract.md) is available for
inspection/assessment integration work. `playbooks/inspect.yml` now emits it, but
its validator is still not consumed by the MCP facade or the operator-owned
collector; the facade below still uses the existing manual evidence shape shown
in this section.

- `submit_plan(plan)` validates `schemas/plan.schema.json` plus candidate evidence,
  then stores the proposal in the local SQLite store.
- `approval_status(run_id)` returns the exact plan, canonical SHA-256, decision and time.
- `request_deployment(run_id, plan_hash)` always returns a blocked report in this
  foundation. Requests for existing plans are recorded in SQLite. No job is started.
- A changed plan resets approval; stale hashes cannot approve a new plan. Re-submitting
  identical JSON content preserves a decision. Object key order does not affect hashes.
- There is no approve/reject MCP tool. The human reviews and decides with the CLI:

```bash
uv run --no-sync python -m patch_agent.operator show RUN_ID
uv run --no-sync python -m patch_agent.operator approve RUN_ID --hash REVIEWED_SHA256
uv run --no-sync python -m patch_agent.operator reject RUN_ID --hash REVIEWED_SHA256
```

The operator alone creates `data/evidence.json` from trusted inspection results:

```json
{
  "vm-01": {
    "packages": {
      "PACKAGE_NAME": {
        "installed": "OBSERVED_DEBIAN_VERSION",
        "candidates": ["EXACT_AVAILABLE_REPOSITORY_VERSION"]
      }
    }
  }
}
```

For isolated development/demo sessions, an operator may set `PATCH_AGENT_DATA_DIR`
in the MCP process and CLI environment to use a different state/evidence directory.
It is not accepted as a tool argument. `python scripts/demo.py` uses this mechanism
to keep its synthetic data separate from real operator data.

This file is a development interface, not an automated collector. `inspect.yml`
does not generate it yet. Never use the synthetic test versions as live evidence.
Submission rejects unknown hosts/packages, mismatched installed versions, unavailable
patch versions, duplicate package decisions, unsupported actions and kernel patches.
It does not yet validate CVEs, Debian version ordering, dependency changes or
repository freshness. Preflight readiness is a separate v1 contract and is not
consumed by submission or execution. Approval therefore cannot enable execution.

## Preflight readiness

`playbooks/preflight.yml` emits a versioned readiness envelope from
`playbooks/library/preflight.py`, validated against
`schemas/preflight.schema.json` by `patch_agent/preflight.py`. It runs only
read-only package-manager checks:

- effective root privileges;
- free space on configured paths;
- non-blocking probes of APT and dpkg lock files;
- `dpkg --audit` package-manager health;
- exact installed-version drift against approved expectations;
- approved target versions still offered by a configured repository.

Configuration backups and recovery artifacts are optional operator-supplied
preparation steps. A host is `ready` only when every check passes, the backup is
`verified`, and the recovery artifacts are `verified`. Missing preparation
therefore yields `not_ready` with explicit blocking entries instead of a false
pass. `patch.yml` and `recover.yml` remain fail-gated, and a valid preflight
record is not an approval.

With `preflight_cache_previous: true` (not in check mode), preflight runs
`apt-get download <package>=<expected_installed>` into
`preflight_recovery_artifact_dir` and verifies the downloaded `.deb` files with
any operator-supplied artifacts. It writes files only; installed packages are
not changed. A previous version that the repository no longer offers makes the
recovery artifacts `failed`. Configuration backups are written to
`<backup_root>/<host>/<timestamp>/<original path>`; recovery must receive that
exact directory as `recover_backup_root`.

Fixed service restarts and health checks are defined in `policies/services.json`
and validated by `patch_agent/policies.py` against
`schemas/policies.schema.json`. Patch and verification must consult that
allowlist; neither is enabled yet. The playbooks read the file on the controller
and pass it to `patch_packages`/`verify_packages` as the `policy` argument,
because Ansible copies only the module file to the target. Library modules must
stay self-contained: they never import `patch_agent`
(`tests/test_library_isolation.py` enforces this).

## Patch, verify and recovery contracts

`playbooks/patch.yml`, `playbooks/verify.yml` and `playbooks/recover.yml`
implement Abderaouf's Sprint 3 canary patch/verify and recovery work, but all
three stay behind fail gates until deployment is unblocked:

- `playbooks/library/patch_packages.py` enforces exact approved versions, only
  configured service restarts, no kernel changes, and reports per-package patch
  outcomes against `schemas/patch.schema.json` (`patch_agent/patch.py`).
- `playbooks/library/verify_packages.py` compares observed installed versions
  against the approved plan using Debian version semantics and runs configured
  service health checks against `schemas/verify.schema.json`
  (`patch_agent/verify.py`).
- `playbooks/library/recover_packages.py` captures diagnostics, attempts bounded
  APT repair and previous-package/config restoration, and reports manual
  intervention when automated recovery fails against
  `schemas/recover.schema.json` (`patch_agent/recover.py`). Repair and package
  restoration are simulated with `apt-get -s` first and refused if APT would
  remove any package; restored package versions and config bytes are checked
  after the change.

All three run in read-only simulate mode by default (`deployment_unblocked`
defaults to `false`). The apply/restart path is gated behind that flag and
cannot be reached while the foundation keeps deployment blocked.

## Sequential fleet rollout

The sequential rollout coordinator (canary vm-01, then vm-02 and vm-03 one at a
time, stop at the first failure, recover only the affected host) belongs to
Baha's orchestration code, not to an extra playbook: Semaphore keeps exactly the
five fixed templates. The coordinator drives `preflight.yml`, `patch.yml`,
`verify.yml` and `recover.yml` per host; `patch.yml` and `recover.yml` keep
`serial: 1` and `any_errors_fatal: true`.

## Trust boundary

This is a local single-operator prototype. OpenCode's project permissions deny built-in
shell, file writes, network tools and unlisted tools; only the two facade servers are
allowed. Use a dedicated OpenCode session for assessment, and use a separate terminal
for development and approval. Global configuration/plugins must not re-enable broader
tools. This configuration is a guardrail, not an OS sandbox: production separation
requires an operator identity/state inaccessible to the agent process.

The upstream Semaphore MCP server is available only through the Compose `upstream`
profile for operator transport tests. Do not register it with the model. The future
facade must derive task arguments from stored approved plans, not model-provided
template IDs, inventory paths, limits, playbook text, shell or arbitrary extra vars.

## Later execution contract

Create a trusted adapter mapping the five logical templates to fixed Semaphore IDs.
Bind the execution to the plan hash, allowed hosts, packages, versions and template
mapping. Revalidate candidates and dependencies during preflight. Execute and verify
the canary first, then fleet hosts sequentially. Stop on any failure and report recovery
results without claiming best-effort downgrade is guaranteed rollback. Extend reports
with evidence, timestamps, task IDs/log references, observed versions and health results.
