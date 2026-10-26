# AI Patch Agent — MVP

## Objective -

Build an AI-assisted patch-management agent that inventories a small Debian fleet, identifies security updates, proposes a prioritized patch plan, requests human approval, and deploys approved changes with canary verification and recovery.

## Architecture baseline

This MVP follows the attached architecture: **Pi or OpenCode, MCP tools, osquery, Semaphore, Ansible, and Debian VMs**.

The earlier Python/LangGraph workflow and Ubuntu/OSV stack are superseded for this scope.

## Target environment

- One Linux control node.
- Three Debian VMs running the same supported release:
  - `vm-01`: canary.
  - `vm-02` and `vm-03`: fleet.
- SSH access, Python, APT, and osquery installed on each target.
- VM snapshots taken before deployment demonstrations.

## Technology stack

| Component | MVP choice |
|---|---|
| Agent runtime | Choose one: Pi or OpenCode |
| Model | One provider supported by the chosen runtime |
| Tool interface | MCP |
| Inventory and verification | osquery through a project fleet adapter |
| Vulnerability information | Debian security advisories and fixed-version data |
| Execution | Approval facade wrapping `semaphore-mcp` |
| Job orchestration | Semaphore API |
| Remote changes | Fixed Ansible playbooks over SSH |
| Reports | Timestamped JSON reports and Semaphore job logs |

## Core principle

**The LLM proposes changes; validated tools execute them.**

The model may interpret evidence, prioritize updates, and explain a plan. It cannot execute arbitrary commands, generate executable playbooks, or bypass approval.

## Required capabilities

### 1. Collect fleet evidence

The osquery MCP adapter must:

- Route queries over SSH to explicitly selected inventory hosts.
- Allow only validated, read-only queries against approved tables.
- Collect OS release, installed packages, and installed versions.
- Collect configured service evidence, such as processes and listening ports.
- Return structured JSON with per-host results and errors.

APT candidate versions and repository availability must be collected through a fixed Ansible inspection playbook.

### 2. Identify security updates

- Match installed packages against Debian security information.
- Resolve binary packages to source packages where required.
- Compare versions using Debian package-version semantics.
- Record advisory identifiers, CVEs, affected versions, and fixed versions when available.
- Confirm that the proposed package version is available from configured repositories.
- Mark missing or uncertain advisory matches explicitly.

### 3. Generate a patch plan

The agent produces a structured plan containing:

- Run identifier.
- Selected targets and canary.
- Packages and current versions per host.
- Exact proposed package versions.
- Supporting advisory or CVE references.
- Priority: `critical`, `high`, `medium`, or `low`.
- Action: `patch` or `defer`.
- Reason for each action.
- Verification checks.
- Recovery prerequisites.

Deterministic validation must reject unknown hosts, unknown packages, unavailable versions, and unsupported actions.

Kernel updates, major upgrades, and automatic reboots are deferred in the MVP.

### 4. Require human approval

Before deployment, the operator must see and approve the exact plan.

The approval gate must:

- Bind approval to the plan identifier or hash.
- Enforce the approved hosts, packages, versions, and execution templates.
- Reject mutation requests without valid approval.
- Require renewed approval if the plan changes.
- Record the decision and timestamp.

Approval includes the defined recovery actions for the approved deployment.

### 5. Run preflight checks

Before modifying each host:

- Confirm SSH connectivity and required privileges.
- Check available disk space.
- Check package-manager locks and package-manager health.
- Confirm approved package versions remain available.
- Capture installed versions and relevant configuration backups.
- Confirm recovery artifacts are available for the demonstration.

Abort an unready target and record the reason. A failed canary preflight blocks fleet deployment.

### 6. Deploy to the canary

- Execute an allowlisted Semaphore template.
- Apply only approved packages at approved versions.
- Restart only configured services required by the update.
- Capture the Semaphore task identifier, output, and final status.
- Stop on installation failure.

### 7. Verify and deploy to the fleet

After canary deployment:

- Re-query installed package versions through osquery.
- Confirm they match the approved versions.
- Run configured service and health checks.

Proceed only when all canary checks pass.

Deploy to the remaining hosts sequentially, verifying each host before continuing. Stop the rollout on the first failure.

### 8. Recover failed deployments

For a failed target:

- Capture diagnostics.
- Attempt predefined APT recovery when applicable.
- Restore cached previous package versions and backed-up configuration when available.
- Re-run verification and health checks.
- Report whether recovery succeeded.

Package downgrade is best effort. If automated recovery fails, stop and report that manual intervention is required. VM snapshots provide the lab recovery fallback.

### 9. Produce a report

Every run must generate a timestamped JSON report, including runs that are rejected, aborted, or failed.

The report must contain:

- Run identifier and timestamps.
- Inventory and advisory lookup results.
- Validated plan and approval decision.
- Preflight results.
- Canary and fleet results.
- Expected and observed package versions.
- Health-check results.
- Semaphore task identifiers.
- Recovery attempts and outcomes.
- Final status and unresolved issues.

## End-to-end workflow

1. Operator selects targets and requests an assessment.
2. Agent collects inventory and available package versions.
3. Agent correlates packages with Debian security information.
4. Agent proposes a validated patch plan.
5. Operator approves or rejects the plan.
6. Approved deployment runs canary preflight checks.
7. Canary is patched and verified.
8. Fleet hosts are patched and verified one at a time.
9. Any failure stops the rollout and triggers the defined recovery path.
10. Agent writes the final report.

## Safety requirements

| Requirement | Enforcement |
|---|---|
| No arbitrary execution | Fixed Ansible playbooks and allowlisted Semaphore templates |
| Mandatory approval | Execution facade validates approval before mutation calls |
| Restricted targeting | Hosts must belong to the configured inventory and approved scope |
| Restricted packages | Package names and versions must match collected candidates |
| Read-only inventory | Validated osquery queries against approved tables |
| Limited rollout | Canary first, then one host at a time |
| Verified success | Package-version checks and configured health checks |
| Protected credentials | Secrets stored outside source control and model context |
| Traceability | Run identifiers, approval records, job logs, and JSON reports |

## Deliverables

- Agent configuration, prompts, and tool policy for one selected runtime.
- osquery MCP fleet adapter.
- Approval facade for Semaphore MCP execution.
- Ansible playbooks and Semaphore templates for inspection, preflight, patching, verification, and recovery.
- Three-VM Debian lab configuration.
- JSON plan and report schemas.
- Setup and demonstration documentation.
- Tests covering validation, approval enforcement, rollout failures, and recovery.

## Acceptance criteria

| Scenario | Expected result |
|---|---|
| Inventory three VMs | Structured package and OS evidence is returned for each reachable host |
| Known vulnerable reference package | Relevant advisory and an available fixed version are identified |
| Invalid model plan | Validation blocks execution |
| Missing or rejected approval | No deployment job starts |
| Changed approved plan | Execution is blocked until renewed approval |
| Failed preflight | Target remains unmodified and the reason is reported |
| Successful canary | Fleet deployment becomes eligible |
| Canary installation or health failure | Fleet remains untouched; recovery is attempted |
| Fleet host failure | No subsequent host is patched |
| Successful deployment | Installed versions and health checks match the approved plan |
| Recovery failure | Run stops with diagnostics and an explicit unresolved status |
| Any terminal outcome | A JSON report is generated |

## Out of scope

- Supporting both Pi and OpenCode.
- Multiple model providers and automatic fallback.
- Windows, Ubuntu, RHEL, or mixed-distribution fleets.
- Kernel upgrades, major upgrades, and automatic reboots.
- Arbitrary natural-language SQL.
- Scheduling and maintenance windows.
- Notifications and a custom dashboard.
- Multi-user RBAC.
- FleetDM, AWX, and large-fleet optimization.
- Platform-specific API integration until the integration contract is available.

## Demonstration

1. Show three Debian VMs with controlled pending security updates.
2. Collect inventory and advisory evidence.
3. Display the prioritized plan.
4. Reject a plan and demonstrate that no deployment occurs.
5. Approve a plan.
6. Patch and verify the canary.
7. Patch and verify the two fleet hosts sequentially.
8. Run a separate controlled failure scenario.
9. Demonstrate rollout stopping and recovery.
10. Inspect the JSON report and Semaphore logs.
