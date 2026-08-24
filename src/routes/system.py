"""Process, authentication, readiness, and metrics endpoints."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from src.auth import (
    SESSION_COOKIE_NAME,
    is_auth_enabled,
    login_rate_limiter,
    session_cookie_params,
    session_cookie_value,
    verify_login_token,
)
from src.collectors import active_now_playing, build_readiness_report
from src.metrics import format_prometheus_metrics
from src.schemas import (
    AuthStatusResponse,
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
async def auth_status():
    """Reports whether dashboard/API access requires authentication."""
    return {"auth_required": is_auth_enabled()}


@router.post("/api/auth/login")
async def auth_login(body: LoginRequest, request: Request):
    """Creates a browser session when STATS_API_TOKEN is configured."""
    if not is_auth_enabled():
        raise HTTPException(status_code=404, detail="Authentication is not enabled")
    retry_after = login_rate_limiter.check(request)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )
    if not verify_login_token(body.token):
        login_rate_limiter.record_failure(request)
        raise HTTPException(status_code=401, detail="Unauthorized")
    login_rate_limiter.clear(request)
    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_cookie_value(),
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



@router.get("/metrics")
async def metrics():
    """Prometheus exposition endpoint; anonymous unless STATS_METRICS_AUTH is on."""
    active = len(active_now_playing())
    return PlainTextResponse(
        content=format_prometheus_metrics(active_sessions=active),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
