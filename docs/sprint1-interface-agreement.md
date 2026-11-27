# Sprint 1 producer/consumer interface agreement (draft)

Status: **draft for team review**. This document records the proposed producer/consumer
decisions for S1.2b. It does not by itself tick a plan checkpoint; the team must confirm
or correct it and record the agreement in a merged PR.

Deployment remains blocked.

## Participants

- **Producers**: Abderaouf (inspection playbook/output), Taha (lab/Semaphore transport)
- **Consumers**: Wassim (collector/readiness/approval), Baha (advisory assessment/matching)
- **Reviewer context**: Dhia/Ahmed for runbook/CI acceptance

## Agreed contract boundaries

| Boundary | Producer | Consumer | Contract | Current state |
|---|---|---|---|---|
| Inspection evidence | `playbooks/inspect.yml` + `playbooks/library/inspect_packages.py` | `patch_agent.collector`, `patch_agent.evidence.validate_evidence_readiness`, `submit_plan` | `schemas/evidence.schema.json`, [evidence-contract.md](evidence-contract.md) | Implemented in code; live Semaphore export pending |
| Evidence readiness/import | Operator-owned collector | `submit_plan` / approval boundary | `patch_agent.evidence`, `patch_agent.collector` | Merged (S1.3) |
| Advisory cache / assessment | Baha (future assessment producer) | future plan generation / review | `schemas/advisory-cache.schema.json`, `schemas/assessment.schema.json`, [assessment-contract.md](assessment-contract.md) | Contracts merged (S1.4b/c); matching not implemented |
| Read-only template mapping | Taha/Abderaouf | operator/Semaphore execution boundary | `semaphore/templates.json`, [interfaces.md](interfaces.md) | Design-only; live template IDs pending (S1.2d) |

## S1.2b decisions to confirm

1. **Evidence shape is contract v1.** Producers emit `schema_version: 1`, `collected_at`,
   `targets`, and per-host `status/collected_at/packages/error`. Consumers reject unknown
   fields, missing required fields, target/host mismatches, and invalid timestamps.
2. **Package identity is architecture-qualified.** Keys use `name:arch` (for example
   `curl:amd64`). Consumers must not match a candidate from another binary/architecture.
3. **Source mapping is explicit.** `source` is an object with `name/version` or `null`.
   `null` means unknown, not a safe match. Candidate `source` may be `null` until producer
   support is added.
4. **Candidates are observed APT versions.** Each candidate has `version`, `source`, and
   nonempty `origins`. Origins record `uri/suite/component`; unsupported/incomplete origins
   are omitted rather than guessed. Duplicate candidate versions are rejected.
5. **Errors are explicit, not partial success.** An `error` host has empty `packages` and
   sanitized `error.code/message`. Failed-host diagnostic collections are structurally valid
   but not ready for plan submission.
6. **Freshness/completeness are consumer policy.** The collector and `submit_plan` require
   `PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS`, exact requested targets, configured inventory
   membership, all hosts successful, and no future/stale timestamps. The age limit is
   operator-owned and not model-chosen.
7. **Provenance is not established by file shape.** The importer validates and atomically
   publishes trusted exports; it does not prove where the file came from. Live Semaphore
   transport and trusted export path remain pending.
8. **Assessment consumes evidence; it does not mutate it.** Assessment results bind to
   evidence/advisory digests and compare Debian source versions via `patch_agent.debversion`.
   Assessment contracts do not authorize approval or execution.

## Known review findings / open items

- Confirm the team age-limit value for `PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS` in lab docs.
- Confirm whether candidate source mapping will be enriched by the producer or resolved by
  assessment; current producer emits candidate `source: null`.
- Confirm Semaphore template IDs and trusted export transport before S1.2d/S1.5c evidence.
- Keep `semaphore/templates.json` design-only until the real Semaphore project is created.

## Evidence to attach before checking S1.2b

- Merged PR updating or confirming this agreement.
- Reviewer confirmation from Abderaouf, Meftah and Baha (PR review/approval or recorded note).
- Any contract review findings resolved in code/docs/tests, with links.