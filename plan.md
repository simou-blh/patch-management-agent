# Patch Management / System Architecture

**Agent:** Intillegent deplyment kit  
**Runtime:** Pi or OpenCode  
**Backend:** Python, FastAPI, and SQLite  
**Status:** proposed architecture and implementation approach; the described features are not yet completed functionality.

![Patch Management / System Architecture](architecture-black.svg)

## 1. Objective and scope

The project centers on an agent that observes a Linux VM fleet, explains deployment and security-update needs, proposes exact changes, obtains operator approval, executes Ansible workflows through MCP, verifies results, and reports failures or recovery.

The agent reasons about evidence. MCP adapters expose controlled operations. Ansible performs changes. osquery supplies system facts. Semaphore provides execution templates, scheduling, task output, and run history.

The first supported environment is Debian Minimal with APT and systemd. The initial lab has three target VMs and one control node. Host count, addresses, groups, application profiles, model providers, thresholds, and rollout settings are described in configuration, allowing the same agent to work with different lab environments.

The project includes:

- A reproducible lab and documented setup/reset procedure.
- The named agent, with Pi and OpenCode runtime adapters.
- Fleet-aware osquery MCP tools and approval-controlled Ansible MCP tools.
- Discovery, planning, preflight, deployment, verification, recovery, and reporting workflows.
- Automated tests, a scenario catalog, and a repeatable demonstration.
- Configuration examples, structured reports, version locks, and the architecture diagram.

Kernel upgrades, OS release upgrades, database migrations, arbitrary shell deployments, and automatic reboots are outside the first release. Later support would involve dedicated profiles and separate recovery tests.

## 2. Architecture and ownership

| Component | Responsibility | Location |
| --- | --- | --- |
| Operator | Supplies goals, reviews evidence, approves or rejects a specific plan | Pi/OpenCode interface |
| Intillegent deplyment kit | Collects evidence, explains findings, proposes plans, invokes tools, interprets results | Control node |
| Pi/OpenCode adapter | Loads agent identity, instructions, model settings, MCP connections, and UI hooks | Control node |
| Model provider | Supplies reasoning and tool selection through the selected runtime | Hosted service or configured local endpoint |
| osquery MCP fleet adapter | Runs named read-only queries on inventory hosts; returns normalized results | Control node |
| Execution MCP facade | Validates plans and approvals before forwarding permitted execution requests | Control node |
| Semaphore MCP backend | Connects approved execution requests and status reads to Semaphore's API | Private control-node service |
| Semaphore + Ansible Core | Runs versioned task templates and playbooks over SSH | Control node |
| osquery + SSH + Python + APT | Exposes facts and executes approved package/service operations | Target VMs |
| Debian advisory data | Supplies release-specific vulnerability and fixed-version information | Cached on control node |
| FastAPI control API | Handles authenticated operator approval, plan/run reads, and report access | Control node |
| Plan/event store | Stores inventory snapshots, plans, approvals, task IDs, and host outcomes | Control-node SQLite database |

Communication paths:

1. Operator -> agent -> model: goal, evidence, proposed plan, and approval interaction.
2. Agent -> osquery MCP -> SSH -> osquery on a target: discovery requests and JSON evidence.
3. Agent -> execution MCP facade -> Semaphore MCP -> Semaphore API -> Ansible -> SSH: approved deployment.
4. Task output and host results return through the execution path to the agent and operator.
5. Advisory data is joined with package inventory before proposing security remediation.

The agent has no target SSH key or unrestricted Semaphore token. Backend credentials belong to the adapters and execution service. Only the execution facade is exposed to the agent; the raw mutation-capable MCP backend is private. The same separation applies to built-in shell/file tools: their accessible files, credentials, and network paths exclude the private execution backend and state store.

The community [Semaphore MCP server](https://github.com/cloin/semaphore-mcp) offers task-launch and task-output tools. The official [AAP MCP server](https://github.com/ansible/aap-mcp-server) targets Ansible Automation Platform; it is not the selected Ansible Core/Semaphore integration.

## 3. Runtime, providers, and agent identity

### 3.1 Pi or OpenCode

Each runtime has a small adapter sharing the same MCP contracts, agent instructions, plan schema, policy, and reporting format. Implementation begins with an end-to-end workflow on one runtime, followed by validation of the same workflow on the other.

Runtime-specific responsibilities are startup, session events, provider/model selection, MCP configuration, approval interaction, and display. Deployment rules belong to the shared services, so switching runtime cannot change the approved execution scope.

Both upstream runtimes document MCP support: [Pi MCP](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/mcp.md) and [OpenCode MCP](https://opencode.ai/docs/mcp-servers/). Project compatibility is tied to pinned, tested releases, making the setup reproducible across machines.

### 3.2 Provider support

Provider support comes from the chosen runtime, including its supported providers and compatible custom endpoints. Authentication and provider SDK integration remain with the upstream runtime.

The upstream provider catalog is the source of truth. With both adapters installed, the agent can offer the union of their catalogs and identify which runtime can serve each entry. A provider supported only by one runtime requires that runtime.

[Pi providers](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/providers.md) and [OpenCode providers](https://opencode.ai/docs/providers/) document the current catalogs and authentication. Hosted, gateway, cloud, and local-model configurations remain available through those integrations.

Provider selection and compatibility:

- Runtime, provider, model, endpoint, and credential reference are selected through configuration or the runtime UI.
- Catalog refreshes preserve upstream provider/model IDs and require no deployment-code changes.
- Credentials remain in runtime credential storage or environment/secret references.
- A session readiness check covers authentication, model availability, structured tool calls, and context capacity.
- A connected provider is not proof that every model can run the tool workflow. Unsupported capabilities disable execution and explain the missing capability.
- Each plan and run records the runtime, version, provider, and model.
- Provider failure pauses reasoning; it does not launch another deployment.
- Changing runtime/model during an unexecuted approved plan requires plan review again.
- Provider fallback is explicit configuration, never an undocumented switch.

The full upstream catalog remains accessible. Configured providers with available credentials receive live tests; the remaining entries are labeled as inherited support without live validation.

### 3.3 Naming and future UI

The agent is named **Intillegent deplyment kit** in its instructions, session header, reports, and examples. The architecture keeps the title **Patch Management / System Architecture**.

The initial interface is the upstream UI with a named agent profile. A later [Pi extension](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md) or [OpenCode plugin](https://opencode.ai/docs/plugins/) can add project labels, a theme, commands, status indicators, and approval display where supported. Branding is a separate follow-up; provider selection and authentication remain available through the runtime.

## 4. Lab and dynamic environment

### 4.1 Initial topology

| Node | Role | Starting allocation |
| --- | --- | --- |
| control-01 | Agent, MCP services, Semaphore, Ansible, state store | 2 vCPU, 4 GB RAM, 20 GB disk |
| vm-01 | Healthy canary / demo application | 1 vCPU, 1 GB RAM, 10 GB disk |
| vm-02 | Second application target / failure scenarios | 1 vCPU, 1 GB RAM, 10 GB disk |
| vm-03 | Mixed-release, offline, or new-host scenarios | 1 vCPU, 1 GB RAM, 10 GB disk |

These allocations are starting values for the lab. Idle and active resource measurements determine whether they are sufficient. Local LLMs may need additional hardware; a hosted provider keeps model inference off the control node.

The baseline is Debian 13 Minimal, with a Debian 12 profile for mixed-release testing. Release and package support are checked during lab preparation against [Debian's release information](https://www.debian.org/releases/).

The lab can run on VirtualBox, libvirt, or Proxmox according to the available host. The reproducible setup documents one platform, while inventory and network requirements describe the equivalent setup on the others. Managed VMs run without a desktop environment.

### 4.2 Network and bootstrap

SSH and application traffic use a private VM network. Controlled outbound access covers package repositories, advisory refresh, and hosted providers. An offline profile uses a prepared package repository, advisory snapshot, and compatible local provider or recorded reasoning fixtures.

Bootstrap installs osquery, SSH, Python, python3-apt, and the demo application's prerequisites. It also provisions trusted SSH host keys and an automation user. Discovery permissions cover the named queries, while approved playbooks have the privilege escalation needed for package and service operations.

Provider credentials, SSH keys, Semaphore tokens, and the state database remain outside Git. Sample configuration contains credential references only.

### 4.3 Inventory rules

- Stable host IDs remain consistent across address and group-membership changes.
- Each inventory entry records OS release, architecture, SSH fingerprint, environment, roles, application profile, and enable/disable state.
- The initial inventory source is a file, behind an interface that can later support hypervisor or cloud discovery.
- Host identity and freshness are checked during discovery and immediately before mutation.
- Groups resolve to an explicit host list when a plan is created.
- A new host never joins an already approved rollout automatically.
- Removed/disabled hosts are excluded from new plans and blocked at execution even if an older plan included them.
- An address change requires identity verification. An unexpected SSH-key change blocks execution.
- Unsupported OS/package-manager profiles return unsupported, not an attempted APT command.
- Provisioned clones have distinct machine identities and host keys.

The following is the proposed project configuration, not native Pi/OpenCode configuration:

~~~yaml
backend:
  framework: "fastapi"
  database_path: "data/idk.sqlite3"

agent:
  name: "Intillegent deplyment kit"
  runtime: "pi"                  # alternative: opencode
  provider: "<upstream-provider-id>"
  model: "<upstream-model-id>"
  credential_ref: "<runtime-managed-reference>"

environment:
  name: "lab"
  inventory_source: "inventory/lab.yml"
  supported_releases: ["bookworm", "trixie"]

discovery:
  query_timeout_seconds: 30
  parallel_hosts: 3
  max_evidence_age_minutes: 15
  advisory_max_age_hours: 24

rollout:
  canary_host: "vm-01"
  batch_size: 1
  parallel_mutations_per_host: 1
  halt_after_canary_failure: true
  continue_after_noncanary_unreachable: true
  minimum_free_disk_mb: 1024
  apt_lock_wait_seconds: 30
  health_timeout_seconds: 60
  approval_ttl_minutes: 30
  reboot_policy: "report_only"

recovery:
  require_verified_backups: true
  retain_previous_packages: true

hosts:
  - id: "vm-01"
    address: "192.168.56.11"
    ssh_user: "automation"
    ssh_key_ref: "lab-controller-key"
    ssh_fingerprint_ref: "known-hosts/vm-01"
    environment: "lab"
    groups: ["web", "canary"]
    application_profile: "demo-http"
    enabled: true
~~~

Configuration validation covers value ranges and relationships as well as YAML syntax. Mutation concurrency respects the profile's minimum healthy instances, and the canary belongs to the approved target set.

## 5. MCP contracts

Local MCP processes use stdio; service connections can use authenticated Streamable HTTP. Transport configuration is separate from tool logic.

### 5.1 osquery fleet adapter

Existing [OsqueryMcpServer](https://github.com/kousen/OsqueryMcpServer) exposes local osquery operations. Its [implementation](https://github.com/kousen/OsqueryMcpServer/blob/main/src/main/java/com/kousenit/osquerymcpserver/OsqueryService.java) is a reference, not an already complete remote-fleet adapter.

The control-node adapter is a small Python service using an SSH library. It resolves a stable host ID from inventory, runs an allowlisted query through osqueryi, parses JSON, and tags every result with host identity and collection time. MCP does not run on every VM.

The adapter exposes named query IDs for installed packages, OS identity, processes, listening ports, and service-related evidence. SQL templates are maintained in the repository. Validated filter values feed fixed command templates; the tool contract excludes free-form remote shell commands and arbitrary model-supplied SQL.

An unavailable query, table, or permission appears as an explicit per-host error. Missing evidence is distinct from an empty successful result.

### 5.2 Execution facade

The Semaphore MCP backend sits behind a project-owned policy service. The agent cannot call its raw launch/admin tools directly. The facade owns plan validation, approval lookup, host locks, task correlation, and permitted execution scope.

| Project tool | Inputs | Result / rule |
| --- | --- | --- |
| list_hosts | Environment and optional group filters | Validated hosts, roles, identity, capability flags |
| query_hosts | Explicit host IDs, named query ID, validated filters | Timestamped evidence or per-host error |
| evaluate_updates | Evidence snapshot and advisory snapshot IDs | Version-matched findings and available candidates |
| create_plan | Findings, selected hosts, application profile | Validated immutable plan and hash |
| get_plan | Plan ID | Exact proposed operations and current approval state |
| execute_plan | Plan ID, approval reference, request ID | Existing/new run ID; no arbitrary extra variables |
| get_run | Run ID | Job state and structured host outcomes |
| get_run_output | Run ID, bounded cursor | Redacted output, task events, next cursor |
| pause_run | Run ID | New hosts/batches paused; in-flight package transactions preserved |
| reconcile_run | Run ID | Uncertain task/host state resolved without another launch |

These are planned project contracts. They are not claims about exact upstream MCP tool names. The backend's run_task, get_task, and get_task_raw_output are mapped inside the facade.

Approval is recorded through an authenticated operator action outside the model's tool set. The model cannot approve its own plan by sending approve=true, inventing an identity, or passing an approval token copied from unrelated output.

All tools validate schemas, sizes, ownership, and host scope. Results include a schema version, request/run ID, host ID when relevant, UTC timestamp, data, and a machine-readable error with retry guidance. Logs and package names are data, never instructions to execute.

## 6. Discovery and update classification

1. Discovery resolves the current inventory and records a snapshot.
2. The fleet adapter collects OS, release, architecture, and package name/version/source information.
3. Named queries collect process and listening-port evidence where permitted.
4. Analysis loads a timestamped Debian advisory snapshot.
5. Matching considers the release, source package, binary-to-source mapping, and Debian package versions.
6. Candidate evaluation checks the available fixed version and dependency changes for that release.
7. Each finding includes evidence, an advisory reference, exposure context, a candidate version, and a confidence/status classification.

The [deb_packages schema](https://github.com/osquery/osquery/blob/master/specs/linux/deb_packages.table) supplies installed package facts. Vulnerability metadata comes separately from the [Debian Security Tracker](https://security-tracker.debian.org/tracker/); the advisory-matching logic belongs to the project service.

Version matching follows Debian comparison rules, including epochs, revisions, and backports. Simple numeric or string comparison is insufficient. An open port or running process supplies exposure context; it does not establish exploitation.

Findings distinguish:

| Classification | Meaning |
| --- | --- |
| current | No applicable update found in the available evidence |
| patchable | Applicable finding with an available approved-source fixed version |
| update_available | Candidate update without a confirmed security finding |
| no_fixed_candidate | Finding exists; an installable fixed version was not resolved |
| unknown | Evidence, mapping, release support, or advisory freshness is insufficient |
| unsupported | Host/profile cannot be evaluated by the current adapters |

Unknown findings remain unresolved in the report. The plan retains advisory timestamps and candidate provenance so the operator can assess the available evidence.

Read-only discovery uses existing package metadata; refreshing APT metadata writes to the target and belongs to bootstrap or an approved execution stage. An authorized refresh before installation is followed by exact-version revalidation. A changed dependency closure or candidate invalidates the execution scope and leads to a new plan.

## 7. Plan, approval, and durable state

A plan is structured data validated independently of the model. Each plan contains:

- Plan ID, schema version, creation time, expiry, environment, and operator request.
- Explicit host IDs with identity and inventory/evidence snapshot references.
- Current and proposed versions, repositories/artifact references, and full dependency changes.
- Versioned application profile, task template, and Git commit for playbooks/configuration.
- Preflight requirements, affected services, health assertions, and rollout order.
- Backup/package-retention requirements and permitted recovery operations.
- Reboot/downtime requirements, risks, and unresolved evidence.
- Runtime/version/provider/model and a hash of the canonical execution fields.

The operator sees the host list, package/dependency changes, downtime, canary, recovery method, and uncertainties before approving.

Example plan fragment; placeholders are not executable values:

~~~json
{
  "schema_version": 1,
  "plan_id": "plan-demo-001",
  "environment": "lab",
  "operation": "targeted_package_update",
  "inventory_snapshot_id": "inventory-demo-001",
  "evidence_snapshot_id": "scan-demo-001",
  "advisory_snapshot_id": "advisories-demo-001",
  "hosts": ["vm-01", "vm-02"],
  "packages": [
    {
      "name": "idk-demo-service",
      "from_version": "1.0.0",
      "to_version": "1.1.0",
      "source": "signed-lab-repository"
    }
  ],
  "dependency_changes": [],
  "application_profile": "demo-http",
  "template_id": "<configured-template-id>",
  "playbook_commit": "<pinned-git-commit>",
  "rollout": {"canary": "vm-01", "batch_size": 1},
  "recovery": {"method": "cached_package_and_config_restore"},
  "plan_hash": "<computed-from-canonical-execution-fields>",
  "approval": null
}
~~~

Approval stores the trusted operator identity, plan hash, time, expiry, and scope. Validation occurs again inside execute_plan. Changes to hosts, versions, dependencies, playbook commit, profile, or recovery policy invalidate approval. Expired approval or material host-state drift blocks execution.

SQLite stores plans, approvals, runs, per-host states, and append-only application events in one local database. This fits the single-control-node lab and avoids a separate database server. Database transactions provide execution claims and per-host locks. The service owns the database file, outside the agent's editing access; approval and execution state come from persisted records.

A unique request ID deduplicates execute_plan. Persisted correlation data links the launch intent to the eventual Semaphore task. If a launch response is lost, reconciliation looks for the existing job using that data. Unconfirmed acceptance becomes execution_unknown and blocks another launch until reconciliation establishes the actual state.

## 8. Deployment and recovery

### 8.1 Application profiles

A profile defines managed packages, configuration files, services, dependency order, graceful-stop behavior, health checks, timeouts, and recovery capability.

The demo-http profile uses a small systemd HTTP service distributed as a lab .deb package. A later multi-service profile can define proxy -> application -> dependency shutdown order, with the reverse startup order. Dependency cycles fail profile validation.

Profiles identify exactly which resources the playbook owns. Suspension affects the defined services, and recovery restores their recorded prior state. Unrelated services remain outside the profile's operations; system libraries are handled as package dependencies.

### 8.2 Execution sequence

1. **Validation:** the gate checks approval, the immutable plan, supported hosts, the playbook commit, and the permitted template.
2. **Preflight:** host checks cover SSH identity, privileges, package locks, free space, baseline service health, candidates, and recovery prerequisites.
3. **Preparation:** verified prior packages and relevant dependency versions are retained in a protected recovery directory. Backups record configs, ownership, permissions, checksums, and service state.
4. **Revalidation:** package-transaction simulation is compared with the approved dependency closure. Unexpected removals or version changes block mutation.
5. **Canary:** the designated ready host is processed first. A failed canary halts later mutations.
6. **Suspension:** profile-managed workloads are drained or stopped in dependency order.
7. **Application:** Ansible installs the exact approved versions and configuration/artifacts within the reviewed scope.
8. **Resumption:** profile-managed services restart in startup order.
9. **Verification:** assertions check package versions, service state, expected ports, and an application health response within a timeout.
10. **Continuation and reporting:** later batches proceed after canary success. Each host's result is stored and included in a fleet summary.

Rollout settings define bounded batches and concurrency, using Ansible's [serial and execution strategies](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html).

Reviewed [APT module options](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/apt_module.html) support exact package versions and the project's controlled recovery path. The playbooks block unapproved removals and unauthenticated installs, retain recovery artifacts, and verify final state explicitly.

A planned preview can use Ansible check/diff mode on supported tasks. It is advisory: [check mode has simulation limits](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html) and does not prove a rollout will succeed. Preview validation excludes tasks that force real execution.

### 8.3 Failure rules

| Failure | Outcome |
| --- | --- |
| Rejected/expired/stale plan | Launch blocked with the exact reason |
| SSH/identity/preflight failure | Host mutation blocked; continuation follows canary/rollout policy |
| Missing recovery artifacts | Recovery-required deployment blocked before suspension |
| Download/signature failure | Backups preserved, stopped services restored, failed stage reported |
| Partial installation | Actual package state captured; recovery limited to the approved, tested procedure |
| Post-update health failure | Retained versions/configs restored; restarted services checked against prior health |
| Recovery failure | recovery_failed outcome; diagnostics preserved and affected batches halted |
| SSH lost during mutation | execution_unknown until host/job state is reconciled |
| Operator pause | New work paused; active APT transaction continues to a safe outcome |
| Model/provider unavailable | Agent reasoning paused; accepted work monitored deterministically |

Mutation handling uses Ansible block/rescue/always with a separate reachability and reconciliation path. Unreachable hosts do not trigger ordinary block rescue. A successful rescue can also change Ansible's failure accounting, so the controller uses explicit host outcomes to enforce the canary policy. See [Ansible blocks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html).

Recovery restores availability when possible; it does not mean the requested patch succeeded. A restored old version is rolled_back and may still require remediation.

Package downgrade is not a universal rollback mechanism. Each profile has its own recovery tests. Kernel changes, irreversible migrations, and unsupported dependency downgrades remain excluded until a tested snapshot/backup procedure is added.

## 9. Scheduling, reports, and observability

Reviewed playbooks run through [Semaphore task templates](https://docs.semaphoreui.com/user-guide/task-templates/), with execution output in the existing task views. Agent reasoning appears in the agent interface; Semaphore provides the execution and history interface.

The initial scheduling options are on-demand discovery and a configurable periodic read-only scan. The scheduler may produce findings and an unapproved plan, but cannot approve mutations. Conflicting scans and mutations are serialized per host.

Persisted host outcomes are unchanged, verified, skipped, preflight_failed, install_failed, rolled_back, recovery_failed, unreachable, execution_unknown, and unsupported.

Each run records:

- Plan/approval hash, operator identity, environment, and resolved targets.
- Model/runtime details, evidence/advisory versions, and playbook commit.
- Semaphore task ID, task transitions, timestamps, and durations.
- Package/configuration/service state before and after.
- Health assertions, failure stage, exit code, and redacted stdout/stderr.
- Recovery actions, final host state, and whether another plan is required.

Reports are available as machine-readable JSON and short Markdown summaries, linked to the corresponding Semaphore task. Separate counts distinguish patched, unchanged, failed, recovered, and unknown hosts.

Measurements cover scan duration, planning latency, deployment duration, recovery duration, task retries, changed-host count, and control-node/VM resource use. Reported values include host count, runtime/model, and test conditions. Model usage and cost appear only when the provider supplies reliable usage data.

Events are recorded locally with monotonically ordered IDs. They provide application history; the local store does not offer immutable or tamper-proof storage.

## 10. Operator workflows

| Request | Expected agent behavior |
| --- | --- |
| "Scan the lab and explain pending security updates." | Read-only inventory/advisory analysis with evidence and uncertainties |
| "Plan updates for the web group." | Current group membership resolved into proposed exact hosts/versions |
| "Deploy version 1.1.0 of the demo service to vm-01 and vm-02." | Profile/artifact validation followed by a plan approval request |
| "Reject this rollout." | Store rejection; no execution |
| "Run the approved plan." | Gate validation, canary, bounded rollout, verification, report |
| "Why did vm-02 fail?" | Explanation of the observed failure stage using task output and host evidence |
| "Pause the rollout." | New batches paused, active transactions preserved, pending hosts reported |
| "Add vm-04 and scan it." | Inventory/identity validation and fresh evidence; prior approval scope preserved |
| "Use another provider/runtime." | Configuration switch and capability check under the shared deployment policy |

## 11. Implementation structure

Planned repository layout; directories below are created during implementation, not by this document:

~~~text
plan.md
architecture-black.svg
architecture-white.svg
architecture-research.md
agent/
  instructions.md
  skills/
  adapters/pi/
  adapters/opencode/
services/
  api/
  osquery_mcp/
  execution_mcp/
  state/
schemas/
  inventory.schema.json
  plan.schema.json
  tool-result.schema.json
config/
  agent.example.yml
  policy.example.yml
inventory/
  lab.example.yml
profiles/
  demo-http.yml
  multi-service.yml
queries/
  installed_packages.sql
  processes.sql
  listening_ports.sql
ansible/
  playbooks/bootstrap.yml
  playbooks/discover.yml
  playbooks/deploy.yml
  playbooks/recover.yml
  roles/
lab/
  provisioning/
  demo-packages/
  reset/
tests/
  unit/
  contracts/
  integration/
  scenarios/
  model-evals/
  fixtures/
reports/examples/
docs/setup.md
docs/demo.md
~~~

The planned backend uses Python. [FastAPI](https://fastapi.tiangolo.com/) provides the control API, request validation, and generated API documentation. SQLite provides durable project state, with no PostgreSQL dependency or separate database server for the lab. TypeScript covers runtime adapters/extensions where needed, and Ansible YAML describes host operations. Dependency versions are pinned after the compatibility spike.

FastAPI handles the operator-facing HTTP endpoints; the [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk) provides MCP tool registration and transport. Both use the same policy and state services, so HTTP and MCP requests are evaluated against the same plan and execution rules.

The proposed API is small:

| Endpoint | Purpose | Access |
| --- | --- | --- |
| GET /plans/{plan_id} | Exact plan, evidence references, and approval state | Authenticated read access within the operator's environment |
| POST /plans/{plan_id}/approval | Approval or rejection bound to the displayed plan hash | Authenticated operator action; unavailable to the model's tools |
| GET /runs/{run_id} | Task correlation, progress, and per-host outcomes | Authenticated read access within the operator's environment |
| GET /runs/{run_id}/report | Structured JSON or Markdown report | Authenticated read access within the operator's environment |

The runtime's approval interface calls the control API through an operator-authenticated path. The model's execution tools cannot submit approvals or access the operator credential. Read endpoints enforce environment access, and approval submissions reject stale hashes, expired plans, and unauthorized identities.

Long-running deployments remain Semaphore jobs. API and MCP responses return durable run IDs, and later status requests read the correlated job state. SQLite transactions cover short state updates and execution claims; SSH calls and Ansible runs occur outside those transactions. Database and recovery-artifact backups are part of the control-node setup and restart tests.

Lockfiles and recorded tool/runtime versions make the setup reproducible. Generated reports, mutable state, caches, credentials, and VM images remain outside version control. Repository examples contain sanitized data.

## 12. Test strategy

### 12.1 Test layers

| Layer | What it proves | Environment |
| --- | --- | --- |
| Unit | Schemas, Debian version matching, inventory expansion, policy, plan hashing, locks, status reduction | Synthetic fixtures; no LLM or VM |
| Control API/state | Authenticated approval, environment access, stale-hash rejection, SQLite persistence and transaction conflicts | FastAPI test client and temporary SQLite databases |
| MCP contracts | Tool discovery, valid/invalid arguments, result schemas, transport errors, timeout behavior | Local services and backend stubs |
| Ansible validation | Syntax, role validation, profile references, lint, bounded preview behavior | CI/control node |
| VM integration | Package transitions, systemd health, SSH failures, lock handling, backups, recovery | Disposable Debian VMs |
| Agent evaluation | Correct tool choices, evidence use, approval requests, honest summaries | Recorded tool responses; selected live models |
| Provider/runtime compatibility | Catalog inheritance, authentication, tool calls, same plan/gate behavior | Both runtimes; configured providers |
| End-to-end | Operator-to-agent-to-MCP-to-Ansible workflow and durable reports | Three-VM lab |

Mocks cover network/model error cases; VMs cover package and systemd behavior. A container-only test does not establish SSH, boot, or VM snapshot behavior. Assertions focus on outcomes and invariants, allowing the model's phrasing to vary.

A reset procedure restores a known package/configuration/service baseline and clears scenario artifacts without deleting shared credentials or approved setup data. Scenario tests declare their setup, injected condition, expected states, evidence, and cleanup.

### 12.2 Scenario matrix

| ID | Scenario | Expected result |
| --- | --- | --- |
| T01 | Healthy fleet with no applicable updates | unchanged hosts; no mutation |
| T02 | Applicable fixed version on one host | Evidence-backed plan names only that host/version |
| T03 | Advisory exists without available fixed candidate | no_fixed_candidate; no invented install |
| T04 | Stale advisory or evidence snapshot | unknown/block planning until refreshed |
| T05 | Debian epoch, backport, revision, and source mapping | Correct matches; no naive version comparison |
| T06 | Debian 12 and 13 in the same inventory | Release-specific candidates and profiles |
| T07 | Missing osquery table or insufficient read permission | Explicit partial evidence; no false clean report |
| T08 | Operator rejects a plan | Rejection stored; no backend launch |
| T09 | Approval expires before execution | Gate rejects launch |
| T10 | Host list/version/profile/commit changed after approval | Plan hash mismatch; approval invalidated |
| T11 | Model submits forged approval or another plan's reference | Rejected independently of runtime prompts |
| T12 | Raw Semaphore launch/admin tool requested | Tool unavailable; backend bypass denied |
| T13 | Two execution requests use the same request ID | One run/task, same returned run ID |
| T14 | Two plans try to mutate the same host concurrently | Exclusive host claim; conflicting plan waits/fails |
| T15 | Host version changes between scan and execution | Drift detected before mutation |
| T16 | Low disk space | preflight_failed; services/configs unchanged |
| T17 | APT lock held by another process | Bounded wait followed by abort; lock and owning process preserved |
| T18 | SSH host key differs from trusted inventory | Identity failure; no commands executed |
| T19 | Recovery package/config backup missing | Deployment blocked before suspension |
| T20 | Unexpected dependency install/removal after metadata refresh | Execution blocked; revised plan needed |
| T21 | Valid single-host update | Exact version installed; all health assertions pass |
| T22 | Valid canary followed by later batches | Defined order/concurrency; verified host results |
| T23 | Canary health fails and recovery succeeds | rolled_back; later hosts receive no mutation |
| T24 | Noncanary vm-03 offline while policy permits continuation | unreachable host; eligible hosts complete; partial report |
| T25 | Package download interrupted or repository unavailable | Failure stage captured; stopped services restored |
| T26 | Invalid signature or altered package artifact | Installation blocked; no unauthenticated bypass |
| T27 | Partial package installation | Approved recovery only; actual dpkg state reported |
| T28 | Service fails after a successful package install | Retained version/config restored and health rechecked |
| T29 | Recovery artifacts lost after preparation or downgrade fails | recovery_failed; honest report; affected rollout halted |
| T30 | SSH disconnect during installation | execution_unknown; reconciliation before any retry |
| T31 | Launch accepted but API response lost | Existing task reconciled; no duplicate deployment |
| T32 | Operator pauses a running rollout | No new hosts; active transaction allowed to reach a safe outcome |
| T33 | Reapply the same verified desired version | No package change or unnecessary service interruption |
| T34 | Add vm-04 after a plan was approved | Fresh discovery/new plan; old target set unchanged |
| T35 | Remove/disable a host or change its address | Inventory validation/revocation rules enforced |
| T36 | Unsupported OS or invalid/cyclic application profile | Unsupported/validation error before execution |
| T37 | MCP server missing, malformed JSON, timeout, or disconnect | Typed failure; no fabricated tool success |
| T38 | Provider authentication failure, rate limit, or outage | Bounded retry/pause; no duplicate backend run |
| T39 | Model cannot produce supported tool calls | Execution disabled with capability explanation |
| T40 | Logs/package metadata contain instructions to bypass approval | Treated as evidence; gate continues to deny mutation |
| T41 | Large tool output or credentials in task output | Bounded/redacted results; full authorized diagnostics retained |
| T42 | Switch runtime/provider and repeat the same workflow | Shared tool/policy behavior; new plan review where required |
| T43 | Controller restarts during an active job | SQLite plan/task mapping restored; actual job state reconciled |
| T44 | Dependency stop/start order or baseline health is wrong | Validation/preflight failure; no uncontrolled restart |
| T45 | Ten-host synthetic inventory with configured concurrency | Bounded scheduling; stable IDs; complete result accounting |
| T46 | Offline prepared lab with cached data/artifacts | Repeatable labeled demo; missing cache blocks relevant work |
| T47 | Preview task tries to force real execution | Validation fails; read-only preview invariant preserved |
| T48 | A recovered Ansible task appears successful in its recap | Explicit host outcome still halts a failed-canary rollout |

T01-T20 and T33-T48 combine deterministic unit/contract tests with integration cases where required. T21-T32 require real VM execution or an explicitly labeled fault-injection integration harness.

Each case records expected and actual status, plan/run/task IDs, relevant before/after evidence, and cleanup outcome. A case is pass, fail, or skipped with reason; no blank/unrun case is counted as passing.

### 12.3 Model and provider evaluation

Pi and OpenCode share a small evaluation set: observe-only request, valid plan, rejection, missing fix, offline host, failed deployment, recovery, and injected instructions in logs.

Evaluation checks the expected tool sequence, valid arguments, approval boundaries, and agreement between the summary and recorded outcomes. Identical wording is unnecessary.

Deterministic evaluations run in CI with recorded provider/tool responses. Presentation preparation includes live evaluations on at least two configured provider/model choices when available. An offline replay option is clearly marked as replay.

Every catalog entry gets a configuration/catalog compatibility check. Each provider with available credentials gets a live authentication/tool-call smoke test. The compatibility record includes runtime, version, endpoint, model, test date, and tested/inherited-only/unavailable status. Providers without credentials remain explicitly untested live.

## 13. Demonstration and reproducibility

### 13.1 Controlled fixtures

The demonstration uses a signed lab APT repository containing these idk-demo-service versions:

- 1.0.0: baseline application with a working health response.
- 1.1.0: successful update; exposes the expected new version.
- 1.2.0-broken: controlled failed-health fixture for recovery testing.

A labeled synthetic advisory fixture links the demo package to its expected fixed version. It demonstrates correlation logic using synthetic vulnerability data. A separate live Debian advisory scan is included when network and data availability permit.

Stored test artifacts and reset scripts make the presentation reproducible, independently of whether older vulnerable packages remain available in public repositories.

### 13.2 Showcase sequence

| Step | Demonstration | Evidence to show |
| --- | --- | --- |
| 1 | Named agent startup with runtime, provider, model, and environment displayed | Session identity and resolved configuration |
| 2 | Three-VM discovery and explanation of package/process/port evidence | Timestamped JSON and readable host summary |
| 3 | Deployment-plan generation followed by operator rejection | Exact scope; zero launched mutation jobs |
| 4 | New exact-version plan and operator approval | Approval bound to plan hash/targets |
| 5 | Canary update followed by later batches | Semaphore task, before/after version, health response |
| 6 | Repeated request for the same desired version | Unchanged packages; no unnecessary interruption |
| 7 | Separate approved rollout with vm-03 deliberately unreachable | Partial outcome with correct continuation policy |
| 8 | Broken-fixture deployment to the canary | Failed health, recovery evidence, later hosts untouched |
| 9 | Preflight-problem and stale-approval scenarios | Both blocked before target mutation |
| 10 | vm-04 added and selected through configuration | Updated inventory, fresh plan, verified host identity |
| 11 | Workflow repeated on the other runtime or a second configured provider | Same MCP contract and approval behavior |
| 12 | Final-report export and lab reset | JSON/Markdown evidence and reproducible baseline |

Incompatible scenarios have separate approved plans and reset points. A recorded full run provides a presentation fallback, clearly labeled as a recording or replay.

### 13.3 Measurements

Performance evaluation compares read-only scan duration for one and three real hosts, followed by a larger synthetic inventory scheduling test. Repeated runs provide median and slowest observed values, accompanied by the test count.

Measurements cover control-node idle/peak RAM, target overhead, provider planning time, deployment time, and recovery time. Configuration limits and reported performance are based on those observations.

## 14. Agile delivery, phases, and completion criteria

### 14.1 Working method

The project follows an Agile approach with a prioritized backlog and short iterations. A one-week sprint is the starting cadence, adjusted around team availability and the school timetable. Each sprint has one observable goal, a small set of selected stories, and a demonstration of the working result.

Sprint planning considers priority, dependencies, available time, and feedback from the previous review. Short team check-ins cover progress and blockers. The sprint ends with a review of the increment and a brief retrospective; feedback changes the next sprint's scope. Unfinished work returns to the backlog with its remaining effort and blockers recorded.

The phases below are backlog epics rather than fixed calendar stages. Discovery, API work, runtime integration, and tests can progress together. Early execution work starts with one controlled host and expands after its approval and verification path works. Phase order expresses dependencies; it does not postpone testing or integration until the end.

Stories describe a user outcome, the affected environment, acceptance criteria, dependencies, and relevant test scenarios. A story is ready for a sprint when its scope and expected result are clear enough to implement and review. Large stories are split into demonstrable increments. The board tracks To do, In progress, In review, and Done, with blockers recorded on the affected item.

Example backlog stories:

| Story | User outcome | Acceptance evidence |
| --- | --- | --- |
| AG01: Fleet visibility | As an operator, I can see which hosts have an applicable update and why | Host-tagged inventory, advisory references, explicit unknown results; T01-T07 |
| AG02: Reviewed deployment | As an operator, I can approve an exact host/version change before it runs | Authenticated approval, matching plan hash, one correlated task; T08-T15 and T21 |
| AG03: Failed-update recovery | As an operator, I can see whether a failed update restored the previous healthy state | Before/after health evidence, rolled_back or recovery_failed outcome, halted failed-canary rollout; T23 and T28-T30 |
| AG04: Flexible environment | As an operator, I can add a host or change runtime/provider through configuration | Fresh discovery, unchanged prior approval scope, shared execution policy; T34-T36 and T42 |

The initial priorities are fleet evidence, trusted approval, a working single-host update, and recovery. Runtime parity, wider scenario coverage, scheduling, and presentation follow as these workflows become stable. UI branding remains an optional follow-up. Estimates are reviewed after the first compatibility and lab increments; the phase list is not a promised delivery schedule.

### 14.2 Phase backlog

All checkboxes start unchecked. A checked item represents reviewed work with its acceptance evidence, rather than a feature merely described in this plan.

#### Phase 1 - Compatibility and first connected workflow

The first increment establishes that the selected runtime can call a real project tool and that the control node can reach the execution backend.

- [ ] Recorded compatible versions for Python, FastAPI, the MCP SDK, one runtime/model, Ansible, Semaphore, and osquery.
- [ ] Named agent profile with inherited provider authentication and a model tool-call readiness check.
- [ ] Minimal Python MCP read tool, FastAPI endpoint, and temporary SQLite state working on the control node.
- [ ] Semaphore task launch/status mapping demonstrated with a harmless lab task outside the model's unrestricted access.
- [ ] Dependency locks, startup configuration, and a repeatable compatibility smoke test.

Acceptance evidence is a recorded tool call, API response, persisted state record, and correlated backend task. Contract and capability checks cover T37-T39. Results determine the dependency versions and the first runtime used in later increments.

#### Phase 2 - Reproducible lab and fixtures

This increment provides the real environment needed for deployment and recovery testing.

- [ ] One control node and three Debian VMs, with Debian 13 as the baseline and a Debian 12 compatibility profile.
- [ ] Stable host IDs, distinct machine identities, trusted host keys, automation permissions, and private-network configuration.
- [ ] Bootstrap playbook for osquery, Python, APT dependencies, and the demo application's prerequisites.
- [ ] Signed demo repository, baseline and healthy-update packages, broken-health fixture, and labeled synthetic advisory data.
- [ ] Documented rebuild/reset workflow and prepared offline artifacts where applicable.

Acceptance evidence is a rebuilt three-VM lab with healthy baseline responses and a successful reset after a fixture run. Identity and offline checks cover T18 and T46. Test artifacts remain separate from real Debian vulnerability claims.

#### Phase 3 - Discovery and update analysis

The operator can inspect a fleet without changing target package state.

- [ ] File-based inventory behind a replaceable source interface, with host/group resolution and configuration validation.
- [ ] Allowlisted osquery queries over SSH with per-host identity, timestamps, timeouts, and normalized errors.
- [ ] Advisory cache with release/source-package mapping and Debian-aware version comparison.
- [ ] Findings for current, patchable, update_available, no_fixed_candidate, unknown, and unsupported states.
- [ ] Read-only fleet summary and tests for added/removed hosts, unavailable evidence, and larger synthetic inventories.

Acceptance evidence is an evidence-backed fleet summary and passing T01-T07, T34-T36, and T45 cases at their appropriate test layers. Missing data stays visible, and discovery leaves target package metadata unchanged.

#### Phase 4 - Plans, approval, and durable execution state

The next increment turns findings into a reviewable change and establishes the execution boundary before package mutation is enabled.

- [ ] Validated plan schema with exact hosts, versions, dependency closure, profile, template, playbook commit, and recovery scope.
- [ ] SQLite plan/approval/run/event records with transaction-backed execution claims, per-host locks, and request deduplication.
- [ ] FastAPI plan/run reads and authenticated approval/rejection, including environment access and stale-hash validation.
- [ ] Execution MCP facade connected to a private Semaphore backend, with approval checked independently of model instructions.
- [ ] Tests for rejection, expiry, forged approval, scope changes, conflicting plans, and duplicate launch requests.

Acceptance evidence is a displayed exact plan, an operator approval record, and a gate that rejects unauthorized or stale requests. T08-T15 and control API/state tests pass before an approved package-changing workflow is exposed.

#### Phase 5 - Deployment, verification, and recovery

Delivery begins with one healthy host, then adds canary batches and controlled failures within the same reviewed workflow.

- [ ] Versioned demo-http profile and Ansible preflight, package/config retention, and exact-version deployment roles.
- [ ] Verified single-host update, including package version, service state, expected port, and health response.
- [ ] Canary-first rollout with configured batch limits, explicit host outcomes, and halt behavior after canary failure.
- [ ] Tested retained-package/config recovery, prior-service-state restoration, and honest recovery_failed reporting.
- [ ] VM scenarios for locks, low disk space, dependency drift, signatures, partial installation, SSH loss, pause, and idempotence.

Acceptance evidence covers T16-T33, T44, T47, and T48 with before/after state and backend task IDs. A recovered failed canary still halts later mutations, and uncertain execution enters reconciliation before another launch.

#### Phase 6 - Runtime parity and provider compatibility

The second runtime uses the existing deployment services, while provider support remains inherited from each upstream runtime.

- [ ] Second runtime adapter using the same instructions, MCP contracts, plan schema, policy, and reporting format.
- [ ] Provider catalogs and custom-endpoint configuration available through the supporting runtime, without a separate provider SDK.
- [ ] Recorded compatibility results for configured provider/model choices and clear inherited-only status for untested entries.
- [ ] Shared evaluation fixtures for evidence use, rejection, missing fixes, failure summaries, and injected log instructions.
- [ ] Repeated workflow on Pi and OpenCode, including capability failure and model/provider-switch review rules.

Acceptance evidence is the same approved workflow on both runtimes and a dated compatibility matrix. T37-T42 pass at the relevant layers. Live provider results are limited to available credentials; offline replays are labeled.

#### Phase 7 - Reports, scheduling, and restart handling

This increment makes the results usable beyond a single uninterrupted agent session.

- [ ] Correlated plan/run/task events and JSON/Markdown reports with distinct success, failure, recovery, and unknown outcomes.
- [ ] Bounded, redacted task-output access and report links to Semaphore history.
- [ ] Configurable periodic read-only discovery with host-conflict handling and no automatic mutation approval.
- [ ] Controller restart and ambiguous-launch reconciliation using persisted SQLite state and backend task evidence.
- [ ] Database/artifact backup procedure, pause/resume accounting, and initial timing/resource measurements.

Acceptance evidence includes accurate partial-fleet reports, a recovered controller session, and T24, T30-T32, T41, and T43 results. Scheduled scans can produce findings and unapproved plans without triggering deployment.

#### Phase 8 - Full demonstration and project handover

The final increment packages the tested workflows into a presentation another team member can reproduce.

- [ ] Scenario runner and recorded pass/fail/skipped results for T01-T48, including reasons for unavailable cases.
- [ ] Completed 12-step showcase from section 13, with separate plans and reset points for incompatible scenarios.
- [ ] Observed timing/resource measurements with host count, model/runtime, test conditions, and replay labels.
- [ ] Setup/reset documentation, sanitized configuration, report examples, dependency locks, minimal README, and matching diagrams.
- [ ] Full recorded fallback demonstration and a final review of remaining limitations and backlog items.

Acceptance evidence is a clean lab reset followed by a repeatable demonstration. Presentation materials distinguish implemented, tested, unavailable, and future work.

### 14.3 Definition of done and release checklist

A story is done when its acceptance criteria are demonstrated, the relevant tests pass, another team member has reviewed the change, and affected documentation/configuration agrees with the implementation. Test evidence includes the environment and any limitations. Unrun or skipped scenarios remain visible and are not counted as passing.

The project release is ready when the following outcomes are reviewed:

- [ ] Both runtime adapters can run the observe -> plan -> approve -> execute -> verify -> report workflow.
- [ ] Provider catalogs remain inherited, with documented capability results for configured providers.
- [ ] Mutation is blocked without a valid matching approval through the execution facade and authenticated operator path.
- [ ] Exact hosts, versions, dependencies, template, and playbook commit remain within reviewed scope.
- [ ] Dynamic inventory works without source edits and cannot expand an old approval.
- [ ] Success, idempotence, rejection, stale approval, offline host, preflight failure, health failure, recovery, and uncertain execution are demonstrated.
- [ ] Core deterministic/API tests and three-VM integration tests pass; optional/unavailable cases are explicitly recorded.
- [ ] Setup/reset instructions, sample configuration, report examples, version locks, README, and diagrams agree.
- [ ] Reports contain evidence and distinguish actual patch success from restored availability.

UI branding refinements remain a separate backlog item and do not redefine completion of the deployment engine.

## 15. Decisions retained for implementation

The architecture uses one control node, Debian targets, SSH transport, a Python/FastAPI backend, SQLite, and the existing Semaphore interface. Custom code covers the fleet adapter, execution policy facade, small control API, runtime adapters, and project-specific profiles/tests.

Schemas and adapters allow integrations to be replaced without changing the deployment workflow. Future OS families, dynamic hypervisor discovery, snapshot recovery, richer UI branding, and additional deployment types would retain the same plan/approval/reporting contracts.

