# Reproducible vulnerable-package fixture (Sprint 1 S1.4d)

This specification defines the lab fixture used for the Sprint 2/3 assessment and
canary demonstrations. It is a **specification**, not a claim that the packages are
currently obtainable. Re-check availability and checksums on the lab before a demo.

## 1. Purpose

Provide a deterministic, recoverable update with:

- an installed version that is affected by a published Debian security advisory;
- a fixed version offered by a configured bookworm-security repository;
- a previous (installed) `.deb` that can be cached for rollback;
- a service with a configured health check (`ssh`), so verification and recovery can
  be exercised without inventing a service.

## 2. Package set

Use the OpenSSH source package group observed on the live lab on 2026-11-27:

| Binary package | Installed (vulnerable) | Fixed (target) | Role |
|---|---|---|---|
| `openssh-server` | `1:9.2p1-2+deb12u7` | `1:9.2p1-2+deb12u10` | service + health check |
| `openssh-client` | `1:9.2p1-2+deb12u7` | `1:9.2p1-2+deb12u10` | dependency in the same transaction |
| `openssh-sftp-server` | `1:9.2p1-2+deb12u7` | `1:9.2p1-2+deb12u10` | dependency in the same transaction |
| `libssl3` | `3.0.17-1~deb12u3` | `3.0.22-1~deb12u2` | dependency, forward-only |
| `openssl` | `3.0.17-1~deb12u3` | `3.0.22-1~deb12u2` | dependency, forward-only |

Approved rollback scope is the three OpenSSH binaries. `libssl3`/`openssl` only move
forward; the previous libssl3/openssl versions may no longer be published, so they must
not be part of the package rollback set. Configuration rollback uses the `sshd_config`
backup.

## 3. Preparation

1. Snapshot every VM as `baseline-before-fixture`.
2. Confirm the repository configuration and run `apt-get update` once.
3. Confirm the vulnerable versions are installed:
   `dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n' openssh-server openssh-client openssh-sftp-server libssl3 openssl`
4. Confirm the fixed versions are offered:
   `apt-cache policy openssh-server libssl3 openssl`
5. Cache the installed OpenSSH `.deb` files for rollback:
   `apt-get download openssh-server=<installed> openssh-client=<installed> openssh-sftp-server=<installed>`
6. Record the exact versions, `.deb` filenames and SHA-256 sums in the operator log
   (outside Git). Do not commit raw logs or machine-specific paths.

## 4. Reset

- Restore the snapshot `baseline-before-fixture` on each VM used in the scenario.
- Restore `sshd_config` from the preflight backup if recovery was exercised.
- Remove cached `.deb` files and `data/` artifacts from the previous run.
- Re-run the inspection and confirm the installed versions match step 3.

## 5. Acceptance checks

- The assessment marks the OpenSSH group affected and proposes the fixed versions.
- A plan that omits `libssl3`/`openssl` is refused by APT simulation
  (`scope_expansion`) before any package changes.
- Preflight reports `ready` only with the backup and all three OpenSSH artifacts
  `verified`; a missing artifact or an unoffered target yields `not_ready`.
- Canary patch applies the approved versions, restarts `ssh` only after a successful
  install, and verification passes version and TCP health checks.
- A verification failure triggers bounded recovery on the affected host only; the
  follow-up verification passes, or manual intervention is reported explicitly.
- Fleet hosts that were not reached remain byte-identical to the pre-rollout evidence.

## 6. Budget and availability

- The `.deb` files are a few MB total; the VM images dominate the 2–5 GB budget.
- If any fixed version is no longer offered, do not substitute a synthetic package.
  Rebuild the fixture from the then-current security update and record the new versions.
- Never use synthetic versions as live evidence.
