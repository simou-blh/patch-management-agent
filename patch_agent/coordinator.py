"""Sequential canary/fleet coordinator.

The coordinator owns the control flow and report; it never starts a job itself.
A runner implements the fixed stages (preflight, patch, verify, recover) and may
delegate to the execution facade. Fleet execution stays disabled unless the
operator explicitly enables it.
"""

from datetime import datetime, timezone

from patch_agent.report import build_report

STAGE_ORDER = ("preflight", "patch", "verify")


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _job(host, stage, result):
    status = result.get("status")
    if stage == "preflight":
        status = "succeeded" if status == "ready" else "failed"
    elif status not in ("succeeded", "failed", "skipped"):
        status = "failed" if status in ("error", "not_ready") else "unknown"
    finished = _timestamp() if status in ("succeeded", "failed", "unknown") else None
    return {
        "host": host, "stage": stage, "template": result.get("template", stage),
        "task_id": result.get("task_id"), "status": status,
        "started_at": _timestamp() if status != "skipped" else None,
        "finished_at": finished, "log_ref": result.get("log_ref"),
        "detail": result.get("detail", f"{stage} {status}"),
    }


def _skipped(host, stage):
    return {"host": host, "stage": stage, "template": stage, "task_id": None,
            "status": "skipped", "started_at": None, "finished_at": None,
            "log_ref": None, "detail": "not attempted"}


def _recovery(host, result):
    status = result.get("status")
    if status == "succeeded":
        recovery_status = "succeeded"
    elif status == "manual_intervention":
        recovery_status = "manual_intervention"
    else:
        recovery_status = "failed"
    return {"host": host, "status": recovery_status,
            "detail": result.get("detail", f"recovery {recovery_status}"),
            "manual_intervention": recovery_status == "manual_intervention"}


class Coordinator:
    def __init__(self, runner):
        self.runner = runner

    def run(self, plan, *, plan_hash, approval="approved", allow_fleet=False):
        targets = list(plan["targets"])
        canary = plan["canary"]
        jobs, recovery = [], []

        def call(host, stage):
            result = getattr(self.runner, stage)(host)
            jobs.append(_job(host, stage, result))
            return result

        def stop_remaining(start_index, reason):
            for host in targets[start_index:]:
                for stage in STAGE_ORDER:
                    jobs.append(_skipped(host, stage))
            verified = any(job["stage"] == "verify" and job["status"] == "succeeded"
                           for job in jobs)
            status = "partial" if verified else "failed"
            return build_report(
                run_id=plan["run_id"], timestamp=_timestamp(), plan_hash=plan_hash,
                approval=approval, final_status=status, reason=reason,
                jobs=jobs, recovery=recovery)

        preflight = call(canary, "preflight")
        if jobs[-1]["status"] != "succeeded":
            return stop_remaining(targets.index(canary) + 1,
                                  "canary preflight failed; no host was modified")

        patch = call(canary, "patch")
        if jobs[-1]["status"] != "succeeded":
            recovery.append(_recovery(canary, self.runner.recover(canary)))
            return stop_remaining(targets.index(canary) + 1,
                                  "canary patch failed; recovery attempted on the canary only")

        verify = call(canary, "verify")
        if jobs[-1]["status"] != "succeeded":
            recovery.append(_recovery(canary, self.runner.recover(canary)))
            return stop_remaining(targets.index(canary) + 1,
                                  "canary verification failed; recovery attempted on the canary only")

        if not allow_fleet:
            return stop_remaining(targets.index(canary) + 1,
                                  "canary verified; fleet rollout is disabled")

        fleet = [host for host in targets if host != canary]
        for index, host in enumerate(fleet):
            preflight = call(host, "preflight")
            if jobs[-1]["status"] != "succeeded":
                return stop_remaining(targets.index(host) + 1,
                                      f"{host} preflight failed; later hosts were not touched")
            call(host, "patch")
            if jobs[-1]["status"] != "succeeded":
                recovery.append(_recovery(host, self.runner.recover(host)))
                return stop_remaining(targets.index(host) + 1,
                                      f"{host} patch failed; recovery attempted on that host only")
            call(host, "verify")
            if jobs[-1]["status"] != "succeeded":
                recovery.append(_recovery(host, self.runner.recover(host)))
                return stop_remaining(targets.index(host) + 1,
                                      f"{host} verification failed; recovery attempted on that host only")

        return build_report(
            run_id=plan["run_id"], timestamp=_timestamp(), plan_hash=plan_hash,
            approval=approval, final_status="succeeded",
            reason="canary and every fleet host verified", jobs=jobs, recovery=recovery)
