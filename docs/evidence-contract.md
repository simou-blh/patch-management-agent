# Fleet evidence contract v1

Producer/consumer proposal for the Sprint 1 inspection collector and assessment tools.
Review the shape with the inspection and assessment owners before integrating it.
The schema is [evidence.schema.json](../schemas/evidence.schema.json); the standalone
entry point is `patch_agent.evidence.validate_evidence_contract(document)`.

## Record shape

| Field | Meaning |
|---|---|
| `schema_version` | Integer `1`. Other versions are rejected rather than guessed. |
| `collected_at` | UTC time when the collection finished. |
| `targets` | Nonempty, unique list of selected inventory host names. |
| `hosts` | Exactly one result for every selected host, with no unselected host results. |

Each host result contains `status` (`ok` or `error`), its own `collected_at`,
`packages`, and `error`. The host timestamp records completion of that host's
inspection attempt and cannot be later than the overall collection completion.
Use `YYYY-MM-DDTHH:MM:SSZ`, optionally with 1–6 fractional-second digits. Offsetless
timestamps, non-UTC offsets, impossible calendar dates and leap seconds are rejected.
Dates are parsed explicitly: JSON Schema's `format` keyword alone is not sufficient.

- `ok`: nonempty installed-package map and `error: null`.
- `error`: empty package map and an error object with nonempty `code` and `message`.
  Do not present partial/stale package results as a successful inspection. Messages
  must be sanitized by the producer, without credentials, private keys or raw logs.

Package keys are architecture-qualified binary names such as `demo-package:amd64`.
This keeps two installed architectures of the same package separate. Each value has:

- `installed`: the observed binary version, preserved as a string.
- `source`: `{name, version}` for the installed source package, or explicit `null`
  if unknown. Omitting the field is invalid; `null` must not be interpreted as a match.
- `candidates`: zero or more available binary versions, each with `version`, its own
  `source` (object or `null`), and nonempty `origins`.

Each origin records `uri`, `suite`, and `component`, for example a Debian repository
URI, `bookworm-security`, and `main`. One candidate entry represents one binary
version; combine multiple origins into its `origins` list. Duplicate versions are
rejected even if their origin lists differ. An empty candidate list means no available
versions were observed, not that the installed package is secure or needs no action.

Unknown fields are rejected so producer/consumer typos cannot silently change meaning.
Version strings are not ordered or interpreted here; use Debian version semantics
in assessment. Origins support HTTP(S) URIs with a host or file URIs with a path,
without embedded username/password credentials. They are recorded, not fetched or
authenticated; the producer must still sanitize other fields and URL parameters.

## Examples and validation

All examples under [tests/fixtures/evidence](../tests/fixtures/evidence) are synthetic:

- [valid.json](../tests/fixtures/evidence/valid.json): known source mapping and one candidate.
- [partial-error.json](../tests/fixtures/evidence/partial-error.json): one successful host
  and one explicit failed host; this is a valid diagnostic collection, not usable
  evidence for patching both hosts.
- [invalid-missing-installed.json](../tests/fixtures/evidence/invalid-missing-installed.json):
  intentionally rejected because a package's installed version is missing.

```python
import json
from pathlib import Path
from patch_agent.evidence import validate_evidence_contract

example = json.loads(Path("tests/fixtures/evidence/valid.json").read_text())
validate_evidence_contract(example)  # returns None; no network, state writes or jobs
```

Malformed shapes raise `jsonschema.ValidationError`. Inconsistent host selection,
impossible timestamps and duplicate candidate versions raise `ValueError`.

## Compatibility and next boundary

This contract is not yet read by `submit_plan`, the collector or the live playbooks.
The existing manual `data/evidence.json` host/package map and approval tests stay
unchanged. Do not replace that file with the v1 envelope until its consumer integration
is implemented; no silent migration or automatic conversion happens in this feature.

Passing this validator does **not** establish trusted provenance, authorized inventory
membership, freshness, complete inspection coverage, advisory correctness or patch
eligibility. Old/future collections and failed-host diagnostic records can be structurally
valid. The next feature must reject them for affected selected hosts using agreed
freshness/completeness rules and a trusted collector. All deployment remains blocked.

Validation uses the project's existing [jsonschema validator pattern](https://python-jsonschema.readthedocs.io/en/stable/validate/).
