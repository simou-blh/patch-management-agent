import json
from pathlib import Path

import pytest

from patch_agent.approval import ApprovalStore
from patch_agent.executor import ExecutionFacade, RunStore, TemplateMap


class FakeTransport:
    def __init__(self):
        self.started = []
        self.statuses = {}

    def start(self, template, host, extra_vars):
        task_id = f"task-{len(self.started) + 1}"
        self.started.append((template, host, extra_vars))
        self.statuses[task_id] = "running"
        return {"task_id": task_id, "log_ref": f"/logs/{task_id}"}

    def status(self, task_id):
        return self.statuses.get(task_id, "unknown")


def templates():
    return TemplateMap({"inspect": 1, "preflight": 3, "patch": 4, "verify": 2, "recover": 5})


def approved_store(tmp_path, plan, evidence):
    (tmp_path / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    store = ApprovalStore(tmp_path)
    state = store.submit(plan, evidence)
    store.decide(plan["run_id"], state["plan_hash"], "approved")
    return store, state["plan_hash"]


def facade(tmp_path, store, transport, *, allow_mutation=False):
    return ExecutionFacade(store, RunStore(tmp_path), transport, templates(),
                           allow_mutation=allow_mutation)


def test_begin_requires_approval(tmp_path, plan, evidence):
    store = ApprovalStore(tmp_path)
    state = store.submit(plan, evidence)
    with pytest.raises(ValueError, match="approval"):
        facade(tmp_path, store, FakeTransport()).begin(plan["run_id"], state["plan_hash"])


def test_begin_blocks_duplicate_runs(tmp_path, plan, evidence):
    store, digest = approved_store(tmp_path, plan, evidence)
    subject = facade(tmp_path, store, FakeTransport())
    subject.begin(plan["run_id"], digest)
    with pytest.raises(ValueError, match="already exists"):
        subject.begin(plan["run_id"], digest)


def test_start_stage_binds_fixed_template_and_host(tmp_path, plan, evidence):
    store, digest = approved_store(tmp_path, plan, evidence)
    transport = FakeTransport()
    subject = facade(tmp_path, store, transport)
    subject.begin(plan["run_id"], digest)
    result = subject.start_stage(plan["run_id"], "vm-01", "preflight")
    assert result["task_id"] == "task-1"
    assert result["log_ref"] == "/logs/task-1"
    assert transport.started == [(3, "vm-01", {})]
    jobs = subject.runs.jobs(plan["run_id"])
    assert jobs[0]["status"] == "running" and jobs[0]["stage"] == "preflight"

    with pytest.raises(ValueError, match="outside"):
        subject.start_stage(plan["run_id"], "vm-99", "preflight")
    with pytest.raises(ValueError, match="unknown stage"):
        subject.start_stage(plan["run_id"], "vm-01", "shell")


def test_mutation_is_blocked_until_enabled(tmp_path, plan, evidence):
    store, digest = approved_store(tmp_path, plan, evidence)
    subject = facade(tmp_path, store, FakeTransport())
    subject.begin(plan["run_id"], digest)
    with pytest.raises(ValueError, match="mutation is blocked"):
        subject.start_stage(plan["run_id"], "vm-01", "patch")

    second = tmp_path / "second"
    second.mkdir()
    (second / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    second_plan = dict(plan, run_id="second-run")
    second_store = ApprovalStore(second)
    state = second_store.submit(second_plan, evidence)
    second_store.decide("second-run", state["plan_hash"], "approved")
    enabled = ExecutionFacade(second_store, RunStore(second), FakeTransport(), templates(),
                              allow_mutation=True)
    enabled.begin("second-run", state["plan_hash"])
    assert enabled.start_stage("second-run", "vm-01", "patch")["task_id"] == "task-1"


def test_refresh_records_terminal_status(tmp_path, plan, evidence):
    store, digest = approved_store(tmp_path, plan, evidence)
    transport = FakeTransport()
    subject = facade(tmp_path, store, transport)
    subject.begin(plan["run_id"], digest)
    started = subject.start_stage(plan["run_id"], "vm-01", "preflight")
    transport.statuses[started["task_id"]] = "failed"
    subject.refresh(plan["run_id"])
    job = subject.runs.jobs(plan["run_id"])[0]
    assert job["status"] == "failed" and job["finished_at"] is not None


def test_begin_initializes_every_target_as_pending(tmp_path, plan, evidence):
    store, digest = approved_store(tmp_path, plan, evidence)
    subject = facade(tmp_path, store, FakeTransport())
    subject.begin(plan["run_id"], digest)
    states = {row["host"]: row["status"] for row in subject.runs.host_states(plan["run_id"])}
    assert states == {"vm-01": "pending", "vm-02": "pending", "vm-03": "pending"}


def test_refresh_tracks_per_host_state_and_task_id(tmp_path, plan, evidence):
    store, digest = approved_store(tmp_path, plan, evidence)
    transport = FakeTransport()
    subject = facade(tmp_path, store, transport)
    subject.begin(plan["run_id"], digest)
    started = subject.start_stage(plan["run_id"], "vm-01", "preflight")
    transport.statuses[started["task_id"]] = "failed"
    subject.refresh(plan["run_id"])
    states = {row["host"]: row for row in subject.runs.host_states(plan["run_id"])}
    assert states["vm-01"]["status"] == "failed"
    assert states["vm-01"]["task_id"] == started["task_id"]
    assert states["vm-02"]["status"] == "pending"


def test_host_states_survive_a_new_store_instance(tmp_path, plan, evidence):
    store, digest = approved_store(tmp_path, plan, evidence)
    subject = facade(tmp_path, store, FakeTransport())
    subject.begin(plan["run_id"], digest)
    subject.start_stage(plan["run_id"], "vm-01", "preflight")
    reopened = RunStore(tmp_path)
    states = {row["host"]: row["status"] for row in reopened.host_states(plan["run_id"])}
    assert states["vm-01"] == "running"
    assert states["vm-02"] == "pending"


def test_template_map_rejects_missing_or_unknown_entries():
    with pytest.raises(ValueError, match="missing"):
        TemplateMap({"inspect": 1})
    with pytest.raises(ValueError, match="unknown"):
        TemplateMap({"inspect": 1, "preflight": 2, "patch": 3, "verify": 4,
                     "recover": 5, "shell": 6})


def test_template_map_reads_operator_file(tmp_path):
    path = tmp_path / "ids.json"
    path.write_text(json.dumps({"templates": {"inspect": 1, "preflight": 3,
                                               "patch": 4, "verify": 2, "recover": 5}}),
                    encoding="utf-8")
    assert TemplateMap.from_file(path).require("verify") == 2
