# Patch Management Agent

MVP foundation for an AI-assisted Debian patch-management agent. The model proposes
changes; deterministic tools validate them, and a human approves the exact plan.

**Course:** Conduite de projet, ESTIN, 2026–2027. Supervisors: Pr. SEBAA Abderrazak
and Dr. MANSOUR Abdelaziz.

Read [mvp.md](mvp.md) for requirements, [plan.md](plan.md) for team tasks, and
[SETUP.md](SETUP.md) for setup. The earlier LangGraph/OSV/Ubuntu-VM instructions
have been replaced. The teacher's [platform reference](PROJECT_FULL_REFERENCE.md)
is retained for the later integration phase.

## Current state

Implemented and locally testable:

- Fixed read-only osquery queries over SSH, selected inventory hosts, per-host errors.
- JSON plan validation against operator-supplied package/version evidence.
- SQLite plan storage, canonical SHA-256 binding, operator-only approval/rejection.
- Changed plans invalidate approval. Every deployment request remains blocked.
- Two stdio MCP servers using Python MCP SDK v2, and restricted OpenCode configuration.
- Three-VM Debian lab configuration, pinned Semaphore images with SQLite, environment checks.
- Read-only inspection/verification observations and blocked preflight/patch/recovery scaffolds.

Not implemented: live Semaphore execution, automatic candidate/advisory collection,
Debian vulnerability matching, canary orchestration, health verification, recovery,
and the complete end-to-end report. The VM/container environment has not been brought
up or validated by the local foundation tests. This is the starting point for the team.

## Architecture

```text
Operator → OpenCode (one provider)
                ├── fleet MCP → fixed osquery queries → SSH → Debian VMs
                └── approval MCP → validated proposals → SQLite plans/decisions
Operator CLI ──────────────────────────────────────────→ approval decision

Later: approved facade → Semaphore MCP/API → fixed Ansible templates
                       → canary → verification → sequential fleet → report/recovery
```

The model does not receive upstream Semaphore mutation tools or an approve tool.
See [interfaces and trust boundary](docs/interfaces.md) before extending execution.

## Lightweight local defaults

Existing Kali WSL2 control node; OpenCode inside WSL; Vagrant and VirtualBox on Windows.
Three headless Debian 12 VMs at `192.168.56.11–13`, one CPU and 768 MB RAM each.
Semaphore uses SQLite. No extra Ubuntu distro, PostgreSQL or platform core is required.
Vagrant creates/recreates the VMs from a shared cached image; VirtualBox runs them.

Budget roughly 2–4 GB of downloads with a 5 GB buffer, subject to actual artifact sizes.
See the [download budget](docs/download-budget.md) before installing. Preparing these
source files does not require pulling images or downloading a VM.

## Development checks

Once dependencies are available:

```bash
python -m pytest -q
python scripts/demo.py
```

The terminal demo launches the real MCP subprocesses and operator CLI with synthetic
evidence in a fresh `data/demo-*` folder. It demonstrates invalid-input rejection,
approval, changed-plan invalidation and blocked execution, and saves readable JSON
reports. It needs no LLM, downloads, Docker or VMs. It does not demonstrate live patching.

For OpenCode on this Windows machine, run `opencode reload` then `opencode mcp list`:
`fleet` and `approval` should connect without uv. The default `patch` agent has a
three-step work limit and short-answer instructions; unrelated inherited MCP servers
are disabled only in this project. On a fresh team machine, activate the synced
Python environment before launching OpenCode. See [SETUP.md](SETUP.md#6-opencode-and-operator-approval).

From the WSL project environment:

```bash
uv sync --python python3
uv run --no-sync python -m pytest -q
bash scripts/check_env.sh
# After the real lab is ready:
bash scripts/check_env.sh --live
```

Direct Python dependencies are pinned; generating/reviewing a transitive `uv.lock`
is still an infrastructure task. Select one model provider through OpenCode `/connect`;
provider credentials stay in its local credential store, outside Git.
