#!/usr/bin/env python3
"""Build a validated assessment result from evidence and an advisory cache.

Run from the repository root:
    python scripts/build_assessment.py \
        --evidence data/evidence.json \
        --advisories data/advisory-cache.json \
        --output data/assessment.json

No network access and no approval/execution authority.
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from patch_agent.assessment_builder import build_assessment  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--advisories", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--assessed-at", default=None,
                        help="UTC timestamp; defaults to now")
    args = parser.parse_args(argv)

    try:
        evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
        cache = json.loads(Path(args.advisories).read_text(encoding="utf-8"))
        assessment = build_assessment(evidence, cache, assessed_at=args.assessed_at)
    except (OSError, ValueError, KeyError) as exc:
        print(f"assessment failed: {exc}", file=sys.stderr)
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(assessment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    counts = {}
    for result in assessment["results"]:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    print(f"assessment written to {output}")
    print("statuses: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
