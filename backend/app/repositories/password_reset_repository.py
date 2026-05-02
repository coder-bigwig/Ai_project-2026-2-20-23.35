from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import PasswordResetTokenORM


class PasswordResetRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, payload: dict[str, Any]) -> PasswordResetTokenORM:
        record = PasswordResetTokenORM(**payload)
        self.db.add(record)
        await self.db.flush()
        return record

    async def get_by_token(self, token: str) -> PasswordResetTokenORM | None:
        token = str(token or "").strip()
        if not token:
            return None
        stmt = select(PasswordResetTokenORM).where(PasswordResetTokenORM.token == token)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def verify_token(self, token: str, now: datetime | None = None) -> PasswordResetTokenORM | None:
        now = now or datetime.now(timezone.utc)
        token_record = await self.get_by_token(token)
        if token_record is None:
            return None
        if token_record.used_at is not None:
            return None
        if token_record.expires_at <= now:
            return None
        return token_record

    async def consume_token(self, token: str, now: datetime | None = None) -> str | None:
        now = now or datetime.now(timezone.utc)
        token = str(token or "").strip()
        if not token:
            return None

        stmt = (
            update(PasswordResetTokenORM)
            .where(
                PasswordResetTokenORM.token == token,
                PasswordResetTokenORM.used_at.is_(None),
                PasswordResetTokenORM.expires_at > now,
            )
            .values(used_at=now)
            .returning(PasswordResetTokenORM.user_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
