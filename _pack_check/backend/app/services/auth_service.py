from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AuthUserORM, AuthUserRole
from ..repositories.password_reset_repository import PasswordResetRepository
from ..repositories.user_repository import AuthUserRepository


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


class AuthService:
    def __init__(
        self,
        db: AsyncSession,
        password_hasher: Callable[[str], str],
    ):
        self.db = db
        self.password_hasher = password_hasher
        self.user_repo = AuthUserRepository(db)
        self.reset_repo = PasswordResetRepository(db)

    async def get_user_by_identifier(self, identifier: str) -> AuthUserORM | None:
        return await self.user_repo.get_by_login_identifier(identifier)

    async def authenticate(self, identifier: str, password: str) -> AuthUserORM | None:
        user = await self.user_repo.get_by_login_identifier(identifier)
        if user is None or not bool(user.is_active):
            return None
        expected_hash = _normalize_text(user.password_hash)
        provided_hash = _normalize_text(self.password_hasher(password or ""))
        if not expected_hash or expected_hash != provided_hash:
            return None
        return user

    async def set_password(self, user_id: str, new_password_hash: str) -> AuthUserORM | None:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            return None
        user.password_hash = _normalize_text(new_password_hash)
        user.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return user

    async def create_reset_token(self, user_id: str, ttl_minutes: int = 15) -> str:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("user not found")

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=max(1, int(ttl_minutes or 15)))
        for _ in range(3):
            token = secrets.token_urlsafe(32)
            existing = await self.reset_repo.get_by_token(token)
            if existing is not None:
                continue
            payload = {
                "id": str(uuid.uuid4()),
                "user_id": user.id,
                "token": token,
                "expires_at": expires_at,
                "used_at": None,
            }
            await self.reset_repo.create(payload)
            return token
        raise RuntimeError("failed to generate unique reset token")

    async def verify_reset_token(self, token: str) -> str | None:
        record = await self.reset_repo.verify_token(token=token)
        if record is None:
            return None
        return record.user_id

    async def consume_reset_token(self, token: str) -> bool:
        user_id = await self.reset_repo.consume_token(token=token)
        return bool(user_id)
