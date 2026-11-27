"""Approval-bound execution facade with durable runs and task references.

The facade never accepts playbook paths, template IDs or shell commands from the model.
It resolves fixed logical stages through an operator-owned template map, rechecks the
approval before each stage and records the task id/log reference in SQLite.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

from patch_agent.approval import ApprovalStore

STAGES = ("inspect", "preflight", "patch", "verify", "recover")
MUTATING = ("patch", "recover")
TRANSPORT_STATUS = {
    "success": "succeeded", "succeeded": "succeeded", "ok": "succeeded",
    "failed": "failed", "error": "failed", "failure": "failed",
    "running": "running", "pending": "pending", "queued": "pending",
    "stopped": "failed", "canceled": "failed", "cancelled": "failed",
}


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class TemplateMap:
    """Operator-owned mapping of logical stages to fixed Semaphore template IDs."""

    def __init__(self, mapping):
        if not isinstance(mapping, dict):
            raise ValueError("template map must be an object")
        unknown = set(mapping) - set(STAGES)
        if unknown:
            raise ValueError(f"unknown logical templates: {', '.join(sorted(unknown))}")
        missing = set(STAGES) - set(mapping)
        if missing:
            raise ValueError(f"missing logical templates: {', '.join(sorted(missing))}")
        for stage, template_id in mapping.items():
            if not isinstance(template_id, int) or template_id <= 0:
                raise ValueError(f"{stage} template id must be a positive integer")
        self.mapping = dict(mapping)

    @classmethod
    def from_file(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8"))["templates"])

    def require(self, stage):
        if stage not in self.mapping:
            raise ValueError(f"unknown stage: {stage}")
        return self.mapping[stage]


class RunStore:
    """Durable execution state; separate from the approval database."""

    def __init__(self, data_dir):
        self.directory = Path(data_dir)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.directory / "execution.sqlite"
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, plan_hash TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, report TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                host TEXT NOT NULL, stage TEXT NOT NULL, template INTEGER NOT NULL,
                task_id TEXT, status TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                log_ref TEXT, detail TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS host_states (
                run_id TEXT NOT NULL, host TEXT NOT NULL, status TEXT NOT NULL,
                task_id TEXT, updated_at TEXT NOT NULL, detail TEXT,
                PRIMARY KEY (run_id, host))""")
        if hasattr(self.database, "chmod"):
            try:
                self.database.chmod(0o600)
            except OSError:
                pass

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_run(self, run_id, plan_hash):
        now = timestamp()
        try:
            with self.connect() as db:
                db.execute("INSERT INTO runs VALUES (?, ?, 'approved', ?, ?, NULL)",
                           (run_id, plan_hash, now, now))
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"run already exists: {run_id}") from exc
        return self.run(run_id)

    def run(self, run_id):
        with self.connect() as db:
            row = db.execute("""SELECT run_id, plan_hash, status, created_at, updated_at, report
                FROM runs WHERE run_id=?""", (run_id,)).fetchone()
        if row is None:
            raise ValueError("unknown run")
        return {"run_id": row[0], "plan_hash": row[1], "status": row[2],
                "created_at": row[3], "updated_at": row[4],
                "report": json.loads(row[5]) if row[5] else None}

    def set_status(self, run_id, status):
        with self.connect() as db:
            db.execute("UPDATE runs SET status=?, updated_at=? WHERE run_id=?",
                       (status, timestamp(), run_id))

    def add_job(self, run_id, host, stage, template, task_id, log_ref, status="pending", detail=None):
        with self.connect() as db:
            cursor = db.execute("""INSERT INTO jobs
                (run_id, host, stage, template, task_id, status, started_at, finished_at, log_ref, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                (run_id, host, stage, template, task_id, status,
                 timestamp() if status in ("pending", "running") else None, log_ref, detail))
        return cursor.lastrowid

    def update_job(self, job_id, status, finished_at=None, detail=None):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?, finished_at=?, detail=COALESCE(?, detail) WHERE id=?",
                       (status, finished_at, detail, job_id))

    def jobs(self, run_id):
        with self.connect() as db:
            rows = db.execute("""SELECT id, host, stage, template, task_id, status,
                started_at, finished_at, log_ref, detail FROM jobs WHERE run_id=? ORDER BY id""",
                (run_id,)).fetchall()
        return [{"id": row[0], "host": row[1], "stage": row[2], "template": row[3],
                 "task_id": row[4], "status": row[5], "started_at": row[6],
                 "finished_at": row[7], "log_ref": row[8], "detail": row[9]} for row in rows]

    def set_host_state(self, run_id, host, status, task_id=None, detail=None):
        with self.connect() as db:
            db.execute("""INSERT INTO host_states VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, host) DO UPDATE SET status=excluded.status,
                task_id=COALESCE(excluded.task_id, host_states.task_id),
                updated_at=excluded.updated_at, detail=excluded.detail""",
                (run_id, host, status, task_id, timestamp(), detail))

    def host_states(self, run_id):
        with self.connect() as db:
            rows = db.execute("""SELECT host, status, task_id, updated_at, detail
                FROM host_states WHERE run_id=? ORDER BY host""", (run_id,)).fetchall()
        return [{"host": row[0], "status": row[1], "task_id": row[2],
                 "updated_at": row[3], "detail": row[4]} for row in rows]

    def save_report(self, run_id, report, status):
        with self.connect() as db:
            db.execute("UPDATE runs SET report=?, status=?, updated_at=? WHERE run_id=?",
                       (json.dumps(report, sort_keys=True), status, timestamp(), run_id))


class ExecutionFacade:
    """Start and track fixed stages for an approved stored plan."""

    def __init__(self, approvals, runs, transport, templates, *, allow_mutation=False):
        for value, name in ((approvals, ApprovalStore), (runs, RunStore)):
            if not isinstance(value, name):
                raise TypeError(f"expected {name.__name__}")
        self.approvals = approvals
        self.runs = runs
        self.transport = transport
        self.templates = templates
        self.allow_mutation = allow_mutation

    def _approved_plan(self, run_id, plan_hash):
        state = self.approvals.status(run_id)
        if state["plan_hash"] != plan_hash:
            raise ValueError("plan changed; renewed approval required")
        if state["decision"] != "approved":
            raise ValueError("human approval is required")
        return state["plan"]

    def _revalidate(self, plan):
        from patch_agent.approval import validate_plan

        directory = self.approvals.directory
        required = os.environ.get("PATCH_AGENT_REQUIRE_GATES") == "1"
        evidence_path = directory / "evidence.json"
        if not evidence_path.is_file():
            if required:
                raise ValueError("operator evidence.json is required by policy")
            return
        documents = {}
        for name in ("assessment", "preflight"):
            path = directory / f"{name}.json"
            if not path.is_file():
                if required:
                    raise ValueError(f"operator {name}.json is required by policy")
                documents[name] = None
                continue
            documents[name] = json.loads(path.read_text(encoding="utf-8"))
        validate_plan(plan, json.loads(evidence_path.read_text(encoding="utf-8")),
                      assessment=documents["assessment"], preflight=documents["preflight"])

    def begin(self, run_id, plan_hash):
        plan = self._approved_plan(run_id, plan_hash)
        self._revalidate(plan)
        run = self.runs.create_run(run_id, plan_hash)
        for host in plan["targets"]:
            self.runs.set_host_state(run_id, host, "pending")
        return run

    def start_stage(self, run_id, host, stage, extra_vars=None):
        if stage not in STAGES:
            raise ValueError(f"unknown stage: {stage}")
        run = self.runs.run(run_id)
        plan = self._approved_plan(run_id, run["plan_hash"])
        self._revalidate(plan)
        if host not in plan["targets"]:
            raise ValueError("host outside the approved plan")
        if stage in MUTATING and not self.allow_mutation:
            raise ValueError("mutation is blocked until the operator enables it")
        template = self.templates.require(stage)
        task = self.transport.start(template, host, dict(extra_vars or {}))
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("transport did not return a task id")
        job_id = self.runs.add_job(run_id, host, stage, template, task_id,
                                  task.get("log_ref"), status="running")
        self.runs.set_host_state(run_id, host, "running", task_id=task_id)
        self.runs.set_status(run_id, "running")
        return {"job_id": job_id, "task_id": task_id, "log_ref": task.get("log_ref")}

    def refresh(self, run_id):
        run = self.runs.run(run_id)
        for job in self.runs.jobs(run_id):
            if job["status"] not in ("pending", "running") or not job["task_id"]:
                continue
            raw = self.transport.status(job["task_id"])
            status = TRANSPORT_STATUS.get(str(raw).lower())
            if status is None:
                status = "unknown"
            if status in ("succeeded", "failed", "unknown"):
                self.runs.update_job(job["id"], status, finished_at=timestamp())
            else:
                self.runs.update_job(job["id"], status)

        jobs = self.runs.jobs(run_id)
        for host in {job["host"] for job in jobs}:
            host_jobs = [job for job in jobs if job["host"] == host]
            statuses = {job["status"] for job in host_jobs}
            task_id = next((job["task_id"] for job in reversed(host_jobs)
                            if job["task_id"]), None)
            if statuses & {"failed", "unknown"}:
                state = "failed"
            elif statuses & {"pending", "running"}:
                state = "running"
            elif statuses <= {"succeeded", "skipped"}:
                state = "succeeded"
            else:
                state = "pending"
            detail = ", ".join(f"{job['stage']}={job['status']}" for job in host_jobs)
            self.runs.set_host_state(run_id, host, state, task_id=task_id, detail=detail)
        return self.runs.run(run_id)

    def finish(self, run_id, report):
        self.runs.save_report(run_id, report, report["final_status"])
        return self.runs.run(run_id)
