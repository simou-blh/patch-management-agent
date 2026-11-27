# Foundation validation — 2026-10-26

## Verified locally

- `python -m pytest -q`: **27 passed**, including actual stdio MCP subprocesses,
  the configured Python launch arguments, and the isolated approval CLI demo.
- `opencode mcp list`: **approval connected, fleet connected**. Project integration
  policies omit unrelated inherited MCP servers and skills.
- The project configuration validates against the live OpenCode v2 JSON schema.
- Real OpenCode/GPT-6 Luna smoke test: called `fleet_inventory_catalog` once and
  returned `vm-01`, `vm-02`, `vm-03`. These are configured names, not live VM evidence.
- `git diff --check`: passed. Compose configuration was also validated without
  starting services or pulling images.

The original connection failures came from launching `uv`, absent on this Windows
machine. MCP commands now use the available `python -m patch_agent...` directly.
The servers set `codemode: false` so the five native MCP tools remain available
while general code execution is denied. OpenCode v2 otherwise hides Code Mode tools
when `execute` is denied, even if their MCP servers are connected.

The CLI's unspecified model hit an OpenCode free-provider quota. Explicitly choosing
the user's existing `openai/gpt-6-luna` model worked; no provider credentials or global
configuration were changed. The successful test used a warmed regular OpenCode
session; standalone startup did not reliably produce a tool result and is not used
in the recommended command.

## Reproduce

```powershell
python -m pytest -q
python scripts/demo.py
opencode reload
opencode mcp list
opencode run --agent patch --model openai/gpt-6-luna "Use the fleet inventory catalog tool once to list configured hosts. Return those names only."
```

Use your own existing selected model if different. The model call consumes provider
usage; tests and the synthetic demo do not. Local smoke-test details are saved in
`data/opencode-smoke.json` and intentionally stay outside Git.

## Still unverified

Docker service startup, three real VMs, SSH/osquery against those machines, actual
APT/security evidence, canary patching, sequential rollout, and recovery. The lab
configuration is committed source for the team; provisioning and live environment
checks remain necessary before the first patching demonstration. See SETUP.md.

## Update 2026-10-31

Re-checked on Windows (Python 3.13.13 selected by uv, without WSL, Vagrant or Docker):

- `uv run python -m pytest -q`: **99 passed**. The suite has grown since the 27-test
  result above, which is kept as the 2026-10-26 record.
- `uv run python scripts/demo.py`: all gates passed, 4 schema-validated JSON reports.
- `uv run python scripts/update_progress.py --check`: README sprint bars are current.

The "Still unverified" list above is unchanged. See [runbook.md](runbook.md).

## Update 2026-11-06 — Sprint 1 CI, approval tests and live checklist

Sprint 1 work by Dhia Eddine LAGHROUR on branch `dhya/sprint1-ci-and-tests`.
Deployment remains blocked; no `plan.md` checkpoint is checked by this change.

### Mocked / synthetic / local results

Environment: Arch Linux, Python 3.14.9, isolated `.venv` with the pinned dependencies
(`mcp==2.3.0`, `jsonschema==4.26.0`, `pytest==9.1.1`, `PyYAML==6.0.3`).

| Check | Command | Result | Tag |
|---|---|---|---|
| Test suite (in-process/subprocess MCP, synthetic demo) | `python -m pytest -q` | **142 passed, 400 skipped** | `VERIFIED-LOCAL` |
| JSON/YAML artifact checks | `python scripts/check_artifacts.py` | "All JSON/YAML artifacts passed." | `VERIFIED-LOCAL` |
| Sprint progress bars | `python scripts/update_progress.py --check` | "README sprint bars are current." | `VERIFIED-LOCAL` |
| Whitespace errors | `git diff --check` | clean | `VERIFIED-LOCAL` |

The 400 skips are the `dpkg --compare-versions` cross-checks in
`tests/test_debversion_dpkg.py`; `dpkg` is unavailable on this Arch machine. The Ubuntu
CI runner executes them (see CI results below).

### CI results

| Check | Result | Tag |
|---|---|---|
| `.github/workflows/ci.yml` (pytest, artifact checks, progress check) | Success for commit `f9a76b8` — [run 42249355848](https://github.com/simou-blh/patch-management-agent/actions/runs/42249355848) | `VERIFIED-CI` |

`VERIFIED-CI` means the workflow ran on GitHub for commit `f9a76b8` and the linked
run concluded successfully. This documentation-only follow-up does not change any
checked artifact.

### Live results

| Check | Command | Result | Tag |
|---|---|---|---|
| SSH login to vm-01..vm-03 | `python scripts/check_env.py --live` | Not run; lab not up | `PENDING-LIVE` |
| osquery Debian 12 on all hosts | `python scripts/check_env.py --live` | Not run | `PENDING-LIVE` |
| Semaphore ping/auth | `SEMAPHORE_URL=... python scripts/check_env.py --live` | Not run | `PENDING-LIVE` |
| Read-only inspection job | Semaphore UI + agreed template IDs | Not configured (S1.2d) | `PENDING-LIVE` |

Semaphore auth is skipped, not failed, when `SEMAPHORE_API_TOKEN` is unset. The token
stays in the operator environment; it is never printed, stored in the repository or
passed as a tool argument.

### Freshness blocker

Freshness and completeness rejection is not implemented or tested: the v1 contract
validates structure only and deliberately accepts old collections and failed hosts as
diagnostics. Max-age/completeness rules and the operator-owned collector belong to
S1.2b/S1.3; until they are merged, no collected data can authorize a patch plan and
deployment stays blocked. `tests/test_collector_contract.py` only proves that a
partial-host collection is valid diagnostics but cannot be used as approval evidence.

### Progress

No checkpoint changed. S1.2a remains the only checked Sprint 1 item; this section records
verification only and does not modify `plan.md` or the README progress bars.

## Update 2026-11-07 — Evidence import and approval integration

Verified on Windows with the repository's Python 3.12 virtual environment:

- `python -m pytest -q`: **204 passed, 400 skipped**. Skips require Linux `dpkg`;
  no dependency versions were changed or downloaded.
- `python scripts/check_artifacts.py`: passed.
- `python scripts/update_progress.py --check`: passed; no new checkpoint is checked
  for this unmerged work.
- The suite exercises the operator import CLI and actual approval MCP subprocess,
  as well as the isolated synthetic demo. The demo now imports contract-v1 evidence
  before submitting plans; it still starts no VM, Ansible or Semaphore jobs.

Import/submission reject stale/future evidence, failed/missing or unrequested hosts,
legacy evidence maps and missing operator age policy. Tests also cover candidate
architecture isolation, concurrent import locking, older-result regression and an
interrupted atomic replacement preserving the previous collection.

The live producer/export and trusted Semaphore transport are still pending. The
existing inspection playbook does not emit v1 yet. An operator-owned import path
does not authenticate a file's provenance; only import actual trusted observations.
The team must agree the age limit before configuring the importer/MCP. Existing
SQLite plans remain intact, legacy evidence needs explicit archival/recollection,
and deployment remains blocked even after approval.

## Update 2026-11-13 — Re-check at main 4a9fd91

Re-checked on Windows at `main` commit `4a9fd91` (merge of PR #11 and the playbooks
branch). `uv sync` resolved 38 packages and updated 6, because `uv.lock` is not in Git.
Deployment remains blocked; no `plan.md` checkpoint is changed by this note.

| Check | Command | Result | Tag |
|---|---|---|---|
| Test suite | `uv run python -m pytest -q` | **344 passed, 400 skipped** (28.66 s) | `VERIFIED-LOCAL` |
| JSON/YAML artifact checks | `uv run python scripts/check_artifacts.py` | "All JSON/YAML artifacts passed." | `VERIFIED-LOCAL` |
| Sprint progress bars | `uv run python scripts/update_progress.py --check` | "README sprint bars are current." | `VERIFIED-LOCAL` |
| Synthetic demo | `uv run python scripts/demo.py` | All gates PASS, 4 schema-validated JSON reports | `VERIFIED-LOCAL` |

The 400 skips are the `dpkg --compare-versions` cross-checks, which need Linux `dpkg`.
The demo prints expected rejection messages on stderr (unknown host, unavailable
version); PowerShell may show them as `NativeCommandError`. The run still ends with
`Demo passed`. CI for this commit was not re-checked here.

Live checks (SSH/osquery on the three VMs, Semaphore, canary patching, rollout,
recovery) were not run and remain `PENDING-LIVE`.

## Update 2026-11-15 (collector verification)

Re-checked on Windows at `main` commit `c7ba285` with the repository's Python 3.12
virtual environment. This records the S1.3 verification for the merged collector
(PR #11). No live data is included and deployment stays blocked.

| Check | Command | Result | Tag |
|---|---|---|---|
| Test suite | `python -m pytest -q` | **427 passed, 400 skipped** (62 s) | `VERIFIED-LOCAL` |
| JSON/YAML artifact checks | `python scripts/check_artifacts.py` | "All JSON/YAML artifacts passed." | `VERIFIED-LOCAL` |
| Sprint progress bars | `python scripts/update_progress.py --check` | "README sprint bars are current." | `VERIFIED-LOCAL` |
| Whitespace errors | `git diff --check` | clean | `VERIFIED-LOCAL` |

The 400 skips are the `dpkg --compare-versions` cross-checks, which need Linux `dpkg`;
the Ubuntu CI runner executes them.

The operator import path rejects stale, future-dated, incomplete and failed-host
collections, legacy evidence maps, unrequested or unknown hosts, duplicate candidate
versions and cross-architecture approvals, and blocks a missing or invalid
`PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS`. Publication is locked, private and atomic, and
an older collection cannot replace a newer one. `submit_plan` applies the same
readiness checks before an approval is stored, so an approval cannot exist for evidence
that would be rejected at submission. `tests/test_collector.py`,
`tests/test_evidence_readiness.py` and `tests/test_collector_contract.py` cover these
paths; the synthetic demo imports contract-v1 evidence before submitting plans.

Correcting the 2026-11-07 note: `playbooks/inspect.yml` and
`playbooks/library/inspect_packages.py` now emit the contract-v1 envelope, covered by
`tests/test_inspect.py`. What is still pending is the live export from a Semaphore-run
inspection (S1.2d/S1.5c) and the team's age-policy value (S1.2b), so no collected data
is live evidence yet.

## Update 2026-11-22 (advisory and assessment contract verification)

Re-checked on Ubuntu 22.04 (WSL2) at `main` commit `83d5881` with a uv-managed Python
3.15.2 environment. This records the S1.4b and S1.4c verification for the merged
advisory-cache and assessment-result contracts (PR #7). No live data is included and
deployment stays blocked.

| Check | Command | Result | Tag |
|---|---|---|---|
| Test suite | `uv run python -m pytest -q` | **827 passed** (7 s) | `VERIFIED-LOCAL` |
| Contract and version tests | `uv run python -m pytest tests/test_assessment.py tests/test_debversion.py tests/test_debversion_dpkg.py -q -rs` | **515 passed, none skipped** | `VERIFIED-LOCAL` |
| JSON/YAML artifact checks | `uv run python scripts/check_artifacts.py` | "All JSON/YAML artifacts passed." | `VERIFIED-LOCAL` |
| Sprint progress bars | `uv run python scripts/update_progress.py --check` | "README sprint bars are current." | `VERIFIED-LOCAL` |
| Whitespace errors | `git diff --check` | clean | `VERIFIED-LOCAL` |

Unlike the Windows run recorded above, this run had Linux `dpkg` (1.21.1), so the 400
`dpkg --compare-versions` cross-checks executed instead of being skipped.

The advisory-cache validator rejects unknown fields, a `resolved` advisory without a
fixed version, an `open` or `undetermined` one with a fixed version, unparseable fixed
versions, duplicate advisory ids, impossible timestamps, and source URIs with
credentials, a query or a fragment. The assessment validator rejects findings whose
reason contradicts their status or the Debian ordering of the source version, results
whose status does not follow their findings, unparseable versions without a
`version_invalid` finding, patch decisions that do not resolve every affected finding or
that sit beside an uncertain finding, and records assessed before their inputs. Versions
are compared on the source package version, and inputs are bound by digests that reuse
`approval.canonical`. `tests/test_assessment.py` covers these paths with synthetic
fixtures in `tests/fixtures/assessment`.

Not yet done: the contracts are not read by `submit_plan` or any tool, the evidence digest
in the example is illustrative, and deriving `priority` from advisory urgency is left to
Sprint 2 (S2.2). The vulnerable-package fixture specification (S1.4d) is still pending, so
S1.4 itself stays unchecked.

## Update 2026-11-26 (S1.2c inspection playbook verification)

Re-checked on Windows at `raouf` branch (commit `f4e09ea` on top of merged playbook work
including commit `8af0e9d`). This records local verification for S1.2c: the fixed inspection
playbook emits the agreed versioned package/candidate/source/origin/timestamp/error fields,
with output validation tests. No live Semaphore job or live VM run is included here; S1.2d
covers the read-only inspection/verification template mapping and successful inspection job
demonstration. Deployment remains blocked.

| Check | Command | Result | Tag |
|---|---|---|---|
| Inspection and evidence contract tests | `uv run --no-sync python -m pytest tests/test_inspect.py tests/test_evidence.py -q` | **61 passed** | `VERIFIED-LOCAL` |

Observed in code/tests:
- `playbooks/inspect.yml` collects structured evidence via `inspect_packages`, normalizes
  per-host records, assembles a `schema_version: 1` fleet envelope with `collected_at`,
  `targets`, and `hosts`, and emits unreachable hosts as explicit `status: error` records.
- `playbooks/library/inspect_packages.py` runs only read-only `dpkg-query` and
  `apt-cache policy`, emits architecture-qualified package keys, installed/source mapping,
  candidate versions with merged repository origins, UTC timestamps, and sanitized error
  records.
- `tests/test_inspect.py` validates parsing, architecture filtering, origin normalization,
  unsupported-origin handling, contract-valid ok/error host records, and that the playbook
  emits v1 evidence without mutating hosts.

Not yet done: S1.2b producer/consumer agreement record, S1.2d read-only template mapping
and successful Semaphore inspection job demonstration, and live three-host evidence export.

## Update 2026-11-27 (live lab runs for Abderaouf's playbooks)

Live runs against vm-01/vm-02/vm-03 (Debian 12) from the Windows machine: playbooks run
through the local Semaphore (`inspect`, `verify` templates) and from a WSL Ansible
controller (ansible-core 2.22) for scenarios that need approved-plan variables. SSH uses
strict host-key checking against a `known_hosts` whose fingerprints were compared with each
VM console. Raw logs stay outside Git; results below are summaries. All emitted records
passed their contract validators (`patch_agent/{preflight,patch,verify,recover}.py`).
Tagged `VERIFIED-LIVE`.

Lab fixture: a refreshed package index showed a real pending security update. openssh
`1:9.2p1-2+deb12u7` (installed) -> `1:9.2p1-2+deb12u10`; the update also requires libssl3
and openssl `3.0.17-1~deb12u3` -> `3.0.22-1~deb12u2`. The installed libssl3/openssl version
is no longer published, so the approved rollback scope is the three openssh packages
(libraries only move forward). VM snapshots `baseline-before-fixture` allow a reset.

| Sprint | Scenario | Host(s) | Result |
|---|---|---|---|
| S1 | Semaphore `inspect` template; export imported by the collector | all | success, `ok=6/2/2`, evidence published; wrong targets and stale evidence rejected |
| S2 | Preflight with config backup and cached previous openssh `.deb` files | vm-01/02/03 | `ready`; backup and 3 artifacts `verified` |
| S2 | Approved target not offered (`deb12u99`) | vm-02 | `not_ready`, blocking `candidates`; gate stopped |
| S3 | Canary: preflight -> patch (deployment unblocked) -> verify | vm-01 | 5 packages applied, ssh restarted after install, verify 5/5 pass, TCP health pass |
| S3 | Plan omits libssl3/openssl (APT would expand scope) | vm-02 | patch refused with `scope_expansion`; no package changed |
| S4 | Injected verify failure (plan expects `deb12u9`) | vm-02 | verify failed -> recovery on vm-02 only: openssh restored to `deb12u7` in one APT transaction, `sshd_config` restored, follow-up verify 3/3 pass |
| S4 | Stop after failure | vm-03 | all 357 packages identical to the pre-rollout evidence |
| S4 | Sequential success: vm-02 then vm-03 | vm-02, vm-03 | each preflight `ready`, patch applied, verify 5/5 pass |

Code changes found necessary by these runs: patch simulates APT first and refuses changes
outside the approved packages/versions or any removal; recovery restores previous versions
in one bounded transaction; preflight caches only the approved rollback scope
(`preflight_cache_packages`); patch reports `changed` when it applied packages.

Not yet done: the rollout coordinator itself is Baha's (the sequence above was driven by the
operator host by host); Semaphore templates still run the playbooks committed on `main`,
which do not include these changes until they are merged.

## Update 2026-11-27 (live failure scenarios)

Second live pass on the same lab, focused on failure handling. Tagged `VERIFIED-LIVE`;
every emitted record passed its contract validator.

| Scenario | Host(s) | Result |
|---|---|---|
| All hosts powered off | all | every host gets an explicit `inspection_failed` record; verify/recover gates stop |
| One host down (vm-03) | all | vm-01/vm-02 report 357 packages, vm-03 an explicit error; verify stops at vm-03; collector rejects the evidence |
| dpkg lock held by another process | vm-01 | preflight `not_ready`, blocking `apt_locks` |
| Package unpacked but not configured | vm-02 | preflight blocks on `apt_health`; bounded repair (`apt-get install -f`) configures it; `dpkg --audit` clean; recovery reports no manual intervention |
| Local port 22 rejected (nft), version correct | vm-03 | verify fails on the TCP health check only; passes again once the rule is removed |
| Kernel package in an approved plan | vm-01 | patch refuses the plan |
| `--check` with deployment unblocked | vm-01 | every package `skipped`; openssh unchanged |

Bug found and fixed by the broken-package scenario: recovery decided manual intervention
from the `dpkg --audit` taken *before* its repair, so a successful repair was still
reported as manual. It now re-runs `dpkg --audit` after live recovery actions (result noted
in the repair detail) and flags manual intervention only for failures or issues that
remain. The recovery contract no longer rejects a successful repair without a package
restore; a manual-intervention record must instead show a failure, an error or
package-manager issues. The full happy-path scenario (23 checks) passed again afterwards,
and the Linux CI build passed with 841 tests.

## Update 2026-11-27 (Sprint 2 test batch on dhya/sprint2-3+review)

Review branch `dhya/sprint2-3+review` at merge `7e78843` integrates Abderaouf's
`origin/raouf` commits; his authorship is preserved. This section records only local
synthetic/contract checks. No live data is added, raw logs stay outside Git and
deployment remains blocked.

| Check | Command | Result | Tag |
|---|---|---|---|
| Full suite | `./.venv/bin/python -m pytest -q` | **452 passed, 400 skipped** | `VERIFIED-LOCAL` |
| JSON/YAML artifact checks | `python scripts/check_artifacts.py` | “All JSON/YAML artifacts passed.” | `VERIFIED-LOCAL` |
| Sprint progress bars | `python scripts/update_progress.py --check` | “README sprint bars are current.” | `VERIFIED-LOCAL` |
| Whitespace errors | `git diff --check` | clean | `VERIFIED-LOCAL` |
| GitHub Actions CI | `CI` workflow on Ubuntu 24.04 | Success for commit `44ac4f8` — [run 46041263367](https://github.com/simou-blh/patch-management-agent/actions/runs/46041263367); every step succeeded, including artifact, progress and test checks | `VERIFIED-CI` |

The 400 skips remain the `dpkg --compare-versions` cross-checks; the Ubuntu CI runner
executes them.

S1.5b is ticked in `plan.md` from already-merged work: PR #9, the recorded CI run and the
collector/readiness/partial-host tests. S2.5 is split into four unchecked substeps so its
remaining work can be reviewed separately.

S2.5a added four contract tests for Debian semantics: a revision suffix that does not
reach the fixed revision cannot be proposed (`test_revision_suffix_decides_the_source_comparison`),
tilde versions sort before the fix (`test_tilde_source_version_is_before_the_fix`), a
binary epoch does not override the source comparison
(`test_binary_epoch_does_not_override_the_source_comparison`) and epoch zero equals a
missing epoch (`test_epoch_zero_equals_a_missing_epoch_in_assessment`). Source mapping and
binary/source fixture tests were already present and were not duplicated.

S2.5b added scope-removal refusal and patch simulation/install timeout tests
(`tests/test_patch.py`). Dependency-expansion, invalid-policy and failed
backup/artifact coverage from the merged playbook work was audited and left intact.
A failed preflight still cannot block execution, because `submit_plan` does not consume
preflight evidence (S2.3, Wassim); no test pretends otherwise.

Sprint 3 groundwork added rejection of an unknown run ID (`tests/test_approval.py`) and
systemd health-check timeout and probe-failure paths (`tests/test_verify.py`). The
remaining Sprint 3 test work is blocked on real interfaces: changed template mapping and
duplicate runs need the execution facade (S3.1), and coordinator-level failure handling
and the extended report need S3.4. Live canary cases need lab access and Taha's run.

Not yet done: stale advisory-cache freshness and unavailable-fixed-version matching
(S2.2, Baha); the assessment-to-plan MCP integration (S2.5c); a real assessment (S2.5d);
live canary/recovery scenarios for this branch (S3.5). No checkpoint other than S1.5b is
ticked.

## Update 2026-11-27 (full-project branch)

Branch `dhya/full-project` adds the missing deterministic pipeline between the existing
contracts. Everything below is **synthetic/contract testing**; no live Semaphore task,
VM mutation or real advisory feed is included, and deployment remains blocked.

| Check | Command | Result | Tag |
|---|---|---|---|
| Full suite | `./.venv/bin/python -m pytest -q` | **504 passed, 400 skipped** | `VERIFIED-LOCAL` |
| JSON/YAML artifact checks | `python scripts/check_artifacts.py` | “All JSON/YAML artifacts passed.” | `VERIFIED-LOCAL` |
| Sprint progress bars | `python scripts/update_progress.py --check` | current | `VERIFIED-LOCAL` |
| Whitespace errors | `git diff --check` | clean | `VERIFIED-LOCAL` |
| CLI smoke test | `scripts/build_assessment.py` + `scripts/build_plan.py` | assessment written, plan hash printed, one patch decision | `VERIFIED-LOCAL` |

Added:

- `patch_agent/assessment_builder.py` — Debian source-version matching from evidence +
  advisory cache, producing validated `affected`/`fixed`/`uncertain`/
  `no_known_advisory` results and `patch`/`defer` decisions with exact versions
  (`tests/test_assessment_builder.py`, 11 tests).
- `patch_agent/planner.py` — assessment + evidence to a schema-valid plan, kernel patches
  converted to defers, evidence digest checked (`tests/test_planner.py`, 6 tests).
- `patch_agent/report.py` and an extended `schemas/report.schema.json` — terminal
  `blocked`/`succeeded`/`failed`/`partial`/`aborted` reports with job and recovery
  records (`tests/test_report.py`, 8 tests). The existing blocked report stays valid.
- `patch_agent/executor.py` — approval-bound facade with fixed logical-template mapping,
  duplicate-run blocking, revalidation before each stage, and durable task/log records
  (`tests/test_executor.py`, 7 tests). The transport is injected; no live Semaphore
  adapter is committed.
- `patch_agent/coordinator.py` — canary then sequential fleet, stop on first failure,
  recovery only on the affected host, fleet disabled by default
  (`tests/test_coordinator.py`, 7 tests).
- Approval gates: `validate_plan` and `submit_plan` consume operator-owned
  `assessment.json`/`preflight.json`; `PATCH_AGENT_REQUIRE_GATES=1` makes them mandatory.
  Assessment/evidence digest binding, exact proposed versions, preflight readiness and
  freshness are checked (`tests/test_plan_gates.py` 8 tests, `tests/test_mcp_gates.py`
  3 tests).
- `scripts/build_assessment.py`, `scripts/build_plan.py`, `README-FULL.md` and
  `docs/vulnerable-fixture.md`.

Not yet done: a live Semaphore transport adapter, a live runner for the coordinator, a
real advisory feed, a real assessment of lab evidence, and live canary/recovery through
the facade. Those remain Sprint 2/3/4 live gates; no synthetic result is presented as
live evidence.

## Update 2026-11-27 (teacher-platform agent contract)

The teacher Noyau contract is implemented as an independent FastAPI service under
`agent/`, with `agent.manifest.json`, `Dockerfile` and `requirements-agent.txt`. This is
local/contract testing; no Noyau instance, VM or Semaphore task is started here.

| Check | Command | Result | Tag |
|---|---|---|---|
| Full suite | `./.venv/bin/python -m pytest -q` | **519 passed, 400 skipped** | `VERIFIED-LOCAL` |
| Agent contract tests | `./.venv/bin/python -m pytest tests/agent -q` | **15 passed** | `VERIFIED-LOCAL` |
| Manifest schema | `tests/agent/test_submission.py` | valid manifest + flattened submission payload | `VERIFIED-LOCAL` |
| Docker image | `docker build -t patch-management-agent:test .` | build success; in-container `/health` returned the standard envelope | `VERIFIED-LOCAL` |
| Host port mapping | `curl` to the mapped port | blocked by the local Docker networking; the container health probe and in-container call passed | `NOT-VERIFIED` |
| JSON/YAML artifacts | `python scripts/check_artifacts.py` | pass | `VERIFIED-LOCAL` |

Implemented:

- `GET /health`, `POST /tenant/activate`, `POST /tenant/deactivate`,
  `GET /tenant/{tenant_id}/status`, `GET /config-schema`, and a safe
  `POST /exchange/notify` no-op.
- Standard `{status, data, error}` envelope on success and on HTTP/validation errors.
- Per-tenant hashed directories with evidence, advisories, assessment, preflight, plans
  and reports; deactivation removes the tenant directory and row.
- Tenant authentication from `X-Tenant-Id` + Bearer key; wrong tenant → 404, wrong key →
  403.
- Noyau webhook events: `patch_affected`, `patch_plan_ready`, `patch_preflight_blocked`,
  with severity mapping and failure tolerance.
- Business endpoints: evidence, advisories, assess, plans, preflight, status, and
  operator-only runs (disabled by default; 503 without a live runner).
- `scripts/submit_agent.py` maps the nested manifest to the Noyau’s flattened
  `AgentManifestSubmission`; `scripts/agent_smoke.py` checks the five mandatory routes.

Not yet done: a real Noyau integration run (certification/subscription), a live runner
adapter, and live lab evidence. The teacher reference kernel lives outside Git in
`Seba/`, which is ignored and never committed.

The core CI install does not include FastAPI/httpx; `tests/agent/` is skipped there via
`pytest.importorskip`. The agent suite is verified locally with
`requirements-agent.txt` and by the Docker `/health` check. A maintainer with GitHub
`workflow` scope should add `fastapi==0.165.0`, `httpx==0.27.2` and `uvicorn==0.54.0` to
the CI install step to run it there.
