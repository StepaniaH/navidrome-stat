"""Admin-only endpoints for offline Ed25519 Supporter Key management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from src.schemas import (
    SupporterEnvelopeResponse,
    SupporterPreferencesUpdate,
)
from src.supporter import (
    clear_supporter_key,
    save_supporter_key,
    save_supporter_show_header,
    settings_supporter_document,
    validate_supporter_key,
)

router = APIRouter()


@router.get("/api/supporter", response_model=SupporterEnvelopeResponse)
async def get_supporter():
    """Return masked offline Supporter Key status for administrators."""
    return {"supporter": await settings_supporter_document()}


@router.put("/api/supporter-key", response_model=SupporterEnvelopeResponse)
async def put_supporter_key(body: Any = Body(default=None)):
    """Verify an NS1 Supporter Key offline and persist it encrypted at rest."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="supporter_key_format")
    raw_key = body.get("key")
    payload, err = validate_supporter_key(raw_key)
    if payload is None:
        raise HTTPException(status_code=400, detail=err or "supporter_key_invalid")
    await save_supporter_key(str(raw_key).strip())
    return {"supporter": await settings_supporter_document()}


@router.delete("/api/supporter-key", response_model=SupporterEnvelopeResponse)
async def delete_supporter_key():
    """Remove any saved Supporter Key from the database."""
    await clear_supporter_key()
    return {"supporter": await settings_supporter_document()}


@router.patch("/api/supporter/preferences", response_model=SupporterEnvelopeResponse)
async def patch_supporter_preferences(body: SupporterPreferencesUpdate):
    """Toggle header badge and Listening Review seal display."""
    await save_supporter_show_header(body.show_in_header)
    return {"supporter": await settings_supporter_document()}
