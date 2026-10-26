# SETUP: one identical environment for the whole team (v2)

**Rule:** all six of us work on the **same stack, the same versions, the same folders**. If something works on one machine and not on another, the environment is wrong, not the code.

Follow this file top to bottom. Do not skip a step, and do not "improve" it on your own (different Python, different Ansible, native Windows Python...). If a step fails, open a GitHub issue with the exact error and the output of `./scripts/check_env.sh`.

Companion files: [README.md](README.md) (concept), [PLAN.md](PLAN.md) (who does what, interfaces, tests), [`docs/reference/PROJECT_FULL_REFERENCE.md`](docs/reference/PROJECT_FULL_REFERENCE.md) (teacher documents and the core's source code).

> **What changed in v2** (aligned with PLAN.md v2):
> - The teacher's **core runs locally**, inside the repo folder in `noyau-local/` (git-ignored, **never modified**), with its **own virtual environment** `.venv-core` and **PostgreSQL in Docker** (`pg-plateforme`). It is required for every integration test (PLAN section 5).
> - New helper `scripts/start_core.sh`, an updated `check_env.sh` (core, PostgreSQL, Docker daemon), new `.gitignore` / `.dockerignore` entries.
> - A table of **which URL to use** depending on where the core and the agent run (section 9).
> - The contract tools `scripts/simulate_core.sh` (Dhia) and `scripts/submit_agent.py` (Ahmed) are described in PLAN.md; section 9 below only tells you when to use them.

| Layer | Standard for everyone |
|---|---|
| Host OS | Windows 10/11 64-bit with virtualization enabled in BIOS/UEFI |
| Linux for development | **WSL2 + Ubuntu 22.04** (the control node) |
| Python | **3.11** (deadsnakes PPA). Agent: `.venv` at the repo root. Core: `noyau-local/.venv-core` (separate, its versions are pinned by the teacher) |
| Lab hypervisor | **VirtualBox + Vagrant**, installed on **Windows** (not inside WSL) |
| Lab VMs | 3 x `ubuntu/jammy64` (Ubuntu 22.04), 1 GB RAM each |
| Automation | Ansible (pip, inside `.venv`) + `ansible.posix` collection |
| Inventory/verification | osquery, installed on the VMs by our playbook |
| Containers | Docker Desktop with WSL integration |
| Database for the core | **PostgreSQL 16 in Docker**, container `pg-plateforme` |
| Editor | VS Code + "WSL" extension (work inside the WSL filesystem) |
| Code location | `~/ai-patch-agent` **inside WSL** (never under `/mnt/c`) |
| Lab location | `C:\lab` on Windows (Vagrant files and VM disks) |
| Platform core | `~/ai-patch-agent/noyau-local/` (unzipped teacher archive, git-ignored) |

> Minimum hardware: 8 GB RAM, about 30 GB free disk. With less RAM, run **2 VMs** (node1 canary + node2 fleet) and remove node3 from `Vagrantfile` and `inventory.ini`. The core + PostgreSQL + agent add roughly 1 GB: close what you do not need. Tell Ahmed if your PC cannot cope so the lab can be shared.

---

## 0. Before you start

1. Make sure **virtualization is on** (Task Manager, Performance, CPU: "Virtualization: Enabled"). If not, enable it in BIOS/UEFI (Intel VT-x / AMD-V / SVM).
2. The **teacher's zip** (sent by Mr SEBAA Abderrazak by email) is archived in the repo under `docs/reference/`. If it is not there yet, download it from the email and keep it: you need it in section 8.
3. Create a GitHub account if needed, and send your username to Ahmed so he can add you to the repository.
4. Create **your own** Gemini API key (https://aistudio.google.com, "Get API key"). One key per person, never shared, never committed.
5. Read the parts of `PROJECT_FULL_REFERENCE.md` listed for your role in **PLAN.md section 0**. Everyone reads sections 0, 2, 4, 13 and 14 of that reference.

---

## 1. Windows side (PowerShell as Administrator)

```powershell
# WSL2 with Ubuntu 22.04 (reboot when asked)
wsl --install -d Ubuntu-22.04
wsl --set-default-version 2

# Tools (or install them manually from their websites)
winget install -e --id Oracle.VirtualBox
winget install -e --id Hashicorp.Vagrant
winget install -e --id Docker.DockerDesktop
winget install -e --id Microsoft.VisualStudioCode
```

After the reboot:

```powershell
wsl -l -v          # Ubuntu-22.04 must show VERSION 2
vagrant --version
VBoxManage --version
```

**Docker Desktop:** Settings, Resources, WSL Integration, enable **Ubuntu-22.04**, then "Apply & restart".

**Limit WSL memory** so the VMs have room. Create `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
memory=3GB
processors=2
```

Then run `wsl --shutdown` and reopen Ubuntu. (3 GB because the core, PostgreSQL and the agent now run in WSL/Docker too. If your PC has only 8 GB, use 2 GB and 2 VMs.)

> VirtualBox next to WSL2/Hyper-V works on current versions but VMs can be slower. If `vagrant up` hangs or the VMs are extremely slow, tell the team (see Troubleshooting).

---

## 2. Inside WSL (Ubuntu 22.04 terminal)

First launch asks for a Linux username and password. Then:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential git curl wget unzip openssh-client \
    software-properties-common ca-certificates sqlite3 jq libpq-dev

# Python 3.11 (same version as our Docker image)
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev

python3.11 --version     # Python 3.11.x
git config --global user.name  "Your Name"
git config --global user.email "your-github-email"
```

---

## 3. Get the repository and install the agent dependencies

```bash
cd ~
git clone https://github.com/<ORG-OR-USER>/ai-patch-agent.git
cd ai-patch-agent

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel

# Until requirements.lock exists (Taha will produce it in Sprint 1):
pip install -r requirements.txt -r requirements-dev.txt
# After requirements.lock exists, use only:
#   pip install -r requirements.lock -r requirements-dev.txt

ansible-galaxy collection install ansible.posix
```

> Every new terminal for the agent: `cd ~/ai-patch-agent && source .venv/bin/activate`. Your prompt must start with `(.venv)`. The **core uses another environment** (section 8): do not mix them.

Open the project in VS Code **from WSL**:

```bash
code .
```

---

## 4. The lab (3 Ubuntu VMs) with Vagrant

Vagrant and VirtualBox run on **Windows**. The lab folder is `C:\lab`.

From **WSL**, copy the lab definition from the repo to Windows:

```bash
mkdir -p /mnt/c/lab
cp ~/ai-patch-agent/lab/Vagrantfile /mnt/c/lab/Vagrantfile
```

Then in **PowerShell** (not WSL):

```powershell
cd C:\lab
vagrant up                      # first time: downloads the box, takes several minutes
vagrant status                  # node1, node2, node3: running
vagrant snapshot save clean     # fresh OS snapshot, taken right after the first boot
```

The VMs and their addresses:

| VM | IP | Ansible group |
|---|---|---|
| node1 | 192.168.56.11 | `canary` |
| node2 | 192.168.56.12 | `fleet` |
| node3 | 192.168.56.13 | `fleet` |

**Check that WSL can reach the VMs:**

```bash
ping -c 2 192.168.56.11
```

If the ping fails, see Troubleshooting (network).

---

## 5. SSH keys, inventory and first Ansible contact

Windows files are world-readable from WSL, and SSH refuses private keys with loose permissions. So we **copy the Vagrant keys into WSL** with the right permissions (script in Appendix A):

```bash
cd ~/ai-patch-agent
chmod +x scripts/*.sh
./scripts/sync_lab_keys.sh          # copies to ~/.ssh/lab/node1..3 with chmod 600
```

> Re-run this script every time the VMs are **destroyed and recreated** (keys change). A `snapshot restore` does not change the keys.

Test Ansible against the three VMs (inventory and config are in the repo, see Appendix A):

```bash
ansible all -m ping
```

Expected: three lines with `"ping": "pong"`.

Check that the JSON callback our code relies on exists:

```bash
ansible-doc -t callback ansible.posix.json | head -3
```

---

## 6. Install osquery on the VMs

```bash
ansible-playbook playbooks/install_osquery.yml
ansible all -a "osqueryi --json \"SELECT name, version FROM os_version;\""
```

You must see Ubuntu 22.04 for each node. Then take the second snapshot (PowerShell, in `C:\lab`):

```powershell
vagrant snapshot save ready       # clean OS + osquery installed
```

**Reset between tests** (this is how we repeat the demo; pending updates come back):

```powershell
vagrant snapshot restore ready
```

> Never test directly on a machine that is not one of our VMs.

---

## 7. Your `.env` (private)

```bash
cd ~/ai-patch-agent
cp .env.example .env
nano .env            # paste YOUR Gemini key; set the current model name from AI Studio
```

Rules:

- `.env` is listed in `.gitignore`. Check with `git status`: it must **never** appear.
- If a key is ever pushed, **regenerate it immediately** and tell the team.
- OpenRouter / Groq keys are optional (fallback providers).
- `NOYAU_URL` depends on where the agent runs, see the table in section 9.

---

## 8. The platform core, run locally (`noyau-local/`)

The core is the teacher's platform. It is **read-only for us**: we never edit its files. We run it locally because every integration test (activation, alerts, isolation, cancellation) goes through it.

### 8.1 Put it in `noyau-local/`

Use the zip archived in `docs/reference/` (or the one from the email; adapt the path):

```bash
cd ~/ai-patch-agent
mkdir -p noyau-local
unzip -q "docs/reference/<teacher-zip-name>.zip" -d /tmp/noyau-zip
# find the folder that contains "app" and copy its content into noyau-local/
src="$(dirname "$(find /tmp/noyau-zip -maxdepth 3 -type d -name app | head -1)")"
cp -r "$src"/. noyau-local/
rm -rf /tmp/noyau-zip
ls noyau-local        # expected: agent-exemple  app  scripts  requirements.txt
git status            # noyau-local/ must NOT appear (it is git-ignored)
```

**Read `noyau-local/agent-exemple/` before coding.** It is the official template: `main.py`, `agent.manifest.json`, `Dockerfile`, `requirements.txt`. Our agent keeps the same organization (manifest at the repo root, working Dockerfile, the mandatory endpoints).

If the teacher publishes a new version of the core: delete `noyau-local/`, redo this step, and tell the team.

### 8.2 PostgreSQL (the core refuses to start without it)

```bash
docker run -d --name pg-plateforme \
  -e POSTGRES_USER=saas_user -e POSTGRES_PASSWORD=saas_pass \
  -e POSTGRES_DB=plateforme_agents \
  -v pg_plateforme_data:/var/lib/postgresql/data \
  -p 5432:5432 postgres:16
```

These are the defaults hard-coded in the core's `database.py`. The volume keeps your data if you remove and recreate the container.

### 8.3 Core virtual environment (separate from the agent's)

The core pins its own versions (fastapi 0.115.0, pydantic 2.9.2, bcrypt 4.0.1...) that can conflict with ours, so it gets its own environment:

```bash
cd ~/ai-patch-agent/noyau-local
python3.11 -m venv .venv-core
source .venv-core/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

### 8.4 Start the core and create the admin

Use the helper (Appendix A):

```bash
cd ~/ai-patch-agent
./scripts/start_core.sh        # keeps running: leave this terminal open
```

In a **second terminal**, once:

```bash
cd ~/ai-patch-agent/noyau-local
source .venv-core/bin/activate
export DATABASE_URL="postgresql+psycopg2://saas_user:saas_pass@localhost:5432/plateforme_agents"
export JWT_SECRET_KEY="dev-only-change-me-$(whoami)"     # same value as in start_core.sh
python scripts/create_admin.py                            # your own local admin account
deactivate
```

> `JWT_SECRET_KEY` must be the same one `start_core.sh` uses, otherwise your login cookie stops working after a restart. The default in the script is `dev-only-change-me-<your linux user>`.

### 8.5 Check it works

```bash
curl -s http://localhost:8000/docs | head -c 100
```

Then open in your Windows browser: `http://localhost:8000/` (home), `/inscription`, `/connexion`, `/catalogue`, `/mon-compte`, `/admin`, and the API docs at `/docs`.

Full scenario to run once the agent API exists: **PLAN.md section 5.6**. Taha writes the detailed `docs/core-local.md` in Sprint 0.

---

## 9. Which URL to use (core and agent together)

Our standard: **the core runs in WSL** (this file), the agent runs **either directly in WSL (uvicorn) or in Docker**.

| Core runs | Agent runs | `base_url` in `agent.manifest.json` | `NOYAU_URL` for the agent |
|---|---|---|---|
| WSL | uvicorn in WSL | `http://localhost:9000` | `http://localhost:8000` |
| WSL | Docker (`-p 9000:9000`) | `http://localhost:9000` | `http://host.docker.internal:8000` |
| Windows host | WSL | `http://localhost:9000` (to test) | Windows host IP seen from WSL (to test) |

The third row is **not guaranteed**: Taha tests every row in Sprint 1 and documents the result in `docs/core-local.md`. Use the first two rows.

Run the agent (once `api/main.py` exists), in your agent terminal:

```bash
cd ~/ai-patch-agent && source .venv/bin/activate
uvicorn api.main:app --port 9000 --reload
```

Or in Docker (Dhia owns the Dockerfile; the command is the same for everybody):

```bash
docker build -t ai-patch-agent .
docker run --rm -p 9000:9000 --env-file .env \
  -e NOYAU_URL=http://host.docker.internal:8000 \
  --add-host=host.docker.internal:host-gateway \
  -v ~/.ssh/lab:/keys:ro \
  -v ai_patch_data:/app/data \
  ai-patch-agent
```

**Contract tools** (details in PLAN.md):

```bash
scripts/simulate_core.sh http://localhost:9000                 # replays the core's calls, no core needed
python scripts/submit_agent.py http://localhost:8000           # submits the manifest to the core
```

Use `simulate_core.sh` **first**: if it passes, an agent problem is not a network problem.

---

## 10. Verify everything

```bash
cd ~/ai-patch-agent && source .venv/bin/activate
./scripts/check_env.sh
```

Every `[ok]` line is required. `[--]` lines (core, PostgreSQL) are required **only if you run the core** (Sprint 0: at least Taha, Dhia and Ahmed; everyone else once they need integration tests). Send a screenshot to the team channel when yours is all green. **Nobody starts coding before their check is green.**

---

## 11. Daily routine

Typical layout: **four terminals** (plus PowerShell for the lab).

| Terminal | Purpose | Commands |
|---|---|---|
| A | Core | `cd ~/ai-patch-agent && ./scripts/start_core.sh` |
| B | Agent | `cd ~/ai-patch-agent && source .venv/bin/activate && uvicorn api.main:app --port 9000 --reload` |
| C | Work/Git/tests | `cd ~/ai-patch-agent && source .venv/bin/activate` |
| PowerShell | Lab | `cd C:\lab` then `vagrant up` / `halt` / `snapshot restore ready` |

Git:

```bash
cd ~/ai-patch-agent && source .venv/bin/activate
git checkout main && git pull
git checkout -b feature/<short-name>        # one branch per feature
# ... work ...
git add -p && git commit -m "Add canary verification step"
git push -u origin feature/<short-name>      # then open a Pull Request
```

Halt the VMs and stop the core (`docker stop pg-plateforme`) when you are not using them to save RAM.

**Rules that avoid classic accidents**

- The core is read-only for us. If it looks wrong, write down the case and ask the supervisors (PLAN.md section 12).
- `git add -p`, never `git add .`. `.env`, keys, `data/` and `noyau-local/` never enter Git.
- If you resubscribe a company in the core, it gets a **new tenant key**: read it again in `/mon-compte` before any manual call to the agent.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| `wsl --install` says virtualization is disabled | Enable VT-x/AMD-V in BIOS/UEFI, then retry. |
| `ping 192.168.56.11` fails from WSL | (1) `vagrant status` in `C:\lab`, the VMs must run. (2) In `C:\Users\<you>\.wslconfig` add `networkingMode=mirrored` under `[wsl2]` (Windows 11 22H2+), then `wsl --shutdown`. (3) Allow ICMP/SSH for the VirtualBox host-only adapter in Windows Firewall. Not verified on every machine: report what works for you. |
| `ansible all -m ping`: "Permission denied (publickey)" | Run `./scripts/sync_lab_keys.sh` again, check `ls -l ~/.ssh/lab` (mode `-rw-------`). |
| `ansible all -m ping`: "UNPROTECTED PRIVATE KEY FILE" | Key was read from `/mnt/c`. Use the copies in `~/.ssh/lab` via the script. |
| `vagrant up` hangs on "SSH auth" | Re-run `vagrant up`; check VirtualBox is not blocked by Hyper-V settings; close other heavy apps; try 2 VMs. |
| `ansible-playbook: command not found` | Agent virtualenv not active: `source .venv/bin/activate`. |
| `Callback plugin ansible.posix.json not found` | `ansible-galaxy collection install ansible.posix` inside the activated `.venv`. |
| `pip install` fails building a package (agent or core) | `sudo apt install -y build-essential python3.11-dev libpq-dev`, retry. |
| Docker: `Cannot connect to the Docker daemon` in WSL | Start Docker Desktop and enable WSL integration for Ubuntu-22.04. |
| Core crashes at startup with a database error | PostgreSQL is not running: `docker start pg-plateforme` (or redo 8.2). Check `docker ps`. |
| Port 5432, 8000 or 9000 already used | Stop the other service or container using it (`docker ps`, `ss -ltnp`). |
| Core says `ModuleNotFoundError` or version conflicts | You are in the wrong virtualenv. The core only runs inside `noyau-local/.venv-core`; `start_core.sh` handles it. |
| Login to `/connexion` works then loses the session after a restart | `JWT_SECRET_KEY` changed. Use the same value every time (default of `start_core.sh`). |
| Agent shows badge **"Suspendu"** right after subscribing | The activation failed (the web UI shows no reason). Read the **agent logs**, reproduce with `scripts/simulate_core.sh`, or subscribe through the core's API `POST /subscriptions` (via `/docs`) to get the error message. Causes: wrong envelope, non-2xx code, answer slower than 10 s. |
| Submission returns `422` | You sent the raw manifest. Use `python scripts/submit_agent.py`. |
| Submission says the slug already exists | Change `slug` in `agent.manifest.json` (or delete the row in PostgreSQL) and resubmit. |
| Agent says `Tenant not active` after a container restart | `data/` was not on a volume. Use `-v ai_patch_data:/app/data`. |
| From Docker, `host.docker.internal` is not found | Add `--add-host=host.docker.internal:host-gateway` to `docker run`. |
| `curl` examples from the docs fail in PowerShell | Use WSL for all commands, or `curl.exe` and no `\` line continuations. |
| Reset the core's database from scratch | `docker rm -f pg-plateforme && docker volume rm pg_plateforme_data`, redo 8.2, restart the core, recreate the admin (8.4). |
| `.env` shows up in `git status` | Stop. Check `.gitignore` has a line `.env`; never `git add .` blindly, use `git add -p`. |
| `noyau-local/` shows up in `git status` | Stop. `.gitignore` must contain `noyau-local/`; never commit the teacher's core. |

---

# Appendix A: configuration files to commit (Ahmed commits these in the first PR)

Everyone else just runs `git pull`. File paths are relative to the repo root.

### `lab/Vagrantfile`

```ruby
Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/jammy64"
  config.vm.box_check_update = false

  {
    "node1" => "192.168.56.11",
    "node2" => "192.168.56.12",
    "node3" => "192.168.56.13",
  }.each do |name, ip|
    config.vm.define name do |node|
      node.vm.hostname = name
      node.vm.network "private_network", ip: ip
      node.vm.provider "virtualbox" do |vb|
        vb.name   = name
        vb.memory = 1024
        vb.cpus   = 1
      end
    end
  end
end
```

### `inventory.ini`

```ini
[canary]
node1 ansible_host=192.168.56.11 ansible_ssh_private_key_file=~/.ssh/lab/node1

[fleet]
node2 ansible_host=192.168.56.12 ansible_ssh_private_key_file=~/.ssh/lab/node2
node3 ansible_host=192.168.56.13 ansible_ssh_private_key_file=~/.ssh/lab/node3

[all:vars]
ansible_user=vagrant
ansible_python_interpreter=/usr/bin/python3
ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
```

### `ansible.cfg`

```ini
[defaults]
inventory = inventory.ini
host_key_checking = False
retry_files_enabled = False
interpreter_python = auto_silent
timeout = 30
```

### `.env.example`

```bash
# --- LLM providers (the agent tries them in this order) ---
GEMINI_API_KEY=
GEMINI_MODEL=            # copy the current model name from Google AI Studio

# Optional fallbacks (leave empty to skip)
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
GROQ_API_KEY=
GROQ_MODEL=

# --- CVE data ---
OSV_ECOSYSTEM=Ubuntu:22.04:LTS

# --- Platform integration (see SETUP.md section 9) ---
# agent in WSL (uvicorn):  http://localhost:8000
# agent in Docker:         http://host.docker.internal:8000 (set with -e in docker run)
NOYAU_URL=http://localhost:8000
KEYS_DIR=~/.ssh/lab       # in Docker: /keys (set by the Dockerfile)
DATA_DIR=                 # empty = ./data (in Docker: /app/data)
```

### `.gitignore`

```gitignore
# secrets
.env
*.pem
id_*
*_key

# python
.venv*/
__pycache__/
*.pyc
.pytest_cache/

# runtime data
data/
reports/
logs/
*.db

# teacher's core: local copy, never committed, never modified
noyau-local/

# lab / local
.vagrant/
.DS_Store
```

### `.dockerignore`

```gitignore
.env
.git
.venv*
__pycache__
data
reports
logs
.vagrant
noyau-local
docs
tests
lab
```

### `requirements.txt`

```text
fastapi==0.115.0
uvicorn[standard]==0.30.6
httpx==0.27.2
python-dotenv
openai
requests
ansible
langgraph
langgraph-checkpoint-sqlite
```

### `requirements-dev.txt`

```text
pytest
```

> Taha generates `requirements.lock` after Sprint 1 (`pip freeze > requirements.lock` from a clean install) so that **everybody and the Docker image use the exact same versions**. The core is **not** part of it: it keeps its own `noyau-local/requirements.txt` in `.venv-core`.

### `scripts/sync_lab_keys.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
LAB_DIR="${LAB_DIR:-/mnt/c/lab}"
mkdir -p ~/.ssh/lab && chmod 700 ~/.ssh/lab
for n in node1 node2 node3; do
  src="$LAB_DIR/.vagrant/machines/$n/virtualbox/private_key"
  if [ ! -f "$src" ]; then
    echo "Missing $src (did 'vagrant up' finish? Only 2 VMs? edit this script)"; exit 1
  fi
  cp "$src" ~/.ssh/lab/$n
  chmod 600 ~/.ssh/lab/$n
  echo "ok: ~/.ssh/lab/$n"
done
```

### `scripts/start_core.sh` (new in v2)

```bash
#!/usr/bin/env bash
# Starts the teacher's core locally (PostgreSQL container + uvicorn on :8000).
# The core is read-only for us: this script never edits noyau-local/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

docker start pg-plateforme >/dev/null 2>&1 || {
  echo "Container pg-plateforme not found. See SETUP.md section 8.2."; exit 1; }

cd "$ROOT/noyau-local"
[ -d .venv-core ] || { echo ".venv-core missing. See SETUP.md section 8.3."; exit 1; }
source .venv-core/bin/activate

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://saas_user:saas_pass@localhost:5432/plateforme_agents}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-dev-only-change-me-$(whoami)}"

exec uvicorn app.main:app --reload --port 8000
```

### `scripts/check_env.sh` (updated in v2)

```bash
#!/usr/bin/env bash
FAIL=0
ok()   { printf "  [ok] %s\n" "$1"; }
ko()   { printf "  [!!] %s\n" "$1"; FAIL=1; }
warn() { printf "  [--] %s\n" "$1"; }
chk()  { if command -v "$1" >/dev/null 2>&1; then ok "$1: $($2 2>&1 | head -1)"; else ko "$1 not found"; fi; }

echo "== Tools =="
chk python3.11 "python3.11 --version"
chk git "git --version"
chk curl "curl --version"
chk docker "docker --version"
chk ssh "ssh -V"
chk ansible "ansible --version"
docker info >/dev/null 2>&1 && ok "docker daemon reachable" || ko "docker daemon not reachable (start Docker Desktop, enable WSL integration)"

echo "== Agent Python env =="
[ -n "${VIRTUAL_ENV:-}" ] && ok "virtualenv active" || ko "virtualenv not active (source .venv/bin/activate)"
python -c "import fastapi, httpx, openai, langgraph" 2>/dev/null && ok "python dependencies" || ko "python dependencies missing"
ansible-galaxy collection list 2>/dev/null | grep -q ansible.posix && ok "ansible.posix collection" || ko "ansible.posix collection missing"

echo "== Secrets and Git hygiene =="
[ -f .env ] && ok ".env present" || ko ".env missing (cp .env.example .env)"
grep -qx '\.env' .gitignore && ok ".env is git-ignored" || ko ".env NOT in .gitignore"
grep -qx 'noyau-local/' .gitignore && ok "noyau-local/ is git-ignored" || ko "noyau-local/ NOT in .gitignore"
grep -qx 'data/' .gitignore && ok "data/ is git-ignored" || ko "data/ NOT in .gitignore"

echo "== Lab =="
ls ~/.ssh/lab/node1 >/dev/null 2>&1 && ok "lab keys synced" || ko "lab keys missing (./scripts/sync_lab_keys.sh)"
if ansible all -m ping -o >/tmp/ansible_ping.txt 2>&1; then ok "ansible ping on all nodes"; else ko "ansible ping failed (see /tmp/ansible_ping.txt)"; fi

echo "== Platform core (required only if you run it) =="
[ -d noyau-local/app ] && ok "noyau-local/ present" || warn "noyau-local/ missing (SETUP.md section 8.1)"
[ -d noyau-local/.venv-core ] && ok "core virtualenv present" || warn "noyau-local/.venv-core missing (section 8.3)"
docker ps --format '{{.Names}}' 2>/dev/null | grep -qx pg-plateforme && ok "PostgreSQL container running" || warn "pg-plateforme not running (docker start pg-plateforme)"
curl -fs -m 5 http://localhost:8000/docs >/dev/null 2>&1 && ok "core answers on :8000" || warn "core not running (./scripts/start_core.sh)"

[ "$FAIL" = 0 ] && echo "ENVIRONMENT OK" || { echo "ENVIRONMENT NOT READY"; exit 1; }
```
