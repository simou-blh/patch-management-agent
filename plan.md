# PLAN: who does what, in which order

Working plan for the six members of the AI Patch Agent team (v2: aligned with the teacher's core, verified from its source code).

Related files: [README.md](README.md) (concept), [SETUP.md](SETUP.md) (identical environment, **do it first**), [`docs/reference/PROJECT_FULL_REFERENCE.md`](docs/reference/PROJECT_FULL_REFERENCE.md) (all teacher documents **and the full source code of the core**), `docs/reference/ai-patch-agent-guide.html` (technical guide).

> **What changed in v2:** the plan now relies on what the core *really does* (section 1B), not only on what the documents say. Four consequences: (1) the guide's `curl ... -d @agent.manifest.json` fails, so we use `scripts/submit_agent.py`; (2) the web UI activates agents with an **empty config**, so hosts are set afterwards through a new `PUT /tenant/{id}/config` endpoint; (3) every contract endpoint must answer in **under 10 seconds**; (4) the core must run **locally** (PostgreSQL included) for every integration test (section 5).

---

## 0. Start here

**Everyone, in this order:**

1. Read sections 1 to 8 of this file (30 min).
2. Read the parts of `PROJECT_FULL_REFERENCE.md` listed for your role below.
3. Complete `SETUP.md`, then run the contract simulation (section 5.5) once you have an API to test.
4. Go to your own tasks in section 9.

**Reading list** (section numbers refer to `PROJECT_FULL_REFERENCE.md`):

| Member | Must read |
|---|---|
| **Everyone** | §0 (overview), §2 (integration contract), §4 (developer guide), §13 (real behavior of the core), §14 (pitfalls and checklist) |
| Ahmed | §7 (manifest), §13.4 (submission format), §13.5 (what the core reads), §12-14 |
| Taha | §1 (core installation), §11.2 (`database.py`), §13.8 (network and PostgreSQL), §13.11 (test scenario) |
| Abderaouf | §2 section 7 (security rules), the technical guide HTML |
| Wassim | §2 section 7, §11.4 (`security.py`), §11.12 (webhooks), §13.7 (alerts), §13.9 (security) |
| Baha | §11.5 (`agent_gateway.py`: 10 s timeout), §13.3, §13.7 |
| Dhia | §2, §6 (example `main.py`), §8 (Dockerfile), §11.5, §11.9, §11.10, §13.1 to §13.5, §13.10, §13.11 |

---

## 1. Platform facts that drive our design

### 1A. Requirements from the contract

Our agent is not only a CLI tool: it must be a **service** that the platform core can talk to.

| Requirement | What it means for us |
|---|---|
| Independent HTTP service in its own Docker container | `api/` layer (FastAPI) on top of the agent logic. |
| **Python must be used** | Already our case. |
| 5 mandatory endpoints: `GET /health`, `POST /tenant/activate`, `POST /tenant/deactivate`, `GET /tenant/{tenant_id}/status`, `GET /config-schema` | `api/main.py` (section 9.6). Paths are **fixed** (see 1B). |
| **Every** response uses the envelope `{"status": "ok"\|"error", "data": ..., "error": ...}`, errors included | Custom exception handlers. A wrong envelope **suspends the subscription**. |
| `agent.manifest.json` at the **repo root**, `filiere` = `cybersecurite`, unique `slug` | Ahmed (section 9.1). |
| Working, standalone `Dockerfile`; the port must match `base_url` | Dhia (section 9.6). Port **9000** like the example agent. |
| Strict **tenant isolation** | One data folder per tenant, validated tenant ids, no global state. |
| `POST /tenant/deactivate` really **deletes** the tenant data | `purge_tenant()`. |
| No secrets in code, no sensitive data in logs | `.env`, secrets only from environment. |
| No network call to a service not **mentioned in the execution report** | Reports list every outbound service (LLM providers, OSV.dev, the core). |
| Alerts go to `POST {NOYAU_URL}/webhooks/agent-events` | `notifier.py` (section 9.4). |
| Agents never call other agents | We do not. `produces` and `consumes` stay empty. |

### 1B. What the core really does (verified in its source code)

This table is the most important part of v2. Source: `PROJECT_FULL_REFERENCE.md` §11 (code) and §13 (analysis).

| # | Fact about the core | Consequence for us | Ref |
|---|---|---|---|
| F1 | `POST /agents/submit` expects a **flat JSON** (`developer_email`, `base_url`, `manifest`, ...), not the manifest file. The guide's `curl -d @agent.manifest.json` returns **422**. | `scripts/submit_agent.py` converts the manifest (Ahmed). | §13.4 |
| F2 | Only `endpoints.base_url` is read from the manifest. All other paths use **fixed defaults**: `/tenant/activate`, `/tenant/deactivate`, `/exchange/notify`. | Never rename these paths. | §13.5 |
| F3 | The core only ever calls `activate`, `deactivate` and (if consumed) `exchange/notify`. It **never** calls `/health`, `/status` or `/config-schema`. | They stay mandatory (the teacher checks them by hand) but are not what breaks activation. | §13.5 |
| F4 | Every core-to-agent call is a `POST` with a **10 s timeout**, expects HTTP **2xx** and a JSON object with `status` = `ok` or `error`. | All contract endpoints answer fast; real work runs in background threads. A non-2xx code is how we refuse an activation. | §13.3 |
| F5 | Any failure (timeout, non-2xx, bad JSON) sets the subscription to `suspended`. In the **web UI this is silent** (badge "Suspendu", no message); the **API** `/subscriptions` returns 502 with the reason. | Debug from our agent logs; test through the API when you need the reason. | §13.3 |
| F6 | Each call carries `Authorization: Bearer <tenant_api_key>`, `X-Tenant-Id: <company id>` (a **UUID**) and a static `X-Platform-Signature: core-gateway` (not a real signature). `deactivate` is sent with body `{}`. | Accept UUID tenant ids; compare the bearer token with the key stored at activation; ignore the static signature. | §13.3, §13.9 |
| F7 | The **web UI subscription sends an empty config** (`{}`). Only the JSON API `POST /subscriptions` can pass a `config`. | Activation must succeed with an empty config; hosts are provided later through `PUT /tenant/{id}/config` (section 3, 9.6). | §11.14, §11.10 |
| F8 | The company sees its `tenant_api_key` in `/mon-compte`. | That key is what the company uses to call our `PUT config` and run endpoints. | §11.15 |
| F9 | Each new subscription generates a **new** tenant key; activation overwrites the key we stored. | `activate` always replaces the stored key. | §11.14 |
| F10 | Cancelling calls `deactivate`, then marks the subscription cancelled **even if our agent fails**; there is no retry. | `purge_tenant` must be reliable and idempotent. | §11.10 |
| F11 | The webhook accepts an event if `tenant_api_key` + `X-Tenant-Id` match a subscription (status not checked). Events are shown in `/mon-compte` (last 20) and `/admin` (last 30), payload in clear. | Alert `data` carries **no secret, no host data, no raw LLM output**. | §13.7 |
| F12 | The core needs **PostgreSQL** at startup (`create_all`), and pins versions (fastapi 0.115.0, pydantic 2.9.2, bcrypt 4.0.1...). | Run the core in its own virtual environment; PostgreSQL via Docker. | §13.8 |
| F13 | The `/admin` page has **no activate/deactivate buttons** (only certify, publish, suspend). Deactivation happens through `POST /subscriptions/{id}/cancel` (API). | Open question 9 (section 12). | §11.14 |

---

## 2. Target repository structure

(Updates section 8 of the README.)

```text
ai-patch-agent/
├── README.md  PLAN.md  SETUP.md
├── agent.manifest.json            # repo root, required by the contract
├── Dockerfile  .dockerignore  .gitignore  .env.example
├── requirements.txt  requirements-dev.txt  requirements.lock
├── ansible.cfg  inventory.ini     # inventory.ini = local lab (CLI mode)
├── lab/Vagrantfile
├── scripts/
│   ├── sync_lab_keys.sh  check_env.sh  reset_lab.sh     # lab (Taha)
│   ├── submit_agent.py                                  # manifest -> core submission (Ahmed)
│   └── simulate_core.sh                                 # replays the core's calls (Dhia)
├── playbooks/                     # install_osquery, osquery_query, check_updates, patch, rollback
├── agent/
│   ├── __init__.py
│   ├── context.py                 # TenantContext, per-tenant paths, state file
│   ├── inventory.py               # validated inventory generation from tenant config
│   ├── tools.py                   # osquery / apt / OSV / deploy / rollback + validation
│   ├── llm.py                     # providers + fallback + JSON validation
│   ├── graph.py                   # LangGraph workflow
│   ├── runner.py                  # run / resume / status (CLI and API both use it)
│   ├── notifier.py                # webhook alerts to the core
│   ├── main.py                    # CLI
│   └── ask.py                     # bonus
├── api/main.py                    # FastAPI service (contract + our endpoints)
├── tests/                         # test_tools.py, test_contract.py, test_scenarios.py
├── data/                          # runtime, git-ignored (data/tenants/<tenant_id>/...)
├── noyau-local/                   # the teacher's core, unzipped, git-ignored, NEVER modified
└── docs/ (architecture.md, roles.md, core-local.md, security.md, lab.md, meetings/, reference/)
```

Add to `.gitignore`: `data/`, `.env`, `noyau-local/`, `.venv*/`.

`docs/reference/` contains: `PROJECT_FULL_REFERENCE.md`, `ai-patch-agent-guide.html`, and the **teacher's zip** (kept as an archive, original files untouched).

Per-tenant runtime layout (created automatically, never committed):

```text
data/tenants/<tenant_id>/
├── state.json          # tenant api key (chmod 600), ecosystem, configured flag
├── inventory.ini       # generated from the tenant config
├── checkpoints.db      # LangGraph SQLite checkpoints
├── runs.json           # run states
└── reports/            # one JSON report per run
```

---

## 3. Interfaces between modules (agree on these first)

These signatures let everyone work **in parallel**. Change one only through a PR that every owner reviews.

`TenantContext` (owner: Wassim), passed as the first argument everywhere:

```python
ctx.tenant_id      # validated: ^[A-Za-z0-9_-]{1,64}$  (a UUID from the core is valid)
ctx.ecosystem      # e.g. "Ubuntu:22.04:LTS"
ctx.inventory      # Path to the inventory used for this tenant
ctx.checkpoints_db # Path
ctx.reports_dir    # Path
```

| Module | Function | Returns |
|---|---|---|
| `tools` | `run_osquery(ctx, sql, target="all")` | `{host: rows}` or `{host: {"error": ...}}` |
| `tools` | `get_upgradable(ctx, target="all")` | `{host: [{"name", "new", "old"}]}` |
| `tools` | `osv_lookup(name, version, ecosystem)` | `{"count": int, "ids": [...], "summary": str}` |
| `tools` | `deploy(ctx, target, packages, dry_run=False)` | `{host: {"ok": bool, "reboot_required": bool, "pins": {...}}}` |
| `tools` | `rollback(ctx, host, pins)` | `{"ok": bool, ...}` |
| `llm` | `chat(system, user)` | `{"plan": dict, "provider": str}`; raises `RuntimeError` only if all providers fail |
| `graph` | `build(ctx)` | uncompiled `StateGraph` bound to `ctx` |
| `runner` | `run(ctx)` / `resume(ctx, run_id, decision)` | blocking, for the CLI |
| `runner` | `start_run(ctx)` / `start_resume(ctx, run_id, decision)` | non-blocking (thread), for the API |
| `runner` | `get_run(ctx, run_id)` | `{"run_id", "state", "plan"?, "report"?, "error"?}` |
| `notifier` | `send_event(ctx, event_type, severity, data)` | `bool`, **never raises** |

Run states: `running`, `waiting_approval`, `done`, `failed`.

**HTTP surface of our agent** (owner: Dhia):

| Method | Path | Auth | Part of |
|---|---|---|---|
| GET | `/health` | none | contract |
| POST | `/tenant/activate` | bearer + `X-Tenant-Id` (sent by the core) | contract |
| POST | `/tenant/deactivate` | bearer + `X-Tenant-Id` (sent by the core) | contract |
| GET | `/tenant/{tenant_id}/status` | `X-Tenant-Id` optional | contract |
| GET | `/config-schema` | none | contract |
| POST | `/exchange/notify` | none | contract (no-op) |
| PUT | `/tenant/{tenant_id}/config` | bearer + `X-Tenant-Id` | ours (F7: set hosts after an empty activation) |
| POST | `/tenant/{tenant_id}/runs` | bearer + `X-Tenant-Id` | ours |
| GET | `/tenant/{tenant_id}/runs/{run_id}` | bearer + `X-Tenant-Id` | ours |
| POST | `/tenant/{tenant_id}/runs/{run_id}/approve` | bearer + `X-Tenant-Id` | ours |

Alert events sent to the core (severity must be one of `info|low|medium|high|critical`). The `data` field holds only counts, package names and the run id (F11):

| event_type | When | Severity |
|---|---|---|
| `patch_plan_ready` | plan produced, waiting for approval | highest priority in the plan (`critical`/`high`), else `medium` |
| `patch_canary_failed` | canary deployment or verification failed | `high` |
| `patch_rollback_done` | rollback executed | `high` |
| `patch_fleet_done` | fleet patched and verified | `info` |

---

## 4. Fixes to apply

### 4A. Bugs and gaps in the guide's code (do not copy blindly)

| # | Issue | Owner |
|---|---|---|
| 1 | **Bug:** in `tools.py` the apt regex group is named `n` (`(?P<n>...)`) but `graph.py` reads `p["name"]`, which raises `KeyError`. Rename the group to `name`. | Wassim |
| 2 | Flat imports (`import tools`, `from llm import chat`) do not work from `api/`. Make `agent/` a package: `from agent import tools`, run the CLI with `python -m agent.main`. | Wassim + Baha |
| 3 | Everything uses global paths (`inventory.ini`, `checkpoints.db`, `reports/`). Replace them with `ctx.*` for tenant isolation. | Wassim + Baha |
| 4 | `validate_sql` can be bypassed with comma joins: `SELECT * FROM users, file ...` only sees `users`. Use the hardened version in section 9.4 and test it. | Wassim, tests by Dhia |
| 5 | In `graph.verify`, package names go into an SQL string. Validate them with `tools.PKG_RE` before building the query. | Baha |
| 6 | Add **dry-run** (`ansible-playbook --check`) before the real canary deployment (SMART objective 3: "dry-run then real"). `command` tasks are skipped in check mode. | Wassim (tool), Baha (graph node) |
| 7 | Rollback must only target hosts that were really patched. | Baha |
| 8 | Reports must contain `tenant_id`, the run id, timestamps and a `network_calls` list (LLM provider used, `api.osv.dev`, the core webhook). | Wassim |
| 9 | Logs: never log API keys, tenant keys, SSH key paths or LLM raw prompts that contain host data. | everyone |
| 10 | The LLM must never receive hostnames or IPs (already the design, add a test). | Dhia |

### 4B. Fixes imposed by the core (new in v2)

| # | Issue | Owner |
|---|---|---|
| 11 | Replace the guide's submission `curl -d @agent.manifest.json` with `scripts/submit_agent.py` (F1). | Ahmed |
| 12 | Contract endpoints answer in well under 10 s and never run agent work inline (F4). Runs stay in threads. | Dhia, Baha |
| 13 | Verify the bearer token (constant-time compare) on `deactivate` and on every endpoint of ours (F6). | Dhia |
| 14 | Activation must succeed with an **empty config**; add `PUT /tenant/{id}/config` for the hosts (F7). | Dhia |
| 15 | Alert `data`: no secret, no hostname/IP, no SSH path, no raw LLM output; counts, package names and run id only (F11). | Wassim, Baha |
| 16 | `purge_tenant` idempotent and safe when the folder does not exist (F10). | Wassim |
| 17 | Accept a **UUID** as tenant id (F6), covered by a test. | Dhia |

---

## 5. Running the core and the agent together

Every integration test goes through the teacher's core. Owner of this section: **Taha** (writes `docs/core-local.md` from it in Sprint 0); **Dhia** owns the end-to-end test (5.6).

### 5.1 Where the core lives

Unzip the teacher's archive into `noyau-local/` (git-ignored). **Never modify it.** If the teacher publishes a new version, replace the folder and tell the team.

### 5.2 PostgreSQL (the core refuses to start without it)

```bash
docker run -d --name pg-plateforme \
  -e POSTGRES_USER=saas_user -e POSTGRES_PASSWORD=saas_pass -e POSTGRES_DB=plateforme_agents \
  -p 5432:5432 postgres:16
```

These are the defaults hard-coded in the core's `database.py`.

### 5.3 Start the core (own virtual environment: its pinned versions can conflict with ours)

```bash
cd noyau-local
python3 -m venv .venv-core && source .venv-core/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg2://saas_user:saas_pass@localhost:5432/plateforme_agents"
export JWT_SECRET_KEY="any-long-random-string"
uvicorn app.main:app --reload --port 8000
# in a second terminal, once: python scripts/create_admin.py
```

Pages: `http://localhost:8000/` (home), `/inscription`, `/connexion`, `/catalogue`, `/mon-compte`, `/admin`, API docs at `/docs`.

### 5.4 Where is what: URLs to use

| Core runs | Agent runs | `base_url` in the manifest | `NOYAU_URL` for the agent |
|---|---|---|---|
| WSL/Linux host | uvicorn on the same host | `http://localhost:9000` | `http://localhost:8000` |
| WSL/Linux host | Docker (`-p 9000:9000`) | `http://localhost:9000` | `http://host.docker.internal:8000` |
| Windows host | WSL | `http://localhost:9000` (test!) | Windows host IP seen from WSL (test!) |

On Linux Docker, add `--add-host=host.docker.internal:host-gateway` to `docker run`. The Windows/WSL row is **not guaranteed**: Taha tests both directions in Sprint 1 and writes the result in `docs/core-local.md`.

### 5.5 Simulate the core first (no core needed)

Before involving the real core, replay exactly what its gateway sends. File `scripts/simulate_core.sh` (owner: Dhia), bash/WSL:

```bash
#!/usr/bin/env bash
# Replays what the core's agent gateway sends to an agent.
# Usage: scripts/simulate_core.sh [base_url]   (default http://localhost:9000)
set -euo pipefail
BASE="${1:-http://localhost:9000}"
TID="${TID:-$(python3 -c 'import uuid;print(uuid.uuid4())')}"      # the core uses UUID tenant ids
KEY="tak_$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
H=(-H "Authorization: Bearer $KEY" -H "X-Tenant-Id: $TID"
   -H "X-Platform-Signature: core-gateway" -H "Content-Type: application/json")

echo "== activate (empty config, like the web UI)"
curl -sS -m 10 -X POST "$BASE/tenant/activate" "${H[@]}" -d '{"config": {}}'; echo
echo "== health";          curl -sS -m 10 "$BASE/health"; echo
echo "== config-schema";   curl -sS -m 10 "$BASE/config-schema" | head -c 200; echo
echo "== status";          curl -sS -m 10 "$BASE/tenant/$TID/status"; echo
echo "== deactivate (body {})"
curl -sS -m 10 -X POST "$BASE/tenant/deactivate" "${H[@]}" -d '{}'; echo
echo "== status after deactivate (must be an error envelope, HTTP 404)"
curl -sS -m 10 -w '\nHTTP %{http_code}\n' "$BASE/tenant/$TID/status"
```

`-m 10` mimics the core's 10-second timeout. Every response must be the envelope.

### 5.6 End-to-end scenario (what we show the teacher)

```text
 1. PostgreSQL up (5.2), core up (5.3), admin created
 2. Agent up (uvicorn or Docker), simulate_core.sh passes
 3. python scripts/submit_agent.py http://localhost:8000      -> agent "Soumis"
 4. Browser, /connexion as admin -> /admin: Certifier, then Publier
 5. /inscription: create test company A, then /catalogue: Souscrire
 6. /mon-compte: badge "Actif" (not "Suspendu") + tenant key; note the company id
 7. Configure the hosts: PUT {agent}/tenant/<company id>/config with the tenant key (9.6)
 8. Start a run, approve it, see canary then fleet on the lab
 9. /mon-compte: the alert events appear ("patch_plan_ready", "patch_fleet_done")
10. Isolation: create test company B, subscribe; B must never see A's runs, hosts or reports
11. Cancel A: POST /subscriptions/<id>/cancel on the core API -> data/tenants/<id> is deleted
```

> Reminder (PowerShell users): use `curl.exe`, and avoid the `\` line continuations of bash examples. In WSL everything above works as written.

### 5.7 Debugging tips

- Badge "Suspendu" right after subscribing: the activation failed. Look at the **agent logs**, then reproduce with `simulate_core.sh`. To get the reason from the core, subscribe through `POST /subscriptions` (API docs at `/docs`): it returns 502 with the message.
- "Slug already exists" on submission: change `slug` (or delete the row in PostgreSQL) to resubmit.
- The agent shows `Tenant not active` after a restart of the container: `data/` was not on a volume. Use the `ai_patch_data` volume.

---

## 6. Sprint calendar

Weekly sprints. **Ahmed fixes the actual dates** once the consolidated module calendar is known (dates in the teacher's calendar win over this table). End of each sprint: 15-minute internal demo and a retro written up as minutes.

| Sprint | Goal | Exit criteria (all must be true) |
|---|---|---|
| **0: Setup** | Same environment for everyone, repo ready, contracts read | `check_env.sh` green for all 6; repo with protected `main`; everyone read their part of `PROJECT_FULL_REFERENCE.md` (section 0 table); **core runs locally for at least Taha, Dhia and Ahmed** (section 5); `docs/core-local.md` written; open questions (section 12) sent to the supervisors |
| **1: Lab + skeleton** | Lab running, playbooks, API skeleton | 3 VMs, snapshots `clean` and `ready`; `ansible all -m ping` OK; 5 playbooks written; `api/main.py` answers the 5 endpoints **and passes `simulate_core.sh`**; `scripts/submit_agent.py` works against the local core; `requirements.lock` committed; Windows/WSL network test documented |
| **2: Tools + LLM** | Collect, enrich, analyze | `tools.py` complete with `ctx`; hardened `validate_sql` tested; `llm.py` with fallback tested on 2 providers; `collect → enrich → analyze` produces a valid plan on the lab |
| **3: Workflow** | Full pipeline with approval | `approve → dry-run → canary → verify → fleet / rollback → report` runs end to end from the CLI; checkpoints resume after a restart; runner, `PUT config` and run endpoints working; **alerts visible in the core's `/mon-compte`** |
| **4: Compliance + Docker** | Contract certified | Docker image builds and runs; conformity tests green; agent submitted, certified, published and subscribed **from the web UI (empty config)**, configured with `PUT config`, cancelled with data purged (section 5.6); failure scenarios (broken patch, rollback) tested; two-tenant isolation proven |
| **5: Final** | Report, demo, submission | Full demo rehearsed twice (section 5.6 script); README/docs final; report and presentation; code submitted as required |

---

## 7. Ground rules

- **One branch per feature**, PR into `main`, **at least one reviewer** (pairs in section 10). Nobody pushes to `main`.
- `git add -p`, never `git add .`. `.env`, keys, `data/` and `noyau-local/` never enter Git.
- Commit messages: short, imperative, English.
- A PR is merged only if: tests pass, no secret, and the owner of any interface it touches has approved.
- Blocked for more than half a day? Say it in the team channel immediately.
- Everything the LLM returns is **untrusted input**.
- The teacher's core is **read-only for us**. If it seems wrong, write down the case and ask (section 12), do not patch it.

---

## 8. Dependencies at a glance

```text
Taha (lab, core-local) ─▶ Abderaouf (playbooks) ─▶ Wassim (tools) ─▶ Baha (graph, runner) ─▶ Dhia (API, Docker, tests)
                                                      │                    │
                                                      └── context/notifier ┘      Ahmed: repo, manifest, submit script, CLI, docs, review
```

Until a dependency lands, work against its **interface** (section 3) with a stub or mock data. The API (Dhia) and the core environment (Taha) do not depend on the lab: they start in Sprint 0/1.

---

## 9. Tasks by member

### 9.1 Ahmed (BOULOUH): team leader, documentation, GitHub, CLI

**Owns:** repo and workflow, `agent.manifest.json`, `scripts/submit_agent.py`, `agent/main.py`, `docs/`, deliverables, Elearn submission, integration review.

**Tasks**

- [ ] Sprint 0: create the repo, protect `main` (require PR + 1 review), add the team, commit Appendix A of `SETUP.md`, `README.md`, `PLAN.md`, `SETUP.md`, `.github/pull_request_template.md`, `.gitignore` (section 2).
- [ ] Sprint 0: put `PROJECT_FULL_REFERENCE.md`, `ai-patch-agent-guide.html` and the teacher's zip in `docs/reference/`. Create the GitHub Projects board (Backlog, In progress, In review, Done) with one issue per checkbox of this plan.
- [ ] Sprint 0: send the open questions (section 12) to Pr. SEBAA and Dr. MANSOUR, and ask for `GUIDE_GITHUB_NOYAU.docx` (repo organization rules, not yet received).
- [ ] Every sprint: weekly meeting, minutes in `docs/meetings/YYYY-MM-DD.md`, board updated, demo.
- [ ] Sprint 1: `agent.manifest.json` (below), checked against the contract and `agent-exemple/`.
- [ ] Sprint 1: `scripts/submit_agent.py` (below), tested against the local core (fix 11).
- [ ] Sprint 3: CLI `agent/main.py` (below).
- [ ] Sprint 4: contract review of every PR touching `api/`; run the contract checklist (section 11) before each milestone.
- [ ] Sprint 5: final report, presentation, deliverables list, Elearn upload.

**`agent.manifest.json`** (repo root; fill the placeholders):

```json
{
  "slug": "ai-patch-agent",
  "name": "AI Patch Agent",
  "version": "1.0.0",
  "description": "Detects, prioritizes and safely deploys Linux security updates (canary rollout, rollback) with human approval.",
  "filiere": "cybersecurite",
  "category": "patch-management",
  "developer": { "name": "BOULOUH Ahmed Ouassim", "email": "TO_FILL@etu.estin.dz" },
  "team_name": "TO_FILL",
  "pricing_model": "flat_monthly",
  "price": 0,
  "resource_requirements": { "cpu": "1", "memory_mb": 512 },
  "endpoints": {
    "base_url": "http://localhost:9000",
    "health": "/health",
    "activate": "/tenant/activate",
    "deactivate": "/tenant/deactivate",
    "status": "/tenant/{tenant_id}/status",
    "config_schema": "/config-schema",
    "exchange_notify": "/exchange/notify"
  },
  "produces": [],
  "consumes": []
}
```

> Only `base_url` is actually read by the core (F2); the other endpoint paths are fixed defaults, so keep them identical to the example. The `base_url` port must equal the Dockerfile's `EXPOSE` and `uvicorn --port` (9000). The host (`localhost` vs a service name) depends on how the teacher deploys: question 3.

**`scripts/submit_agent.py`** (the core expects a flat payload, not the manifest file: F1). Run from the repo root:

```python
"""Submit the agent to the core: converts agent.manifest.json into the flat
payload expected by POST /agents/submit.
Usage: python scripts/submit_agent.py [core_url]   (default http://localhost:8000)
"""
import json
import sys

import httpx

CORE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

with open("agent.manifest.json", encoding="utf-8") as f:
    m = json.load(f)

payload = {
    "slug": m["slug"],
    "name": m["name"],
    "version": m["version"],
    "description": m["description"],
    "filiere": m["filiere"],
    "category": m["category"],
    "developer_email": m["developer"]["email"],
    "team_name": m.get("team_name"),
    "base_url": m["endpoints"]["base_url"],
    "pricing_model": m.get("pricing_model", "flat_monthly"),
    "price": m.get("price", 0),
    "manifest": m,
    "produces": m.get("produces", []),
    "consumes": m.get("consumes", []),
}

r = httpx.post(f"{CORE}/agents/submit", json=payload, timeout=10)
print(r.status_code, r.text)
if r.status_code == 400:
    print("Hint: the slug already exists. Change it (or delete the row) to resubmit.")
elif r.status_code == 422:
    print("Hint: a required field is missing in agent.manifest.json.")
```

**`.github/pull_request_template.md`**

```markdown
## What and why
<!-- one or two sentences -->

## Checklist
- [ ] Tests pass (`pytest`)
- [ ] No secret, key or `.env` in the diff
- [ ] Inputs validated; nothing the LLM returns is executed
- [ ] Tenant-isolated (no global paths/state)
- [ ] Contract endpoints still return the envelope and answer in < 10 s
- [ ] Docs updated if an interface changed
- [ ] Reviewer assigned (see PLAN.md section 10)
```

**`agent/main.py`** (thin CLI over the runner; local lab only):

```python
"""CLI for the local lab. Usage:
    python -m agent.main run
    python -m agent.main approve <run_id> yes|no
    python -m agent.main status <run_id>
"""
import argparse
import json

from agent import runner
from agent.context import TenantContext


def main() -> None:
    p = argparse.ArgumentParser(prog="agent.main")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    a = sub.add_parser("approve")
    a.add_argument("run_id")
    a.add_argument("decision", choices=["yes", "no"])
    s = sub.add_parser("status")
    s.add_argument("run_id")
    args = p.parse_args()

    ctx = TenantContext.local()          # uses the repo's inventory.ini
    if args.cmd == "run":
        out = runner.run(ctx)
    elif args.cmd == "approve":
        out = runner.resume(ctx, args.run_id, args.decision)
    else:
        out = runner.get_run(ctx, args.run_id)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
```

**Done when:** a new member can go from zero to green `check_env.sh` using only `SETUP.md`; the agent can be submitted with one command; every PR has a reviewer; deliverables are on time.

---

### 9.2 Taha (BELALOUI): infrastructure, lab and local core

**Owns:** `lab/Vagrantfile`, `inventory.ini`, `ansible.cfg`, `scripts/` (lab ones), `requirements.lock`, the lab snapshots, `docs/core-local.md` and `docs/lab.md`.

**Tasks**

- [ ] Sprint 0: be the first to complete `SETUP.md` end to end and **fix any wrong command** in it (PR). You are the reference machine.
- [ ] Sprint 0: run the **core locally** following section 5.1 to 5.3 (PostgreSQL in Docker, own virtual environment, `create_admin.py`), then write `docs/core-local.md` so any teammate can do it in 15 minutes.
- [ ] Sprint 1: working 3-VM lab; snapshots `clean` (fresh) and `ready` (osquery installed); `ansible all -m ping` green; `scripts/sync_lab_keys.sh` and `check_env.sh` tested on a second machine.
- [ ] Sprint 1: write `docs/lab.md`: how to start/stop/reset, how to share the lab (R5: weaker PCs), expected IPs.
- [ ] Sprint 1: from a clean install, `pip freeze > requirements.lock`; commit; update `Dockerfile` and `SETUP.md` to use it.
- [ ] Sprint 1: **network tests**, results written in `docs/core-local.md` and `docs/lab.md`:
  - agent container reaches the VMs: `docker run --rm -v ~/.ssh/lab:/keys:ro <image> ssh -i /keys/node1 vagrant@192.168.56.11 true` (Docker Desktop networking to the host-only network is not guaranteed on every machine);
  - the core reaches the agent and the agent reaches the core in each row of the table of section 5.4 (especially Windows host with WSL).
- [ ] Sprint 2+: help any teammate whose environment fails (you own `check_env.sh`).
- [ ] Sprint 3: `scripts/reset_lab.sh` documenting the PowerShell commands (`vagrant snapshot restore ready`) and a short checklist to rehearse the demo.
- [ ] Sprint 4: confirm the lab **and the local core** survive a full reboot of the host and document what to do after.

**Commands to know**

```powershell
cd C:\lab
vagrant up | halt | status
vagrant snapshot save clean
vagrant snapshot save ready
vagrant snapshot restore ready
vagrant snapshot list
```

**Done when:** any teammate can reset the lab to a known state in under 5 minutes, start the core in 15, and get three pending-update machines for the demo.

---

### 9.3 Abderaouf (BECHICHE): Ansible playbooks

**Owns:** `playbooks/*.yml` and their tests on the VMs.

**Tasks**

- [ ] Sprint 1: copy the five playbooks from the guide (`install_osquery`, `osquery_query`, `check_updates`, `patch`, `rollback`) into `playbooks/`, then make each run on the lab.
- [ ] Sprint 1: `install_osquery.yml` idempotent (second run changes nothing); verify with `osqueryi`.
- [ ] Sprint 1: `check_updates.yml` is read-only and prints one parseable line per upgradable package.
- [ ] Sprint 2: `patch.yml` with `serial: 1`, `max_fail_percentage: 0`, `only_upgrade`, and `reboot_required` reported. Verify it **stops at the first failing host**.
- [ ] Sprint 2: confirm `ansible-playbook --check playbooks/patch.yml -e '{"packages":["curl"]}'` behaves sensibly (apt simulates; `command` tasks are skipped). Document it in `playbooks/README.md`; Wassim relies on it for dry-run.
- [ ] Sprint 2: `rollback.yml`: test with a pinned previous version really available in the repo/cache; document when it **cannot** work.
- [ ] Sprint 3: provide a **failure scenario kit** in `scripts/` (below) so the team can force a failing patch.
- [ ] Sprint 4: run the full playbook set against the `ready` snapshot three times from scratch; fix flaky parts.
- [ ] Review: Taha's lab/PRs.

**Failure scenario kit** (a broken apt source makes `update_cache` fail on that host; verify the failure is detected as expected on your VM):

```bash
# break apt on node1 (canary)
ansible node1 -b -m copy -a "dest=/etc/apt/sources.list.d/broken.list content='deb http://invalid.example/ubuntu jammy main\n'"
# ... run the agent: the canary must fail, the fleet must NOT be touched ...
# repair
ansible node1 -b -m file -a "path=/etc/apt/sources.list.d/broken.list state=absent"
```

Or simply restore the snapshot: `vagrant snapshot restore ready`.

**Rules for playbooks**

- Only the five playbooks exist. The LLM never chooses or writes one.
- Variables come from `-e` JSON passed by Python; use `argv`, never shell interpolation of user input.
- Every playbook is safe to run twice.

**Done when:** each playbook has a documented purpose, runs on the 3 VMs, is idempotent where expected, and the failure kit reproduces a failed patch.

---

### 9.4 Wassim (MEFTAH): tools, security, reports, secrets

**Owns:** `agent/context.py`, `agent/inventory.py`, `agent/tools.py`, `agent/notifier.py`, report generation, `docs/security.md`.

**Tasks**

- [ ] Sprint 1: `agent/__init__.py`, `context.py`, `inventory.py`, `notifier.py` (code below), unit-tested.
- [ ] Sprint 1: port `tools.py` from the guide, applying fixes 1, 2, 3 of section 4A.
- [ ] Sprint 2: hardened `validate_sql` (below) with a table of accepted/rejected queries; `run_osquery`, `get_upgradable`, `osv_lookup` (with cache and a timeout, no crash if OSV is down: return `count: 0` and a note).
- [ ] Sprint 2: `PKG_RE` for package names and version pins; every function validates its inputs first.
- [ ] Sprint 3: `deploy(..., dry_run=False)` adds `--check`; `rollback`; JSON reports (fix 8) with `network_calls`.
- [ ] Sprint 3: alert payloads follow fix 15 (nothing sensitive: the company dashboard and the admin page display them in clear). Review every `send_event` call with Baha.
- [ ] Sprint 3: secrets: only from env; check that no log line prints a key; `.gitignore` audit.
- [ ] Sprint 4: security review of `api/` and `runner` (path traversal, injection, tenant isolation, token checks of fix 13); written note in `docs/security.md`.
- [ ] Review: Baha's graph (plan validation, SQL building).

**`agent/context.py`**

```python
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.getenv("DATA_DIR") or ROOT / "data")
TENANT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")     # a UUID from the core matches
DEFAULT_ECOSYSTEM = "Ubuntu:22.04:LTS"
LOCAL_ID = "local"          # reserved for the CLI, rejected by the API


def tenant_path(tenant_id: str) -> Path:
    if not TENANT_RE.match(tenant_id or ""):
        raise ValueError("invalid tenant_id")
    return DATA_ROOT / "tenants" / tenant_id


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    ecosystem: str = DEFAULT_ECOSYSTEM

    @classmethod
    def local(cls) -> "TenantContext":
        return cls(LOCAL_ID, os.getenv("OSV_ECOSYSTEM", DEFAULT_ECOSYSTEM))

    @property
    def base_dir(self) -> Path:
        p = tenant_path(self.tenant_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def inventory(self) -> Path:
        if self.tenant_id == LOCAL_ID:
            return ROOT / "inventory.ini"
        return self.base_dir / "inventory.ini"

    @property
    def checkpoints_db(self) -> Path:
        return self.base_dir / "checkpoints.db"

    @property
    def reports_dir(self) -> Path:
        p = self.base_dir / "reports"
        p.mkdir(exist_ok=True)
        return p


def save_state(tenant_id: str, data: dict) -> None:
    base = tenant_path(tenant_id)
    base.mkdir(parents=True, exist_ok=True)
    f = base / "state.json"
    f.write_text(json.dumps(data))
    os.chmod(f, 0o600)


def load_state(tenant_id: str):
    f = tenant_path(tenant_id) / "state.json"
    return json.loads(f.read_text()) if f.exists() else None


def purge_tenant(tenant_id: str) -> None:
    shutil.rmtree(tenant_path(tenant_id), ignore_errors=True)    # idempotent (fix 16)
```

**`agent/inventory.py`** (tenant config to a validated inventory; nothing user-supplied reaches the file unchecked, and key files can only come from `KEYS_DIR`):

```python
import os
import re
from pathlib import Path

from agent.context import TenantContext

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
ADDR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
KEY_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def keys_dir() -> Path:
    return Path(os.path.expanduser(os.getenv("KEYS_DIR", "~/.ssh/lab")))


def write_inventory(ctx: TenantContext, hosts: list) -> None:
    if not isinstance(hosts, list) or not hosts:
        raise ValueError("hosts must be a non-empty list")
    groups = {"canary": [], "fleet": []}
    names = set()
    for h in hosts:
        name, addr = str(h.get("name", "")), str(h.get("address", ""))
        group = h.get("group")
        user = str(h.get("ssh_user", "vagrant"))
        key = str(h.get("ssh_key", ""))
        if not NAME_RE.match(name) or name in names:
            raise ValueError(f"invalid or duplicate host name: {name!r}")
        if not ADDR_RE.match(addr) or not USER_RE.match(user) or not KEY_RE.match(key):
            raise ValueError(f"invalid host definition for {name!r}")
        if group not in groups:
            raise ValueError("group must be 'canary' or 'fleet'")
        names.add(name)
        groups[group].append(
            f"{name} ansible_host={addr} ansible_user={user} "
            f"ansible_ssh_private_key_file={keys_dir() / key}"
        )
    if not groups["canary"]:
        raise ValueError("at least one canary host is required")
    lines = []
    for g, items in groups.items():
        lines.append(f"[{g}]")
        lines.extend(items)
        lines.append("")
    lines += [
        "[all:vars]",
        "ansible_python_interpreter=/usr/bin/python3",
        "ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'",
    ]
    ctx.inventory.write_text("\n".join(lines) + "\n")
```

**`agent/notifier.py`** (never raises, never logs keys; the core displays `data` in clear, so keep it minimal):

```python
import logging
import os

import httpx

from agent.context import TenantContext, load_state

log = logging.getLogger("notifier")
SEVERITIES = {"info", "low", "medium", "high", "critical"}


def send_event(ctx: TenantContext, event_type: str, severity: str, data: dict) -> bool:
    if severity not in SEVERITIES:
        severity = "info"
    state = load_state(ctx.tenant_id) or {}
    key = state.get("tenant_api_key")
    if not key:
        return False                     # CLI/local mode: nothing to notify
    url = os.getenv("NOYAU_URL", "http://localhost:8000") + "/webhooks/agent-events"
    try:
        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}", "X-Tenant-Id": ctx.tenant_id},
            json={"event_type": event_type, "severity": severity, "data": data},
            timeout=5,
        )
        return r.is_success
    except httpx.HTTPError as e:
        log.warning("webhook failed: %s", type(e).__name__)
        return False
```

**Hardened `validate_sql`** (replaces the guide's version; keeps `ALLOWED_TABLES` = `deb_packages`, `os_version`, `system_info`, `uptime`, `kernel_info`, `listening_ports`, `processes`, `users`):

```python
import re

FORBIDDEN = re.compile(r"(--|/\*|\*/|;|\battach\b|\bpragma\b)", re.I)
FROM_CLAUSE = re.compile(
    r"(?is)\bfrom\b(.*?)(?=\bwhere\b|\bgroup\b|\border\b|\blimit\b|\bhaving\b|\bunion\b|$)"
)
TABLE_REF = re.compile(r"(?i)\b(?:from|join)\s+([a-z_][a-z0-9_]*)")


def validate_sql(sql: str) -> str:
    s = (sql or "").strip().rstrip(";").strip()
    if not re.match(r"(?is)^select\s", s) or FORBIDDEN.search(s):
        raise ValueError("Only a single SELECT statement is allowed")
    for clause in FROM_CLAUSE.findall(s):
        if "," in clause or "(" in clause:
            raise ValueError("Comma joins and sub-selects in FROM are not allowed")
    tables = {t.lower() for t in TABLE_REF.findall(s)}
    if not tables or not tables <= ALLOWED_TABLES:
        raise ValueError(f"Table not allowed: {sorted(tables - ALLOWED_TABLES)}")
    return s
```

**Done when:** all inputs are validated before use; the hardening cases in `tests/test_tools.py` pass; no key can appear in a log, a report or an alert; tenant data cannot escape its folder.

---

### 9.5 Baha (GAHTAR): agent core (LLM, graph, runner)

**Owns:** `agent/llm.py`, `agent/graph.py`, `agent/runner.py`, prompts.

**Tasks**

- [ ] Sprint 1: port `llm.py` from the guide; two providers tested (Gemini + one fallback); model names only from `.env`.
- [ ] Sprint 2: JSON validation (reject any plan whose package is not in the real candidate list, any priority/action outside the allowed values); a test with a deliberately broken LLM answer.
- [ ] Sprint 2: `graph.py` nodes `collect`, `enrich`, `analyze` bound to `ctx` via `build(ctx)`; the LLM receives **only** package names, versions, CVE ids/summaries, host count. Never hostnames or IPs.
- [ ] Sprint 3: nodes `approve` (`interrupt()`), `dryrun`, `canary`, `verify`, `fleet`, `rollback`, `report`, with conditional edges (fixes 5, 6, 7).
- [ ] Sprint 3: call `notifier.send_event` at the points listed in section 3; payloads follow fix 15 (counts, package names, run id).
- [ ] Sprint 3: `runner.py` (below) and the checkpoint resume test: kill the process while waiting for approval, restart, approve, the run finishes.
- [ ] Sprint 4: prompt tuning on real lab data; keep the plan short and deterministic (temperature low).
- [ ] Review: Wassim's tools and Dhia's API run endpoints.

**How `build(ctx)` binds the tenant**: define nodes as functions `(state, ctx)` and register them with `functools.partial(node, ctx=ctx)` (or define them inside `build`). Compile in the runner with a SQLite checkpointer pointing at `ctx.checkpoints_db`.

**Why runs are threads:** the core gives up after 10 s (F4) and the API must stay responsive; a run can last minutes. `start_run` returns immediately with the run id.

**`agent/runner.py`** (sketch to adapt; check the exact LangGraph API of the installed version, `interrupt`/`Command(resume=...)` usage and `get_state`):

```python
import json
import threading
import uuid

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from agent.context import TenantContext
from agent.graph import build

_LOCK = threading.Lock()


def _runs_file(ctx: TenantContext):
    return ctx.base_dir / "runs.json"


def _set(ctx: TenantContext, run_id: str, **fields) -> dict:
    with _LOCK:
        f = _runs_file(ctx)
        runs = json.loads(f.read_text()) if f.exists() else {}
        runs.setdefault(run_id, {"run_id": run_id}).update(fields)
        f.write_text(json.dumps(runs, default=str))
        return runs[run_id]


def get_run(ctx: TenantContext, run_id: str) -> dict:
    f = _runs_file(ctx)
    runs = json.loads(f.read_text()) if f.exists() else {}
    if run_id not in runs:
        raise KeyError("unknown run")
    return runs[run_id]


def _execute(ctx: TenantContext, run_id: str, payload) -> dict:
    cfg = {"configurable": {"thread_id": run_id}}
    _set(ctx, run_id, state="running", error=None)
    try:
        with SqliteSaver.from_conn_string(str(ctx.checkpoints_db)) as cp:
            app = build(ctx).compile(checkpointer=cp)
            out = app.invoke(payload, cfg)
            snap = app.get_state(cfg)
        if snap.next:                                   # paused on interrupt()
            return _set(ctx, run_id, state="waiting_approval", plan=out.get("plan"))
        return _set(ctx, run_id, state="done", report=out.get("report"))
    except Exception as e:                              # never leak details/keys
        return _set(ctx, run_id, state="failed", error=type(e).__name__)


def run(ctx: TenantContext) -> dict:
    return _execute(ctx, uuid.uuid4().hex[:8], {})


def resume(ctx: TenantContext, run_id: str, decision: str) -> dict:
    return _execute(ctx, run_id, Command(resume=decision))


def start_run(ctx: TenantContext) -> str:
    run_id = uuid.uuid4().hex[:8]
    _set(ctx, run_id, state="running")
    threading.Thread(target=_execute, args=(ctx, run_id, {}), daemon=True).start()
    return run_id


def start_resume(ctx: TenantContext, run_id: str, decision: str) -> None:
    _set(ctx, run_id, state="running")
    threading.Thread(
        target=_execute, args=(ctx, run_id, Command(resume=decision)), daemon=True
    ).start()
```

**Done when:** one command runs collect → … → report on the lab; an invalid or dangerous LLM answer never reaches a playbook; resume after restart works; alerts are sent and carry nothing sensitive.

---

### 9.6 Dhia Eddine (LAGHROUR): API, Docker, tests, compliance

**Owns:** `api/main.py`, `Dockerfile`, `tests/`, `scripts/simulate_core.sh`, the contract checklist, the end-to-end test (section 5.6).

**Tasks**

- [ ] Sprint 0/1: `api/main.py` with the 5 endpoints, `PUT config` and the envelope everywhere (below), runnable with `uvicorn api.main:app --port 9000`; `/exchange/notify` as a no-op returning the envelope.
- [ ] Sprint 1: `scripts/simulate_core.sh` (section 5.5) passing; `tests/test_contract.py` (below) green.
- [ ] Sprint 2: `tests/test_tools.py`: table of accepted/rejected SQL (include comma joins, `file`, `curl`, subselect, `;`, comments), package-name regex cases, tenant id cases (`../x`, empty, 65 chars, a real UUID).
- [ ] Sprint 3: wire `POST /tenant/{id}/runs`, `GET .../runs/{run_id}`, `POST .../approve` to `runner` (stub it until Baha delivers).
- [ ] Sprint 4: `Dockerfile` builds and runs without manual steps; test with the commands below; run the **whole scenario of section 5.6** with the real core (submit, certify, publish, subscribe from the web UI, `PUT config`, run, alerts in `/mon-compte`, cancel and purge).
- [ ] Sprint 4: `tests/test_scenarios.py`: failed canary leaves the fleet untouched; rollback path; invalid LLM output rejected; no hostname/IP in the LLM prompt (use a mock provider).
- [ ] Sprint 4: two-tenant isolation test through the real HTTP API against the running core.
- [ ] Review: Baha's runner and Wassim's inventory code.

**`api/main.py`**

```python
import hmac
import re
import time

from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from agent.context import (
    DEFAULT_ECOSYSTEM, LOCAL_ID, TENANT_RE, TenantContext,
    load_state, purge_tenant, save_state,
)
from agent.inventory import write_inventory

app = FastAPI(title="AI Patch Agent")
STARTED = time.time()
RUN_ID_RE = re.compile(r"^[a-f0-9]{8}$")


# ---------- envelope ----------
def ok(data):
    return {"status": "ok", "data": data, "error": None}


def fail(code: int, msg: str):
    return JSONResponse(status_code=code, content={"status": "error", "data": None, "error": msg})


@app.exception_handler(StarletteHTTPException)
async def _http_error(_, exc):
    return fail(exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def _validation_error(_, exc):
    return fail(422, "invalid request")


@app.exception_handler(Exception)
async def _unexpected(_, exc):
    return fail(500, "internal error")       # never leak details


# ---------- helpers ----------
def _tenant(x_tenant_id):
    if not x_tenant_id or x_tenant_id == LOCAL_ID or not TENANT_RE.match(x_tenant_id):
        raise HTTPException(400, "invalid or missing X-Tenant-Id")
    return x_tenant_id


def _bearer(authorization):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    return authorization[7:]


def _check_key(tenant_id, authorization):
    state = load_state(tenant_id)
    if state is None:
        raise HTTPException(404, "tenant not active")
    if not hmac.compare_digest(_bearer(authorization), state["tenant_api_key"]):
        raise HTTPException(401, "invalid token")
    return state


def _authed_ctx(tenant_id, authorization, x_tenant_id):
    if _tenant(x_tenant_id) != tenant_id:
        raise HTTPException(403, "tenant mismatch")
    state = _check_key(tenant_id, authorization)
    return TenantContext(tenant_id, state.get("ecosystem", DEFAULT_ECOSYSTEM))


def _apply_hosts(ctx, config) -> bool:
    """Write the inventory if hosts are given. Returns True if hosts were applied."""
    hosts = config.get("hosts")
    if not hosts:
        return False
    try:
        write_inventory(ctx, hosts)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return True


# ---------- the 5 mandatory endpoints ----------
@app.get("/health")
def health():
    return ok({"uptime_seconds": int(time.time() - STARTED)})


@app.post("/tenant/activate")
def activate(
    body: dict,
    authorization: str = Header(None),
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
):
    tid = _tenant(x_tenant_id)
    key = _bearer(authorization)
    config = body.get("config") or {}
    ctx = TenantContext(tid, str(config.get("ecosystem", DEFAULT_ECOSYSTEM)))
    # The web UI of the core always activates with an EMPTY config (F7):
    # activation must succeed; hosts arrive later through PUT /tenant/{id}/config.
    configured = _apply_hosts(ctx, config)
    save_state(tid, {"tenant_api_key": key, "ecosystem": ctx.ecosystem, "configured": configured})
    return ok({"activated": True})


@app.post("/tenant/deactivate")
def deactivate(
    authorization: str = Header(None),
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
):
    tid = _tenant(x_tenant_id)
    state = load_state(tid)
    if state is not None:                      # the core always sends the key (F6)
        _check_key(tid, authorization)
    purge_tenant(tid)                          # idempotent
    return ok({"deactivated": True, "data_purged": True})


@app.get("/tenant/{tenant_id}/status")
def tenant_status(tenant_id: str, x_tenant_id: str = Header(None, alias="X-Tenant-Id")):
    # The core never calls this one (F3); the teacher may check it by hand, so no auth.
    if not TENANT_RE.match(tenant_id) or tenant_id == LOCAL_ID:
        raise HTTPException(400, "invalid tenant id")
    if x_tenant_id and x_tenant_id != tenant_id:
        raise HTTPException(403, "tenant mismatch")
    state = load_state(tenant_id)
    if state is None:
        raise HTTPException(404, "tenant not active")
    return ok({"state": "running", "configured": state.get("configured", False)})


@app.get("/config-schema")
def config_schema():
    return ok({
        "type": "object",
        "properties": {
            "ecosystem": {"type": "string", "default": DEFAULT_ECOSYSTEM,
                          "description": "OSV ecosystem matching the target OS"},
            "hosts": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["name", "address", "group", "ssh_key"],
                    "properties": {
                        "name": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,30}$"},
                        "address": {"type": "string"},
                        "group": {"type": "string", "enum": ["canary", "fleet"]},
                        "ssh_user": {"type": "string", "default": "vagrant"},
                        "ssh_key": {"type": "string",
                                    "description": "file name inside the keys directory"},
                    },
                },
            },
        },
    })


# optional endpoint of the contract: we consume nothing, so it is a no-op
@app.post("/exchange/notify")
def exchange_notify(body: dict):
    return ok({"processed": True})


# ---------- our own endpoints (agent business) ----------
@app.put("/tenant/{tenant_id}/config")
def configure(tenant_id: str, body: dict, authorization: str = Header(None),
              x_tenant_id: str = Header(None, alias="X-Tenant-Id")):
    """Set or replace the hosts after activation. The company uses the tenant key
    shown in /mon-compte of the core."""
    _authed_ctx(tenant_id, authorization, x_tenant_id)
    state = load_state(tenant_id)
    config = body.get("config") or {}
    ecosystem = str(config.get("ecosystem", state.get("ecosystem", DEFAULT_ECOSYSTEM)))
    ctx = TenantContext(tenant_id, ecosystem)
    configured = _apply_hosts(ctx, config) or state.get("configured", False)
    state.update(ecosystem=ecosystem, configured=configured)
    save_state(tenant_id, state)
    return ok({"configured": configured})


@app.post("/tenant/{tenant_id}/runs")
def create_run(tenant_id: str, authorization: str = Header(None),
               x_tenant_id: str = Header(None, alias="X-Tenant-Id")):
    from agent import runner
    ctx = _authed_ctx(tenant_id, authorization, x_tenant_id)
    if not load_state(tenant_id).get("configured"):
        raise HTTPException(409, "no hosts configured for this tenant (PUT /tenant/{id}/config)")
    return ok({"run_id": runner.start_run(ctx), "state": "running"})


@app.get("/tenant/{tenant_id}/runs/{run_id}")
def read_run(tenant_id: str, run_id: str, authorization: str = Header(None),
             x_tenant_id: str = Header(None, alias="X-Tenant-Id")):
    from agent import runner
    ctx = _authed_ctx(tenant_id, authorization, x_tenant_id)
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(400, "invalid run id")
    try:
        return ok(runner.get_run(ctx, run_id))
    except KeyError:
        raise HTTPException(404, "unknown run")


@app.post("/tenant/{tenant_id}/runs/{run_id}/approve")
def approve_run(tenant_id: str, run_id: str, body: dict, authorization: str = Header(None),
                x_tenant_id: str = Header(None, alias="X-Tenant-Id")):
    from agent import runner
    ctx = _authed_ctx(tenant_id, authorization, x_tenant_id)
    if not RUN_ID_RE.match(run_id) or body.get("decision") not in ("yes", "no"):
        raise HTTPException(400, "invalid run id or decision")
    runner.start_resume(ctx, run_id, body["decision"])
    return ok({"run_id": run_id, "state": "running"})
```

**`tests/test_contract.py`**

```python
import os
import tempfile
import uuid

os.environ["DATA_DIR"] = tempfile.mkdtemp()          # before importing the app

from fastapi.testclient import TestClient            # noqa: E402
from agent.context import DATA_ROOT                  # noqa: E402
from api.main import app                             # noqa: E402

c = TestClient(app)


def h(tenant, key=None):
    return {"Authorization": f"Bearer {key or 'key-' + tenant}", "X-Tenant-Id": tenant}


def assert_envelope(r):
    j = r.json()
    assert set(j) == {"status", "data", "error"}
    assert j["status"] in ("ok", "error")
    return j


def test_health():
    j = assert_envelope(c.get("/health"))
    assert j["status"] == "ok" and "uptime_seconds" in j["data"]


def test_config_schema():
    assert assert_envelope(c.get("/config-schema"))["status"] == "ok"


def test_errors_use_the_envelope():
    for r in (c.get("/nope"), c.post("/tenant/activate", json={}),
              c.post("/tenant/activate", json={}, headers={"X-Tenant-Id": "../x"})):
        assert assert_envelope(r)["status"] == "error"


def test_lifecycle_and_isolation():
    assert c.post("/tenant/activate", json={"config": {}}, headers=h("acme")).status_code == 200
    assert c.post("/tenant/activate", json={"config": {}}, headers=h("globex")).status_code == 200
    assert assert_envelope(c.get("/tenant/acme/status"))["data"]["state"] == "running"

    r = c.get("/tenant/acme/status", headers={"X-Tenant-Id": "globex"})   # cross-tenant
    assert r.status_code == 403 and assert_envelope(r)["status"] == "error"

    r = c.post("/tenant/deactivate", headers=h("acme"))
    assert assert_envelope(r)["data"]["data_purged"] is True
    assert not (DATA_ROOT / "tenants" / "acme").exists()
    assert c.get("/tenant/acme/status").status_code == 404
    assert c.get("/tenant/globex/status").status_code == 200              # untouched


def test_core_style_uuid_tenant_and_empty_body_deactivate():
    tid = str(uuid.uuid4())                                               # the core uses UUIDs
    assert c.post("/tenant/activate", json={"config": {}}, headers=h(tid)).status_code == 200
    assert c.post("/tenant/deactivate", json={}, headers=h(tid)).status_code == 200


def test_deactivate_requires_the_right_token():
    c.post("/tenant/activate", json={"config": {}}, headers=h("initech"))
    r = c.post("/tenant/deactivate", headers=h("initech", key="wrong"))
    assert r.status_code == 401 and assert_envelope(r)["status"] == "error"
    assert c.get("/tenant/initech/status").status_code == 200             # still there
    assert c.post("/tenant/deactivate", headers=h("initech")).status_code == 200


def test_config_endpoint_needs_token_and_validates_hosts():
    c.post("/tenant/activate", json={"config": {}}, headers=h("hooli"))
    assert c.put("/tenant/hooli/config", json={"config": {}},
                 headers=h("hooli", key="wrong")).status_code == 401
    bad = {"config": {"hosts": [{"name": "BAD NAME", "address": "x", "group": "canary", "ssh_key": "k"}]}}
    assert c.put("/tenant/hooli/config", json=bad, headers=h("hooli")).status_code == 400
    good = {"config": {"hosts": [{"name": "node1", "address": "192.168.56.11",
                                  "group": "canary", "ssh_key": "node1"}]}}
    r = c.put("/tenant/hooli/config", json=good, headers=h("hooli"))
    assert assert_envelope(r)["data"]["configured"] is True


def test_runs_refused_until_configured():
    c.post("/tenant/activate", json={"config": {}}, headers=h("umbrella"))
    assert c.post("/tenant/umbrella/runs", headers=h("umbrella")).status_code == 409


def test_reserved_and_malicious_tenant_ids_are_rejected():
    for t in ("local", "..", "a/b"):
        r = c.post("/tenant/activate", json={"config": {}}, headers=h(t))
        assert r.status_code in (400, 422)
```

**`Dockerfile`** (repo root; use `requirements.lock` once Taha has produced it):

```dockerfile
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && ansible-galaxy collection install ansible.posix

COPY . .

ENV DATA_DIR=/app/data KEYS_DIR=/keys
EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:9000/health').status_code==200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "9000"]
```

```bash
docker build -t ai-patch-agent .
docker run --rm -p 9000:9000 --env-file .env \
  -e NOYAU_URL=http://host.docker.internal:8000 \
  --add-host=host.docker.internal:host-gateway \
  -v ~/.ssh/lab:/keys:ro \
  -v ai_patch_data:/app/data \
  ai-patch-agent
curl localhost:9000/health
scripts/simulate_core.sh http://localhost:9000
```

> `.dockerignore` must exclude `data/`, `.env`, `noyau-local/`, `.git/`, `.venv*/`.

**Submit to the local core** (core running on :8000): `python scripts/submit_agent.py http://localhost:8000`, then follow section 5.6 from step 4.

**Done when:** `pytest` is green; the image builds and runs from scratch; `simulate_core.sh` passes against the container; the full scenario of section 5.6 runs through the real core without errors.

---

## 10. Cross-review pairs

| Author | Reviewer | Looks at |
|---|---|---|
| Taha | Abderaouf | lab reproducibility, scripts, `docs/core-local.md` |
| Abderaouf | Taha | playbooks on a fresh lab |
| Wassim | Baha | validation, inputs reaching playbooks, alert payloads |
| Baha | Wassim | plan validation, SQL building, prompts (no host data) |
| Dhia | Ahmed | contract compliance of `api/` (envelope, 10 s, token checks) |
| Ahmed | Dhia | docs, manifest and `submit_agent.py` vs the contract and the core |

---

## 11. Contract checklist (before every milestone and before submission)

Items marked **(core)** come from the verified behavior of the core (section 1B).

- [ ] The 5 mandatory endpoints answer with the envelope `{status, data, error}`, **errors included** (unknown route, bad input, wrong token).
- [ ] Paths are exactly `/health`, `/tenant/activate`, `/tenant/deactivate`, `/tenant/{tenant_id}/status`, `/config-schema` **(core: fixed defaults, F2)**.
- [ ] Every contract endpoint answers in well under 10 s (`curl -m 10` in `simulate_core.sh`) **(core: F4)**.
- [ ] Failure to activate returns a **non-2xx** code; success returns HTTP 200 with `status: "ok"` **(core: F4)**.
- [ ] Activation works with an **empty** config, and after a web-UI subscription the agent can be configured with `PUT /tenant/{id}/config` **(core: F7)**.
- [ ] A **UUID** tenant id works **(core: F6)**.
- [ ] Manifest valid, slug unique, `filiere = cybersecurite`, `base_url` port = Dockerfile port.
- [ ] Submission done with `scripts/submit_agent.py` (flat payload), not the raw manifest **(core: F1)**.
- [ ] Two test tenants never see each other's data (hosts, runs, reports).
- [ ] `POST /tenant/deactivate` really deletes the tenant folder, is idempotent, and checks the bearer token **(core: F6, F10)**.
- [ ] `docker build` then `docker run` works with no manual step (only environment variables).
- [ ] No secret in code, in Git history, or in logs.
- [ ] Every outbound service is listed in the execution report (`network_calls`).
- [ ] No call to another agent.
- [ ] Alerts reach `/webhooks/agent-events` with a valid severity, appear in `/mon-compte`, and contain nothing sensitive **(core: F11)**.
- [ ] Agent submitted, then certified and published from `/admin`, then subscribed from the web UI with badge "Actif" (not "Suspendu").

---

## 12. Questions for the supervisors (Ahmed sends the open ones in Sprint 0)

**Answered by the core's code** (no need to ask, but mention them if the teacher disagrees):

1. ~~Which headers on `deactivate` and `status`?~~ `deactivate`: `POST` with `Authorization: Bearer <key>`, `X-Tenant-Id` and body `{}`. `status`: never called by the core (F3, F6).
2. ~~Empty config at activation?~~ Yes: the web UI always sends `{}`; only the API `POST /subscriptions` can send a config (F7).

**Still open:**

3. Which `base_url` host will be used at certification and demo (`localhost:9000`, a Docker service name)? Will the demo machine be able to reach our VM lab?
4. Is a call to an external LLM API (Gemini, OpenRouter, Groq) and to `api.osv.dev` acceptable if listed in the execution report?
5. What is the exact file naming and the deadline of each deliverable (charter, minutes, plan, report, follow-up, final presentation)?
6. Can we have `GUIDE_GITHUB_NOYAU.docx` (how repositories must be organized)?
7. `team_name` and contact email to put in the manifest.
8. The guide says `curl ... -d @agent.manifest.json` but the core's `POST /agents/submit` requires a flat payload (it returns 422 with the raw manifest). Is there an updated guide or core? Is `submit_agent.py` an acceptable way to submit?
9. The `/admin` page has no activate/deactivate buttons. How will you test deactivation: through `POST /subscriptions/{id}/cancel`? Will you also call `GET /tenant/{id}/status` yourself, and with which headers?
10. Will the core be run by you at certification (on your machine), and will the agent be started by us or by you from our Docker image?

---

## 13. Risks specific to this plan

| Risk | Mitigation |
|---|---|
| The agent container cannot reach the VM lab network | Taha tests it in Sprint 1; fallback: demo with the agent running directly in WSL and Docker only for certification |
| Core and agent cannot reach each other (Windows host vs WSL vs Docker) | Section 5.4 table; Taha tests every row in Sprint 1; `simulate_core.sh` isolates agent problems from network problems |
| A wrong envelope or a slow answer suspends the subscription (silently in the web UI) | Envelope tests, global exception handlers, `curl -m 10` in `simulate_core.sh`, runs in threads |
| The agent is "Actif" but unusable because the web UI sent no hosts | `PUT /tenant/{id}/config`, step 7 of the demo script, covered by tests |
| Re-subscribing generates a new tenant key and breaks scripts that kept the old one | `activate` always overwrites the stored key; read the current key in `/mon-compte` before each manual call |
| PostgreSQL or the core's pinned versions break local setups | Separate virtual environment for the core; PostgreSQL via Docker; `docs/core-local.md` |
| The teacher updates the core or the guide | `noyau-local/` is replaceable; re-run `simulate_core.sh` and the scenario of 5.6; update `PROJECT_FULL_REFERENCE.md` |
| Alert data shown in clear to the company and the admin | Fix 15: counts, package names and run id only |
| Free LLM quotas hit during the demo | Fallback providers, a cached plan for the demo, mock provider for tests |
| Different environments on different PCs | `check_env.sh` green is mandatory, `requirements.lock` |
| One module blocks everybody | Stubs against the interfaces of section 3; cross-review pairs |
| Last-week rush | Demo rehearsal from Sprint 4; Sprint 5 reserved for report and polish |