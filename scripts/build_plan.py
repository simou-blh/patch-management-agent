#!/usr/bin/env python3
"""Generate a schema-valid plan from an assessment and its evidence.

Run from the repository root:
    export PATCH_AGENT_EVIDENCE_MAX_AGE_SECONDS=86400
    python scripts/build_plan.py \
        --assessment data/assessment.json \
        --evidence data/evidence.json \
        --run-id sprint2-demo --canary vm-01 \
        --output data/plan.json

The plan is a proposal. A human still has to approve its exact hash with the
operator CLI before any execution can be requested.
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from patch_agent.approval import plan_hash  # noqa: E402
from patch_agent.planner import build_plan  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--canary", default=None)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        assessment = json.loads(Path(args.assessment).read_text(encoding="utf-8"))
        evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
        plan = build_plan(assessment, evidence, run_id=args.run_id, canary=args.canary)
    except (OSError, ValueError, KeyError) as exc:
        print(f"plan generation failed: {exc}", file=sys.stderr)
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    patch = sum(entry["action"] == "patch" for entry in plan["packages"])
    defer = sum(entry["action"] == "defer" for entry in plan["packages"])
    print(f"plan written to {output}")
    print(f"run_id={plan['run_id']} canary={plan['canary']} patch={patch} defer={defer}")
    print(f"plan_hash={plan_hash(plan)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
