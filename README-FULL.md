# Patch Management Agent — full project and configuration guide

This document explains how the repository is wired end to end: the Debian lab, Ansible,
osquery, Semaphore, the MCP facade, the approval store, the assessment/plan pipeline and
the execution/report layer. It is the operator/developer guide that complements
[README.md](README.md), [SETUP.md](SETUP.md) and [docs/interfaces.md](docs/interfaces.md).

> **Status:** the code-level pipeline is implemented and covered by the local suite.
> Live deployment remains blocked until the sprint gates are demonstrated on the lab.
> No document here authorizes a mutation; only the operator CLI can approve a plan.

## 1. Architecture

```text
Debian 12 VMs (vm-01..vm-03)
  │  SSH (strict host keys)
  ├── Ansible playbooks: inspect / preflight / patch / verify / recover
  │       └── output contracts: evidence v1, preflight v1, patch v1, verify v1, recover v1
  ├── osquery (fixed, read-only queries) ──► fleet MCP
  └── Semaphore (five fixed templates) ────► execution facade
                                                │
Operator terminal ── collector ──► evidence.json │
        │                          │            │
        ├── advisory cache (Debian security data)
        │        │
        │        └── assessment builder ──► assessment.json
        │                                      │
        ├── planner ───────────────────────────┴──► plan.json
        │                                              │
        ├── approval CLI (human) ◄── submit_plan/hash ─┘
        │        │
        │        └── approved run ──► execution facade ──► coordinator ──► report.json
        │                                  │
        └── preflight envelope ────────────┘
```

Trust boundaries:

- The model sees only the `fleet` and `approval` MCP tools. It never sees Semaphore
  mutation tools, shell access, template IDs or file paths.
- Approval/rejection exists only in `patch_agent.operator`.
- Execution arguments come from the stored approved plan, never from model text.
- `deployment_unblocked`/`allow_mutation` defaults to false.

## 2. Components

| Area | Files | Purpose |
|---|---|---|
| Evidence contract | `schemas/evidence.schema.json`, `patch_agent/evidence.py` | v1 fleet inspection, readiness/freshness |
| Collector | `patch_agent/collector.py` | operator-only atomic import of a trusted export |
| Inspection | `playbooks/inspect.yml`, `playbooks/library/inspect_packages.py` | read-only package/candidate/source collection |
| Advisory/assessment contracts | `schemas/advisory-cache.schema.json`, `schemas/assessment.schema.json`, `patch_agent/assessment.py` | validation of cached advisories and assessment results |
| Assessment builder | `patch_agent/assessment_builder.py` | deterministic matching: affected/fixed/uncertain + patch/defer decision |
| Planner | `patch_agent/planner.py` | assessment + evidence → schema-valid plan |
| Approval store | `patch_agent/approval.py`, `patch_agent/operator.py` | hash-bound human approval, SQLite |
| MCP facade | `patch_agent/approval_mcp.py`, `patch_agent/osquery_mcp.py` | model-facing tools |
| Preflight | `playbooks/preflight.yml`, `playbooks/library/preflight.py`, `patch_agent/preflight.py` | readiness, backups, recovery artifacts |
| Patch/verify/recover | `playbooks/{patch,verify,recover}.yml`, `playbooks/library/*_packages.py` | exact-version canary stages and recovery |
| Execution facade | `patch_agent/executor.py` | approved run → fixed template tasks, durable task IDs |
| Coordinator | `patch_agent/coordinator.py` | canary then sequential fleet, stop on first failure |
| Reports | `schemas/report.schema.json`, `patch_agent/report.py` | terminal run report validation |
| Policies | `policies/services.json`, `patch_agent/policies.py` | fixed restarts/health checks |
| Semaphore | `compose.yml`, `semaphore/ids.json`, `docs/semaphore-setup.md` | orchestration layer |
| Lab | `lab/Vagrantfile`, `inventory.ini`, `lab/hosts.json` | three Debian 12 VMs |

## 3. Prerequisites

- Python 3.12+ (the project is tested with 3.12 and newer).
- WSL2/Kali or a Linux control node with Ansible, SSH and Docker.
- VirtualBox + Vagrant for the three Debian 12 VMs.
- osquery 5.24.0 on each VM (pinned package).
- Semaphore (Docker image pinned in `compose.yml`).
- The Python dependencies pinned in `pyproject.toml`:
  `mcp==2.3.0`, `jsonschema==4.26.0`; dev: `pytest==9.1.1`, `PyYAML==6.0.3`.
- The teacher-platform agent runtime is installed from `requirements-agent.txt`
  (`fastapi==0.165.0`, `httpx==0.27.2`, `uvicorn==0.54.0`, `jsonschema==4.26.0`).

```bash
python -m venv .venv
. .venv/bin/activate
pip install "mcp==2.3.0" "jsonschema==4.26.0" "pytest==9.1.1" "PyYAML==6.0.3"
python -m pytest -q
python scripts/check_artifacts.py
```

## 4. Environment variables

| Variable | Who sets it | Meaning |
|---|---|---|
| `PATCH_AGENT_DATA_DIR` | operator | state/evidence directory (default `./data`). Never a model argument. |
| `PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS` | operator | positive freshness limit; required for import and plan submission |
| `PATCH_AGENT_REQUIRE_GATES` | operator | `1` requires `assessment.json` and `preflight.json` for submission |
| `SEMAPHORE_URL` | operator shell | e.g. `http://localhost:3000` |
| `SEMAPHORE_API_TOKEN` | operator shell | never printed, committed or passed to the model |
| `SEMAPHORE_ADMIN_PASSWORD` | `.env` | first-boot admin password |
| `SEMAPHORE_ACCESS_KEY_ENCRYPTION` | `.env` | 32-byte key; losing it invalidates stored keys |

`.env` is git-ignored. Tokens belong only in the operator environment.

## 5. Lab and SSH

```bash
cd lab
vagrant up
vagrant status
```

- VMs: `vm-01` 192.168.56.11, `vm-02` .12, `vm-03` .13; user `vagrant`.
- `inventory.ini` and `lab/hosts.json` must use the same host names.
- Verify fingerprints against each VM console before trusting `known_hosts`.
- `ansible.cfg` enforces `StrictHostKeyChecking=yes` and
  `UserKnownHostsFile=~/.ssh/known_hosts`. Never disable it.

Sync the Vagrant key for your control node:

```bash
./scripts/sync_lab_keys.sh
ssh -o BatchMode=yes vagrant@192.168.56.11 true
```

## 6. osquery

Install the pinned package with the operator playbook:

```bash
ansible-playbook -i inventory.ini setup/osquery_bootstrap.yml
```

The playbook downloads `osquery_5.24.0-1.linux_amd64.deb` once and verifies its SHA-256
before installing. Confirm:

```bash
ansible -i inventory.ini all -m command -a "osqueryi --version"
```

osquery is queried only through the fixed SQL in `patch_agent/osquery.py`; the MCP server
exposes `inventory_catalog()` and `query_fleet(hosts, query_id)`. Query IDs are fixed:
`os_version`, `packages`, `processes`, `listening_ports`. Unknown hosts/queries fail
before SSH.

## 7. Ansible playbooks

| Playbook | Kind | Output |
|---|---|---|
| `playbooks/inspect.yml` | read-only | evidence v1 envelope (`fleet_evidence`) |
| `playbooks/preflight.yml` | read-only + optional backup/cache | preflight v1 readiness |
| `playbooks/patch.yml` | mutate only when unblocked | patch v1 result |
| `playbooks/verify.yml` | read-only | verify v1 result |
| `playbooks/recover.yml` | mutate only when unblocked | recover v1 result |

Run from the repository root:

```bash
ansible-playbook -i inventory.ini playbooks/inspect.yml
```

Semaphore templates run the same committed playbooks; local working-tree edits are not
used by Semaphore. Commit and push before running a template.

## 8. Semaphore

Create a git-ignored `.env` with the two required values (never commit it):

```bash
cat > .env <<'EOF'
SEMAPHORE_ADMIN_PASSWORD=replace-with-a-strong-password
SEMAPHORE_ACCESS_KEY_ENCRYPTION=replace-with-32-bytes-of-random-text
EOF
docker compose config --quiet
docker compose up -d semaphore
curl --fail http://localhost:3000/api/ping
```

Follow [docs/semaphore-setup.md](semaphore-setup.md) for:

- the SQLite database-path trap (move it into `/etc/semaphore`);
- the SSH known-hosts mount and `ansible.cfg` override;
- project, key, inventory, repository and five template creation;
- recording template IDs in `semaphore/ids.json`.

The five logical templates are `inspect`, `verify`, `preflight`, `patch`, `recover`.
`patch` and `recover` are fail-gated. Never register the upstream Semaphore MCP server
with OpenCode; use the `upstream` profile only for operator transport tests.

Smoke test: run `inspect` in the UI; expect `ok=6/2/2` and a contract-valid
`fleet_evidence` envelope.

## 9. MCP and OpenCode

`opencode.json` denies all tools except `fleet_*` and `approval_*`, and launches:

- `python -m patch_agent.osquery_mcp` (fleet)
- `python -m patch_agent.approval_mcp` (approval)

Do not add shell, file-write, network or upstream Semaphore tools to this project.
The model-facing approval tools are exactly `submit_plan`, `approval_status` and
`request_deployment`.

## 10. Evidence → assessment → plan

### 10.1 Collect trusted evidence

Import a contract-v1 inspection export (operator only):

```bash
export PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS=86400
python -m patch_agent.collector export.json --targets vm-01 vm-02 vm-03
```

The collector validates and atomically publishes `data/evidence.json`. It rejects stale,
future, incomplete, failed-host or legacy-map records. It does not authenticate the
export's origin; the Semaphore transport and verified host keys are the trust chain.

### 10.2 Cache advisories

Place the Debian security data for one release in `data/advisory-cache.json` following
`schemas/advisory-cache.schema.json`. The cache records `fetched_at`, the source URI and
per-source-package advisories. No credentials, query strings or fragments.

### 10.3 Build the assessment

```bash
python scripts/build_assessment.py \
  --evidence data/evidence.json \
  --advisories data/advisory-cache.json \
  --output data/assessment.json
```

Matching compares the **source** package version with Debian ordering (epochs, revisions,
tilde), never the binary version as a string. Results are `affected`, `fixed`,
`uncertain` or `no_known_advisory`; decisions are `patch`/`defer` with exact proposed
versions and priorities. An affected package is only patched to a candidate that
resolves every affected advisory.

### 10.4 Generate the plan

```bash
python scripts/build_plan.py \
  --assessment data/assessment.json \
  --evidence data/evidence.json \
  --run-id sprint2-demo --canary vm-01 \
  --output data/plan.json
```

The planner binds the assessment digest to the evidence, converts kernel patches to
defers, and validates the plan against the evidence candidates. It prints the plan hash.

## 11. Approval

Publish the operator documents into the same data directory:

```text
data/evidence.json        (required)
data/assessment.json      (required when PATCH_AGENT_REQUIRE_GATES=1)
data/preflight.json       (required when PATCH_AGENT_REQUIRE_GATES=1)
```

`submit_plan` reads these files itself; their paths are never model arguments. With
`PATCH_AGENT_REQUIRE_GATES=1`, missing gates are rejected. `validate_plan` additionally
checks:

- assessment/evidence digest binding;
- each plan patch matches the assessed decision and version;
- a plan cannot defer a package the assessment proposes to patch;
- preflight targets match the plan and every host is `ready`;
- the preflight record is fresh.

Human decision:

```bash
python -m patch_agent.operator show RUN_ID
python -m patch_agent.operator approve RUN_ID --hash REVIEWED_SHA256
python -m patch_agent.operator reject RUN_ID --hash REVIEWED_SHA256
```

Re-submitting identical JSON preserves a decision; changing the plan resets it to pending.

## 12. Execution facade and coordinator

The facade is deliberately transport-injected and operator-controlled:

```python
from patch_agent.approval import local_store
from patch_agent.executor import ExecutionFacade, RunStore, TemplateMap

facade = ExecutionFacade(
    local_store(),
    RunStore(local_store().directory),
    transport,                         # operator-owned Semaphore transport
    TemplateMap.from_file("semaphore/ids.json"),
    allow_mutation=False,              # enable only after the live gates pass
)
facade.begin(run_id, plan_hash)
facade.start_stage(run_id, "vm-01", "preflight")
facade.refresh(run_id)
```

- `begin` rechecks the approval hash, duplicates and the evidence/assessment/preflight
  gates (when files are present).
- `start_stage` resolves the fixed logical template from `semaphore/ids.json`; the model
  never supplies a template, playbook, host list or extra vars.
- `patch`/`recover` require `allow_mutation=True`.
- Task IDs and log references are persisted in `execution.sqlite`.

The coordinator owns canary/fleet order:

```python
from patch_agent.coordinator import Coordinator

report = Coordinator(runner).run(plan, plan_hash=plan_hash, allow_fleet=False)
```

`runner` implements `preflight(host)`, `patch(host)`, `verify(host)`, `recover(host)` and
returns structured status/task/log fields. The default keeps fleet execution disabled.
On failure it stops, recovers only the affected host and marks later hosts skipped.

Reports are validated by `patch_agent/report.py`: `blocked`, `succeeded`, `failed`,
`partial`, `aborted`; jobs carry host/stage/template/task ID/status/timestamps/log ref;
recovery carries host/status/detail.

## 13. Verification

```bash
python -m pytest -q
python scripts/check_artifacts.py
python scripts/update_progress.py --check
git diff --check
```

Live environment checklist:

```bash
export SEMAPHORE_URL=http://localhost:3000
export SEMAPHORE_API_TOKEN=...   # operator shell only
python scripts/check_env.py --live
```

Expected: SSH to all three hosts, osquery installed, Docker/Ansible present, Semaphore
ping/auth. Results are recorded separately from mocked tests.

## 14. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `No ED25519 host key is known` | empty container `known_hosts`; mount the verified file and keep strict checking |
| Semaphore loses projects after recreate | SQLite DB in the container layer; move it to `/etc/semaphore` |
| `Could not connect to github.com` in Semaphore | host-network flakiness; retry, never weaken checks |
| `set PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS` | operator policy missing; set a positive integer |
| `evidence is stale` | collect again or adjust the operator policy deliberately |
| `preflight blocks: ...` | a host is not ready; fix the check or preparation, do not bypass |
| `plan changed` | the plan was edited after approval; review and approve the new hash |
| `mutation is blocked` | `allow_mutation` is false; enable only after the live gates pass |
| `run already exists` | duplicate run; use a new run ID after reviewing the prior outcome |

## 15. Safety and current limits

- Deployment remains blocked by default. `patch`/`recover` are fail-gated.
- Raw logs, tokens, keys and machine-specific paths stay outside Git.
- The live Semaphore transport adapter is not committed here; the facade is transport
  injected so the operator can bind the verified endpoint without exposing it to the
  model.
- Sprint completion still requires the live lab gates: real inventory, a real assessment,
  a real canary, recovery and reports, plus teammate confirmations. Code and synthetic
  tests alone are not live evidence.

## 16. Teacher platform agent

The repository now also delivers the teacher-platform **agent** described in
[docs/AGENT_DELIVERY.md](AGENT_DELIVERY.md):

- `agent.manifest.json` — `filiere: cybersecurite`, category `patch_management`
- `agent/` — FastAPI service exposing the 5 mandatory endpoints with the standard
  envelope, tenant isolation, config schema and Noyau webhook alerts
- `Dockerfile` + `requirements-agent.txt`
- `scripts/submit_agent.py` — adapter for the Noyau’s flattened submission schema
- `scripts/agent_smoke.py` — local 5-endpoint smoke test
- `tests/agent/` — contract, isolation, webhook and business tests

Run it separately from the Noyau:

```bash
uvicorn agent.main:create_app --factory --host 0.0.0.0 --port 9000
```

`Seba/` (teacher reference kernel) is ignored and never committed; the Noyau runs from a
separate folder. See the delivery guide for submission, certification, subscription,
tenant isolation, purge, webhook and push instructions.
