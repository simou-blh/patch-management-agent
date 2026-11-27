import pytest
from jsonschema import ValidationError

from patch_agent.report import build_report, validate_report

HASH = "a" * 64
NOW = "2026-11-27T12:00:00Z"


def job(status="succeeded", *, host="vm-01", stage="patch", task_id="42", finished=NOW):
    return {"host": host, "stage": stage, "template": "patch", "task_id": task_id,
            "status": status, "started_at": NOW, "finished_at": finished, "log_ref": "/logs/42"}


def test_blocked_report_remains_valid():
    report = build_report(run_id="run-1", timestamp=NOW, plan_hash=HASH,
                          approval="approved", final_status="blocked",
                          reason="live execution not implemented")
    assert report["jobs"] == [] and report["recovery"] == []


def test_success_report_with_job_and_recovery():
    report = build_report(run_id="run-1", timestamp=NOW, plan_hash=HASH,
                          approval="approved", final_status="succeeded",
                          reason="canary verified", jobs=[job()],
                          recovery=[{"host": "vm-01", "status": "not_attempted",
                                     "detail": "no recovery needed"}],
                          observed_versions={"demo-package:amd64": "1:1.0-2"})
    validate_report(report)


def test_partial_report_needs_both_outcomes():
    with pytest.raises(ValueError, match="partial"):
        build_report(run_id="run-1", timestamp=NOW, plan_hash=HASH,
                     approval="approved", final_status="partial",
                     reason="one host failed", jobs=[job()])
    build_report(run_id="run-1", timestamp=NOW, plan_hash=HASH,
                 approval="approved", final_status="partial", reason="one host failed",
                 jobs=[job(), job(status="failed", host="vm-02", task_id="43")])


def test_succeeded_report_rejects_failed_job():
    with pytest.raises(ValueError, match="succeeded"):
        build_report(run_id="run-1", timestamp=NOW, plan_hash=HASH,
                     approval="approved", final_status="succeeded",
                     reason="done", jobs=[job(status="failed")])


def test_job_status_is_constrained():
    with pytest.raises(ValidationError):
        build_report(run_id="run-1", timestamp=NOW, plan_hash=HASH,
                     approval="approved", final_status="failed", reason="failed",
                     jobs=[job(status="exploded")])


def test_pending_job_cannot_have_started_at():
    with pytest.raises(ValueError, match="pending"):
        build_report(run_id="run-1", timestamp=NOW, plan_hash=HASH,
                     approval="approved", final_status="blocked", reason="waiting",
                     jobs=[job(status="pending")])


def test_failed_report_needs_a_failure():
    with pytest.raises(ValueError, match="failed"):
        build_report(run_id="run-1", timestamp=NOW, plan_hash=HASH,
                     approval="approved", final_status="failed",
                     reason="failed", jobs=[job()])


def test_successful_job_needs_finished_at():
    with pytest.raises(ValueError, match="finished_at"):
        build_report(run_id="run-1", timestamp=NOW, plan_hash=HASH,
                     approval="approved", final_status="succeeded", reason="done",
                     jobs=[job(finished=None)])
