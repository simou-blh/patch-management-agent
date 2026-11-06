"""Operator-only import of a contract-v1 inspection export; no model-facing tool.

This consumes a trusted producer export. It does not run Ansible or Semaphore, parse
raw logs, or turn manually authored/model-generated JSON into trusted observations.
"""

import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from jsonschema import ValidationError

from patch_agent.approval import data_directory
from patch_agent.evidence import evidence_max_age, validate_evidence_contract, validate_evidence_readiness


def read_evidence(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("inspection evidence could not be read as JSON") from exc


def publish_evidence(evidence: dict, *, targets: list[str], directory: Path | None = None) -> Path:
    """Validate and atomically publish; failed imports leave the old file intact.

    A concurrent publisher fails instead of silently overwriting another import.
    After a crashed import, the operator must investigate and remove its lock.
    """
    evidence = deepcopy(evidence)
    max_age = evidence_max_age()
    validate_evidence_readiness(evidence, targets=targets, max_age=max_age)
    payload = json.dumps(evidence, ensure_ascii=True, allow_nan=False, indent=2) + "\n"
    directory = data_directory() if directory is None else Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = directory / "evidence.json"
    lock = directory / "evidence.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError("evidence import already locked; check operator-side import status") from exc
    temporary = None
    try:
        os.close(descriptor)
        # A late older export must not replace newer evidence, even if still fresh.
        if destination.exists():
            previous = read_evidence(destination)
            validate_evidence_contract(previous)
            if datetime.fromisoformat(previous["collected_at"]) > datetime.fromisoformat(evidence["collected_at"]):
                raise ValueError("a newer evidence collection is already published")
            for name in set(previous["hosts"]) & set(evidence["hosts"]):
                if datetime.fromisoformat(previous["hosts"][name]["collected_at"]) > datetime.fromisoformat(evidence["hosts"][name]["collected_at"]):
                    raise ValueError(f"newer evidence for host {name} is already published")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".evidence-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        # Check again immediately before publishing; time spent writing cannot renew age.
        validate_evidence_readiness(evidence, targets=targets, max_age=max_age)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)
    return destination


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="trusted contract-v1 inspection export")
    parser.add_argument("--targets", nargs="+", required=True, help="exact inspected inventory host names")
    args = parser.parse_args(argv)
    try:
        path = publish_evidence(read_evidence(args.source), targets=args.targets)
    except ValidationError:
        parser.exit(1, "Evidence rejected: inspection export does not match contract v1.\n")
    except ValueError as exc:
        parser.exit(1, f"Evidence rejected: {exc}\n")
    except OSError:
        parser.exit(1, "Evidence import failed: check operator-side storage permissions and space.\n")
    print(f"Published validated inspection evidence: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
