"""ASGI request-body size limits for privacy import."""

from __future__ import annotations

from collections.abc import Callable

from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

IMPORT_TOO_LARGE_DETAIL = "Import payload is too large"
HeaderWrapper = Callable[[Response], Response]


def is_privacy_import_request(method: str, path: str) -> bool:
    return (
        method == "POST"
        and path.startswith("/api/privacy/users/")
        and path.endswith("/import")
    )


def declared_content_length_exceeds(
    headers: list[tuple[bytes, bytes]],
    max_bytes: int,
) -> bool:
    for name, value in headers:
        if name.lower() == b"content-length":
            try:
                return int(value) > max_bytes
            except ValueError:
                return True
    return False


async def read_http_body_limited(receive: Receive, max_bytes: int) -> bytes | None:
    """Assemble an HTTP body, returning immediately when it exceeds the limit."""
    chunks: list[bytes] = []
    total = 0
    while True:
        message = await receive()
        msg_type = message.get("type")
        if msg_type == "http.disconnect":
            return b"".join(chunks)
        if msg_type != "http.request":
            continue
        body = message.get("body", b"") or b""
        more = bool(message.get("more_body", False))
        total += len(body)
        if total > max_bytes:
            return None
        if body:
            chunks.append(body)
        if not more:
            return b"".join(chunks)


def replay_body(body: bytes) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


class PrivacyImportBodyLimitMiddleware:
    """Cap privacy-import bodies by actual received bytes, not just Content-Length."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        apply_headers: HeaderWrapper,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.apply_headers = apply_headers

    def _too_large_response(self) -> Response:
        return self.apply_headers(
            JSONResponse({"detail": IMPORT_TOO_LARGE_DETAIL}, status_code=413)
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "")
        path = scope.get("path", "")
        if not is_privacy_import_request(str(method), str(path)):
            await self.app(scope, receive, send)
            return

        if declared_content_length_exceeds(list(scope.get("headers", [])), self.max_bytes):
            await self._too_large_response()(scope, receive, send)
            return

        body = await read_http_body_limited(receive, self.max_bytes)
        if body is None:
            await self._too_large_response()(scope, receive, send)
            return

        await self.app(scope, replay_body(body), send)
