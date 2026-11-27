"""Validate terminal run reports against the extended report schema."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas/report.schema.json"
REPORT_VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))

TERMINAL = ("succeeded", "failed", "partial", "aborted")


def validate_report(report: dict) -> None:
    """Raise ValidationError for shape errors or ValueError for inconsistent reports."""
    REPORT_VALIDATOR.validate(report)
    status = report["final_status"]
    jobs = report["jobs"]
    recovery = report["recovery"]

    for job in jobs:
        if job["status"] == "succeeded" and job["finished_at"] is None:
            raise ValueError(f"{job['host']} {job['stage']}: succeeded job needs finished_at")
        if job["status"] == "failed" and job["task_id"] is None and job["stage"] != "preflight":
            raise ValueError(f"{job['host']} {job['stage']}: failed job needs a task id")
        if job["status"] == "pending" and job["started_at"] is not None:
            raise ValueError(f"{job['host']} {job['stage']}: pending job cannot have started_at")

    if status == "blocked":
        return
    if status not in TERMINAL:
        raise ValueError(f"unknown terminal status: {status}")

    if status == "succeeded":
        if not jobs:
            raise ValueError("a succeeded report needs at least one job")
        if any(job["status"] in ("failed", "unknown") for job in jobs):
            raise ValueError("a succeeded report cannot contain failed or unknown jobs")
        if any(entry["status"] in ("failed", "manual_intervention") for entry in recovery):
            raise ValueError("a succeeded report cannot contain failed recovery")
    elif status == "failed":
        if not any(job["status"] in ("failed", "unknown") for job in jobs) and not any(
                entry["status"] in ("failed", "manual_intervention") for entry in recovery):
            raise ValueError("a failed report needs a failed job or recovery outcome")
    elif status == "partial":
        if not any(job["status"] == "succeeded" for job in jobs):
            raise ValueError("a partial report needs at least one succeeded job")
        if not any(job["status"] in ("failed", "unknown", "skipped") for job in jobs):
            raise ValueError("a partial report needs an unfinished or failed job")
    elif status == "aborted":
        if not report["reason"].strip():
            raise ValueError("an aborted report needs a reason")
        if any(job["status"] == "running" for job in jobs):
            raise ValueError("an aborted report cannot leave a running job")


def build_report(*, run_id, timestamp, plan_hash, approval, final_status, reason,
                 jobs=None, recovery=None, observed_versions=None):
    report = {
        "run_id": run_id, "timestamp": timestamp, "plan_hash": plan_hash,
        "approval": approval, "final_status": final_status, "reason": reason,
        "jobs": list(jobs or []), "recovery": list(recovery or []),
    }
    if observed_versions is not None:
        report["observed_versions"] = dict(observed_versions)
    validate_report(report)
    return report
