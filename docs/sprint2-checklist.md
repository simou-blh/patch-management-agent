# Sprint 2 acceptance checklist

Status of the Sprint 2 outcomes in [plan.md](../plan.md), read from `main` at commit
`4a9fd91` and the project documents (2026-11-13). This page records evidence; it does not
tick any `plan.md` item. A box there is ticked only after merged work and a recorded
`Evidence:` reference. Mocked/synthetic and live evidence are kept in separate columns.
Deployment remains blocked.

Completion gate (Sprint 2 plan): a known vulnerable package produces an evidence-backed,
installable patch plan; stale or invalid evidence and failed preflight block execution;
recovery prerequisites are verified; deployment stays blocked.

## 1. Checklist

| Item | Outcome | Mocked/synthetic evidence | Live evidence |
|---|---|---|---|
| S2.1 | Repeatable vulnerable lab, obtainable fixed/previous package artifacts, validated template IDs and connectivity, compatible Semaphore Ansible runtime | None yet. Only the fixture requirements in [runbook.md](runbook.md) section 8.3 exist | None yet. The lab has not been brought up (runbook blocker 1) |
| S2.2 | Timestamped advisory cache and source/version matching give affected/fixed/uncertain decisions and installable fixes or explicit deferrals | Debian version helpers are merged (PR #6, S1.4a). Advisory-cache and assessment contracts are proposed in PR #7 (open, not merged). Matching is not implemented | None yet |
| S2.3 | Advisory/candidate validation and APT simulation reject dependency expansion, removals and unsupported actions; verification/recovery policies and executor/report contracts are fixed | Service policy file, schema and validator are on main (`policies/services.json`, `schemas/policies.schema.json`, `patch_agent/policies.py`), as are the patch, verify and recover result schemas. `submit_plan` rejects kernel patches but does not yet check dependency changes, CVEs or Debian ordering ([interfaces.md](interfaces.md)). Scope-expansion simulation is not documented | None yet |
| S2.4 | Preflight checks privileges, disk, APT health/locks, drift and candidate availability; previous artifacts, configuration backups and service policies are verified | Preflight playbook, library module, schema, `patch_agent/preflight.py` and `tests/test_preflight.py` are on main; the parser/contract tests run in the local suite (344 passed on 2026-11-13). A host is `ready` only if every check passes and the backup and recovery artifacts are `verified` | None yet. Preflight has not run against the live lab (runbook blocker 11); a real run must show one ready host and one blocked host |
| S2.5 | Negative and integration tests pass; a documented real assessment produces an evidence-backed plan; failed readiness or evidence blocks execution | Evidence side: import and `submit_plan` reject stale or future evidence, failed or missing hosts, legacy maps and a missing age policy ([validation.md](validation.md), 2026-11-07). Readiness side: preflight is a separate contract that submission and execution do not consume yet, so failed readiness cannot block anything. No assessment-to-plan generation exists | None yet |

## 2. Ahmed's Sprint 2 documentation

| Deliverable | State |
|---|---|
| Assessment-to-approval workflow and exact plan fields | `docs/assessment-workflow.md`, PR #13 (open) |
| Patch/defer examples with sanitized reasons | `docs/plan-examples.md`, PR #14 (open). Synthetic, taken from the demo plan; not from a real assessment |
| Fixture setup, reset and recovery prerequisites | Requirements only, in runbook section 8.3. Waiting for the fixture and reset steps from the S2.1 owner |
| Interface consistency review | PR #7 was reviewed. The remaining questions between an assessment and a plan are recorded in `assessment-workflow.md` section 5. A full pass over all interface documents is not done yet |

The two new documents are linked here once their PRs are merged.

## 3. Checks to repeat before a Sprint 2 PR

Local (Windows PowerShell, repo root):

    uv run python -m pytest -q
    uv run python scripts/check_artifacts.py
    uv run python scripts/update_progress.py --check
    git diff --check

Live (`PENDING-LIVE`, run on the lab machine, results recorded separately):

- A known vulnerable package, with obtainable fixed and previous versions, is installed on vm-01.
- A read-only Semaphore preflight template completes a task.
- Preflight reports a ready host, and a blocked host when artifacts or backups are missing.
- A real assessment of real evidence produces a plan that `submit_plan` accepts.
- Stale evidence from a real export is rejected.
- Approved and unapproved deployment requests both remain blocked.
