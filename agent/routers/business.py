"""Tenant-scoped business endpoints carrying the patch-management sprints."""

from datetime import datetime, timezone
import inspect

from fastapi import APIRouter, HTTPException, Request, Header
from jsonschema import ValidationError

from patch_agent.approval import plan_hash, validate_plan
from patch_agent.assessment import CONTRACT_ERRORS
from patch_agent.assessment_builder import build_assessment
from patch_agent.evidence import validate_evidence_contract
from patch_agent.assessment import validate_advisory_cache
from patch_agent.planner import build_plan
from patch_agent.preflight import validate_preflight_contract
from agent.alerts import send_event
from agent.contract import ok, require_tenant, require_operator

router = APIRouter(prefix="/api/v1")
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
PRIORITY_SEVERITY = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _tenant(request, x_tenant_id, authorization):
    return require_tenant(request, x_tenant_id, authorization)


def _tenant_state(request, tenant):
    return request.app.state.store.get(tenant)


def _alert_threshold(request, tenant):
    config = (_tenant_state(request, tenant) or {}).get("config", {})
    return config.get("alert_severity_threshold", "medium")


async def _send(request, tenant, event_type, severity, data):
    state = _tenant_state(request, tenant) or {}
    api_key = state.get("api_key")
    return await send_event(tenant, api_key, event_type, severity, data)


@router.post("/evidence")
def upload_evidence(
    request: Request,
    body: dict | None = None,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    tenant = _tenant(request, x_tenant_id, authorization)
    if not body:
        raise HTTPException(400, "evidence body is required")
    try:
        validate_evidence_contract(body)
    except CONTRACT_ERRORS as exc:
        raise HTTPException(400, f"invalid evidence contract: {exc}") from exc
    request.app.state.store.write_json(tenant, "evidence.json", body)
    return ok({"accepted": True, "targets": body["targets"],
               "collected_at": body["collected_at"]})


@router.post("/advisories")
def upload_advisories(
    request: Request,
    body: dict | None = None,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    tenant = _tenant(request, x_tenant_id, authorization)
    if not body:
        raise HTTPException(400, "advisory cache body is required")
    try:
        validate_advisory_cache(body)
    except CONTRACT_ERRORS as exc:
        raise HTTPException(400, f"invalid advisory cache: {exc}") from exc
    request.app.state.store.write_json(tenant, "advisories.json", body)
    return ok({"accepted": True, "release": body["release"],
               "fetched_at": body["fetched_at"], "packages": len(body["packages"])})


@router.post("/assess")
async def assess(
    request: Request,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    tenant = _tenant(request, x_tenant_id, authorization)
    store = request.app.state.store
    evidence = store.read_json(tenant, "evidence.json")
    cache = store.read_json(tenant, "advisories.json")
    if evidence is None or cache is None:
        raise HTTPException(409, "evidence.json and advisories.json must be uploaded first")
    try:
        assessment = build_assessment(evidence, cache, assessed_at=_now())
    except CONTRACT_ERRORS as exc:
        raise HTTPException(400, f"assessment failed: {exc}") from exc
    store.write_json(tenant, "assessment.json", assessment)

    threshold = SEVERITY_RANK.get(_alert_threshold(request, tenant), 2)
    alerts = 0
    for result in assessment["results"]:
        if result["status"] != "affected":
            continue
        decision = result["decision"] or {}
        severity = PRIORITY_SEVERITY.get(decision.get("priority", "medium"), "medium")
        if SEVERITY_RANK[severity] < threshold:
            continue
        advisories = [finding["advisory_id"] for finding in result["findings"]
                      if finding["status"] == "affected"]
        await _send(request, tenant, "patch_affected", severity, {
            "host": result["host"], "package": result["package"],
            "advisories": advisories,
            "proposed_version": decision.get("proposed_version"),
            "action": decision.get("action"),
        })
        alerts += 1

    counts = {}
    for result in assessment["results"]:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return ok({"assessed_at": assessment["assessed_at"], "counts": counts, "alerts": alerts})


@router.post("/plans")
async def create_plan(
    request: Request,
    body: dict | None = None,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    tenant = _tenant(request, x_tenant_id, authorization)
    store = request.app.state.store
    evidence = store.read_json(tenant, "evidence.json")
    assessment = store.read_json(tenant, "assessment.json")
    if evidence is None or assessment is None:
        raise HTTPException(409, "evidence.json and assessment.json must exist first")
    payload = body or {}
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise HTTPException(400, "run_id is required")
    try:
        plan = build_plan(assessment, evidence, run_id=run_id,
                         canary=payload.get("canary"))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, f"plan generation failed: {exc}") from exc
    store.write_json(tenant, f"plans/{run_id}.json", plan)
    preflight = store.read_json(tenant, "preflight.json")
    ready = preflight is not None and all(
        host.get("status") == "ready" for host in preflight.get("hosts", {}).values())
    await _send(request, tenant, "patch_plan_ready", "info", {
        "run_id": run_id, "patch": sum(p["action"] == "patch" for p in plan["packages"]),
        "defer": sum(p["action"] == "defer" for p in plan["packages"]),
        "preflight_ready": ready,
    })
    return ok({"run_id": run_id, "plan_hash": plan_hash(plan),
               "canary": plan["canary"], "preflight_ready": ready,
               "patch": sum(p["action"] == "patch" for p in plan["packages"]),
               "defer": sum(p["action"] == "defer" for p in plan["packages"])})


@router.post("/preflight")
async def upload_preflight(
    request: Request,
    body: dict | None = None,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    tenant = _tenant(request, x_tenant_id, authorization)
    if not body:
        raise HTTPException(400, "preflight body is required")
    try:
        validate_preflight_contract(body)
    except CONTRACT_ERRORS as exc:
        raise HTTPException(400, f"invalid preflight contract: {exc}") from exc
    request.app.state.store.write_json(tenant, "preflight.json", body)
    blocking = [name for name, host in body["hosts"].items() if host["status"] != "ready"]
    if blocking:
        await _send(request, tenant, "patch_preflight_blocked", "high",
                    {"hosts": blocking})
    return ok({"accepted": True, "targets": body["targets"],
               "ready": not blocking, "blocking": blocking})


@router.get("/status")
def business_status(
    request: Request,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    tenant = _tenant(request, x_tenant_id, authorization)
    store = request.app.state.store
    assessment = store.read_json(tenant, "assessment.json") or {}
    plans = list((store.directory(tenant) / "plans").glob("*.json")) \
        if (store.directory(tenant) / "plans").is_dir() else []
    return ok({
        "tenant": tenant,
        "has_evidence": store.has(tenant, "evidence.json"),
        "has_advisories": store.has(tenant, "advisories.json"),
        "has_assessment": store.has(tenant, "assessment.json"),
        "has_preflight": store.has(tenant, "preflight.json"),
        "assessed_at": assessment.get("assessed_at"),
        "plans": len(plans),
        "execution_enabled": request.app.state.execution_enabled,
    })


@router.post("/runs")
async def start_run(
    request: Request,
    body: dict | None = None,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
    x_operator_token: str = Header(None, alias="X-Operator-Token"),
):
    tenant = _tenant(request, x_tenant_id, authorization)
    require_operator(request, x_operator_token)
    payload = body or {}
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise HTTPException(400, "run_id is required")
    store = request.app.state.store
    plan = store.read_json(tenant, f"plans/{run_id}.json")
    evidence = store.read_json(tenant, "evidence.json")
    assessment = store.read_json(tenant, "assessment.json")
    preflight = store.read_json(tenant, "preflight.json")
    if plan is None or evidence is None or assessment is None:
        raise HTTPException(409, "plan, evidence and assessment must exist first")
    if preflight is None:
        raise HTTPException(409, "preflight is required before execution")
    try:
        validate_plan(plan, evidence, assessment=assessment, preflight=preflight)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(409, f"plan cannot be executed: {exc}") from exc
    factory = request.app.state.runner_factory
    if factory is None:
        raise HTTPException(503, "execution adapter is not configured on this agent")
    result = factory(plan)
    if inspect.isawaitable(result):
        result = await result
    store.write_json(tenant, f"reports/{run_id}.json", result)
    return ok(result)


@router.get("/runs/{run_id}")
def get_run(
    request: Request,
    run_id: str,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    tenant = _tenant(request, x_tenant_id, authorization)
    report = request.app.state.store.read_json(tenant, f"reports/{run_id}.json")
    if report is None:
        raise HTTPException(404, "run report not found")
    return ok(report)
