# Foundation validation — 2026-10-26

## Verified locally

- `python -m pytest -q`: **27 passed**, including actual stdio MCP subprocesses,
  the configured Python launch arguments, and the isolated approval CLI demo.
- `opencode mcp list`: **approval connected, fleet connected**. Project integration
  policies omit unrelated inherited MCP servers and skills.
- The project configuration validates against the live OpenCode v2 JSON schema.
- Real OpenCode/GPT-6 Luna smoke test: called `fleet_inventory_catalog` once and
  returned `vm-01`, `vm-02`, `vm-03`. These are configured names, not live VM evidence.
- `git diff --check`: passed. Compose configuration was also validated without
  starting services or pulling images.

The original connection failures came from launching `uv`, absent on this Windows
machine. MCP commands now use the available `python -m patch_agent...` directly.
The servers set `codemode: false` so the five native MCP tools remain available
while general code execution is denied. OpenCode v2 otherwise hides Code Mode tools
when `execute` is denied, even if their MCP servers are connected.

The CLI's unspecified model hit an OpenCode free-provider quota. Explicitly choosing
the user's existing `openai/gpt-6-luna` model worked; no provider credentials or global
configuration were changed. The successful test used a warmed regular OpenCode
session; standalone startup did not reliably produce a tool result and is not used
in the recommended command.

## Reproduce

```powershell
python -m pytest -q
python scripts/demo.py
opencode reload
opencode mcp list
opencode run --agent patch --model openai/gpt-6-luna "Use the fleet inventory catalog tool once to list configured hosts. Return those names only."
```

Use your own existing selected model if different. The model call consumes provider
usage; tests and the synthetic demo do not. Local smoke-test details are saved in
`data/opencode-smoke.json` and intentionally stay outside Git.

## Still unverified

Docker service startup, three real VMs, SSH/osquery against those machines, actual
APT/security evidence, canary patching, sequential rollout, and recovery. The lab
configuration is committed source for the team; provisioning and live environment
checks remain necessary before the first patching demonstration. See SETUP.md.
