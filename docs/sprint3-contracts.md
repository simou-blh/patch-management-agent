# Sprint 3 result contracts

Sprint 3 documentation draft. It describes the result contracts on `main` at commit
`4a9fd91`, read from the schema files, `policies/services.json` and
[interfaces.md](interfaces.md). I did not read the Python validators or the playbook code,
so consistency rules beyond the schemas are not described here. Deployment stays blocked
for every plan, and this page does not tick any `plan.md` checkpoint.

## 1. Where each contract fits

| Stage | Schema | Produced by | State |
|---|---|---|---|
| Preflight | `schemas/preflight.schema.json` | `playbooks/preflight.yml` | Read-only checks; not run on the live lab |
| Patch | `schemas/patch.schema.json` | `playbooks/patch.yml` | Simulate mode by default; apply path gated by `deployment_unblocked` (default false) |
| Verify | `schemas/verify.schema.json` | `playbooks/verify.yml` | Same gating |
| Recover | `schemas/recover.schema.json` | `playbooks/recover.yml` | Same gating |
| Final report | `schemas/report.schema.json` | `request_deployment` | Blocked reports only |

Patch, verify and recover results are per host. Schema validity never authorizes execution
or proves that recovery worked.

## 2. Patch result v1

Top level (all required except `canary`): `schema_version` (1), `collected_at`, `target`
(host name), optional `canary` (boolean), `packages`, `summary`, `error`.

- `packages`: one entry per package, keyed by package name. Each entry has `name`,
  `architecture` (or null), `status` (`applied`, `skipped`, `deferred`, `failed`), `detail`,
  `installed_before`, `installed_after`, `target_version` (each a version or null),
  `action` (`patch` or `defer`), `service_restart` and `error`.
- `service_restart`: a list of `{service, restarted, error}`.
- `summary`: counts `total`, `applied`, `skipped`, `deferred`, `failed`.
- `error`: null, or `{code, message}` for a host-level failure.

## 3. Verify result v1

Top level (all required): `schema_version` (1), `collected_at`, `target`, `packages`,
`summary`, `error`.

- Package entry: `name`, `architecture`, `status` (`pass`, `fail`, `error`), `detail`,
  `expected_version`, `observed_version` (or null), `version_check` and `health_checks`.
- `version_check`: `name`, `architecture`, `status`, `detail` and a free-form `data` object.
- Health check entry: `service`, `check`, `status` (`pass`, `fail`, `error`, `skipped`),
  `detail`, plus optional `host`, `port`, `unit` and `url`.
- `summary`: counts `total`, `passed`, `failed`, `error`.

## 4. Recover result v1

Top level (all required): `schema_version` (1), `collected_at`, `target`, `diagnostics`,
`repair`, `restoration`, `manual_intervention` (boolean), `error`.

- `diagnostics`: free-form objects `dpkg_audit`, `apt_policy`, `service_status`.
- `repair`: `attempted`, `command`, `dry_run`, `result` (`succeeded`, `failed`,
  `not_attempted`), `detail`.
- `restoration.previous_packages`: `name`, `previous_version`, `architecture`, `attempted`,
  `result`, `detail` per package.
- `restoration.config_backups`: `path`, `attempted`, `result`, `detail` per file.
- Per [interfaces.md](interfaces.md), repair and package restoration are simulated with
  `apt-get -s` first and refused if APT would remove a package, and restored versions and
  config bytes are checked afterwards. The schema itself does not say when
  `manual_intervention` must be true.

## 5. Service policy

`policies/services.json` is the fixed allowlist for restarts and health checks. Today it
has `restart_policy: configured-only`, one service (`ssh`, restart `on-change`, one TCP
check on 127.0.0.1 port 22) and one package mapping (`openssh-server` to `ssh`). The demo
package `demo-package` has no entry. What patch and verify do for a package without an
entry was not checked here.

## 6. Final report today

`schemas/report.schema.json` is a foundation report. It requires `run_id`, `timestamp`,
`plan_hash`, `approval` (`pending`, `approved`, `rejected`), `final_status`, `reason`,
`jobs` and `recovery`, and it fixes `final_status` to `blocked` and both `jobs` and
`recovery` to empty lists. Its own title says to extend it for live rollout.

## 7. Gaps to settle before live canary work

1. The final report cannot represent success, failure, skipped hosts, recovery outcomes
   or partial success. Sprint 3 (S3.4) and Sprint 4 (S4.3) need an extended report.
2. The report cannot hold task IDs or log references, because `jobs` must stay empty.
3. Patch, verify and recover results carry no `run_id`, `plan_hash` or task ID, so linking a
   host result to an approved run is left to the future coordinator and facade (S3.1, S3.4).
4. The service policy covers a single package and service.
5. No contract here has been exercised against a real host. The parser and contract tests
   run in the local suite with synthetic data only.

## 8. Verified today

The local suite (344 passed, 400 skipped on 2026-11-13, see [validation.md](validation.md))
includes `tests/test_patch.py`, `tests/test_verify.py`, `tests/test_recover.py` and
`tests/test_preflight.py`. They use synthetic inputs. All live checks remain
`PENDING-LIVE`.
