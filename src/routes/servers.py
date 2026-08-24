"""Navidrome connection management: source fallback config and server CRUD."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from src.client import NavidromeClient
from src.collector_manager import CollectorManager  # noqa: F401  (docs parity)
from src.collectors import CollectorApplyError, apply_collector_runtime_or_rollback
from src.database import (
    SCHEMA_VERSION,
    delete_server,
    get_server,
    list_servers,
    save_server,
)
from src.runtime_state import runtime_state
from src.schemas import (
    AboutResponse,
    ServerRequest,
    ServerResponse,
    ServerTestResponse,
    SourceConfigResponse,
    SourceConfigUpdate,
    SourceTestRequest,
    SourceTestResponse,
)
from src.source_config import (
    get_saved_source_config,
    has_full_config,
    redacted_view,
    replace_saved_source_config,
    resolve_source_config,
    validate_source_url,
)
from src.stats_service import server_mutation_lock, stats_service
from src.version import APP_VERSION, LICENSE, PROJECT_NAME, PROJECT_URL

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/source/config", response_model=SourceConfigResponse)
async def api_source_config_get():
    """Return the effective source configuration without its password."""
    saved = await get_saved_source_config()
    config = resolve_source_config(overrides=None, saved=saved)
    view = redacted_view(config)
    return SourceConfigResponse(**view)


@router.put("/api/source/config", response_model=SourceConfigResponse)
async def api_source_config_put(body: SourceConfigUpdate):
    """Save fallback source settings; environment variables retain priority."""
    if body.url is not None:
        try:
            body.url = validate_source_url(body.url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.username is not None and not body.username.strip():
        raise HTTPException(status_code=422, detail="username must not be empty")

    async with server_mutation_lock():
        saved = await get_saved_source_config()
        new_url = body.url if body.url is not None else saved.get("url")
        new_user = body.username if body.username is not None else saved.get("user")
        if not new_url or not new_user:
            raise HTTPException(status_code=422, detail="url and username are required")
        new_password = body.password or saved.get("password")

        try:
            await replace_saved_source_config(
                url=new_url,
                user=new_user,
                password=new_password,
            )
        except Exception as exc:
            logger.error("Source config persist failed")
            raise HTTPException(
                status_code=503,
                detail="Failed to save source config",
            ) from exc

        updated = await get_saved_source_config()
        config = resolve_source_config(overrides=None, saved=updated)
        try:
            await apply_collector_runtime_or_rollback(
                lambda: replace_saved_source_config(
                    url=saved.get("url"),
                    user=saved.get("user"),
                    password=saved.get("password"),
                )
            )
        except CollectorApplyError as exc:
            raise HTTPException(
                status_code=503,
                detail="Saved configuration could not be applied",
            ) from exc
        view = redacted_view(config)
        return SourceConfigResponse(**view)


@router.post("/api/source/test", response_model=SourceTestResponse)
async def api_source_test(body: SourceTestRequest):
    """Test source connectivity without persisting or echoing credentials."""
    saved = await get_saved_source_config()
    overrides = {
        "url": body.url,
        "user": body.username,
        "password": body.password,
    }
    config = resolve_source_config(overrides=overrides, saved=saved)
    if not has_full_config(config):
        return SourceTestResponse(ok=False, message="配置不完整，缺少 URL、用户名或密码")

    test_client = NavidromeClient(
        url=config["url"],
        user=config["user"],
        password=config["password"],
    )
    try:
        data = await test_client.get_now_playing()
        if not NavidromeClient.response_is_ok(data):
            return SourceTestResponse(ok=False, message="上游拒绝连接或返回错误")
    except Exception:
        return SourceTestResponse(ok=False, message="无法连接到上游 Navidrome")
    finally:
        try:
            await test_client.close()
        except Exception:
            logger.error("Failed to close test NavidromeClient")
    return SourceTestResponse(ok=True, message="连接成功")


def _server_view(server: dict) -> ServerResponse:
    snapshot = runtime_state.collector_snapshot(server["id"])
    seconds_since_last_poll = None
    if snapshot["last_poll_at"] is not None:
        seconds_since_last_poll = max(
            0,
            int(
                (
                    datetime.now(timezone.utc) - snapshot["last_poll_at"]
                ).total_seconds()
            ),
        )
    return ServerResponse(
        id=server["id"], display_name=server["display_name"], url=server["url"],
        username=server["username"], password_configured=bool(server.get("password")),
        enabled=bool(server.get("enabled", True)),
        runtime_status=snapshot["status"],
        last_poll_ok=snapshot["last_poll_ok"],
        seconds_since_last_poll=seconds_since_last_poll,
    )


@router.get("/api/servers", response_model=list[ServerResponse])
async def api_servers_get():
    return [_server_view(server) for server in await list_servers()]


@router.post("/api/servers", response_model=ServerResponse)
async def api_servers_create(body: ServerRequest):
    if not body.display_name.strip() or not body.username.strip():
        raise HTTPException(status_code=422, detail="display_name and username are required")
    try:
        url = validate_source_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not body.password:
        raise HTTPException(status_code=422, detail="password is required")
    server = {"id": uuid.uuid4().hex, "display_name": body.display_name.strip(), "url": url,
              "username": body.username.strip(), "password": body.password, "enabled": body.enabled}
    async with server_mutation_lock():
        await stats_service.create_server(server)
        try:
            await apply_collector_runtime_or_rollback(
                lambda: delete_server(server["id"])
            )
        except CollectorApplyError as exc:
            raise HTTPException(
                status_code=503,
                detail="Saved configuration could not be applied",
            ) from exc
        return _server_view(server)


@router.put("/api/servers/{server_id}", response_model=ServerResponse)
async def api_servers_update(server_id: str, body: ServerRequest):
    if not body.display_name.strip() or not body.username.strip():
        raise HTTPException(
            status_code=422,
            detail="display_name and username are required",
        )
    try:
        url = validate_source_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    async with server_mutation_lock():
        existing = await get_server(server_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Server not found")
        server = {"id": server_id, "display_name": body.display_name.strip(), "url": url,
                  "username": body.username.strip(), "password": body.password or existing["password"],
                  "enabled": body.enabled}
        await stats_service.update_server(server)
        try:
            await apply_collector_runtime_or_rollback(
                lambda: save_server(existing)
            )
        except CollectorApplyError as exc:
            raise HTTPException(
                status_code=503,
                detail="Saved configuration could not be applied",
            ) from exc
        return _server_view(server)


@router.delete("/api/servers/{server_id}")
async def api_servers_delete(server_id: str):
    async with server_mutation_lock():
        existing = await get_server(server_id)
        if not existing or not await stats_service.remove_server(server_id):
            raise HTTPException(status_code=404, detail="Server not found")
        try:
            await apply_collector_runtime_or_rollback(
                lambda: save_server(existing)
            )
        except CollectorApplyError as exc:
            raise HTTPException(
                status_code=503,
                detail="Saved configuration could not be applied",
            ) from exc
        return {"status": "ok"}


@router.post("/api/servers/{server_id}/test", response_model=ServerTestResponse)
async def api_servers_test(server_id: str, body: ServerRequest | None = None):
    server = await get_server(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    config = body or ServerRequest(
        display_name=server["display_name"],
        url=server["url"],
        username=server["username"],
    )
    if not config.username.strip():
        raise HTTPException(status_code=422, detail="username is required")
    try:
        url = validate_source_url(config.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    password = config.password or server["password"]
    test_client = NavidromeClient(
        url=url,
        user=config.username.strip(),
        password=password,
    )
    try:
        data = await test_client.get_now_playing()
        if not NavidromeClient.response_is_ok(data):
            return ServerTestResponse(ok=False, message="上游拒绝连接或返回错误")
    except Exception:
        return ServerTestResponse(ok=False, message="无法连接到上游 Navidrome")
    finally:
        await test_client.close()
    return ServerTestResponse(ok=True, message="连接成功")


@router.get("/api/about", response_model=AboutResponse)
async def api_about():
    return AboutResponse(
        name=PROJECT_NAME,
        version=APP_VERSION,
        schema_version=SCHEMA_VERSION,
        features=["多 Navidrome 服务器", "播放历史统计", "隐私数据管理", "本地外观偏好"],
        license=LICENSE,
        project_url=PROJECT_URL,
    )
