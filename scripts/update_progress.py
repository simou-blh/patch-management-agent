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
    progress = []
    for sprint in range(1, 5):
        first, last = between(plan, f"<!-- sprint:{sprint}:start -->",
                              f"<!-- sprint:{sprint}:end -->")
        checkpoints = []
        for line in plan[first:last].splitlines():
            if not line.lstrip().startswith("- ["):
                continue
            match = re.fullmatch(r"( *)- \[([ xX])\] (.+)", line)
            if match is None or len(match[1]) not in (0, 2):
                raise ValueError(f"Sprint {sprint}: invalid checkbox or indentation")
            item = (match[2].lower(), match[3], [])
            if not match[1]:
                checkpoints.append(item)
            elif checkpoints:
                checkpoints[-1][2].append(item)
            else:
                raise ValueError(f"Sprint {sprint}: substep needs a parent checkpoint")
        if len(checkpoints) != 5:
            raise ValueError(f"Sprint {sprint} must have exactly five checkpoints")
        percent = 0
        for checked, description, children in checkpoints:
            for state, text, _ in [(checked, description, children), *children]:
                if state == "x" and not re.search(r"\bEvidence:\s*\S", text):
                    raise ValueError(f"Sprint {sprint}: checked item needs an Evidence: reference")
            if children:
                if len(children) != 4:
                    raise ValueError(f"Sprint {sprint}: split checkpoints need exactly four substeps")
                done = sum(state == "x" for state, _, _ in children)
                if (checked == "x") != (done == 4):
                    raise ValueError(f"Sprint {sprint}: check the parent exactly when all four substeps are complete")
                percent += done * 5
            elif checked == "x":
                percent += 20
        progress.append((percent, sum(state == "x" for state, _, _ in checkpoints)))
    return progress


def updated_readme(readme, plan):
    progress = completion(plan)
    lines = ["**Sprint progress**", "", "```text"]
    for sprint, (label, (percent, done)) in enumerate(zip(LABELS, progress), 1):
        filled = percent // 5
        bar = "█" * filled + "░" * (20 - filled)
        lines.append(f"Sprint {sprint}  {label:<23} [{bar}] {percent:>3}%  {done}/5 full checkpoints")
    lines += ["```", "", "Verified checkpoints and substeps · [Criteria and evidence](plan.md#5-sprint-progress)."]
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
