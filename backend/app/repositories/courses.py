import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import CourseORM


class CourseRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def _table_schema(self) -> str:
        return str(CourseORM.__table__.schema or "public")

    @property
    def _qualified_table_name(self) -> str:
        schema = self._table_schema
        if schema and schema != "public":
            return f'"{schema}"."courses"'
        return "courses"

    async def _has_db_column(self, table_name: str, column_name: str) -> bool:
        stmt = text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = :table_schema
                  AND table_name = :table_name
                  AND column_name = :column_name
            )
            """
        )
        value = await self.db.scalar(
            stmt,
            {
                "table_schema": self._table_schema,
                "table_name": table_name,
                "column_name": column_name,
            },
        )
        return bool(value)

    async def create(self, payload: dict[str, Any]) -> CourseORM:
        # Compatibility path: some existing deployments still have a legacy
        # non-null `course_code` column in `courses` that is not mapped by the
        # current ORM model. Insert it explicitly so old volumes keep working.
        if await self._has_db_column("courses", "course_code"):
            course_id = str(payload.get("id") or "").strip() or str(uuid.uuid4())
            created_at = payload.get("created_at") or datetime.now()
            updated_at = payload.get("updated_at") or created_at
            params = {
                "id": course_id,
                "name": str(payload.get("name") or "").strip(),
                "description": str(payload.get("description") or ""),
                "created_by": str(payload.get("created_by") or "").strip(),
                "created_at": created_at,
                "updated_at": updated_at,
                "version": int(payload.get("version") or 1),
                "course_code": str(payload.get("course_code") or "").strip() or f"C{uuid.uuid4().hex[:15].upper()}",
            }
            await self.db.execute(
                text(
                    f"""
                    INSERT INTO {self._qualified_table_name}
                    (id, name, description, created_by, created_at, updated_at, version, course_code)
                    VALUES
                    (:id, :name, :description, :created_by, :created_at, :updated_at, :version, :course_code)
                    """
                ),
                params,
            )
            record = await self.get(course_id)
            if record is None:
                raise RuntimeError("course insert succeeded but row reload failed")
            return record

        record = CourseORM(**payload)
        self.db.add(record)
        return record

    async def get(self, course_id: str) -> CourseORM | None:
        if not course_id:
            return None
        return await self.db.get(CourseORM, course_id)

    async def list_all(self) -> Sequence[CourseORM]:
        result = await self.db.execute(select(CourseORM))
        return list(result.scalars().all())

    async def count(self) -> int:
        stmt = select(func.count()).select_from(CourseORM)
        value = await self.db.scalar(stmt)
        return int(value or 0)

    async def list_by_creator(self, created_by: str) -> Sequence[CourseORM]:
        stmt = select(CourseORM).where(CourseORM.created_by == created_by)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def find_by_teacher_and_name(self, teacher_username: str, course_name: str) -> CourseORM | None:
        normalized_name = (course_name or "").strip().lower()
        if not teacher_username or not normalized_name:
            return None
        stmt = select(CourseORM).where(
            CourseORM.created_by == teacher_username,
            func.lower(CourseORM.name) == normalized_name,
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def update(self, record: CourseORM, payload: dict[str, Any]) -> CourseORM:
        for key, value in payload.items():
            setattr(record, key, value)
        return record

    async def upsert(self, payload: dict[str, Any]) -> CourseORM:
        course_id = str(payload.get("id") or "").strip()
        if not course_id:
            raise ValueError("course id is required")

        record = await self.get(course_id)
        if record is None:
            return await self.create(payload)
        return await self.update(record, payload)

    async def touch(self, course_id: str, updated_at: datetime) -> CourseORM | None:
        record = await self.get(course_id)
        if record is None:
            return None
        record.updated_at = updated_at
        return record

    async def delete(self, course_id: str) -> CourseORM | None:
        record = await self.get(course_id)
        if record is None:
            return None
        await self.db.delete(record)
        return record
