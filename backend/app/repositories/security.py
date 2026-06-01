from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import PasswordHashORM, SecurityQuestionORM


class SecurityQuestionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_username(self, username: str) -> SecurityQuestionORM | None:
        if not username:
            return None
        stmt = select(SecurityQuestionORM).where(SecurityQuestionORM.username == username)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def upsert(self, payload: dict[str, Any]) -> SecurityQuestionORM:
        username = str(payload.get("username") or "").strip()
        if not username:
            raise ValueError("username is required")

        record = await self.get_by_username(username)
        if record is None:
            record = SecurityQuestionORM(**payload)
            self.db.add(record)
            return record

        for key, value in payload.items():
            setattr(record, key, value)
        return record


class PasswordHashRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_username(self, username: str) -> PasswordHashORM | None:
        if not username:
            return None
        stmt = select(PasswordHashORM).where(PasswordHashORM.username == username)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def upsert(self, payload: dict[str, Any]) -> PasswordHashORM:
        username = str(payload.get("username") or "").strip()
        if not username:
            raise ValueError("username is required")
        record = await self.get_by_username(username)
        if record is None:
            record = PasswordHashORM(**payload)
            self.db.add(record)
            return record
        for key, value in payload.items():
            setattr(record, key, value)
        return record

    async def delete_by_username(self, username: str) -> bool:
        record = await self.get_by_username(username)
        if record is None:
            return False
        await self.db.delete(record)
        return True
