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
