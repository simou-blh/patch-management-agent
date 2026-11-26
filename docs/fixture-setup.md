# Vulnerable-package fixture: setup, reset and recovery

Status: TEMPLATE. Every `TODO` is a value the S2.1 owner (Taha) must supply.
Requirements come from [runbook.md](runbook.md) section 8.3. Nothing here is
live evidence until a run is recorded in [validation.md](validation.md).

## 1. Fixture package

| Field | Value |
|---|---|
| Package (architecture-qualified) | TODO (name:amd64) |
| Release | Debian 12 (bookworm) |
| Previous (vulnerable) version | TODO |
| Fixed version | TODO |
| Advisory / CVE | TODO |
| Source package and source version | TODO |
| Where both versions are obtained | TODO |
| How long both stay obtainable | TODO |

## 2. Lab baseline

| Host | Role | Snapshot name | Installed version at baseline |
|---|---|---|---|
| vm-01 | canary | TODO | TODO (previous) |
| vm-02 | fleet | TODO | TODO (previous) |
| vm-03 | fleet | TODO | TODO (previous) |

## 3. Reset procedure

1. TODO: restore the baseline snapshot on each host.
2. TODO: check the installed version equals the previous version.
3. TODO: check SSH keys, fingerprints and Semaphore connectivity.
4. TODO: record the time the reset takes.

## 4. Recovery prerequisites

- Previous package artifact cached at: TODO
- Configuration backups stored at: TODO
- Preflight must report `ready` for: privileges, disk space, APT locks,
  installed-version drift, candidate availability.

## 5. Checks after reset

| Check | Command | Expected output | Recorded by |
|---|---|---|---|
| Installed version | TODO | previous version | TODO |
| Candidate version | TODO | fixed version | TODO |

## 6. Known blockers

- The lab has not been brought up (see runbook blockers and
  [sprint2-checklist.md](sprint2-checklist.md) S2.1).