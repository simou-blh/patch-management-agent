# MVP foundation setup

The current entry point is [SETUP.md](../SETUP.md). Download estimates live in
[download-budget.md](download-budget.md); development contracts live in
[interfaces.md](interfaces.md). Follow [plan.md](../plan.md) for unfinished work.

Documentation was checked against the following primary sources on 2026-10-26.
Context7 was requested but no Context7 tools were exposed in the session, so these
sources and installed package APIs were used directly:

- [OpenCode live JSON schema](https://opencode.ai/config.json): v2 uses `mcp.servers`, `agents` and `permissions`; the prose guides also contain legacy examples.
- [OpenCode v2 permissions](https://opencode.ai/v2/docs/permissions): deny general execution/edit tools; expose only the two native MCP tool catalogs.
- [OpenCode v2 integration policies](https://opencode.ai/v2/docs/policies/): load only the project MCP servers and omit unrelated skills.
- [Python MCP SDK v2](https://py.sdk.modelcontextprotocol.io/): `MCPServer`, `Client`, stdio transport.
- [Semaphore Docker setup](https://semaphoreui.com/docs/admin-guide/installation/docker): SQLite is supported in v2.16+.
- [Semaphore MCP](https://github.com/cloin/semaphore-mcp): its `MCP_PORT` must match the container port mapping.
- [Vagrant VirtualBox provider](https://developer.hashicorp.com/vagrant/docs/providers/virtualbox).
- [osquery packages](https://osquery.io/downloads/official): use the official signing/repository instructions when implementing bootstrap.
- [osquery Debian table](https://github.com/osquery/osquery/blob/master/specs/linux/deb_packages.table).
