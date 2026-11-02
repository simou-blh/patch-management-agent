# Advisory cache and assessment result contracts v1

Producer/consumer proposal for the Sprint 2 advisory matching and plan generation.
Schemas: [advisory-cache.schema.json](../schemas/advisory-cache.schema.json) and
[assessment.schema.json](../schemas/assessment.schema.json). Entry points:
`patch_agent.assessment.validate_advisory_cache` and `validate_assessment_result`.
Versions are compared only with [`patch_agent.debversion`](../patch_agent/debversion.py).

Nothing here fetches data, reads the evidence store or is connected to `submit_plan`.
Passing validation does **not** establish freshness, authenticity, that evidence is
trusted, or that a patch is approved. All deployment remains blocked.

## Advisory cache

One cache holds the Debian security data for one `release`, keyed by **source package**
name. Each entry has `id`, `status` (`resolved`, `open`, `undetermined`),
`fixed_version` and `urgency`.

- `resolved` requires a `fixed_version`; `open` and `undetermined` require `null`.
- A fixed version must parse as a Debian version, and ids are unique per source package.
  `0` is valid and means "not affected in this release"; it always compares as fixed.
- `fetched_at` records when the data was cached; freshness limits belong to the consumer.
- The source URI is recorded, not fetched, and must not contain credentials.
- A source package absent from the cache means no advisory is known, not that it is safe.

## Assessment result

One record per assessed evidence collection. `evidence_collected_at` and
`advisory_fetched_at` bind the result to its inputs and cannot be later than `assessed_at`.
Each result is one `host` + architecture-qualified `package` (same IDs as
[evidence v1](evidence-contract.md)), unique within the record, with the observed
`installed` version, the evidence `source` (object or explicit `null`), a `status`,
its `findings` and a `decision`.

Finding `reason` fixes the finding `status` and whether a fixed version is present:

| reason | status | fixed_version |
|---|---|---|
| `installed_before_fix` | affected | required, and installed is older |
| `advisory_open` | affected | null |
| `installed_at_or_after_fix` | fixed | required, and installed is not older |
| `advisory_undetermined` | uncertain | null |
| `version_invalid` | uncertain | any; the installed version does not parse |

Result `status` follows the findings: `affected` if any finding is affected, else
`uncertain` if any is uncertain, else `fixed`. A result with **no findings** is allowed
only when the evidence `source` is `null` (advisories cannot be matched); its status is
`uncertain`.

`decision` is `null` for a `fixed` package; otherwise it is required:

- `defer`: `proposed_version` is `null`; the `reason` says why. Uncertain packages must defer.
- `patch`: only for an `affected` package, with an exact `proposed_version` that is at
  or after the fixed version of **every** affected finding. A package with an open
  (unfixed) affected finding must be deferred.
- `priority` uses the plan values. How it is derived from urgency is decided in Sprint 2.

## Mapping to a plan package

A result with a decision maps onto an item of [plan.schema.json](../schemas/plan.schema.json):
`host`, `name` = `package`, `current_version` = `installed`, `proposed_version`, `action`,
`priority`, `advisories` = the finding ids, `reason`. The proposed version must still be
confirmed as an available candidate in the trusted evidence before submission.

## Examples and validation

Synthetic examples (not real CVEs) are in
[tests/fixtures/assessment](../tests/fixtures/assessment). Malformed shapes raise
`jsonschema.ValidationError`; inconsistent records raise `ValueError`.
