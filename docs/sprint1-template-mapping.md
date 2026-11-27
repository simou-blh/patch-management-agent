# Sprint 1 read-only template mapping (draft)

Status: **mapping recorded; live Semaphore inspection demonstrated on 2026-11-27** (see
[validation record](validation.md#update-2026-11-27-live-lab-runs-for-abderaoufs-playbooks)).
This supports S1.2d; Taha still needs to confirm the mapping before the checkpoint is ticked.

Deployment remains blocked.

## Fixed read-only inspection/verification mapping

The Semaphore project/templates are operator-owned. Template IDs are assigned in Semaphore
and must be recorded outside model-visible config before execution is enabled. This file
records the fixed playbook mapping; actual Semaphore template IDs are pending.

| Logical template | Playbook | Kind | Mutates host | Output contract | S1.2d role |
|---|---|---|---|---|---|
| `inspect` | `playbooks/inspect.yml` | read-only evidence collection | No | evidence v1 (`schemas/evidence.schema.json`) | Required inspection demonstration |
| `verify` | `playbooks/verify.yml` | read-only post-check / observed version & health verification | No | verify v1 (`schemas/verify.schema.json`) | Fixed read-only verification mapping |

Related read-only template (not the S1.2d demo target, but fixed mapping):

| Logical template | Playbook | Kind | Mutates host | Output contract |
|---|---|---|---|---|
| `preflight` | `playbooks/preflight.yml` | read-only readiness checks | No | preflight v1 (`schemas/preflight.schema.json`) |

Blocked mutation templates (must remain blocked in Sprint 1):

| Logical template | Playbook | Kind | Status |
|---|---|---|---|
| `patch` | `playbooks/patch.yml` | simulate-only exact-version patch | `deployment_unblocked` defaults to false; fail gate |
| `recover` | `playbooks/recover.yml` | simulate-only recovery | `deployment_unblocked` defaults to false; fail gate |

## Inspection template (S1.2d target)

- **Playbook**: `playbooks/inspect.yml`
- **Module**: `playbooks/library/inspect_packages.py`
- **Read-only commands**: `dpkg-query -W -f ...`, `apt-cache policy <names>`
- **Expected envelope fields**: `schema_version`, `collected_at`, `targets`, `hosts`
- **Per-host fields**: `status`, `collected_at`, `packages`, `error`
- **Package fields**: arch-qualified key, `installed`, `source` (object or `null`), `candidates[]` with `version`, `source`, `origins[]`
- **Failure behavior**: unreachable/failed hosts become explicit error records; other hosts' evidence is preserved
- **No mutation**: no apt install/upgrade/remove, no service restart, no file writes to managed host config, no `apt update`

## Verification template (read-only mapping)

- **Playbook**: `playbooks/verify.yml`
- **Module**: `playbooks/library/verify_packages.py`
- **Purpose**: compare observed installed versions and configured service health checks against approved expectations
- **Read-only behavior**: does not install, remove, restart, or change anything
- **Failure behavior**: emits structured result and fails the canary gate when verification does not pass

## Pending live demonstration (required to check S1.2d)

- [x] Semaphore project created with fixed template IDs recorded by the operator: project 1,
  inventory 1, repository 1, templates `inspect`=1, `verify`=2, `preflight`=3, `patch`=4,
  `recover`=5 (matches `semaphore/ids.json`; the SSH key is id 2 because Semaphore creates a
  built-in `None` key as id 1).
- [x] Read-only `inspect` template ran successfully through Semaphore against vm-01, vm-02,
  vm-03 (task status `success`, recap `ok=6/2/2`, all hosts `status: ok`).
- [x] Exported output validated as evidence-contract v1 and published by
  `python -m patch_agent.collector` (wrong target set and stale evidence were rejected).
- [x] Transport follows `scripts/collect_evidence.sh`: the operator extracts `fleet_evidence`
  from its own inspection run; no model-authored evidence.
- [ ] Runbook updated with sanitized evidence/log references and command transcript.

## Local evidence available now

- `tests/test_inspect.py` and `tests/test_evidence.py` pass locally (61 passed, 2026-11-26).
- `playbooks/inspect.yml` and `playbooks/library/inspect_packages.py` emit contract v1 fields.
- `semaphore/templates.json` records the design-only fixed template mapping.