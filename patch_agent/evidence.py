"""Validate the v1 collection contract, not its freshness or authority to patch.

This helper is deliberately not connected to plan submission yet.
"""

from datetime import datetime
import json
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas/evidence.schema.json"
EVIDENCE_VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def validate_evidence_contract(evidence: dict) -> None:
    """Raise ValidationError for shape errors or ValueError for inconsistent records.

    Failed-host records are valid diagnostics. Passing this check alone must never
    make them eligible for plan generation or execution.
    """
    EVIDENCE_VALIDATOR.validate(evidence)
    if set(evidence["targets"]) != set(evidence["hosts"]):
        raise ValueError("targets and host results must match exactly")

    # jsonschema's date-time format assertion needs optional dependencies. Parse
    # explicitly so impossible calendar dates are rejected in every environment.
    completed_at = datetime.fromisoformat(evidence["collected_at"])
    for name, host in evidence["hosts"].items():
        observed_at = datetime.fromisoformat(host["collected_at"])
        if observed_at > completed_at:
            raise ValueError(f"host {name} timestamp is after collection completion")
        for package in host["packages"].values():
            versions = [candidate["version"] for candidate in package["candidates"]]
            if len(versions) != len(set(versions)):
                raise ValueError("candidate versions must be unique; combine their repository origins")
            for candidate in package["candidates"]:
                for origin in candidate["origins"]:
                    uri = urlsplit(origin["uri"])
                    if uri.username is not None or uri.password is not None:
                        raise ValueError("repository origin URI must not contain credentials")
                    if uri.scheme in ("http", "https"):
                        if not uri.hostname:
                            raise ValueError("HTTP repository origin URI requires a host")
                        # Accessing port also rejects nonnumeric/out-of-range ports.
                        uri.port
                    elif not uri.path:
                        raise ValueError("file repository origin URI requires a path")
