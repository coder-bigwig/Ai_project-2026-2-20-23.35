from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ResourceORM


class ResourceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def _table_schema(self) -> str:
        return str(ResourceORM.__table__.schema or "public")

    @property
    def _qualified_table_name(self) -> str:
        schema = self._table_schema
        if schema and schema != "public":
            return f'"{schema}"."resources"'
        return "resources"

    async def _ensure_course_id_column(self) -> None:
        value = await self.db.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = :table_schema
                      AND table_name = 'resources'
                      AND column_name = 'course_id'
                )
                """
            ),
            {"table_schema": self._table_schema},
        )
        if bool(value):
            return
        await self.db.execute(
            text(f"ALTER TABLE {self._qualified_table_name} ADD COLUMN IF NOT EXISTS course_id VARCHAR(64)")
        )
        await self.db.execute(
            text(
                f'CREATE INDEX IF NOT EXISTS "ix_resources_course_id_created_at" '
                f"ON {self._qualified_table_name} (course_id, created_at)"
            )
        )

    async def create(self, payload: dict[str, Any]) -> ResourceORM:
        await self._ensure_course_id_column()
        record = ResourceORM(**payload)
        self.db.add(record)
        return record

    async def get(self, resource_id: str) -> ResourceORM | None:
        if not resource_id:
            return None
        await self._ensure_course_id_column()
        return await self.db.get(ResourceORM, resource_id)

    async def list_all(self) -> Sequence[ResourceORM]:
        await self._ensure_course_id_column()
        result = await self.db.execute(select(ResourceORM))
        return list(result.scalars().all())

    async def list_platform(self) -> Sequence[ResourceORM]:
        await self._ensure_course_id_column()
        result = await self.db.execute(select(ResourceORM).where(ResourceORM.course_id.is_(None)))
        return list(result.scalars().all())

    async def list_by_course(self, course_id: str) -> Sequence[ResourceORM]:
        normalized_course_id = str(course_id or "").strip()
        if not normalized_course_id:
            return []
        await self._ensure_course_id_column()
        result = await self.db.execute(select(ResourceORM).where(ResourceORM.course_id == normalized_course_id))
        return list(result.scalars().all())

    async def count(self) -> int:
        await self._ensure_course_id_column()
        stmt = select(func.count()).select_from(ResourceORM)
        value = await self.db.scalar(stmt)
        return int(value or 0)

    async def update(self, record: ResourceORM, payload: dict[str, Any]) -> ResourceORM:
        for key, value in payload.items():
            setattr(record, key, value)
        return record

    async def upsert(self, payload: dict[str, Any]) -> ResourceORM:
        resource_id = str(payload.get("id") or "").strip()
        if not resource_id:
            raise ValueError("resource id is required")
        await self._ensure_course_id_column()
        record = await self.get(resource_id)
        if record is None:
            return await self.create(payload)
        return await self.update(record, payload)

    async def delete(self, resource_id: str) -> ResourceORM | None:
        await self._ensure_course_id_column()
        record = await self.get(resource_id)
        if record is None:
            return None
        await self.db.delete(record)
        return record
