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
inspection/assessment integration work. Its validator currently stands alone; the
MCP facade below still uses the existing manual evidence shape shown in this section.

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
It does not yet validate CVEs, Debian version ordering, dependency changes, repository
freshness, service checks or recovery artifacts. Approval therefore cannot enable execution.

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
