# Project instructions

For development, read `mvp.md` and `plan.md`. During patch assessment, use MCP evidence;
do not load project documentation into every conversation.
This repository is an MVP foundation, not a working deployment system yet.

- Use OpenCode, MCP, osquery, Debian 12, Semaphore and fixed Ansible playbooks.
- Reuse Kali WSL for this machine's control node. Vagrant/VirtualBox run on Windows.
- Keep inventory queries fixed and read-only. Never accept arbitrary SQL or shell commands.
- Only the operator CLI may approve a plan. MCP tools must never grant approval.
- Keep deployment blocked until hash-bound approval, preflight, canary verification,
  sequential rollout and recovery have all been implemented and tested together.
- Never expose upstream Semaphore mutation tools directly to the model.
- Keep `.env`, SSH keys, advisory caches, plans and reports out of Git and model context.
- Do not install the superseded LangGraph/OSV/Ubuntu-VM stack or the teacher's core
  as part of the MVP setup. Preserve `PROJECT_FULL_REFERENCE.md` for later integration.
- Respect the 2–5 GB mobile-data budget: inspect metadata before large downloads;
  avoid blanket OS upgrades, image updates and downloading duplicate VM images.
- Verify changes with `python -m pytest`; live lab checks are separate and must
  never be reported as passing based only on mocks.

## Token discipline

- Answer in at most 100 words unless a full plan/report is requested.
- Use the minimum tool calls, batch hosts, and reuse collected evidence.
- No repeated plans, narrated work, delegation, speculative exploration or retry loops.
- On missing evidence or infrastructure, state the blocker once and stop.
- The default OpenCode `patch` agent has a three-step limit. It is not a total-token cap.
