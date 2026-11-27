# Teacher platform delivery — agent contract, testing and push guide

This is the delivery guide for the teacher’s **Noyau** platform. The repository is the
**Patch Management Agent**; the Noyau is supplied by the teacher and runs separately.
`Seba/` and the extracted kernel are reference material only and are never committed.

## 1. What the teacher requires

The agent must expose:

| Endpoint | Purpose |
|---|---|
| `GET /health` | standard envelope with `uptime_seconds` |
| `POST /tenant/activate` | receive `X-Tenant-Id`, Bearer tenant key, `{config}` |
| `POST /tenant/deactivate` | purge all tenant data |
| `GET /tenant/{tenant_id}/status` | `state: running` for an active tenant |
| `GET /config-schema` | JSON Schema for tenant configuration |
| `POST /exchange/notify` | optional no-op; this agent declares no exchange objects |

Every response must be:

```json
{"status": "ok" | "error", "data": {...} | null, "error": "message" | null}
```

The manifest is `agent.manifest.json`; the container is `Dockerfile`.

## 2. Repository layout

```text
agent.manifest.json        teacher manifest (filiere: cybersecurite)
Dockerfile                 agent container
requirements-agent.txt     FastAPI/httpx runtime
agent/                     FastAPI service
  main.py                  create_app() factory
  contract.py              envelope, tenant auth, error handlers
  state.py                 per-tenant SQLite/files and purge
  config.py                environment + config schema
  alerts.py                Noyau webhook client
  routers/lifecycle.py     mandatory endpoints
  routers/business.py      evidence/assess/plan/preflight/runs
patch_agent/               existing assessment, planning, approval, execution core
schemas/                   contracts, including agent.manifest.schema.json
policies/, lab/            service policy and inventory host names
tests/agent/               contract, isolation, webhook, business tests
scripts/submit_agent.py    manifest → Noyau submission payload
scripts/agent_smoke.py     5-endpoint smoke test
```

The service is created with a factory, not a module-level app:

```bash
uvicorn agent.main:create_app --factory --host 0.0.0.0 --port 9000
```

## 3. Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_DATA_DIR` | `./agent-data` | tenant state, evidence, plans, reports |
| `NOYAU_URL` | `http://localhost:8000` | Noyau base URL for webhook alerts |
| `AGENT_EXECUTION_ENABLED` | `0` | `1` enables operator-only run endpoints |
| `AGENT_OPERATOR_TOKEN` | empty | required header `X-Operator-Token` for runs |
| `PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS` | required for plan generation | evidence freshness policy |
| `PATCH_AGENT_REQUIRE_GATES` | `0` | `1` requires assessment + preflight for submission |

Never put tenant keys or tokens in the repository.

## 4. Run and test locally (without the Noyau)

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-agent.txt
pip install pytest PyYAML mcp==2.3.0
python -m pytest -q
python scripts/check_artifacts.py
```

Agent contract smoke test against a running agent:

```bash
uvicorn agent.main:create_app --factory --port 9000
python scripts/agent_smoke.py \
  --url http://localhost:9000 \
  --tenant 11111111-1111-1111-1111-111111111111 \
  --key tenant-secret
```

It checks health, config-schema, activate, status, exchange notify and deactivate. It
prints no key material.

## 5. Docker

```bash
docker build -t patch-management-agent .
docker run --rm -p 9000:9000 \
  -e NOYAU_URL=http://host.docker.internal:8000 \
  -v patch-agent-data:/data \
  patch-management-agent
```

- On Linux add `--add-host=host.docker.internal:host-gateway`, or run the Noyau and
  agent in the same Docker network and use the Noyau service name.
- The manifest’s `endpoints.base_url` is `http://localhost:9000` for a local demo; when
  submitting from another container, override it with
  `scripts/submit_agent.py --base-url http://patch-management-agent:9000`.
- The image listens on port 9000 and has a `/health` healthcheck.

## 6. Submit to the Noyau

The Noyau’s `AgentManifestSubmission` model expects **flattened** fields, while
`agent.manifest.json` is nested. Do not post the manifest directly; use the adapter:

```bash
python scripts/submit_agent.py \
  --kernel http://localhost:8000 \
  --manifest agent.manifest.json \
  --base-url http://localhost:9000
```

It maps `developer.email` → `developer_email`, `endpoints.base_url` → `base_url`, and
embeds the full manifest. The agent enters `in_review`.

Teacher flow:

1. Open the Noyau `/admin` page and sign in as platform admin.
2. Certify the submitted agent, then publish it.
3. Create a test company via `/inscription`.
4. Subscribe to the agent from `/catalogue`; the Noyau calls `POST /tenant/activate`.
5. Check `/mon-compte` for alerts and `/admin/events` for the global feed.
6. Cancel the subscription; the Noyau calls `POST /tenant/deactivate`.

If activation fails, the Noyau suspends the subscription; inspect the agent envelope.

## 7. Business demo endpoints

All are tenant-scoped with `X-Tenant-Id` + `Authorization: Bearer <tenant_key>`.
They are extra endpoints; the Noyau contract only requires the 5 lifecycle routes.

```bash
# 1. Upload evidence v1 (existing contract)
curl -X POST http://localhost:9000/api/v1/evidence \
  -H "X-Tenant-Id: $TENANT" -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" -d @evidence.json

# 2. Upload advisory cache v1
curl -X POST http://localhost:9000/api/v1/advisories \
  -H "X-Tenant-Id: $TENANT" -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" -d @advisory-cache.json

# 3. Assess and send patch_affected alerts
curl -X POST http://localhost:9000/api/v1/assess \
  -H "X-Tenant-Id: $TENANT" -H "Authorization: Bearer $KEY"

# 4. Generate a plan
curl -X POST http://localhost:9000/api/v1/plans \
  -H "X-Tenant-Id: $TENANT" -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"run_id": "demo-run", "canary": "vm-01"}'

# 5. Upload preflight readiness
curl -X POST http://localhost:9000/api/v1/preflight \
  -H "X-Tenant-Id: $TENANT" -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" -d @preflight.json

# 6. Tenant summary
curl http://localhost:9000/api/v1/status \
  -H "X-Tenant-Id: $TENANT" -H "Authorization: Bearer $KEY"
```

Execution is operator-only and disabled by default. If
`AGENT_EXECUTION_ENABLED=1` and `AGENT_OPERATOR_TOKEN` is set, `POST /api/v1/runs`
requires `X-Operator-Token`; without a configured live runner it returns
`503 execution adapter is not configured` rather than pretending to run.

## 8. Tenant isolation and purge

- Each tenant has its own hashed directory under `AGENT_DATA_DIR/tenants/`.
- Evidence, advisories, assessment, preflight, plans and reports are per tenant.
- `POST /tenant/deactivate` removes the directory and the tenant row.
- Tests cover: two tenants cannot read each other’s state; deactivating one leaves the
  other intact.

## 9. Webhook events

The agent sends:

| Event | Severity | When |
|---|---|---|
| `patch_affected` | decision priority | assessment finds affected packages |
| `patch_plan_ready` | info | a plan is generated |
| `patch_preflight_blocked` | high | a host is not ready |

The header carries the tenant API key received at activation. The Noyau validates it
against the subscription and records the event. Webhook failures never fail a business
request.

## 10. Testing and pushing on `dhya/full-project`

`Seba/` is reference only. It is in `.gitignore`; never stage it.

```bash
git switch dhya/full-project
git status --short                # only intended files
python -m pytest -q               # 519 passed, 400 skipped locally
python scripts/check_artifacts.py
python scripts/update_progress.py --check
git diff --check

git add <explicit files>          # never git add -A
git commit -m "..."               # separate logical commits
git push origin dhya/full-project
```

Never push to `main`, never force-push, never commit `.env`, keys, tokens, raw lab logs,
`Seba/`, `Plan/` or `agent-data/`.

**CI coverage note:** the repository’s existing `ci.yml` installs the core dependencies
only. Until a maintainer with GitHub `workflow` scope adds
`fastapi==0.165.0 httpx==0.27.2 uvicorn==0.54.0` to its install step, the
`tests/agent/` directory is skipped by the core CI (via `pytest.importorskip`) and the
agent contract is verified locally and by the Docker `/health` check. Add those three
pins to the install step to run `tests/agent` in CI.

To test with the real Noyau, extract/run it **outside** this repository:

```bash
# in a separate folder, not in this repo
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg2://..."
export JWT_SECRET_KEY="..."
python scripts/create_admin.py
uvicorn app.main:app --port 8000
```

Then run the agent, submit the manifest, certify/publish, subscribe, exercise the
business endpoints and inspect `/mon-compte` and `/admin/events`.

## 11. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `config does not match /config-schema` | unknown config field; use the schema |
| `tenant is not active` | activate first; deactivate removes the tenant |
| `tenant api key is not valid` | use the key issued by the Noyau subscription |
| `AgentManifestSubmission` validation error | use `scripts/submit_agent.py`, not raw manifest |
| Noyau cannot reach agent | `base_url` / Docker network / port 9000 |
| subscription suspended | activation returned a non-envelope error or timed out |
| `execution adapter is not configured` | expected until a live runner is bound by the operator |
| webhook not visible | verify `NOYAU_URL`, tenant key, and Noyau `/admin/events` |

## 12. Sprint mapping

The teacher envelope carries the four-sprint work:

- **Sprint 1** — evidence v1 upload/validation, tenant configuration, health/status.
- **Sprint 2** — advisory cache, assessment matching, plan generation, preflight gate,
  `patch_affected` alerts.
- **Sprint 3** — approval-bound run records, failure/recovery reports, operator-only
  execution endpoint.
- **Sprint 4** — Docker/manifest/submission/certification, tenant isolation, smoke tests,
  delivery documentation.

Live VM/Semaphore canary and fleet evidence remains a separate live gate; the agent does
not claim it without recorded lab results.
