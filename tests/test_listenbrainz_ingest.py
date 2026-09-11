import sqlite3
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import init_db
from src.listenbrainz_ingest import ListenBrainzIngestConfig, parse_submission
from src.main import app


def _payload(timestamp: int = 1_788_937_200) -> dict:
    return {
        "listen_type": "single",
        "payload": [{
            "listened_at": timestamp,
            "track_metadata": {
                "artist_name": "Synthetic Artist",
                "track_name": "Synthetic Song",
                "release_name": "Synthetic Album",
                "additional_info": {
                    "recording_mbid": "recording-id",
                    "release_mbid": "release-id",
                    "artist_mbids": ["artist-id"],
                    "duration_ms": 180000,
                    "submission_client": "navidrome",
                },
            },
        }],
    }


def _config() -> ListenBrainzIngestConfig:
    return ListenBrainzIngestConfig(
        token="receiver-secret",
        username="listener",
        source_id="push-source",
        source_name="Push source",
    )


def test_listenbrainz_normalization_keeps_unknown_fields_unknown():
    parsed = parse_submission(
        _payload(),
        _config(),
        now=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    event = parsed.events[0]
    assert event["track_id"] == "mbid:recording-id"
    assert event["listen_duration_sec"] is None
    assert event["duration_confidence"] == "unknown"
    assert event["is_transcoding"] is None


def test_distinct_recording_ids_do_not_share_a_deduplication_key():
    first_payload = _payload()
    second_payload = _payload()
    second_payload["payload"][0]["track_metadata"]["additional_info"][
        "recording_mbid"
    ] = "different-recording-id"

    first = parse_submission(first_payload, _config()).events[0]
    second = parse_submission(second_payload, _config()).events[0]

    assert first["external_event_key"] != second["external_event_key"]


def test_playing_now_is_validated_but_not_persisted():
    payload = _payload()
    payload["listen_type"] = "playing_now"
    payload["payload"][0].pop("listened_at")
    parsed = parse_submission(payload, _config())
    assert parsed.listen_type == "playing_now"
    assert parsed.events == ()


@pytest.mark.asyncio
async def test_receiver_authenticates_and_deduplicates_retries(isolated_db, monkeypatch):
    await init_db(isolated_db)
    monkeypatch.setenv("LISTENBRAINZ_INGEST_TOKEN", "receiver-secret")
    monkeypatch.setenv("LISTENBRAINZ_INGEST_USERNAME", "listener")
    monkeypatch.setenv("LISTENBRAINZ_INGEST_SOURCE_ID", "push-source")
    headers = {"Authorization": "Token receiver-secret"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        first = await ac.post("/1/submit-listens", headers=headers, json=_payload())
        retry = await ac.post("/1/submit-listens", headers=headers, json=_payload())
        validation = await ac.get("/1/validate-token", headers=headers)

    assert first.status_code == 200
    assert first.json()["inserted"] == 1
    assert retry.json()["inserted"] == 0
    assert retry.json()["duplicates"] == 1
    assert validation.json()["user_name"] == "listener"
    with sqlite3.connect(isolated_db) as db:
        row = db.execute(
            "SELECT listen_duration_sec, is_transcoding, source FROM play_history"
        ).fetchone()
    assert row == (None, None, "listenbrainz")


@pytest.mark.asyncio
async def test_receiver_rejects_invalid_token_before_reading_body(monkeypatch):
    monkeypatch.setenv("LISTENBRAINZ_INGEST_TOKEN", "receiver-secret")
    monkeypatch.setenv("LISTENBRAINZ_INGEST_USERNAME", "listener")
    body_reads = 0

    async def body_iter():
        nonlocal body_reads
        body_reads += 1
        yield b"{}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/1/submit-listens",
            headers={"Authorization": "Token wrong"},
            content=body_iter(),
        )
    assert response.status_code == 401
    assert body_reads == 0


@pytest.mark.asyncio
async def test_validate_token_does_not_accept_credentials_in_the_url(monkeypatch):
    monkeypatch.setenv("LISTENBRAINZ_INGEST_TOKEN", "receiver-secret")
    monkeypatch.setenv("LISTENBRAINZ_INGEST_USERNAME", "listener")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/1/validate-token?token=receiver-secret")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_receiver_limits_chunked_request_bodies(monkeypatch):
    import src.routes.listenbrainz as receiver

    monkeypatch.setenv("LISTENBRAINZ_INGEST_TOKEN", "receiver-secret")
    monkeypatch.setenv("LISTENBRAINZ_INGEST_USERNAME", "listener")
    monkeypatch.setattr(receiver, "LISTENBRAINZ_MAX_PAYLOAD_BYTES", 5)

    async def chunks():
        yield b'{"a"'
        yield b': 1}'

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/1/submit-listens",
            headers={"Authorization": "Token receiver-secret"},
            content=chunks(),
        )

    assert response.status_code == 413
