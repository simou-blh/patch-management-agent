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
