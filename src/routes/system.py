"""Process, authentication, readiness, and metrics endpoints."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from src.auth import (
    SESSION_COOKIE_NAME,
    authorization_context,
    is_auth_enabled,
    login_rate_limiter,
    session_cookie_params,
    session_cookie_value,
    verify_login_access,
)
from src.collectors import active_now_playing, build_readiness_report
from src.connection_diagnostics import build_connection_diagnostics
from src.metrics import format_prometheus_metrics
from src.schemas import (
    AuthStatusResponse,
    ConnectionDiagnosticsResponse,
    HealthLiveResponse,
    LoginRequest,
    ReadinessResponse,
)

router = APIRouter()


@router.get("/health", response_model=HealthLiveResponse)
async def health():
    """Liveness probe: process is running."""
    return {"status": "ok"}



@router.get("/api/auth/status", response_model=AuthStatusResponse)
async def auth_status(request: Request):
    """Reports whether dashboard/API access requires authentication."""
    access = authorization_context(request)
    return {
        "auth_required": is_auth_enabled(),
        "access_level": access.level if access else None,
        "source_id": access.source_id if access else None,
        "username": access.username if access else None,
    }


@router.post("/api/auth/login")
async def auth_login(body: LoginRequest, request: Request):
    """Create an administrator or viewer browser session."""
    if not is_auth_enabled():
        raise HTTPException(status_code=404, detail="Authentication is not enabled")
    retry_after = login_rate_limiter.check(request)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )
    access = verify_login_access(body.token)
    if access is None:
        login_rate_limiter.record_failure(request)
        raise HTTPException(status_code=401, detail="Unauthorized")
    login_rate_limiter.clear(request)
    response = JSONResponse(
        {
            "status": "ok",
            "access_level": access.level,
            "source_id": access.source_id,
            "username": access.username,
        }
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_cookie_value(access.level),
        max_age=60 * 60 * 24 * 30,
        **session_cookie_params(),
    )
    return response


@router.post("/api/auth/logout")
async def auth_logout():
    """Clears the browser session cookie."""
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(key=SESSION_COOKIE_NAME, **session_cookie_params())
    return response



@router.get("/health/ready", response_model=ReadinessResponse)
async def health_ready():
    """Readiness probe: database and background collector state."""
    report = await build_readiness_report()
    status_code = 200 if report["status"] != "not_ready" else 503
    return JSONResponse(content=report, status_code=status_code)


@router.get("/api/diagnostics", response_model=ConnectionDiagnosticsResponse)
async def connection_diagnostics():
    """Return redacted connection and first-run state for the settings UI."""
    return await build_connection_diagnostics()



@router.get("/metrics")
async def metrics():
    """Prometheus exposition endpoint; anonymous unless STATS_METRICS_AUTH is on."""
    active = len(active_now_playing())
    return PlainTextResponse(
        content=format_prometheus_metrics(active_sessions=active),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
