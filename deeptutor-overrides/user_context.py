"""Request-scoped DeepTutor user context for local SSO overrides."""

from __future__ import annotations

from contextvars import ContextVar
import os
from pathlib import Path
import re
from typing import Any

import jwt

_current_user_id: ContextVar[str | None] = ContextVar("deeptutor_user_id", default=None)
_current_username: ContextVar[str | None] = ContextVar("deeptutor_username", default=None)

_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_DEFAULT_MULTI_USER_DIR = Path("/app/multi-user")


class UserContextError(ValueError):
    pass


def _normalize_user_id(value: Any) -> str:
    user_id = _SAFE_ID_RE.sub("_", str(value or "").strip())
    user_id = user_id.strip("._-")
    if not user_id:
        raise UserContextError("Missing uid in DeepTutor token")
    return user_id[:128]


def multi_user_root() -> Path:
    return Path(os.getenv("DEEPTUTOR_MULTI_USER_DIR", str(_DEFAULT_MULTI_USER_DIR)))


def user_root(user_id: str | None = None) -> Path:
    resolved_id = _normalize_user_id(user_id or get_current_user_id())
    return multi_user_root() / resolved_id


def chat_db_path(user_id: str | None = None) -> Path:
    root = user_root(user_id)
    root.mkdir(parents=True, exist_ok=True)
    return root / "chat_history.db"


def get_current_user_id() -> str | None:
    return _current_user_id.get()


def get_current_username() -> str | None:
    return _current_username.get()


def set_current_user(user_id: str, username: str | None = None):
    uid_token = _current_user_id.set(_normalize_user_id(user_id))
    username_token = _current_username.set(str(username or "").strip() or None)
    return uid_token, username_token


def reset_current_user(tokens) -> None:
    uid_token, username_token = tokens
    _current_user_id.reset(uid_token)
    _current_username.reset(username_token)


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def token_from_http_request(request) -> str | None:
    return _bearer_token(request.headers.get("authorization")) or request.cookies.get("dt_token")


def token_from_websocket(ws) -> str | None:
    return (
        _bearer_token(ws.headers.get("authorization"))
        or ws.cookies.get("dt_token")
        or ws.query_params.get("token")
    )


def payload_from_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    secret = os.getenv("AUTH_SECRET") or os.getenv("DEEPTUTOR_AUTH_SECRET") or ""
    if not secret:
        raise UserContextError("DeepTutor auth secret is not configured")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise UserContextError("Invalid or expired DeepTutor token") from exc
    if not isinstance(payload, dict):
        raise UserContextError("Invalid DeepTutor token payload")
    return payload


def user_from_token(token: str | None) -> tuple[str, str | None] | None:
    payload = payload_from_token(token)
    if payload is None:
        return None
    return _normalize_user_id(payload.get("uid")), str(payload.get("sub") or "").strip() or None
