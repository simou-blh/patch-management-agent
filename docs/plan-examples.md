# Plan examples (synthetic)

All examples are synthetic: no real host data and no real advisories. The shape comes from
`schemas/plan.schema.json`, and the patch plan is the one `scripts/demo.py` submits.
Deployment stays blocked for every plan, including approved ones. Field definitions are in
[assessment-workflow.md](assessment-workflow.md) section 3.

Write each `reason` as one factual sentence saying why the package is patched or deferred.
Never put credentials, key paths or raw logs in it.

## 1. Patch plan

The plan used by the demo: three hosts, canary `vm-01`, one package patched on each host.

    {
      "run_id": "synthetic-demo",
      "targets": [
        "vm-01",
        "vm-02",
        "vm-03"
      ],
      "canary": "vm-01",
      "packages": [
        {
          "host": "vm-01",
          "name": "demo-package:amd64",
          "current_version": "1.0-1",
          "proposed_version": "1.0-2",
          "action": "patch",
          "priority": "high",
          "advisories": [
            "SYNTHETIC-DEMO-NOT-A-REAL-ADVISORY"
          ],
          "reason": "Synthetic evidence for testing the approval boundary only."
        },
        {
          "host": "vm-02",
          "name": "demo-package:amd64",
          "current_version": "1.0-1",
          "proposed_version": "1.0-2",
          "action": "patch",
          "priority": "high",
          "advisories": [
            "SYNTHETIC-DEMO-NOT-A-REAL-ADVISORY"
          ],
          "reason": "Synthetic evidence for testing the approval boundary only."
        },
        {
          "host": "vm-03",
          "name": "demo-package:amd64",
          "current_version": "1.0-1",
          "proposed_version": "1.0-2",
          "action": "patch",
          "priority": "high",
          "advisories": [
            "SYNTHETIC-DEMO-NOT-A-REAL-ADVISORY"
          ],
          "reason": "Synthetic evidence for testing the approval boundary only."
        }
      ],
      "verification": [
        "Check observed package versions; not executed in this demo"
      ],
      "recovery": {
        "snapshot": "synthetic-not-created",
        "previous_packages": false,
        "config_backup": false
      }
    }

How it was checked: the demo submits this plan against synthetic contract-v1 evidence where
each host has `demo-package:amd64` installed at `1.0-1` with candidate `1.0-2` (step
`Plan submitted`, decision pending). The plan schema check was run when this page was
generated. Nothing is executed: `request_deployment` still returns a blocked report.

## 2. Defer items

Package items only; the other plan fields are as in section 1.

    [
      {
        "host": "vm-01",
        "name": "demo-open:amd64",
        "current_version": "2.0-1",
        "proposed_version": null,
        "action": "defer",
        "priority": "low",
        "advisories": [
          "SYNTHETIC-DEMO-OPEN-ADVISORY"
        ],
        "reason": "Synthetic example: no fixed version is published yet, so the package is deferred."
      },
      {
        "host": "vm-01",
        "name": "mystery:amd64",
        "current_version": "3.1-1",
        "proposed_version": null,
        "action": "defer",
        "priority": "medium",
        "advisories": [],
        "reason": "Synthetic example: the source package is unknown, so advisories cannot be matched."
      }
    ]

These items were checked against the plan schema when this page was generated, wrapped
in a full plan.

`submit_plan` adds two rules that the schema does not express (read from
`patch_agent/approval.py`): a `defer` item must have a null `proposed_version`, and the
hosts that have package decisions must be exactly the plan's `targets`. In a plan that
targets vm-01, vm-02 and vm-03, the two items above would be refused unless vm-02 and
vm-03 also had package decisions. This page does not run `submit_plan` on them.

## 3. What gets rejected or blocked

| Case | What happens | Demo step |
|---|---|---|
| Proposed version is not among the trusted candidates (`99.0-unavailable`) | `submit_plan` is refused: "proposed version is unavailable in collected candidates" | Invalid version rejected |
| A `defer` item with a non-null `proposed_version` | `submit_plan` is refused: "deferred packages must have a null proposed version" | Not in the demo (from `approval.py`) |
| A `patch` item for a kernel package (name starting with `linux-` or `kernel`) | `submit_plan` is refused: "kernel changes are deferred in the MVP" | Not in the demo (from `approval.py`) |
| A target host with no package decision | `submit_plan` is refused: "each selected host must have package decisions" | Not in the demo (from `approval.py`) |
| Deployment requested for a pending plan | Blocked; the report reason contains "human approval required"; no job starts | Unapproved deployment blocked |
| Deployment requested for an approved plan | Blocked; the reason contains "live execution not implemented"; no job starts | Approved deployment blocked |
| Plan edited after approval | New hash; decision back to pending | Changed plan invalidates approval |
| Deployment requested with the old hash | Blocked; the reason contains "plan changed" | Stale hash blocked |
| Plan rejected by the operator | Blocked; approval recorded as rejected | Operator rejection |
