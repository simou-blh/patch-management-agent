# Semaphore environment setup (operator guide)

This guide stands up the orchestration layer: Ansible Semaphore (UI/API on
`localhost:3000`, SQLite, Docker) with the five fixed task templates bound to
the three-VM lab. It complements [SETUP.md](../SETUP.md) §5 and records the
failure modes found while bringing this exact stack live (2026-11-17/18).

Everything below assumes: Vagrant lab running (`C:\lab`), the Kali WSL control
node cloned and tooled, and Docker Desktop with **WSL integration enabled for
`kali-linux`** (Settings → Resources → WSL Integration).

## 1. Secrets first: `.env` (never in Git)

```bash
cp .env.example .env
```

Set in `.env`:

- `SEMAPHORE_ADMIN_PASSWORD` — the admin login password.
- `SEMAPHORE_ACCESS_KEY_ENCRYPTION` — the 32-byte key (generate with the
  command in `.env.example`). Stored keys become undecryptable without it.

`.env` is git-ignored. Losing it means re-entering key-store material, not
losing projects.

## 2. Start the stack

```bash
docker compose config --quiet
docker compose up -d semaphore
curl --fail http://localhost:3000/api/ping
```

Do **not** enable the `upstream` profile (`semaphore-mcp`, port 8500) unless
performing the operator-only transport test. Never register it with OpenCode.

## 3. First login, and the first-boot trap

Login: user `admin` (from `SEMAPHORE_ADMIN` in `compose.yml`) + your
`.env` password.

> **Trap:** `SEMAPHORE_ADMIN*` variables create the admin **only at first
> boot**, when the database is initialized. Editing `.env` later never updates
> an existing account. If the stored password diverges, reset it from inside
> the container:
>
> ```bash
> docker compose exec semaphore semaphore users change-by-login \
>   --login admin --password 'NEW_PASSWORD'
> ```

## 4. The database-path trap (read before any recreate)

The `SEMAPHORE_DB` environment variable is **not honored** by the image. The
generated `/etc/semaphore/config.json` points SQLite at
`/var/lib/semaphore/database.sqlite`, which lives in the container's
**ephemeral layer** — destroyed by every `docker compose up` recreate.

**Fix (apply once, per machine):** move the DB into the persistent
`semaphore_config` volume by pointing the config at `/etc/semaphore`:

```bash
docker compose exec -u root semaphore sed -i \
  's|/var/lib/semaphore/database.sqlite|/etc/semaphore/semaphore.sqlite|' \
  /etc/semaphore/config.json
docker compose restart semaphore
docker compose exec semaphore ls -la /etc/semaphore/   # semaphore.sqlite must appear here
```

After this, projects/keys/templates survive recreates. The original config is
regenerated only when missing, so the edit persists.

## 5. Project wiring (UI, five steps)

1. **New project** (e.g. `patch-management-agent`).
2. **Key Store** → new SSH key `patch-lab-vagrant`; upload the Vagrant private
   key (`C:\lab\.vagrant\machines\vm-01\virtualbox\private_key`). One entry
   covers all three VMs.
3. **Inventory** → static, user credentials = that key, content:
   ```text
   vm-01 ansible_host=192.168.56.11 ansible_user=vagrant
   vm-02 ansible_host=192.168.56.12 ansible_user=vagrant
   vm-03 ansible_host=192.168.56.13 ansible_user=vagrant
   ```
   Host **names** must match `lab/hosts.json` (plan validation binds to names,
   not IPs).
4. **Repository** → the fork you push to (`https://github.com/<you>/patch-management-agent.git`),
   branch `main`, no access key. Templates run *what is committed on that
   branch*, not local working trees.
5. **Task templates** — five, bound to that repo + inventory, playbook paths
   `playbooks/{inspect,verify,preflight,patch,recover}.yml`, no arguments, no
   environment. `preflight/patch/recover` are fail-gates by design.

Record the IDs the UI assigns into the operator-owned `semaphore/ids.json`
(kept out of Git; IDs and names only, never secrets):

```text
GET http://localhost:3000/api/projects                          → project id
GET http://localhost:3000/api/project/{id}/keys|inventory|repositories|templates
```

## 6. The container SSH trap (host-key verification)

The image ships `/etc/ssh/ssh_config.d/semaphore.conf`:

```text
Host *
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
```

The repo's `ansible.cfg` forces `-o StrictHostKeyChecking=yes`, which overrides
the `no` — leaving strict checking against an **empty** known_hosts: every
task fails with `No ED25519 host key is known`. Three pieces fix it, in order:

**a) Known-hosts file (host machine, git-ignored).** From the control node
with already-verified fingerprints:

```bash
cp ~/.ssh/known_hosts lab/semaphore_known_hosts   # entries for 192.168.56.11-13
```

Teammates without a verified `known_hosts` run `ssh-keyscan -t ed25519,rsa
192.168.56.11 192.168.56.12 192.168.56.13` after completing SETUP.md §4 and
compare fingerprints against each VM console first. `lab/semaphore_known_hosts`
is in `.gitignore`.

**b) Compose mount — note the container user.** The service runs as user
`semaphore` (`HOME=/home/semaphore`), **not** root:

```yaml
volumes:
  - ./lab/semaphore_known_hosts:/home/semaphore/.ssh/known_hosts:ro
```

**c) Override the image's ssh config (two options).** Windows bind-mounts
appear as mode 0777, and ssh rejects group/world-writable config files, so
the override cannot simply be mounted. Either:

- **Durable (preferred):** the repo's `ansible.cfg` pins the file explicitly
  for every Ansible ssh, in both worlds:
  ```ini
  ssh_args = -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=~/.ssh/known_hosts
  ```
  (`~` resolves to the control user's home in WSL and to
  `/home/semaphore` in the container.) Committed and pushed, it survives all
  recreates.
- **Immediate (ephemeral):** copy the override into the running container —
  `lab/semaphore_ssh.conf` containing:
  ```text
  Host *
    StrictHostKeyChecking yes
    UserKnownHostsFile /home/semaphore/.ssh/known_hosts
  ```
  ```bash
  docker cp lab/semaphore_ssh.conf \
    <project>-semaphore-1:/etc/ssh/ssh_config.d/semaphore.conf
  ```
  This lives in the container layer and is lost on the next recreate; use it
  only until the `ansible.cfg` change is pushed.

Never disable strict host-key checking. The whole trust chain (SETUP.md §4)
depends on it.

## 7. Smoke test

Run the `inspect` template in the UI. Expected: repository clones, no
`UNREACHABLE`, recap `ok=6/2/2`, and the emitted `fleet_evidence` envelope with
`"status": "ok"` on all three hosts. That envelope feeds the operator evidence
collector (`scripts/collect_evidence.sh`, [evidence contract](evidence-contract.md)).

If the clone fails with `Could not connect to github.com port 443`, that is
host-network flakiness seen on this setup: re-run the task. Do not "fix" it by
weakening any check.

## 8. Durability matrix (what survives what)

| Event | Survives | Lost |
|---|---|---|
| Container restart / Docker Desktop restart | volume DB, mounts, container-layer files | nothing |
| `docker compose up -d` recreate (config change) | volume DB, `lab/*` mounts | container-layer files: the `docker cp` ssh override |
| `docker compose down` (no `-v`) | everything above | nothing |
| `docker compose down -v` | **nothing** — by design | DB, projects, keys, templates |

Rule of thumb: run with the `ansible.cfg` fix pushed, and no recreate can hurt
you; run with the `docker cp` fix only, and re-apply §6(c) after any recreate.
