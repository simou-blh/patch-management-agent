"""Teacher-contract lifecycle endpoints."""

import time

from fastapi import APIRouter, Header, HTTPException, Request
from jsonschema import Draft202012Validator, ValidationError

from agent import config
from agent.contract import bearer, ok, require_tenant, require_tenant_path

router = APIRouter()
CONFIG_VALIDATOR = Draft202012Validator(config.CONFIG_SCHEMA)


@router.get("/health")
def health(request: Request):
    return ok({
        "uptime_seconds": int(time.time() - request.app.state.started),
        "version": request.app.state.version,
        "execution_enabled": request.app.state.execution_enabled,
    })


@router.post("/tenant/activate")
def activate(
    request: Request,
    body: dict | None = None,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    if not x_tenant_id:
        raise HTTPException(400, "X-Tenant-Id header is required")
    api_key = bearer(authorization)
    configuration = (body or {}).get("config", {})
    try:
        CONFIG_VALIDATOR.validate(configuration)
        request.app.state.store.activate(x_tenant_id, api_key, configuration)
    except ValidationError as exc:
        raise HTTPException(400, "config does not match /config-schema") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ok({"activated": True})


@router.post("/tenant/deactivate")
def deactivate(
    request: Request,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    tenant = require_tenant(request, x_tenant_id, authorization)
    purged = request.app.state.store.deactivate(tenant)
    return ok({"deactivated": True, "data_purged": purged})


@router.get("/tenant/{tenant_id}/status")
def tenant_status(
    request: Request,
    tenant_id: str,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    tenant = require_tenant_path(request, tenant_id, x_tenant_id, authorization)
    status = request.app.state.store.status(tenant)
    if status is None:
        raise HTTPException(404, "tenant is not active")
    status["execution_enabled"] = request.app.state.execution_enabled
    return ok(status)


@router.get("/config-schema")
def config_schema():
    return ok(config.CONFIG_SCHEMA)


@router.post("/exchange/notify")
def exchange_notify(
    request: Request,
    body: dict | None = None,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    require_tenant(request, x_tenant_id, authorization)
    return ok({"processed": False, "reason": "this agent consumes no exchange objects"})
