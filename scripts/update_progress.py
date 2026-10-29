"""Generate the four README sprint bars from plan.md; --check never writes files."""

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
START = "<!-- sprint-progress:start -->"
END = "<!-- sprint-progress:end -->"
LABELS = (
    "Lab & trusted evidence",
    "Assessment & readiness",
    "Canary & recovery",
    "Fleet & delivery",
)


def between(text, start, end):
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"expected exactly one {start} and {end}")
    first = text.index(start) + len(start)
    last = text.index(end)
    if first > last:
        raise ValueError("progress markers are out of order")
    return first, last


def completion(plan):
    counts = []
    for sprint in range(1, 5):
        first, last = between(plan, f"<!-- sprint:{sprint}:start -->",
                              f"<!-- sprint:{sprint}:end -->")
        rows = re.findall(r"^- \[([ xX])\] (.+)$", plan[first:last], re.MULTILINE)
        if len(rows) != 5:
            raise ValueError(f"Sprint {sprint} must have exactly five checkpoints")
        for checked, description in rows:
            if checked.lower() == "x" and not re.search(r"\bEvidence:\s*\S", description):
                raise ValueError(f"Sprint {sprint}: checked checkpoint needs an Evidence: reference")
        counts.append(sum(checked.lower() == "x" for checked, _ in rows))
    return counts


def updated_readme(readme, plan):
    counts = completion(plan)
    lines = ["**Sprint progress**", "", "```text"]
    for sprint, (label, done) in enumerate(zip(LABELS, counts), 1):
        bar = "█" * (done * 4) + "░" * (20 - done * 4)
        lines.append(f"Sprint {sprint}  {label:<23} [{bar}] {done * 20:>3}%  {done}/5")
    lines += ["```", "", "Verified team checkpoints · [Criteria and evidence](plan.md#5-sprint-progress)."]
    first, last = between(readme, START, END)
    return readme[:first] + "\n" + "\n".join(lines) + "\n" + readme[last:]


def main(argv=None, *, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if README bars are out of date")
    args = parser.parse_args(argv)
    try:
        path = root / "README.md"
        current = path.read_text(encoding="utf-8")
        generated = updated_readme(current, (root / "plan.md").read_text(encoding="utf-8"))
        if args.check:
            if generated != current:
                print("README sprint bars are stale. Run python scripts/update_progress.py", file=sys.stderr)
                return 1
            print("README sprint bars are current.")
        elif generated != current:
            path.write_text(generated, encoding="utf-8", newline="\n")
            print("Updated README sprint bars.")
        else:
            print("README sprint bars are current.")
    except (OSError, ValueError) as error:
        print(f"Progress check failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
