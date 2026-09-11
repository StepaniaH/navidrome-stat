"""Small ListenBrainz-compatible receiver for opt-in push collection."""

import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from src.listenbrainz_ingest import (
    LISTENBRAINZ_MAX_PAYLOAD_BYTES,
    ListenBrainzIngestConfig,
    load_ingest_config,
    parse_submission,
)
from src.stats_service import stats_service

router = APIRouter()
logger = logging.getLogger(__name__)


def _configured() -> ListenBrainzIngestConfig:
    try:
        config = load_ingest_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Receiver configuration is invalid") from exc
    if config is None:
        raise HTTPException(status_code=404, detail="ListenBrainz receiver is disabled")
    return config


def _presented_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, separator, token = header.partition(" ")
    if separator and scheme.lower() == "token" and token.strip():
        return token.strip()
    return None


def _authorized(request: Request, config: ListenBrainzIngestConfig) -> bool:
    presented = _presented_token(request)
    return bool(
        presented
        and hmac.compare_digest(presented.encode("utf-8"), config.token.encode("utf-8"))
    )


async def _read_limited_body(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > LISTENBRAINZ_MAX_PAYLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Payload too large")
        body.extend(chunk)
    return bytes(body)


@router.get("/1/validate-token")
async def validate_token(request: Request):
    config = _configured()
    presented = _presented_token(request)
    if presented is None:
        raise HTTPException(status_code=400, detail="No token was sent")
    if not _authorized(request, config):
        return {"code": 200, "message": "Token invalid.", "valid": False}
    return {
        "code": 200,
        "message": "Token valid.",
        "valid": True,
        "user_name": config.username,
    }


@router.post("/1/submit-listens")
async def submit_listens(request: Request):
    config = _configured()
    if not _authorized(request, config):
        raise HTTPException(status_code=401, detail="Invalid authorization")
    content_length = request.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > LISTENBRAINZ_MAX_PAYLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Payload too large")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from None
    body = await _read_limited_body(request)
    try:
        payload = json.loads(body)
        submission = parse_submission(payload, config)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        inserted = await stats_service.record_imported_events(list(submission.events))
    except Exception as exc:
        logger.error("ListenBrainz submission persistence failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Listen persistence failed") from exc
    return {
        "status": "ok",
        "inserted": inserted,
        "duplicates": len(submission.events) - inserted,
        "playing_now_stored": False,
    }
