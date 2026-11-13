# Assessment-to-approval workflow

Sprint 2 documentation draft. It describes what exists on `main` at commit `4a9fd91`
and marks what does not exist yet. Deployment stays blocked for every plan. This page
does not tick any `plan.md` checkpoint.

Sources: [interfaces.md](interfaces.md), [evidence-contract.md](evidence-contract.md),
`schemas/plan.schema.json`, and PR #7 (open, not merged).

## 1. The flow

| # | Stage | Done by | State |
|---|---|---|---|
| 1 | Inspect the hosts with the fixed read-only `playbooks/inspect.yml` | Operator | Emits contract v1. A read-only run on vm-01, vm-02 and vm-03 from WSL was verified outside Semaphore; the Semaphore-run export is pending. |
| 2 | Import the export with `python -m patch_agent.collector` | Operator | Implemented (PR #11). |
| 3 | Assess advisories against the evidence | Baha | Not implemented. Contracts are proposed in PR #7 (open); matching is S2.2. |
| 4 | Submit a plan with `submit_plan` | Model, through the approval MCP | Implemented. |
| 5 | Review and decide with `python -m patch_agent.operator` | Human operator | Implemented. |
| 6 | Request deployment with `request_deployment` | Model | Always returns a blocked report; no job starts. |

## 2. What each stage checks

### 2.1 Evidence import

The operator must set `PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS` (a positive integer; there
is no default). The import validates contract v1, requires the requested targets to match
exactly, requires every host to be configured in `lab/hosts.json` and successful, and
requires the collection and host timestamps to be neither older than the limit nor in the
future. It then replaces `data/evidence.json` atomically. It does not query hosts and does
not prove where the file came from.

    python -m patch_agent.collector EXPORT.json --targets vm-01 vm-02 vm-03

### 2.2 Assessment (proposed)

PR #7 proposes two contracts: an advisory cache keyed by Debian source package, and an
assessment result with one record per host and package. Each record holds findings and a
decision, `patch` or `defer`. These are validators only: nothing fetches data, reads the
evidence store or is connected to `submit_plan`. See `docs/assessment-contract.md` in that PR.

### 2.3 Plan submission

`submit_plan` checks the plan schema and the candidate evidence. It rejects unknown hosts
and packages, installed versions that differ from the evidence, patch versions that are not
available candidates, duplicate package decisions, unsupported actions and kernel patches.
It does not yet check CVEs, Debian version ordering, dependency changes, repository index
freshness, service checks or recovery artifacts. The plan targets must equal the evidence
targets. A valid plan is stored as pending with its canonical SHA-256. Changing the plan
resets any decision; resubmitting identical content keeps it.

### 2.4 Approval

Only the human operator approves or rejects, bound to the reviewed hash. The model has no
approve or reject tool.

    python -m patch_agent.operator show RUN_ID
    python -m patch_agent.operator approve RUN_ID --hash REVIEWED_SHA256
    python -m patch_agent.operator reject RUN_ID --hash REVIEWED_SHA256

### 2.5 Deployment request

Always blocked in this phase, including for an approved plan. The future executor must
revalidate the evidence and the scope before any change.

## 3. Exact plan fields

Source: `schemas/plan.schema.json`. All top-level fields are required and extra fields are
rejected.

| Field | Type | Rule |
|---|---|---|
| `run_id` | string | letters, digits, `_` or `-`; starts with a letter or digit; at most 64 characters |
| `targets` | array of strings | at least 1, unique |
| `canary` | string | |
| `packages` | array of items | at least 1 (see below) |
| `verification` | array of strings | at least 1, each non-empty |
| `recovery` | object | `snapshot` (non-empty string), `previous_packages` (boolean), `config_backup` (boolean) |

Package item (all fields required):

| Field | Type | Rule |
|---|---|---|
| `host` | string | |
| `name` | string | use the architecture-qualified form such as `curl:amd64`, matching the evidence keys |
| `current_version` | string | non-empty; must match the evidence |
| `proposed_version` | string or null | non-empty if a string; the schema does not tie it to `action` |
| `action` | enum | `patch` or `defer` |
| `priority` | enum | `critical`, `high`, `medium`, `low` |
| `advisories` | array of strings | each non-empty; may be empty |
| `reason` | string | non-empty |

## 4. From an assessment to a plan item (proposed)

| Assessment (PR #7) | Plan item |
|---|---|
| `host` | `host` |
| `package` | `name` |
| `installed` | `current_version` |
| `decision.proposed_version` | `proposed_version` |
| `decision.action` | `action` |
| `decision.priority` | `priority` |
| `decision.reason` | `reason` |
| finding ids | `advisories` |

An assessment does not provide `run_id`, `targets`, `canary`, `verification` or `recovery`.

## 5. Open questions

Raised in the PR #7 review; to settle with Baha and Wassim before plan generation is built.

1. Who fills `verification` and `recovery`? S2.3 binds configured policies into plans.
2. Plan targets must equal the evidence targets, but an assessment only lists hosts that have results.
3. `packages` needs at least one item, so a fleet with nothing to patch has no valid plan.
4. How to record "assessed, no advisory known": PR #7 rejects a known source package with no findings.
5. Nothing links a submitted plan back to an assessment.
6. The candidate `source` is null in the current producer, so a candidate binary version is compared with a source fixed version without knowing the candidate's source.

## 6. Verified today

The synthetic demo and the test suite exercise stages 2, 4, 5 and 6 with synthetic
evidence only; see [runbook.md](runbook.md) section 8.1 for the demo. Sanitized plan examples with patch and defer reasons
are not written yet.
