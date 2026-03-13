from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ClassroomORM, UserORM


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, payload: dict[str, Any]) -> UserORM:
        record = UserORM(**payload)
        self.db.add(record)
        return record

    async def get_by_id(self, user_id: str) -> UserORM | None:
        if not user_id:
            return None
        return await self.db.get(UserORM, user_id)

    async def get_by_username(self, username: str) -> UserORM | None:
        if not username:
            return None
        stmt = select(UserORM).where(UserORM.username == username)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_student_by_student_id(self, student_id: str) -> UserORM | None:
        if not student_id:
            return None
        stmt = select(UserORM).where(UserORM.student_id == student_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_users(self) -> Sequence[UserORM]:
        result = await self.db.execute(select(UserORM))
        return list(result.scalars().all())

    async def list_by_role(self, role: str) -> Sequence[UserORM]:
        stmt = select(UserORM).where(UserORM.role == role)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, record: UserORM, payload: dict[str, Any]) -> UserORM:
        for key, value in payload.items():
            setattr(record, key, value)
        return record

    async def upsert(self, payload: dict[str, Any]) -> UserORM:
        username = str(payload.get("username") or "").strip()
        user_id = str(payload.get("id") or "").strip()
        if not username:
            raise ValueError("username is required")
        if not user_id:
            raise ValueError("user id is required")

        record = await self.get_by_username(username)
        if record is None:
            return await self.create(payload)
        return await self.update(record, payload)

    async def delete(self, user_id: str) -> UserORM | None:
        record = await self.get_by_id(user_id)
        if record is None:
            return None
        await self.db.delete(record)
        return record

    async def upsert_class(self, payload: dict[str, Any]) -> ClassroomORM:
        class_id = str(payload.get("id") or "").strip()
        if not class_id:
            raise ValueError("class id is required")
        record = await self.db.get(ClassroomORM, class_id)
        if record is None:
            record = ClassroomORM(**payload)
            self.db.add(record)
            return record
        for key, value in payload.items():
            setattr(record, key, value)
        return record

    async def list_classes(self) -> Sequence[ClassroomORM]:
        result = await self.db.execute(select(ClassroomORM))
        return list(result.scalars().all())

    async def list_classes_by_creator(self, created_by: str) -> Sequence[ClassroomORM]:
        stmt = select(ClassroomORM).where(ClassroomORM.created_by == created_by)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_class_by_name(self, class_name: str) -> ClassroomORM | None:
        normalized_name = str(class_name or "").strip().lower()
        if not normalized_name:
            return None
        stmt = select(ClassroomORM).where(func.lower(ClassroomORM.name) == normalized_name)
        result = await self.db.execute(stmt)
        return result.scalars().first()
