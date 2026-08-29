"""Privacy settings, storage metrics, retention, and per-user data endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from src.privacy_ops import (
    RETENTION_MAX_DAYS,
    RETENTION_MIN_DAYS,
    export_user_data,
    get_retention_days,
    get_storage_stats,
    list_users,
    preview_delete_user,
    preview_retention_purge,
    set_retention_days,
    validate_retention_days,
)
from src.schemas import (
    ConfirmRequest,
    PrivacySettingsResponse,
    PrivacySettingsUpdate,
    RetentionApplyRequest,
    RetentionApplyResponse,
    RetentionPreviewResponse,
    StorageStatsResponse,
    UserDeletePreviewResponse,
    UserDeleteResponse,
    UserImportRequest,
    UserImportResponse,
    UserSummary,
)
from src.stats_service import retention_policy_lock, stats_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _privacy_settings_response(days: int | None) -> PrivacySettingsResponse:
    return PrivacySettingsResponse(retention_days=days, permanent=days is None)


def _validated_username(username: str) -> str:
    normalized = username.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="username is required")
    if len(normalized) > 255:
        raise HTTPException(status_code=422, detail="username is too long")
    return normalized


@router.get("/api/privacy/settings", response_model=PrivacySettingsResponse)
async def api_privacy_settings():
    days = await get_retention_days()
    return _privacy_settings_response(days)


@router.put("/api/privacy/settings", response_model=PrivacySettingsResponse)
async def api_update_privacy_settings(body: PrivacySettingsUpdate):
    validate_retention_days(body.retention_days)
    async with retention_policy_lock():
        await set_retention_days(body.retention_days)
    return _privacy_settings_response(body.retention_days)


@router.get("/api/privacy/storage", response_model=StorageStatsResponse)
async def api_privacy_storage():
    return await get_storage_stats()


@router.get("/api/privacy/retention/preview", response_model=RetentionPreviewResponse)
async def api_retention_preview(
    days: int | None = Query(default=None, ge=RETENTION_MIN_DAYS, le=RETENTION_MAX_DAYS),
):
    return await preview_retention_purge(days)


@router.post("/api/privacy/retention/apply", response_model=RetentionApplyResponse)
async def api_retention_apply(body: RetentionApplyRequest):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required to delete data")
    async with retention_policy_lock():
        try:
            current_retention_days = await get_retention_days()
        except Exception as exc:
            logger.error("Retention policy query failed")
            raise HTTPException(
                status_code=503,
                detail="Retention operation failed",
            ) from exc
        if current_retention_days != body.expected_retention_days:
            raise HTTPException(
                status_code=409,
                detail="Retention policy changed; preview again",
            )
        try:
            result = await stats_service.purge_retention()
            return result
        except Exception as exc:
            logger.error("Retention apply failed")
            raise HTTPException(
                status_code=503,
                detail="Retention operation failed",
            ) from exc


@router.get("/api/privacy/users", response_model=list[UserSummary])
async def api_privacy_users():
    users = await list_users()
    return users


@router.get("/api/privacy/users/{username}/export")
async def api_export_user(username: str):
    normalized = _validated_username(username)
    try:
        payload = await export_user_data(normalized)
    except Exception as exc:
        logger.error("User export failed")
        raise HTTPException(status_code=503, detail="Export failed") from exc
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": 'attachment; filename="navidrome-stat-export.json"'
        },
    )


@router.post("/api/privacy/users/{username}/import", response_model=UserImportResponse)
async def api_import_user(username: str, body: UserImportRequest):
    normalized = _validated_username(username)
    try:
        result = await stats_service.import_user(
            normalized,
            body.payload,
            merge=body.merge,
        )
    except ValueError:
        # Validation failures propagate to the shared 422 handler.
        raise
    except Exception as exc:
        logger.error("User import failed")
        raise HTTPException(status_code=503, detail="Import failed") from exc
    return UserImportResponse(
        imported=result["imported"],
        attempts_imported=result.get("attempts_imported", 0),
        inserted=result.get(
            "inserted",
            result["imported"] + result.get("attempts_imported", 0),
        ),
        skipped=result.get("skipped", 0),
        conflicts=result.get("conflicts", 0),
        merge=body.merge,
    )


@router.get(
    "/api/privacy/users/{username}/delete/preview",
    response_model=UserDeletePreviewResponse,
)
async def api_delete_user_preview(username: str):
    return await preview_delete_user(_validated_username(username))


@router.post("/api/privacy/users/{username}/delete", response_model=UserDeleteResponse)
async def api_delete_user(username: str, body: ConfirmRequest):
    normalized = _validated_username(username)
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required to delete data")
    try:
        result = await stats_service.delete_user(normalized)
        return result
    except Exception as exc:
        logger.error("User delete failed")
        raise HTTPException(status_code=503, detail="Delete failed") from exc
