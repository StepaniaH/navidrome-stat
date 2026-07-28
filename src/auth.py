import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException, Request

SESSION_COOKIE_NAME = "stats_session"
SESSION_SALT = b"navidrome-stat-session-v1"
_LOGIN_KEY_SALT = secrets.token_bytes(32)


def get_stats_api_token() -> Optional[str]:
    token = os.getenv("STATS_API_TOKEN")
    if token is None:
        return None
    token = token.strip()
    return token or None


def is_auth_enabled() -> bool:
    return get_stats_api_token() is not None


def _session_value(token: str) -> str:
    return hmac.new(token.encode("utf-8"), SESSION_SALT, hashlib.sha256).hexdigest()


def is_authorized(request: Request) -> bool:
    token = get_stats_api_token()
    if token is None:
        return True

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        presented = auth_header[7:].strip()
        if secrets.compare_digest(presented, token):
            return True

    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie and secrets.compare_digest(cookie, _session_value(token)):
        return True

    return False


def require_stats_access(request: Request) -> None:
    if is_authorized(request):
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


def verify_login_token(presented: str) -> bool:
    token = get_stats_api_token()
    if token is None:
        return False
    return secrets.compare_digest(presented, token)


def session_cookie_value() -> str:
    token = get_stats_api_token()
    if token is None:
        raise RuntimeError("Session cookie requires STATS_API_TOKEN")
    return _session_value(token)


def secure_session_cookie_enabled() -> bool:
    return os.getenv("SESSION_COOKIE_SECURE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class LoginRateLimiter:
    """Small process-local limiter that never stores raw client addresses."""

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
