# Sprint 1 runbook

Operational companion to [SETUP.md](../SETUP.md). It does not repeat the full
installation steps; it records what was actually run, on which machine, and what is
still unverified. Requirements: [mvp.md](../mvp.md). Roadmap: [plan.md](../plan.md).

Deployment stays blocked for all of Sprint 1.

## 1. Status legend

| Tag | Meaning |
|---|---|
| `VERIFIED-LOCAL` | Run on a developer machine; output recorded below. No VMs, Docker or network lab needed. |
| `PENDING-LIVE` | Needs the real lab (VMs, SSH, osquery, Semaphore). Owned by the person named; do not treat as passing. |

Mocked/synthetic results and live results are recorded separately (see the
acceptance checklist in section 10).

## 2. Environments

| Role | Machine | Tooling |
|---|---|---|
| Docs, unit tests, synthetic demo | Windows native, no WSL/VirtualBox/Vagrant/Docker | Python (uv selects 3.13), uv, Git, OpenCode |
| Lab, SSH, osquery, Semaphore | Kali WSL2 control node + Windows VirtualBox/Vagrant | See [SETUP.md](../SETUP.md) sections 2-5 |

A machine without WSL or VirtualBox can still run everything tagged `VERIFIED-LOCAL`.
Do not install WSL, VirtualBox or Docker only to work on documentation.

## 3. Verified local commands (Windows PowerShell, repo root)

Re-checked 2026-11-13 on Windows at `main` commit `4a9fd91`. The earlier
2026-10-31 results (99 tests) are kept in [validation.md](validation.md).

```powershell
uv sync
uv run python -m pytest -q
uv run python scripts/check_artifacts.py
uv run python scripts/update_progress.py --check
uv run python scripts/demo.py
```

| Command | Result | Tag |
|---|---|---|
| `uv sync` | 38 packages resolved; 6 updated because `uv.lock` is not in Git | `VERIFIED-LOCAL` |
| `uv run python -m pytest -q` | 344 passed, 400 skipped | `VERIFIED-LOCAL` |
| `uv run python scripts/check_artifacts.py` | "All JSON/YAML artifacts passed." | `VERIFIED-LOCAL` |
| `uv run python scripts/update_progress.py --check` | "README sprint bars are current." | `VERIFIED-LOCAL` |
| `uv run python scripts/demo.py` | All gates PASS, starting with the contract-v1 evidence import; 4 schema-validated JSON reports under `data/demo-*` | `VERIFIED-LOCAL` |

Notes:

- `uv sync` creates an untracked `uv.lock`. Reviewing and committing it belongs to
  the S1.1 owner; do not add it to unrelated PRs.
- The `uv` hardlink warning on some drives is harmless; set `UV_LINK_MODE=copy` to hide it.
- `scripts/check_env.sh` is bash and runs only in WSL.
- The 400 skipped tests are the `dpkg --compare-versions` cross-checks. They need
  Linux `dpkg`, so they are skipped on Windows and run in CI.

## 4. Expected noise in the synthetic demo

`scripts/demo.py` deliberately sends a request for an unknown host and an
unavailable package version. The MCP servers refuse them and print, for example,
`Tool 'query_fleet' failed: ... unknown inventory host` on stderr. PowerShell can
show this as a `NativeCommandError`. The matching lines in the demo output start
with `PASS`, and the run ends with `Demo passed`. This is the intended rejection,
not a failure.

The demo needs no LLM, downloads, Docker or VMs, and does not demonstrate live patching.

## 5. Environment variables and local settings

None of these values belong in Git or in model context.

| Name | Used by | Set by | Notes |
|---|---|---|---|
| `SEMAPHORE_ADMIN_PASSWORD` | `compose.yml`, service `semaphore` | Lab owner (Taha) | Required; Compose refuses to start without it. Lives in `.env`. |
| `SEMAPHORE_ACCESS_KEY_ENCRYPTION` | `compose.yml`, service `semaphore` | Lab owner (Taha) | Required; 32 random bytes, base64. Generate with the command in `.env.example`. |
| `SEMAPHORE_API_TOKEN` | `compose.yml`, profile `upstream` only | Lab owner (Taha) | Created in the Semaphore UI after first startup. Needed only to test the upstream MCP transport; never registered with OpenCode. |
| `PATCH_AGENT_DATA_DIR` | MCP servers and operator CLI | Operator | Moves the state/evidence directory away from `data/`. Never a tool argument. `scripts/demo.py` uses it for its `data/demo-*` folders. |
| `UV_LINK_MODE` | uv | Optional | `copy` hides the hardlink warning on cross-filesystem installs. |
| Model provider credentials | OpenCode `/connect` | Each developer | One provider only. Stored in OpenCode's local credential store, outside the repo. |

Other fixed local settings (committed, operator-owned, keep in sync):

- `lab/hosts.json` and `inventory.ini`: `vm-01` canary `192.168.56.11`, `vm-02` fleet
  `192.168.56.12`, `vm-03` fleet `192.168.56.13`, user `vagrant`, keys under
  `~/.ssh/patch-lab/`.
- `data/evidence.json`: manual, operator-created candidate evidence (format in
  [interfaces.md](interfaces.md)) until the Sprint 1 collector replaces it.
- Semaphore UI `http://localhost:3000`; optional upstream MCP `http://localhost:8500/mcp`.

## 6. Owners and reviewers

From [plan.md](../plan.md). Each owner is paired with the reviewer shown, and PRs go
to `main` through a branch; no direct pushes.

| Owner | Sprint 1 expected result | Reviewer |
|---|---|---|
| Taha BELALOUI | Locked dependencies, three reachable Debian 12 VMs, signed osquery, Semaphore read-only job succeeds | Abderaouf |
| Abderaouf BECHICHE | Structured inspection results from all three hosts; fixed template mapping | Taha |
| Wassim MEFTAH | Collector writes trusted evidence accepted by plan validation; invalid evidence rejected | Baha |
| Baha GAHTAR | Assessment interfaces, tested Debian version helpers, package-fixture specification | Wassim |
| Dhia Eddine LAGHROUR | Passing foundation/collector CI; recorded environment-check results (mocked and live kept separate) | Ahmed |
| Ahmed BOULOUH | Tested runbook, owner/reviewer and interface decisions recorded, agreed sprint acceptance checklist, demo and fixture/reset drafts | Dhia |

## 7. Day-1 interface decisions

Status: **proposed, pending team confirmation.** These restate what the repository
and the sprint plan already imply. Each owner confirms or corrects their line in the
PR review; nothing here changes code.

| # | Decision | Source | Confirm with |
|---|---|---|---|
| 1 | Evidence format is the versioned contract v1 ([evidence-contract.md](evidence-contract.md), S1.2a merged). The validator stands alone; `submit_plan` does not read it yet. | plan.md S1.2 | Abderaouf, Wassim, Baha |
| 2 | Manual `data/evidence.json` stays the plan-validation input until Wassim's collector replaces it. No silent migration to the v1 envelope. | evidence-contract.md | Wassim |
| 3 | Inspection, preflight and verification templates are read-only; patch, verify and recover are simulate-only. Deployment_unblocked defaults to false. | plan.md section 1 | Abderaouf, Taha |
| 4 | Template IDs are agreed between Taha and Abderaouf and recorded in an operator-owned mapping, not in model-visible config. | plan.md S1.2d, SETUP.md | Taha, Abderaouf |
| 5 | Mocked/synthetic results and live results are recorded in separate places and never merged into one pass/fail claim. | Sprint 1 PDF (Dhia) | Dhia |
| 6 | A plan checkbox is ticked only after merged work plus an `Evidence:` reference. This runbook does not tick any. | AGENTS.md, plan.md section 5 | Whole team |
| 7 | Deployment requests stay blocked for every plan, including approved ones, for all of Sprint 1. | interfaces.md | Whole team |

## 8. Demo walkthrough (target script)

Steps follow the Demonstration section of [mvp.md](../mvp.md). Only the steps tagged
`VERIFIED-LOCAL` can be shown today, and they use synthetic data.

| # | Step | Tag | How / who |
|---|---|---|---|
| 1 | Three Debian VMs with controlled pending security updates | `PENDING-LIVE` | Taha (lab, Sprint 1-2); fixture spec from Baha |
| 2 | Collect inventory and advisory evidence | `PENDING-LIVE` | Inventory over SSH/osquery: Sprint 1 gate. Advisory matching: Sprint 2 (Baha) |
| 3 | Display the plan | `VERIFIED-LOCAL` (synthetic) | `demo.py` submits a plan and prints its pending state and SHA-256. Prioritization from real evidence is Sprint 2 |
| 4 | Reject a plan; show no deployment occurs | `VERIFIED-LOCAL` (synthetic) | `demo.py`: "Operator rejection ... no jobs started" |
| 5 | Approve a plan | `VERIFIED-LOCAL` (synthetic) | `demo.py`: operator CLI approves the exact hash; approved deployment is still blocked |
| 6 | Patch and verify the canary | `PENDING-LIVE` | Sprint 3 |
| 7 | Patch and verify vm-02 then vm-03 sequentially | `PENDING-LIVE` | Sprint 4 |
| 8 | Controlled failure scenario | `PENDING-LIVE` | Sprints 3-4 (Dhia injects, Abderaouf/Taha support) |
| 9 | Rollout stops, recovery runs | `PENDING-LIVE` | Sprints 3-4 |
| 10 | Inspect JSON report and Semaphore logs | `PENDING-LIVE` for the full report; blocked-request reports exist locally | Sprint 3-4 (Wassim, Ahmed) |

### 8.1 Show the verified part (steps 3-5)

```powershell
uv run python scripts/demo.py
Get-ChildItem data -Directory | Sort-Object LastWriteTime | Select-Object -Last 1
```

The second command finds the newest `data/demo-*` folder, which holds the readable,
schema-validated JSON reports. The demo output lines to point out, in order:

1. `Unknown host rejected`: queries are refused before SSH.
2. `Approval tool boundary`: the model has no approve/reject tool.
3. `Invalid version rejected`: a version missing from trusted candidates is refused.
4. `Plan submitted`: the plan is stored as pending with its SHA-256.
5. `Unapproved deployment blocked`, `Operator CLI approval`, `Approved deployment blocked`.
6. `Changed plan invalidates approval`, `Stale hash blocked`.
7. `Operator rejection`, then `Report artifacts: 4 schema-validated JSON reports`.

For a manual operator session against your own data directory (a plan must already be
submitted and the hash reviewed):

```powershell
uv run python -m patch_agent.operator show RUN_ID
uv run python -m patch_agent.operator approve RUN_ID --hash REVIEWED_SHA256
uv run python -m patch_agent.operator reject RUN_ID --hash REVIEWED_SHA256
```

Exact plan fields are defined in `schemas/plan.schema.json`. Sanitized plan examples
with patch/defer reasons are Sprint 2 documentation work and are not written yet.

### 8.2 Failure scenarios to demonstrate later (all `PENDING-LIVE`)

Expected results come from the acceptance criteria in [mvp.md](../mvp.md) and the
scenario table in [plan.md](../plan.md). None runs against a real lab yet.

| Scenario | Expected result |
|---|---|
| Missing or rejected approval | No deployment job starts |
| Changed approved plan | Blocked until renewed approval |
| One unreachable inventory host | Other hosts keep their evidence; the failed host is explicit |
| Failed canary preflight | Target unmodified; fleet untouched; reason reported |
| Canary install or health failure | Fleet untouched; recovery attempted and reported |
| Fleet host failure | No later host is patched |
| Recovery failure | Stops with diagnostics and an explicit manual-intervention status |
| Any terminal outcome | A JSON report is generated |

### 8.3 Fixture and reset requirements

- Three Debian 12 VMs from the pinned `bento/debian-12` box (version in `lab/Vagrantfile`),
  one CPU and 768 MB RAM each, created by Vagrant from Windows `C:\lab`.
- Snapshots: `clean` after first boot and `ready` after SSH and osquery work on all three.
  Restoring a snapshot discards every guest change made since it was taken.
- Demo packages: a small, pinned, vulnerable-package fixture whose fixed and previous
  versions remain obtainable (specified by Baha in Sprint 1, built by Taha in Sprint 2).
  Do not rely on whatever updates are pending on the day.
- Reset between scenarios: restore the snapshot, then re-run the read-only environment
  check. Record task IDs and outcomes for each scenario.
- Never use synthetic test versions as live evidence.

## 9. Open blockers

| # | Blocker | Owner | Notes |
|---|---|---|---|
| 1 | The real lab has not been brought up: VMs, SSH from WSL, Docker-to-host-only routing, Semaphore. | Taha | Everything tagged `PENDING-LIVE` depends on it. See the live gates in [SETUP.md](../SETUP.md). |
| 2 | Bootstrap with pinned SHA-256 is merged in [PR #8](https://github.com/simou-blh/patch-management-agent/pull/8); signed-package verification and real VM installation remain unverified. | Taha | Operator command: see [SETUP.md section 4](../SETUP.md#4-ssh-and-osquery). Required before accepting S1.1. |
| 3 | Transitive Python dependencies are not locked in Git; `uv.lock` is generated locally and untracked. | Taha | Review and commit once; others pull it. |
| 4 | The operator importer accepts contract-v1 exports and `inspect.yml` now emits them (read-only run verified on vm-01/vm-02/vm-03 from WSL, outside Semaphore); trusted Semaphore transport is unverified. | Abderaouf, Wassim, Taha | S1.2c merge and the live S1.3 handoff remain pending; do not fabricate exports. |
| 5 | Import/submission enforce freshness and complete successful host results; the operator age limit and producer/consumer agreement still need team confirmation. | Wassim | Explicit policy is required (S1.2b); see [SETUP.md](../SETUP.md) for configuration and legacy-file handling. |
| 6 | `semaphore/templates.json` is a design list; no Semaphore project, credentials or template IDs exist. | Taha, Abderaouf | S1.2d. |
| 7 | Debian version helpers are merged in [PR #6](https://github.com/simou-blh/patch-management-agent/pull/6); advisory/assessment contracts and matching remain pending. | Baha | S1.4a records helper verification; remaining contracts/fixtures belong to Sprint 1, matching to Sprint 2. |
| 8 | Box availability: the pinned Bento version must still be downloadable when the lab is built, and its real size is unmeasured. | Taha | Check before downloading; see [download-budget.md](download-budget.md). |
| 9 | **Resolved:** verification results are dated and installed-tool notes identify the original machine. | Ahmed | [PR #5](https://github.com/simou-blh/patch-management-agent/pull/5) merged on 2026-11-04; the original validation record remains preserved. |
| 10 | `scripts/check_env.sh` is bash and only runs in WSL, so Windows-only machines cannot run it. | Dhia | Record live check results from the lab machine. |
| 11 | Preflight has parser/contract tests but has not run against the live lab; backup roots, configuration paths and recovery artifacts are operator-supplied. | Abderaouf | S2.4; a real run must prove a ready host and a blocked host. |
| 12 | Patch, verify and recovery playbooks are implemented in simulate mode only; `deployment_unblocked` defaults to false. Live patching, service restarts and recovery on the real lab are pending. | Abderaouf | S3.2 and S3.3; requires live lab and approved canary. |
| 13 | The five fixed playbooks ran read-only on vm-01/vm-02/vm-03; the sequential rollout coordinator (Baha) and live fleet rollout are pending. `deployment_unblocked` defaults to false. | Abderaouf, Baha | S4.1; requires live lab, Semaphore templates and approved canary. |

## 10. Sprint 1 acceptance checklist

This checklist records what each Sprint 1 outcome needs and what evidence exists.
It does not tick [plan.md](../plan.md) items. A box there is ticked only after merged
work and a recorded `Evidence:` reference.

Completion gate (from the Sprint 1 plan): real inventory works on vm-01, vm-02 and
vm-03; Semaphore inspection produces trusted candidate evidence; CI passes;
deployment remains blocked.

| Item | Outcome | Mocked/synthetic evidence | Live evidence |
|---|---|---|---|
| S1.1 | Locked dependencies, three reachable VMs, signed osquery, snapshots, read-only Semaphore job | Not applicable | None yet |
| S1.2 | Agreed evidence format; fixed inspection emits it; template mapping and a successful inspection job | Contract v1 validator, fixtures and tests merged (S1.2a); `inspect.yml` v1 producer and parser/contract tests pass locally (S1.2c code) | None yet |
| S1.3 | Operator-owned collector; stale, incomplete and failed-host evidence rejected | Import/publication and approval readiness checks have synthetic coverage; live producer/transport integration remains pending | None yet |
| S1.4 | Advisory/assessment contracts, Debian version helpers with tests, vulnerable-package fixture spec | Version helpers and tests merged in PR #6 (S1.4a); contracts and vulnerable-package fixture remain pending | None yet |
| S1.5 | Passing CI, reviewed runbook and acceptance checklist, real inventory/candidate evidence for all three hosts | Runbook and dated validation/setup corrections merged in PRs #4/#5 (S1.5a). Recorded 2026-10-31: 99 local tests, synthetic demo and progress check passed. CI and interface confirmation remain pending. | None yet |

Local checks to repeat before any Sprint 1 PR (Windows PowerShell, repo root):

```powershell
uv run python -m pytest -q
uv run python scripts/update_progress.py --check
git diff --check
```

Live checks (`PENDING-LIVE`, run on the lab machine, results recorded separately):

- Windows `vagrant status`: three Debian machines running.
- WSL `ansible all -m ping`: three pongs with verified SSH host keys.
- osquery reports Debian 12 on all three machines.
- Semaphore answers; a read-only inspection template completes a task.
- OpenCode lists both local adapters and returns per-host read-only inventory.
- Approved and unapproved deployment requests both remain blocked.
