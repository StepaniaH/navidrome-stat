"""Application assembly: middleware, static pages, and lifespan wiring.

Route modules live in :mod:`src.routes`; collectors in :mod:`src.collectors`;
retention maintenance in :mod:`src.retention`; write paths and the dashboard
cache in :mod:`src.stats_service`.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from src import collectors
from src.auth import is_auth_enabled, is_authorized
from src.config import env_flag
from src.database import init_db
from src.privacy_ops import IMPORT_MAX_PAYLOAD_BYTES
from src.request_limits import PrivacyImportBodyLimitMiddleware
from src.retention import (
    retention_maintenance_loop,
    run_startup_retention_purge,
)
from src.routes import privacy, servers, stats, system
from src.runtime_state import runtime_state
from src.version import APP_VERSION, PROJECT_NAME

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

OPENAPI_ENABLED = env_flag("OPENAPI_ENABLED", default=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    await run_startup_retention_purge()

    retention_task = asyncio.create_task(retention_maintenance_loop())
    try:
        await collectors.reconcile_collectors()
    except Exception as exc:
        runtime_state.client_initialized = False
        logger.error(
            "Collector initialization failed (type=%s)",
            type(exc).__name__,
        )

    yield

    logger.info("Shutting down background task...")
    retention_task.cancel()
    try:
        await retention_task
    except asyncio.CancelledError:
        logger.info("Retention maintenance task cancelled.")
    await collectors.collector_manager.stop_all()
    runtime_state.polling_task = None


app = FastAPI(
    title=PROJECT_NAME,
    description=(
        "Aggregate Navidrome playback activity across clients, devices, users, "
        "and servers."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json" if OPENAPI_ENABLED else None,
)

ALWAYS_AUTH_EXEMPT_PATHS = frozenset(
    {"/health", "/health/ready", "/api/auth/login", "/api/auth/status"}
)


def _metrics_require_auth() -> bool:
    """Return True when /metrics should follow STATS_API_TOKEN."""
    return env_flag("STATS_METRICS_AUTH", default=False)


def _is_auth_exempt(path: str) -> bool:
    if path in ALWAYS_AUTH_EXEMPT_PATHS:
        return True
    if path == "/metrics":
        return not _metrics_require_auth()
    return False


def _with_security_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    return response


# Starlette prepends middleware, so auth and security declared below run before
# the body limiter. Unauthorized imports therefore never consume the payload.
app.add_middleware(
    PrivacyImportBodyLimitMiddleware,
    max_bytes=IMPORT_MAX_PAYLOAD_BYTES,
    apply_headers=_with_security_headers,
)


@app.middleware("http")
async def stats_auth_middleware(request: Request, call_next):
    if not is_auth_enabled():
        return await call_next(request)

    path = request.url.path
    if _is_auth_exempt(path):
        return await call_next(request)
    if is_authorized(request):
        return await call_next(request)
    if path in ("/docs", "/redoc", "/openapi.json"):
        if not OPENAPI_ENABLED:
            return await call_next(request)
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    if path.startswith("/api/") or path == "/metrics":
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    return _with_security_headers(response)


@app.exception_handler(ValueError)
async def validation_error_handler(_request: Request, exc: ValueError):
    """Translate domain validation failures into client errors."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Dashboard not found"}


@app.get("/review")
async def review_page():
    review_file = os.path.join(STATIC_DIR, "review.html")
    if os.path.exists(review_file):
        return FileResponse(review_file)
    raise HTTPException(status_code=404, detail="Review page not found")


@app.get("/settings")
async def settings_page():
    settings_file = os.path.join(STATIC_DIR, "settings.html")
    if os.path.exists(settings_file):
        return FileResponse(settings_file)
    raise HTTPException(status_code=404, detail="Settings page not found")


if OPENAPI_ENABLED:

    @app.get("/docs", include_in_schema=False)
    @app.get("/redoc", include_in_schema=False)
    async def api_reference_page():
        docs_file = os.path.join(STATIC_DIR, "api-docs.html")
        if os.path.exists(docs_file):
            return FileResponse(docs_file)
        raise HTTPException(status_code=404, detail="API reference not found")


app.include_router(system.router)
app.include_router(stats.router)
app.include_router(privacy.router)
app.include_router(servers.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=39421, access_log=False)
