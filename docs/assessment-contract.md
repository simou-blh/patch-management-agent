# Advisory cache and assessment result contracts v1

Producer/consumer proposal for the Sprint 2 advisory matching and plan generation.
Schemas: [advisory-cache.schema.json](../schemas/advisory-cache.schema.json) and
[assessment.schema.json](../schemas/assessment.schema.json). Entry points:
`patch_agent.assessment.validate_advisory_cache` and `validate_assessment_result`.
Versions are compared only with [`patch_agent.debversion`](../patch_agent/debversion.py).

Nothing here fetches data, reads the evidence store or is connected to `submit_plan`.
Passing validation does **not** establish freshness, authenticity, that evidence is
trusted, or that a patch is approved. All deployment remains blocked.

Both validators raise `jsonschema.ValidationError` for shape errors or `ValueError` for
inconsistent records. Callers can catch `patch_agent.assessment.CONTRACT_ERRORS`, a tuple
of both.

## Advisory cache

One cache holds the Debian security data for one `release`, keyed by **source package**
name. Each entry has `id`, `status` (`resolved`, `open`, `undetermined`),
`fixed_version` and `urgency`.

- `resolved` requires a `fixed_version`; `open` and `undetermined` require `null`.
- A fixed version is a **source package** version. It must parse as a Debian version, and
  ids are unique per source package. `0` is valid and means "not affected in this
  release"; it always compares as fixed.
- `fetched_at` records when the data was cached; freshness limits belong to the consumer.
- The source URI is recorded, not fetched. It must not contain credentials, a query or
  a fragment.
- A source package absent from the cache means no advisory is known, not that it is safe.

## Assessment result

One record per assessed evidence collection, bound to its two inputs by timestamp and by
digest: `evidence_collected_at` / `advisory_fetched_at` cannot be later than `assessed_at`,
and `evidence_sha256` / `advisory_cache_sha256` are the SHA-256 of each input record's
canonical JSON (sorted keys, compact separators, UTF-8), computed with
`patch_agent.assessment.canonical_sha256`. Evidence v1 has no identifier of its own, so the
digest is the binding; a consumer recomputes it to check which record was assessed.

Each result is one `host` + architecture-qualified `package` (same IDs as
[evidence v1](evidence-contract.md)), unique within the record, with the observed binary
`installed` version, the evidence `source` (object or explicit `null`), a `status`, its
`findings` and a `decision`.

### Which version is compared

Advisories carry **source** package versions, and binary versions can differ from them
(for example a rebuild such as `1.0-1+b1`). So the comparison input is the evidence
`source.version`, never `installed`. `installed` is recorded because it is what the plan
and the patch job bind to. A decision therefore carries both the exact binary
`proposed_version` to install and its `proposed_source_version`, which is what is compared
with fixed versions.

If `installed` or `source.version` does not parse, the result must carry a
`version_invalid` finding (and nothing can be compared or patched). If both parse, a
`version_invalid` finding is rejected. A result with `source: null` is never compared.

### Findings and status

Finding `reason` fixes the finding `status` and whether a fixed version is present:

| reason | status | fixed_version |
|---|---|---|
| `installed_before_fix` | affected | required, and source version is older |
| `advisory_open` | affected | null |
| `installed_at_or_after_fix` | fixed | required, and source version is not older |
| `advisory_undetermined` | uncertain | null |
| `version_invalid` | uncertain | any |

Result `status` follows the findings: `affected` if any finding is affected, else
`uncertain` if any is uncertain, else `fixed`. A result with no findings is:

- `no_known_advisory` when the source package is known: the package **was assessed** and
  no advisory is known. This is an explicit record, not a statement that it is safe.
- `uncertain` when `source` is `null`: advisories cannot be matched. Findings are not
  allowed without a known source.

A package without an entry was **not assessed**. An empty `results` list is invalid:
assessing nothing is a failure to report, not a clean result.

### Decision

`decision` is `null` for `fixed` and `no_known_advisory` packages; otherwise it is required:

- `defer`: `proposed_version` and `proposed_source_version` are `null`; `reason` says why.
  Uncertain packages must defer.
- `patch`: only for an `affected` package with **no uncertain finding**. The
  `proposed_source_version` must be at or after the fixed version of **every** affected
  finding, and a package with an open (unfixed) affected finding must be deferred.
- `priority` uses the plan values. How it is derived from urgency is decided in Sprint 2.
  Until then a package with an unknown source uses `medium`, which is enforced.

## Mapping to a plan package

A result with a decision maps onto an item of [plan.schema.json](../schemas/plan.schema.json):
`host`, `name` = `package`, `current_version` = `installed`, `proposed_version`, `action`,
`priority`, `advisories` = the finding ids, `reason`. `proposed_source_version` is not part
of the plan. The proposed version must still be confirmed as an available candidate in the
trusted evidence before submission.

## Examples and validation

Synthetic examples (not real CVEs) are in
[tests/fixtures/assessment](../tests/fixtures/assessment). The advisory digest in the
assessment example is that of the cache example; the evidence digest is illustrative.
