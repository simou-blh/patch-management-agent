"""Local, single-operator approval store. There is no live execution backend yet."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from jsonschema import Draft202012Validator
from patch_agent.evidence import evidence_max_age, validate_evidence_readiness

ROOT = Path(__file__).resolve().parent.parent
PLAN_VALIDATOR = Draft202012Validator(json.loads((ROOT / "schemas/plan.schema.json").read_text()))


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def plan_hash(plan):
    return hashlib.sha256(canonical(plan).encode()).hexdigest()


def validate_plan(plan, evidence, *, assessment=None, preflight=None):
    PLAN_VALIDATOR.validate(plan)
    validate_evidence_readiness(evidence, targets=plan["targets"], max_age=evidence_max_age())
    targets = set(plan["targets"])
    if plan["canary"] not in targets:
        raise ValueError("canary outside selected targets")
    seen = set()
    for package in plan["packages"]:
        host, name = package["host"], package["name"]
        if host not in targets or (host, name) in seen:
            raise ValueError("package host outside scope or duplicate package")
        seen.add((host, name))
        known = evidence["hosts"][host]["packages"].get(name)
        if known is None or known["installed"] != package["current_version"]:
            raise ValueError("unknown package or installed-version evidence mismatch")
        version = package["proposed_version"]
        if package["action"] == "patch":
            if name.startswith(("linux-", "kernel")):
                raise ValueError("kernel changes are deferred in the MVP")
            if version is None or version not in {candidate["version"] for candidate in known["candidates"]}:
                raise ValueError("proposed version is unavailable in collected candidates")
        elif version is not None:
            raise ValueError("deferred packages must have a null proposed version")
    if {p["host"] for p in plan["packages"]} != targets:
        raise ValueError("each selected host must have package decisions")
    if assessment is not None:
        _validate_assessment_binding(plan, evidence, assessment)
    if preflight is not None:
        _validate_preflight_binding(plan, preflight)


def _validate_assessment_binding(plan, evidence, assessment):
    from patch_agent.assessment import canonical_sha256, validate_assessment_result

    validate_assessment_result(assessment)
    if assessment["evidence_sha256"] != canonical_sha256(evidence):
        raise ValueError("assessment is bound to a different evidence record")
    results = {(result["host"], result["package"]): result for result in assessment["results"]}
    for package in plan["packages"]:
        result = results.get((package["host"], package["name"]))
        if result is None:
            raise ValueError(
                f"package {package['name']} on {package['host']} was not assessed")
        decision = result["decision"]
        if package["action"] == "patch":
            if decision is None or decision["action"] != "patch":
                raise ValueError(
                    f"assessment does not approve a patch for {package['host']}/{package['name']}")
            if decision["proposed_version"] != package["proposed_version"]:
                raise ValueError(
                    f"plan version does not match the assessed decision for "
                    f"{package['host']}/{package['name']}")
        elif decision is not None and decision["action"] != "defer":
            raise ValueError(
                f"plan defers {package['host']}/{package['name']} but the assessment proposes a patch")


def _validate_preflight_binding(plan, preflight):
    from datetime import datetime
    from patch_agent.preflight import validate_preflight_contract

    validate_preflight_contract(preflight)
    if set(preflight["targets"]) != set(plan["targets"]):
        raise ValueError("preflight targets must match the plan targets")
    blocking = [name for name, host in preflight["hosts"].items() if host["status"] != "ready"]
    if blocking:
        raise ValueError(f"preflight blocks: {', '.join(sorted(blocking))}")
    age_limit = evidence_max_age()
    collected_at = datetime.fromisoformat(preflight["collected_at"])
    age = datetime.now(timezone.utc) - collected_at
    if age < timedelta(0):
        raise ValueError("preflight timestamp is in the future")
    if age > age_limit:
        raise ValueError("preflight result is stale")


class ApprovalStore:
    def __init__(self, data_dir):
        self.directory = Path(data_dir)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.directory / "approvals.sqlite"
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS plans (
                run_id TEXT PRIMARY KEY, plan TEXT NOT NULL, digest TEXT NOT NULL,
                decision TEXT NOT NULL, decided_at TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY, report TEXT NOT NULL)""")
        if os.name != "nt":
            self.database.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def submit(self, plan, evidence, *, assessment=None, preflight=None):
        validate_plan(plan, evidence, assessment=assessment, preflight=preflight)
        digest = plan_hash(plan)
        with self.connect() as db:
            db.execute("""INSERT INTO plans VALUES (?, ?, ?, 'pending', NULL)
                ON CONFLICT(run_id) DO UPDATE SET plan=excluded.plan, digest=excluded.digest,
                decision='pending', decided_at=NULL WHERE plans.digest != excluded.digest""",
                (plan["run_id"], canonical(plan), digest))
        return self.status(plan["run_id"])

    def status(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT plan, digest, decision, decided_at FROM plans WHERE run_id=?",
                             (run_id,)).fetchone()
        if row is None:
            raise ValueError("unknown run id")
        plan, digest, decision, decided_at = row
        if plan_hash(json.loads(plan)) != digest:
            raise ValueError("stored plan hash mismatch")
        return {"plan": json.loads(plan), "plan_hash": digest,
                "decision": decision, "decided_at": decided_at}

    def decide(self, run_id, expected_hash, decision):
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be approved or rejected")
        with self.connect() as db:
            result = db.execute("""UPDATE plans SET decision=?, decided_at=?
                WHERE run_id=? AND digest=?""", (decision, now(), run_id, expected_hash))
            if result.rowcount != 1:
                raise ValueError("plan changed or run id unknown; review the plan again")
        return self.status(run_id)

    def request_deployment(self, run_id, expected_hash):
        state = self.status(run_id)
        if state["plan_hash"] != expected_hash:
            reason = "plan changed; renewed review and approval required"
        elif state["decision"] != "approved":
            reason = "human approval required"
        else:
            reason = "live execution not implemented; no Semaphore job was started"
        report = {
            "run_id": run_id, "timestamp": now(), "plan_hash": state["plan_hash"],
            "approval": state["decision"], "final_status": "blocked", "reason": reason,
            "jobs": [], "recovery": [],
        }
        with self.connect() as db:
            db.execute("INSERT INTO requests(report) VALUES (?)", (canonical(report),))
        return report


def data_directory():
    """Operator-configured state root; never accepted as a model tool argument."""
    return Path(os.environ.get("PATCH_AGENT_DATA_DIR", ROOT / "data")).resolve()


def local_store():
    return ApprovalStore(data_directory())
