# Sprint evidence matrix — all members, all four sprints

This matrix maps the teacher’s four-sprint PDF to the delivered repository and to the
teacher-platform agent. It distinguishes **code/tests/docs delivered and verified
locally** from **live-lab evidence**, which is not claimed without recorded lab results.

Legend: ✅ code/tests/docs delivered · 🟡 delivered but live evidence pending · ⬜ not yet delivered.

## Sprint 1 — Lab and trusted evidence

| Member | PDF task | Delivered in | Verification | Live |
|---|---|---|---|---|
| Taha | Lock deps, three VMs, SSH, signed osquery, Semaphore, snapshots | `SETUP.md`, `lab/`, `setup/osquery_bootstrap.yml`, `semaphore/`, `Dockerfile` healthcheck | `scripts/check_env.py`, Docker `/health` | 🟡 |
| Abderaouf | `inspect.yml` versioned evidence; fixed templates | `playbooks/inspect.yml`, `playbooks/library/inspect_packages.py`, `agent` evidence upload | `tests/test_inspect.py`, `tests/agent/test_business.py` | 🟡 |
| Wassim | Evidence contract, freshness, collector, approval | `patch_agent/evidence.py`, `collector.py`, `approval.py`, tenant evidence store | `tests/test_collector.py`, `test_evidence_readiness.py`, `tests/agent` | 🟡 |
| Baha | Advisory/assessment contracts, version helpers, fixture spec | `schemas/`, `patch_agent/assessment.py`, `debversion.py`, `assessment_builder.py`, `docs/vulnerable-fixture.md` | `tests/test_assessment.py`, `test_assessment_builder.py` | 🟡 |
| Dhia | CI, MCP/approval/collector tests, live checklist | `.github/workflows/ci.yml`, `tests/`, `scripts/check_env.py`, agent contract tests | CI + 522 local tests | 🟡 |
| Ahmed | Runbook, interface decisions, fixture/reset, blockers | `docs/runbook.md`, `docs/interfaces.md`, `docs/AGENT_DELIVERY.md`, `agent.manifest.json` | artifact checks, manifest schema | 🟡 |

## Sprint 2 — Security assessment and execution preparation

| Member | PDF task | Delivered in | Verification | Live |
|---|---|---|---|---|
| Taha | Vulnerable fixture, artifacts, template IDs/runtime | `docs/vulnerable-fixture.md`, `semaphore/ids.json`, agent config schema | artifact checks; live fixture pending | 🟡 |
| Abderaouf | Preflight privileges/disk/APT/drift/candidates, backups/policies | `playbooks/preflight.yml`, `playbooks/library/preflight.py`, `patch_agent/preflight.py` | `tests/test_preflight.py` | 🟡 |
| Wassim | Advisory/candidate validation, APT simulation, policies, executor/report contracts | `patch_agent/approval.py` gates, `policies/`, `executor.py`, `report.py`, `schemas/report.schema.json` | `tests/test_plan_gates.py`, `test_patch.py`, `test_report.py` | 🟡 |
| Baha | Advisory cache, matching, installable fixes/defers, plans | `patch_agent/assessment_builder.py`, `planner.py`, agent `/assess` and `/plans` | `tests/test_assessment_builder.py`, `test_planner.py`, `tests/agent` | 🟡 |
| Dhia | Negative tests, dependency/policy/preflight tests, MCP integration | `tests/test_assessment.py`, `test_patch.py`, `test_preflight.py`, `test_plan_gates.py`, `test_mcp_gates.py` | full suite | 🟡 |
| Ahmed | Workflow, plan fields, examples, fixture docs | `docs/assessment-workflow.md`, `docs/plan-examples.md`, `docs/fixture-setup.md`, `docs/AGENT_DELIVERY.md` | artifact checks | 🟡 |

## Sprint 3 — Approved canary, recovery and reports

| Member | PDF task | Delivered in | Verification | Live |
|---|---|---|---|---|
| Taha | Semaphore submission/polling/logs, artifacts, canary runs | `patch_agent/executor.py` transport API, `docs/AGENT_DELIVERY.md` | `tests/test_executor.py` (fake transport) | 🟡 |
| Abderaouf | Exact-version patch/verify, restarts, health, recovery | `playbooks/patch.yml`, `verify.yml`, `recover.yml`, `playbooks/library/*` | `tests/test_patch.py`, `test_verify.py`, `test_recover.py` | 🟡 |
| Wassim | Facade, approval binding, duplicate runs, task IDs, reports | `patch_agent/executor.py`, `report.py`, `agent/routers/business.py` runs | `tests/test_executor.py`, `test_report.py`, `tests/agent` | 🟡 |
| Baha | Canary coordinator, failures/timeouts/unknown states, fleet blocked | `patch_agent/coordinator.py`, agent `/api/v1/runs` (operator-only, disabled) | `tests/test_coordinator.py`, `tests/agent/test_business.py` | 🟡 |
| Dhia | Approval/failure/timeout/report tests, live canary | `tests/test_approval.py`, `test_verify.py`, `test_coordinator.py`, `test_report.py` | full suite | 🟡 |
| Ahmed | Report fields/walkthroughs, operator wording | `docs/sprint3-contracts.md`, `docs/AGENT_DELIVERY.md` | artifact checks | 🟡 |

## Sprint 4 — Sequential fleet rollout and delivery

| Member | PDF task | Delivered in | Verification | Live |
|---|---|---|---|---|
| Taha | Fixture/snapshots/connectivity/rehearsals | `docs/vulnerable-fixture.md`, `docs/runbook.md`, lab scripts | docs | 🟡 |
| Abderaouf | Fleet playbook validation, failure recovery scope | `playbooks/`, `patch_agent/coordinator.py` | `tests/test_coordinator.py` | 🟡 |
| Wassim | Durable per-host state, task IDs, duplicate/interruption | `patch_agent/executor.py` RunStore, reports | `tests/test_executor.py` | 🟡 |
| Baha | Sequential rollout, stop at first failure | `patch_agent/coordinator.py` | `tests/test_coordinator.py` | 🟡 |
| Dhia | Success/rejection/failure/duplicate checks, CI | `tests/`, CI, `docs/validation.md` | full suite + CI | 🟡 |
| Ahmed | Demo scripts, release, submission | `scripts/agent_smoke.py`, `scripts/submit_agent.py`, `docs/AGENT_DELIVERY.md` | smoke + submission tests | 🟡 |

## Teacher-platform contract (new deliverable)

| Requirement | Delivered in | Verification |
|---|---|---|
| Manifest | `agent.manifest.json`, `schemas/agent.manifest.schema.json` | `tests/agent/test_submission.py`, `check_artifacts.py` |
| 5 mandatory endpoints | `agent/routers/lifecycle.py` | `tests/agent/test_lifecycle.py` |
| Standard envelope + errors | `agent/contract.py` | lifecycle tests |
| Tenant isolation + purge | `agent/state.py` | `tests/agent/test_business.py` |
| Webhook alerts | `agent/alerts.py`, business router | business tests with fake sender |
| Docker | `Dockerfile`, `requirements-agent.txt` | Docker build + `/health` |
| Submission adapter | `scripts/submit_agent.py` | `tests/agent/test_submission.py` |
| Test/push guide | `docs/AGENT_DELIVERY.md` | docs |

## Verification

```bash
python -m pytest -q                 # 522 passed, 400 skipped locally
python -m pytest tests/agent -q     # 15 passed
python scripts/check_artifacts.py
python scripts/update_progress.py --check
git diff --check
```

## Live gates not claimed

Real VMs, Semaphore task execution, live canary/recovery, fleet rollout and live Noyau
certification are not claimed by this matrix. They require the lab and the teacher’s
running Noyau; the repository provides the code, tests, Docker image and step-by-step
protocol.
