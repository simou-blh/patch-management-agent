# Open questions: proposed answers

Status: PROPOSALS from the documentation owner. Nothing here is decided. Each
item needs a yes/no or a correction from the named owner. Numbering follows
[assessment-workflow.md](assessment-workflow.md) section 5 (items 1-4 are on
`main`; 5-8 are added by PR #21).

## Q1. Who fills `verification` and `recovery`? (Wassim)

Proposal: the plan generator copies them from the configured policies
(`policies/services.json`, S2.3) and the operator-configured recovery scope.
The assessment never provides them, and the model cannot edit them.

## Q2. Targets: an assessment only lists hosts that have results (Wassim, Baha)

Proposal: the generator sets `targets` to the evidence targets, not to the
hosts found in the assessment. A host with no result is an error, not a
silent omission, because plan targets must equal evidence targets.

## Q3. Nothing to patch: `packages` needs at least one item (Wassim, Baha)

Proposal: no schema change. When every package is fixed or has no known
advisory, the generator returns "nothing to patch" and does not submit a plan.
Defer items still produce a valid plan.

## Q4. Nothing links a plan to an assessment (Wassim)

Proposal: add an optional `assessment_sha256` field to `plan.schema.json`
(the schema rejects extra fields, so this is a schema change owned by Wassim).
`submit_plan` stores it, and `python -m patch_agent.operator show` displays it,
so the reviewer sees which assessment produced the plan.

## Q5. Candidate source is `null` in evidence (Abderaouf, Baha)

Proposal: the producer fills the candidate source from the APT metadata it
already reads (it is an observation, not a guess). Until it does, a package
whose candidate source is `null` must `defer`. The assessor never infers a
source version, because the evidence contract forbids guessing.

## Q6. `release`: evidence has no release field (Baha, Abderaouf)

Proposal: add the host release (for example the Debian codename) to evidence
as a producer-observed per-host field. The assessor refuses to match when a
host release differs from the advisory cache `release`. Until then the operator
is responsible, and the workflow page says so.

## Q7. `canary` is a free string (Wassim)

Proposal: `submit_plan` rejects a plan unless `canary` is in `targets` and
equals the operator-configured canary (`vm-01` in `lab/hosts.json`).

## Q8. Which MCP server exposes assessment? (Baha, Wassim)

Proposal: a read-only assessment tool on the Fleet MCP, and the generated plan
is still submitted through `submit_plan` on the Plan and approval MCP. This
keeps the two-server trust boundary and the approval flow unchanged. No
mutation tool is exposed.

## Q9. Priority from urgency (Baha)

The contract leaves this to Sprint 2. Proposal: Debian `high`, `medium` and
`low` map to the same plan priority; any other or missing urgency maps to
`medium`; `critical` is never produced automatically and is set by the
operator at review.