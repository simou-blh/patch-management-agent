# Implementation plan and team handoff

This plan replaces the superseded LangGraph/OSV/Ubuntu-VM roadmap. [mvp.md](mvp.md)
is the product requirement; [SETUP.md](SETUP.md) is the environment entry point.
The goal now is a lightweight, reviewable foundation the six developers can extend.

## 1. Locked baseline and current state

- OpenCode, one operator-selected provider, MCP tools implemented in Python 3.12+.
- Existing Kali WSL2 control node; Windows VirtualBox/Vagrant; three Debian 12 VMs.
- osquery for inventory/observations; fixed Ansible inspection for APT candidates.
- Debian security tracker/advisories, binary-to-source matching and Debian version semantics.
- Approval facade in front of Semaphore MCP/API; SQLite for Semaphore and local approvals.
- No LangGraph, OSV, second runtime/provider fallback, PostgreSQL or platform core in this phase.
- Mobile-data allowance: 2–5 GB. Check [estimates](docs/download-budget.md) before downloads.

| Foundation component | Current state |
|---|---|
| Repository config, tool policy, setup docs | Added; provider still selected locally |
| Vagrant lab, inventory, key sync, check script | Added; real VMs/network not validated |
| osquery MCP | Implemented fixed queries and per-host errors; mocked SSH tests |
| Approval facade | Implemented schema/evidence validation, storage, hash binding, operator decisions |
| Live deployment | Blocked for all plans, including approved ones |
| Five playbooks | Inspect/verify collect observations; preflight/patch/recover explicitly fail |
| Semaphore services/templates | Compose prepared; template list is design-only; services not started |
| Plan/report schemas | Starter schemas; report currently covers blocked requests only |
| Tests | Validation, approvals, persistence, inventory and in-process MCP checks |

See [interfaces.md](docs/interfaces.md) for exact starter contracts. A passed unit test
is not evidence of working infrastructure or a successful deployment.

## 2. Team ownership and next mergeable changes

Keep PRs small. Each author pairs with the reviewer shown; no remote PRs or project
settings have been created as part of this foundation.

| Owner | Responsibility / next work | Reviewer |
|---|---|---|
| Ahmed BOULOUH | Docs, milestones, demo script, scope and eventual platform manifest | Dhia |
| Taha BELALOUI | Kali/tool checks, transitive uv lock, lab, SSH/network tests, osquery bootstrap, Semaphore project/templates/credentials | Abderaouf |
| Abderaouf BECHICHE | Five fixed playbooks: candidate collection, readiness/backups, exact-version patching, health verification, recovery | Taha |
| Wassim MEFTAH | Approval/execution boundary, trusted evidence, candidate/dependency validation, recovery permissions, complete reports | Baha |
| Baha GAHTAR | Debian advisory cache and matching, source mapping, version comparison, structured plans and rollout coordinator | Wassim |
| Dhia Eddine LAGHROUR | MCP integration tests, scenario tests, CI, reproducibility and later HTTP contract adapter | Ahmed |

Build in this order:

1. **Reproduce the environment.** Review/pin transitive Python dependencies, validate
   the lab config, bring up three VMs, verify SSH from WSL and Docker, implement signed
   osquery bootstrap, save clean/ready snapshots. Validate the 2–5 GB allowance first.
2. **Collect trusted evidence.** Extend fixed inspection to emit installed/candidate
   versions, repository/source mapping and collection timestamps. Replace manual
   `data/evidence.json` with an operator-owned collector. Reject stale/incomplete data.
3. **Match advisories.** Cache Debian data deliberately; use Debian version ordering
   (never string/PEP 440 ordering), resolve binary/source names and mark unknown matches.
   Confirm fixed versions exist in configured repositories; defer unsupported changes.
4. **Complete execution safety.** Implement real preflight/backups and fixed template
   mapping. Derive all job arguments from the stored approved plan. Bind the template
   configuration as well as host/package/version scope. Block stale/missing approval,
   kernel/major upgrades, reboots, arbitrary playbooks/SQL and dependency scope expansion.
5. **Canary and sequential rollout.** Wait for each task's terminal status, compare
   observed versions, run configured service health checks, then patch/verify one fleet
   host at a time. Stop immediately on any failure; never advance based on model text.
6. **Recovery and complete reports.** Attempt only approved predefined recovery,
   verify its result, stop on failure and flag manual intervention. Record evidence,
   decisions, timestamps, task IDs/log references, versions and recovery for every
   terminal outcome. Extend the starter report schema before enabling live jobs.
7. **Rehearse.** Pin a small deterministic set of demo package versions with recoverable
   artifacts; document/reset using snapshots. Run success, rejection, canary failure,
   fleet stop and failed recovery against the real lab. Avoid relying on today's updates.

Do not remove the fail gates or enable live deployment until steps 2–6 have scenario
coverage. Read-only templates may be exercised independently while deployment remains blocked.

## 3. Interfaces and acceptance tests

- Fleet MCP returns `{query_id, hosts: {host: {rows, error}}}`. Query IDs are fixed.
- Plan schema defines exact targets/canary, per-host package decisions, versions,
  references, priorities, reasons, verification and recovery prerequisites.
- `submit_plan`, `approval_status`, `request_deployment` are model-facing. Human
  approval/rejection stays in the separate operator CLI and binds to the reviewed hash.
- Upstream mutation tools never appear directly in OpenCode's tool list.
- The future executor accepts stored plan ID/hash, not caller-supplied commands,
  templates or extra variables. Report all task IDs and observed outcomes.

Run current checks with `python -m pytest -q` (or `uv run --no-sync python -m pytest -q`).
Add scenario coverage alongside the implementation:

| Scenario | Required result before enabling live execution |
|---|---|
| Unknown host/package/version/action or stale evidence | Reject before any job starts |
| Missing/rejected approval, changed plan/template mapping | No mutation job starts |
| One unreachable inventory host | Other hosts retain evidence; failed host is explicit |
| Failed canary preflight | No target modified; fleet untouched |
| Canary install/version/health failure | Fleet untouched; report recovery outcome |
| Fleet host failure | Subsequent hosts untouched |
| Recovery artifacts unavailable or repair fails | Stop with diagnostics and manual intervention status |
| Success, rejection, abort or failure | Complete timestamped JSON report |

Tests for rollout stop and recovery are pending implementation; they are not represented
as passing mock deployment demonstrations. Validate YAML with Ansible in WSL and run the
same playbooks against the pinned Semaphore runtime. Confirm OpenCode can initialize
both stdio adapters, then run the real environment-ready gates in SETUP.md.

## 4. Later platform integration

Preserve [PROJECT_FULL_REFERENCE.md](PROJECT_FULL_REFERENCE.md). Once the standalone
MVP is stable, review its contract and implement a separate FastAPI service/container,
mandatory response envelope and fixed endpoints, tenant isolation and authenticated
configuration/run APIs, manifest/submission adapter and safe webhook reporting.
Do not claim contract compliance until tested against the actual teacher-provided core.
Its PostgreSQL requirement belongs to that integration environment, not this MVP setup.
Team identity/contact and provider choice remain operator/team configuration; no secrets
or invented values are committed here.
