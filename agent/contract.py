"""Standard response envelope, tenant authentication and error handling."""

import hmac

from fastapi import Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def ok(data):
    return {"status": "ok", "data": data, "error": None}


def error(message):
    return {"status": "error", "data": None, "error": message}


def bearer(authorization):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authorization Bearer token is required")
    token = authorization[len("Bearer "):].strip()
    if not token:
        raise HTTPException(401, "Authorization Bearer token is empty")
    return token


def require_tenant(
    request: Request,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    if not x_tenant_id:
        raise HTTPException(400, "X-Tenant-Id header is required")
    if request.app.state.store.get(x_tenant_id) is None:
        raise HTTPException(404, "tenant is not active")
    token = bearer(authorization)
    if not request.app.state.store.validate_key(x_tenant_id, token):
        raise HTTPException(403, "tenant api key is not valid for this company")
    return x_tenant_id


def require_tenant_path(
    request: Request,
    tenant_id: str,
    x_tenant_id: str = Header(None, alias="X-Tenant-Id"),
    authorization: str = Header(None),
):
    if x_tenant_id != tenant_id:
        raise HTTPException(403, "tenant id does not match the authenticated tenant")
    return require_tenant(request, x_tenant_id, authorization)


def require_operator(
    request: Request,
    x_operator_token: str = Header(None, alias="X-Operator-Token"),
):
    if not request.app.state.execution_enabled:
        raise HTTPException(403, "execution is disabled by the operator")
    expected = request.app.state.operator_token
    if not expected or not x_operator_token or not hmac.compare_digest(expected, x_operator_token):
        raise HTTPException(403, "a valid operator token is required")
    return True


def install_error_handlers(app):
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content=error(str(exc.detail)))

    @app.exception_handler(HTTPException)
    async def fastapi_http_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content=error(str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(status_code=422,
                            content=error("request body does not match the expected schema"))

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return JSONResponse(status_code=500,
                            content=error("internal agent error; details are not exposed"))
