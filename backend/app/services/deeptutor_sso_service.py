"""DeepTutor SSO bridge.

Mints a `dt_token` JWT compatible with DeepTutor's built-in AUTH so portal
users land in their isolated `/app/multi-user/<user_id>/` workspace without
seeing DeepTutor's own login page.

Two responsibilities:
  1. Sign the JWT with the same secret (`DEEPTUTOR_AUTH_SECRET`) and
     algorithm (HS256) DeepTutor uses.
  2. Ensure the user is registered in DeepTutor's `users.json` so workspace
     resolution works — written via the shared docker volume mounted at
     `DEEPTUTOR_MULTI_USER_DIR`.

We deliberately write `users.json` directly rather than calling DeepTutor's
admin API: avoids bootstrap (need admin token before any user exists) and
removes a runtime dependency on DeepTutor being healthy at registration time.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEEPTUTOR_AUTH_SECRET = os.getenv("DEEPTUTOR_AUTH_SECRET", "").strip()
DEEPTUTOR_AUTH_ALGORITHM = "HS256"
DEEPTUTOR_TOKEN_EXPIRE_HOURS = int(os.getenv("DEEPTUTOR_TOKEN_EXPIRE_HOURS", "24"))
DEEPTUTOR_COOKIE_NAME = "dt_token"

# Path inside the backend container where the deeptutor-multi-user volume is
# mounted. Inside the DeepTutor container the same volume lives at
# /app/multi-user — but we keep the backend mount path separate to avoid
# colliding with anything backend-owned.
_DEFAULT_MULTI_USER_DIR = "/app/deeptutor-multi-user"
DEEPTUTOR_MULTI_USER_DIR = Path(os.getenv("DEEPTUTOR_MULTI_USER_DIR", _DEFAULT_MULTI_USER_DIR))

_USERS_FILE = DEEPTUTOR_MULTI_USER_DIR / "_system" / "auth" / "users.json"
_USERS_WRITE_LOCK = threading.Lock()


def is_enabled() -> bool:
    """SSO is only viable when both the secret and the shared dir are reachable."""
    return bool(DEEPTUTOR_AUTH_SECRET) and DEEPTUTOR_MULTI_USER_DIR.exists()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def derive_user_id(username: str) -> str:
    """Stable per-username uid; matches DeepTutor's `u_<hex>` shape."""
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return f"u_{digest[:32]}"


def _read_users() -> dict[str, Any]:
    try:
        if _USERS_FILE.exists():
            with _USERS_FILE.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read DeepTutor users.json (%s); treating as empty.", exc)
    return {}


def _atomic_write_users(users: dict[str, Any]) -> None:
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _USERS_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(users, fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, _USERS_FILE)


def ensure_user_registered(username: str, user_id: str, role: str) -> dict[str, Any]:
    """Make sure DeepTutor knows about this user; idempotent.

    `hash` is filled with a random bcrypt-shaped string. Students never use
    DeepTutor's own /login (they SSO through us), so the password is never
    used. We mark the hash with a sentinel suffix to make it visually obvious
    in the file that this account is SSO-managed.
    """
    if role not in ("admin", "user"):
        role = "user"

    with _USERS_WRITE_LOCK:
        users = _read_users()
        existing = users.get(username) or {}
        record = {
            "id": str(existing.get("id") or user_id),
            "hash": str(existing.get("hash") or _sso_managed_hash()),
            "role": role,
            "created_at": str(existing.get("created_at") or _utc_now_iso()),
            "disabled": bool(existing.get("disabled", False)),
        }
        # If uid drifted (e.g. user record predates our deterministic uid),
        # rewrite it so workspace paths line up with the JWT we're about to mint.
        record["id"] = user_id

        users[username] = record
        _atomic_write_users(users)
        return record


def _sso_managed_hash() -> str:
    # Random non-decryptable string in bcrypt's $2b$12$... shape so DeepTutor's
    # `verify_password()` always returns False if anyone tries the local /login.
    return f"$2b$12${secrets.token_urlsafe(48)[:53]}"


def mint_token(username: str, role: str, user_id: str) -> str:
    if not DEEPTUTOR_AUTH_SECRET:
        raise RuntimeError("DEEPTUTOR_AUTH_SECRET is not configured; cannot mint SSO token")
    # Import here so unit tests can import this module without python-jose installed.
    from jose import jwt  # type: ignore

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": username,
        "role": role,
        "uid": user_id,
        "iat": now,
        "exp": now + timedelta(hours=DEEPTUTOR_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, DEEPTUTOR_AUTH_SECRET, algorithm=DEEPTUTOR_AUTH_ALGORITHM)


def map_role(portal_role: Optional[str]) -> str:
    """Map portal role (admin/teacher/student) to DeepTutor role (admin/user)."""
    normalized = (portal_role or "").strip().lower()
    if normalized == "admin":
        return "admin"
    return "user"


def cookie_max_age_seconds() -> int:
    return max(60, DEEPTUTOR_TOKEN_EXPIRE_HOURS * 3600)
