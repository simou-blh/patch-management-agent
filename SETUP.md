# MVP foundation setup

This replaces the old Ubuntu 22.04/LangGraph/OSV setup. Requirements are in
[mvp.md](mvp.md); remaining development work is in [plan.md](plan.md).

## 1. Check the download budget first

Use the existing Kali WSL2 distro. Reserve roughly **2–4 GB of downloads**, with a
**5 GB buffer**, and **15–25 GB of disk space**. These are estimates; see
[download-budget.md](docs/download-budget.md). Do not run a full distribution upgrade,
reinstall Docker/VirtualBox, or download another WSL distro for this foundation.

Check existing tools before installing anything:

```powershell
wsl --list --verbose
Get-Command vagrant,docker,opencode -ErrorAction SilentlyContinue
& 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe' --version
```

Vagrant is the small orchestration tool that reads `lab/Vagrantfile` and asks
VirtualBox to create, start, stop and snapshot the three lab machines. It downloads
one Debian base image which all three machines reuse.

## 2. Windows lab prerequisites (download stage)

Install Vagrant only if missing, after checking its installer size:

```powershell
winget install -e --id Hashicorp.Vagrant
vagrant --version
```

Restart the terminal if PATH has not updated. Keep Vagrant/VirtualBox on Windows.
The lab is deliberately outside the WSL development tree:

```powershell
New-Item -ItemType Directory -Force C:\lab | Out-Null
Copy-Item .\lab\Vagrantfile C:\lab\Vagrantfile
Set-Location C:\lab
vagrant validate
# Downloads the pinned base box on first use; check its actual size first.
vagrant up --provider=virtualbox
vagrant status
vagrant snapshot save clean
```

Defaults: `bento/debian-12` version `202510.26.0`, amd64, headless, one CPU and 768 MB
RAM per VM. The handoff's newest `debian/bookworm64` had no VirtualBox build; Bento
has the required provider. Package repositories and box availability must be checked
before relying on an old image for a demonstration. Increase RAM only if required.

## 3. WSL control node (download stage)

Open Kali:

```powershell
wsl -d kali-linux
```

Check Python and existing tools first:

```bash
python3 --version  # 3.12+ required
command -v git curl ssh python3 uv ansible opencode docker || true
```

Install only missing development prerequisites; inspect APT's summary before accepting:

```bash
sudo apt update
sudo apt install --no-install-recommends git curl openssh-client python3 python3-venv jq shellcheck
```

Use system Python 3.12+ instead of downloading another Python distribution. If the
existing interpreter is older, schedule that upgrade within the download budget.
Install `uv` using the [official instructions](https://docs.astral.sh/uv/getting-started/installation/).
Install OpenCode **inside WSL** using its [Linux instructions](https://opencode.ai/docs/).
The Windows OpenCode installation is separate; it does not provide Linux tool access.
Use a trusted existing Git remote to clone this repository into a WSL directory such
as `~/patch-management-agent`, then enter it. Copying from `/mnt/c/...` also works;
exclude `.git` only if you deliberately want an unversioned copy. Do development on
the Linux filesystem to keep SSH key permissions and tool execution consistent.

```bash
uv sync --python python3
uv tool install ansible-core
uv run --no-sync python -m pytest -q
```

`uv sync` creates a transitive lock; review and commit `uv.lock` for the team after
resolution. Direct dependency versions are pinned in `pyproject.toml`. Test playbooks
with the same Ansible version as the pinned Semaphore container before enabling them.
No extra Ansible collection is required by the current read-only scaffolds.

## 4. SSH and osquery

From the WSL repo, copy Vagrant's per-machine keys onto the Linux filesystem:

```bash
bash scripts/sync_lab_keys.sh /mnt/c/lab
```

Before trusting hosts, compare their SSH host-key fingerprints with the fingerprints
printed from each VM console/Windows `vagrant ssh vm-01` session. Then connect once
from WSL using the key, accept the verified key, and repeat for `.12`/`.13`:

```bash
ssh -i ~/.ssh/patch-lab/vm-01 vagrant@192.168.56.11
ansible all -m ping
```

Keep strict host-key checking enabled. If WSL cannot reach VirtualBox's host-only
subnet, fix routing/firewall connectivity before proceeding; do not turn off SSH
verification. The default lab user has passwordless sudo for `sudo -n osqueryi`.

The infrastructure owner must implement the osquery bootstrap playbook using the
[official signed packages](https://osquery.io/downloads/official), then install it
on the VMs. Bootstrap is not implemented in this foundation. Once installed:

```bash
ansible all -b -m command -a 'osqueryi --json "select * from os_version"'
bash scripts/check_env.sh --live
```

In Windows `C:\lab`, save `vagrant snapshot save ready` after all three machines pass.
Restoring snapshots is an operator action: it discards guest changes since the snapshot.

## 5. Semaphore (download stage)

Start Docker Desktop. In Settings → Resources → WSL Integration, enable Kali if
available, then check `docker info` from WSL. The CLI must reach the daemon before
continuing. Do not install a second Docker daemon for this setup.

Copy `.env.example` to `.env`, set a nonempty admin password, and generate the
32-byte encryption key using the command in the example file. Keep both outside Git.

```bash
cp .env.example .env
# Edit .env in your terminal/editor before these commands.
docker compose config --quiet
docker compose pull semaphore
docker compose up -d semaphore
curl --fail http://localhost:3000/api/ping
```

The UI is at `http://localhost:3000`. SQLite and configuration live in a named volume;
`docker compose down` keeps it. Do not use `down -v` unless intentionally deleting data.

For an **operator-only upstream transport test**, create a Semaphore API token through
its UI, put it in `.env`, then explicitly enable the optional profile:

```bash
docker compose --profile upstream pull semaphore-mcp
docker compose --profile upstream up -d semaphore-mcp
```

It serves MCP at `http://localhost:8500/mcp`. It listens on container port 8000;
`MCP_PORT=8000` matches the port mapping. Do not register this upstream server with
OpenCode. Its code is AGPL; run it separately rather than vendoring it.

`semaphore/templates.json` is a design list, not an import payload. The infrastructure
and playbook owners still need to create the project, repository, inventory, SSH
credentials and fixed templates, then record their IDs in an operator-owned mapping.
Windows host-only routes from Docker also require a live connectivity check.

## 6. OpenCode and operator approval

From the WSL repo, after syncing dependencies:

```bash
source .venv/bin/activate
opencode mcp list
opencode
```

Connect one provider via `/connect`. No provider or fallback is hardcoded, and API
traffic costs depend on the chosen provider. For OpenCode 2.1.4 the project uses
`mcp.servers`, `agents` and `permissions`, verified against its live JSON schema.
The old flat `mcp` map remains legacy-compatible; earlier setup notes confused the two.
The servers launch with `python -m ...`, without requiring `uv` at launch. Activate
the project environment first on a fresh machine. On this Windows machine the existing
Python installation already has the required dependencies, so `opencode mcp list`
also works directly from PowerShell. Do not mix Windows and WSL virtual environments.

After configuration changes run `opencode reload`, then start a fresh conversation
with the `patch` agent. For a small test, ask:

> Call fleet_inventory_catalog once. Return only the configured host names. Do not query or deploy.

The `patch` agent limits work to three steps, asks for at most 100 words, and disables
unrelated inherited MCP servers and skills through project integration policies.
Your global OpenCode configuration is unchanged. Both project servers use
`codemode: false`, so their five tools are available directly while general execution
stays denied. These settings reduce tool context and work loops; they do not enforce
an exact total token budget or provider billing cap.

For a CLI smoke test, explicitly choose the model you already use in the UI:

```powershell
opencode run --agent patch --model openai/gpt-6-luna "Call fleet_inventory_catalog once. Return only configured host names. Do not query or deploy."
```

The CLI's default model can differ from the UI's selected model. If it reports a
provider quota/429 error, stop and choose your existing connected model; do not retry
or reconfigure another provider automatically.

The project config denies built-in tools and allows only `fleet_*` and `approval_*`
MCP tools for assessment. Do development and human approval in a separate terminal.
Read [interfaces.md](docs/interfaces.md) for the local prototype's trust boundary.

Candidate evidence collection is unfinished. Until the team implements it, an operator
must create `data/evidence.json` from real trusted inspection results before the
model can submit a plan. Show/approve/reject it with `patch_agent.operator`; deployment
requests stay blocked even after approval. No code currently starts a Semaphore job.

## Environment-ready gates (live, still to validate)

The lab is necessary before claiming a patching MVP works, but is not needed for this
MCP/approval smoke test. Every developer should use the same committed lab/configuration;
not every developer needs to run the VMs continuously. The infrastructure/playbook
owners must validate the full environment before the first live rollout demonstration.

- Windows `vagrant status`: three Debian machines running.
- WSL `ansible all -m ping`: three pongs with verified host keys.
- osquery returns Debian 12 on all machines.
- Semaphore UI/ping answers; inventory and a read-only inspection template complete a task.
- If testing upstream: an MCP client can initialize and list tools at `:8500/mcp`.
- OpenCode lists both local adapters and returns per-host read-only inventory evidence.
- Approved and unapproved deployment requests both remain blocked in this foundation.

Foundation tests do not prove these gates. Advisory matching, deterministic pending
updates, deployment and recovery have separate acceptance gates in `mvp.md`.
