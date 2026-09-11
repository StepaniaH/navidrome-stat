import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Literal, Optional

from fastapi import Request

SESSION_COOKIE_NAME = "stats_session"
SESSION_SALT = b"navidrome-stat-session-v1"
_LOGIN_KEY_SALT = secrets.token_bytes(32)
AccessLevel = Literal["admin", "viewer"]


@dataclass(frozen=True, slots=True)
class AccessContext:
    """Authorization result and any backend-enforced statistics scope."""

    level: AccessLevel
    source_id: str | None = None
    username: str | None = None


_current_access: ContextVar[AccessContext | None] = ContextVar(
    "current_stats_access",
    default=None,
)


def get_stats_api_token() -> Optional[str]:
    token = os.getenv("STATS_API_TOKEN")
    if token is None:
        return None
    token = token.strip()
    return token or None


def get_stats_read_only_token() -> Optional[str]:
    token = os.getenv("STATS_READ_ONLY_TOKEN")
    if token is None:
        return None
    token = token.strip()
    return token or None


def _scope_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def read_only_access_scope() -> tuple[str | None, str | None]:
    """Return the optional fixed server and user scope for viewer sessions."""

    return (
        _scope_value("STATS_READ_ONLY_SOURCE_ID"),
        _scope_value("STATS_READ_ONLY_USERNAME"),
    )


def is_auth_enabled() -> bool:
    return get_stats_api_token() is not None or get_stats_read_only_token() is not None


def validate_auth_configuration(ingest_token: str | None = None) -> None:
    """Reject credentials that would grant more than one access level."""

    configured = [
        ("STATS_API_TOKEN", get_stats_api_token()),
        ("STATS_READ_ONLY_TOKEN", get_stats_read_only_token()),
        ("LISTENBRAINZ_INGEST_TOKEN", ingest_token),
    ]
    for index, (left_name, left_value) in enumerate(configured):
        if left_value is None:
            continue
        for right_name, right_value in configured[index + 1 :]:
            if right_value is not None and _constant_time_equal(left_value, right_value):
                raise RuntimeError(f"{left_name} and {right_name} must use different values")


def _session_value(token: str, level: AccessLevel = "admin") -> str:
    # Preserve the pre-viewer admin cookie signature so upgrades do not force
    # every administrator to sign in again. Viewer cookies use a distinct salt.
    message = SESSION_SALT if level == "admin" else SESSION_SALT + b":viewer"
    return hmac.new(token.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _constant_time_equal(presented: str, expected: str) -> bool:
    """Compare UTF-8 bytes so non-ASCII input cannot raise TypeError."""
    if not isinstance(presented, str) or not isinstance(expected, str):
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def _presented_bearer_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    scheme, separator, remainder = auth_header.partition(" ")
    if separator != " " or scheme.lower() != "bearer":
        return None
    presented = remainder.strip()
    return presented or None


def session_cookie_params() -> dict:
    """Return attributes shared by cookie creation and deletion."""
    return {
        "path": "/",
        "httponly": True,
        "samesite": "lax",
        "secure": secure_session_cookie_enabled(),
    }


def authorization_context(request: Request) -> AccessContext | None:
    """Resolve an admin or viewer bearer/cookie credential."""

    admin_token = get_stats_api_token()
    viewer_token = get_stats_read_only_token()
    if admin_token is None and viewer_token is None:
        return AccessContext(level="admin")
    presented = _presented_bearer_token(request)
    if presented is not None:
        if admin_token is not None and _constant_time_equal(presented, admin_token):
            return AccessContext(level="admin")
        if viewer_token is not None and _constant_time_equal(presented, viewer_token):
            source_id, username = read_only_access_scope()
            return AccessContext(
                level="viewer",
                source_id=source_id,
                username=username,
            )

    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie:
        if admin_token is not None and _constant_time_equal(
            cookie,
            _session_value(admin_token, "admin"),
        ):
            return AccessContext(level="admin")
        if viewer_token is not None and _constant_time_equal(
            cookie,
            _session_value(viewer_token, "viewer"),
        ):
            source_id, username = read_only_access_scope()
            return AccessContext(
                level="viewer",
                source_id=source_id,
                username=username,
            )

    return None


def is_authorized(request: Request) -> bool:
    return authorization_context(request) is not None


def verify_login_access(presented: str) -> AccessContext | None:
    """Resolve a login token without retaining the presented secret."""

    admin_token = get_stats_api_token()
    if admin_token is not None and _constant_time_equal(presented, admin_token):
        return AccessContext(level="admin")
    viewer_token = get_stats_read_only_token()
    if viewer_token is not None and _constant_time_equal(presented, viewer_token):
        source_id, username = read_only_access_scope()
        return AccessContext(
            level="viewer",
            source_id=source_id,
            username=username,
        )
    return None


def verify_login_token(presented: str) -> bool:
    return verify_login_access(presented) is not None


def session_cookie_value(level: AccessLevel = "admin") -> str:
    token = get_stats_api_token() if level == "admin" else get_stats_read_only_token()
    if token is None:
        raise RuntimeError(f"Session cookie requires a configured {level} token")
    return _session_value(token, level)


def bind_access_context(context: AccessContext) -> Token:
    """Bind request access so cached result adapters can redact scope metadata."""

    return _current_access.set(context)


def reset_access_context(token: Token) -> None:
    _current_access.reset(token)


def current_access_context() -> AccessContext:
    return _current_access.get() or AccessContext(level="admin")


def enforce_stats_scope(
    source_id: str | None,
    username: str | None,
) -> tuple[str | None, str | None]:
    """Apply viewer scope to a body-based statistics request."""

    access = current_access_context()
    if access.level != "viewer":
        return source_id, username
    if access.source_id is not None and source_id not in (None, access.source_id):
        raise PermissionError("source scope mismatch")
    if access.username is not None and username not in (None, access.username):
        raise PermissionError("user scope mismatch")
    return access.source_id or source_id, access.username or username


def secure_session_cookie_enabled() -> bool:
    return os.getenv("SESSION_COOKIE_SECURE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class LoginRateLimiter:
    """Process-local limiter keyed by HMAC-derived client identifiers."""

    def __init__(self, max_attempts: int = 5, window_sec: int = 60):
        self.max_attempts = max_attempts
        self.window_sec = window_sec
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    def _key(request: Request) -> str:
        host = request.client.host if request.client else "unknown"
        return hmac.new(_LOGIN_KEY_SALT, host.encode("utf-8"), hashlib.sha256).hexdigest()

    def check(self, request: Request) -> int | None:
        now = time.monotonic()
        attempts = self._attempts[self._key(request)]
        while attempts and now - attempts[0] >= self.window_sec:
            attempts.popleft()
        if len(attempts) < self.max_attempts:
            return None
        return max(1, int(self.window_sec - (now - attempts[0])))

    def record_failure(self, request: Request) -> None:
        self._attempts[self._key(request)].append(time.monotonic())

    def clear(self, request: Request) -> None:
        self._attempts.pop(self._key(request), None)

    def reset(self) -> None:
        self._attempts.clear()


login_rate_limiter = LoginRateLimiter()
