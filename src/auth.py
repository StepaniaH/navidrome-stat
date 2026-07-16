import hashlib
import hmac
import os
import secrets
from typing import Optional

from fastapi import HTTPException, Request

SESSION_COOKIE_NAME = "stats_session"
SESSION_SALT = b"navidrome-stat-session-v1"


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
