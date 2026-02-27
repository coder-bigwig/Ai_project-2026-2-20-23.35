from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AuthUserORM


class AuthUserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @classmethod
    def _normalize_email(cls, value: Any) -> str:
        return cls._normalize_text(value).lower()

    async def get_by_id(self, user_id: str) -> AuthUserORM | None:
        user_id = self._normalize_text(user_id)
        if not user_id:
            return None
        return await self.db.get(AuthUserORM, user_id)

    async def get_by_email(self, email: str) -> AuthUserORM | None:
        email = self._normalize_email(email)
        if not email:
            return None
        stmt = select(AuthUserORM).where(func.lower(AuthUserORM.email) == email)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_by_username(self, username: str) -> AuthUserORM | None:
        username = self._normalize_text(username).lower()
        if not username:
            return None
        stmt = select(AuthUserORM).where(func.lower(AuthUserORM.username) == username)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_by_login_identifier(self, identifier: str) -> AuthUserORM | None:
        normalized = self._normalize_text(identifier).lower()
        if not normalized:
            return None

        stmt = select(AuthUserORM).where(
            (func.lower(AuthUserORM.email) == normalized) | (func.lower(AuthUserORM.username) == normalized)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def upsert_by_email(self, payload: dict[str, Any]) -> tuple[AuthUserORM, bool]:
        email = self._normalize_email(payload.get("email"))
        if not email:
            raise ValueError("email is required")

        record = await self.get_by_email(email)
        created = record is None
        if record is None:
            record = AuthUserORM(
                id=self._normalize_text(payload.get("id")) or str(uuid.uuid4()),
                email=email,
                username=self._normalize_text(payload.get("username")) or None,
                role=payload.get("role") or "student",
                password_hash=self._normalize_text(payload.get("password_hash")),
                is_active=bool(payload.get("is_active", True)),
                created_at=payload.get("created_at") or datetime.now(),
                updated_at=payload.get("updated_at") or datetime.now(),
            )
            self.db.add(record)
            return record, created

        for key, value in payload.items():
            if key == "email":
                setattr(record, key, email)
                continue
            if key == "username":
                value = self._normalize_text(value) or None
            setattr(record, key, value)
        return record, created

    async def list_all(self) -> list[AuthUserORM]:
        result = await self.db.execute(select(AuthUserORM))
        return list(result.scalars().all())

    async def list_by_role(self, role: str) -> list[AuthUserORM]:
        normalized = self._normalize_text(role).lower()
        if not normalized:
            return []
        stmt = select(AuthUserORM).where(AuthUserORM.role == normalized)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_username(self, username: str) -> bool:
        record = await self.get_by_username(username)
        if record is None:
            return False
        await self.db.delete(record)
        return True
