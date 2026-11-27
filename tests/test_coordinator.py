import pytest

from patch_agent.coordinator import Coordinator

HASH = "a" * 64
PLAN = {"run_id": "coordinator-run", "targets": ["vm-01", "vm-02", "vm-03"],
        "canary": "vm-01"}


class FakeRunner:
    def __init__(self, preflight=None, patch=None, verify=None, recover=None):
        self.overrides = {"preflight": preflight or {}, "patch": patch or {},
                          "verify": verify or {}, "recover": recover or {}}
        self.calls = []

    def _result(self, stage, host):
        self.calls.append((stage, host))
        status = self.overrides[stage].get(host)
        if status is None:
            status = "ready" if stage == "preflight" else "succeeded"
        return {"status": status, "task_id": f"{stage}-{host}",
                "log_ref": f"/logs/{stage}/{host}", "detail": f"{stage} {status}"}

    def preflight(self, host):
        return self._result("preflight", host)

    def patch(self, host):
        return self._result("patch", host)

    def verify(self, host):
        return self._result("verify", host)

    def recover(self, host):
        return self._result("recover", host)


def run(runner, *, allow_fleet=False):
    return Coordinator(runner).run(PLAN, plan_hash=HASH, allow_fleet=allow_fleet)


def test_canary_only_when_fleet_is_disabled():
    runner = FakeRunner()
    report = run(runner)
    assert report["final_status"] == "partial"
    assert runner.calls == [("preflight", "vm-01"), ("patch", "vm-01"), ("verify", "vm-01")]
    skipped = [job for job in report["jobs"] if job["status"] == "skipped"]
    assert {job["host"] for job in skipped} == {"vm-02", "vm-03"}


def test_canary_preflight_failure_modifies_nothing():
    runner = FakeRunner(preflight={"vm-01": "not_ready"})
    report = run(runner)
    assert report["final_status"] == "failed"
    assert runner.calls == [("preflight", "vm-01")]
    assert report["recovery"] == []
    assert "no host was modified" in report["reason"]


def test_canary_patch_failure_recovers_only_the_canary():
    runner = FakeRunner(patch={"vm-01": "failed"})
    report = run(runner)
    assert report["final_status"] == "failed"
    assert ("recover", "vm-01") in runner.calls
    assert all(host == "vm-01" for _, host in runner.calls)
    assert report["recovery"][0]["host"] == "vm-01"


def test_canary_verify_failure_recovers_only_the_canary():
    runner = FakeRunner(verify={"vm-01": "failed"})
    report = run(runner)
    assert report["final_status"] == "failed"
    assert runner.calls[-1] == ("recover", "vm-01")
    assert report["recovery"][0]["status"] == "succeeded"


def test_fleet_failure_stops_later_hosts_and_recovers_only_that_host():
    runner = FakeRunner(patch={"vm-02": "failed"})
    report = run(runner, allow_fleet=True)
    assert report["final_status"] == "partial"
    assert ("preflight", "vm-03") not in runner.calls
    assert ("recover", "vm-02") in runner.calls
    assert all(host != "vm-03" for stage, host in runner.calls if stage == "recover")
    assert [entry["host"] for entry in report["recovery"]] == ["vm-02"]
    skipped = [job["host"] for job in report["jobs"] if job["status"] == "skipped"]
    assert "vm-03" in skipped


def test_all_hosts_succeed_when_fleet_is_enabled():
    runner = FakeRunner()
    report = run(runner, allow_fleet=True)
    assert report["final_status"] == "succeeded"
    assert [host for stage, host in runner.calls if stage == "verify"] == ["vm-01", "vm-02", "vm-03"]
    assert report["recovery"] == []


def test_manual_intervention_is_reported():
    runner = FakeRunner(patch={"vm-01": "failed"},
                        recover={"vm-01": "manual_intervention"})
    report = run(runner)
    assert report["final_status"] == "failed"
    assert report["recovery"][0]["status"] == "manual_intervention"
    assert report["recovery"][0]["manual_intervention"] is True
