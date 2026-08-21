import json

import pytest

from src.privacy_ops import IMPORT_MAX_PAYLOAD_BYTES
from src.request_limits import (
    IMPORT_TOO_LARGE_DETAIL,
    declared_content_length_exceeds,
    is_privacy_import_request,
    read_http_body_limited,
    replay_body,
)


def test_is_privacy_import_request_matches_user_import_only():
    assert is_privacy_import_request("POST", "/api/privacy/users/synthetic-user/import")
    assert not is_privacy_import_request("GET", "/api/privacy/users/synthetic-user/import")
    assert not is_privacy_import_request("POST", "/api/privacy/users/synthetic-user/export")
    assert not is_privacy_import_request("POST", "/api/privacy/retention/apply")


def test_declared_content_length_exceeds_limit_and_invalid_values():
    limit = 10
    assert declared_content_length_exceeds([(b"content-length", b"11")], limit)
    assert not declared_content_length_exceeds([(b"content-length", b"10")], limit)
    assert declared_content_length_exceeds([(b"Content-Length", b"abc")], limit)
    assert not declared_content_length_exceeds([(b"host", b"test")], limit)


@pytest.mark.asyncio
async def test_read_http_body_limited_joins_chunks_under_limit():
    messages = [
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.request", "body": b"def", "more_body": False},
    ]

    async def receive():
        return messages.pop(0)

    body = await read_http_body_limited(receive, 10)
    assert body == b"abcdef"
    assert messages == []


@pytest.mark.asyncio
async def test_read_http_body_limited_drains_overflow_without_returning_body():
    messages = [
        {"type": "http.request", "body": b"aaaaaa", "more_body": True},
        {"type": "http.request", "body": b"bbbbbb", "more_body": True},
        {"type": "http.request", "body": b"cccccc", "more_body": False},
    ]

    async def receive():
        return messages.pop(0)

    body = await read_http_body_limited(receive, 8)
    assert body is None
    assert messages == []


@pytest.mark.asyncio
async def test_replay_body_sends_once_then_disconnects():
    receive = replay_body(b'{"ok":true}')
    first = await receive()
    second = await receive()
    assert first == {"type": "http.request", "body": b'{"ok":true}', "more_body": False}
    assert second == {"type": "http.disconnect"}


@pytest.mark.asyncio
async def test_import_rejects_chunked_body_over_limit_without_parsing(isolated_db, monkeypatch):
    from src.database import init_db
    from src.main import app

    await init_db(isolated_db)
    called = []

    async def should_not_run(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("import_user_data must not run for oversized bodies")

    monkeypatch.setattr("src.main.import_user_data", should_not_run)

    oversized = b"{" + (b" " * (IMPORT_MAX_PAYLOAD_BYTES + 1)) + b"}"
    chunks = [oversized[i : i + 64_000] for i in range(0, len(oversized), 64_000)]
    status = {"code": None, "body": b""}

    async def receive():
        if chunks:
            chunk = chunks.pop(0)
            return {
                "type": "http.request",
                "body": chunk,
                "more_body": bool(chunks),
            }
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
        elif message["type"] == "http.response.body":
            status["body"] += message.get("body", b"")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/privacy/users/synthetic-user/import",
        "raw_path": b"/api/privacy/users/synthetic-user/import",
        "query_string": b"",
        "headers": [
            (b"host", b"test"),
            (b"content-type", b"application/json"),
        ],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    await app(scope, receive, send)

    assert status["code"] == 413
    assert json.loads(status["body"]) == {"detail": IMPORT_TOO_LARGE_DETAIL}
    assert called == []
    assert chunks == []


@pytest.mark.asyncio
async def test_import_accepts_chunked_body_under_limit(isolated_db):
    from httpx import ASGITransport, AsyncClient

    from src.database import init_db
    from src.main import app

    await init_db(isolated_db)
    payload = {
        "payload": {
            "format_version": 2,
            "username": "synthetic-user",
            "records": [],
            "attempts": [],
        },
        "merge": True,
    }
    raw = json.dumps(payload).encode("utf-8")

    async def body_iter():
        yield raw[:20]
        yield raw[20:]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/privacy/users/synthetic-user/import",
            content=body_iter(),
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 200
    assert response.json()["imported"] == 0
