from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ResourceFolderORM, ResourceORM


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

    async def _has_column(self, column_name: str) -> bool:
        value = await self.db.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = :table_schema
                      AND table_name = 'resources'
                      AND column_name = :column_name
                )
                """
            ),
            {"table_schema": self._table_schema, "column_name": column_name},
        )
        return bool(value)

    async def _ensure_resource_columns(self) -> None:
        if not await self._has_column("course_id"):
            await self.db.execute(
                text(f"ALTER TABLE {self._qualified_table_name} ADD COLUMN IF NOT EXISTS course_id VARCHAR(64)")
            )
        if not await self._has_column("folder_id"):
            await self.db.execute(
                text(f"ALTER TABLE {self._qualified_table_name} ADD COLUMN IF NOT EXISTS folder_id VARCHAR(64)")
            )
        await self.db.execute(
            text(
                f'CREATE INDEX IF NOT EXISTS "ix_resources_course_id_created_at" '
                f"ON {self._qualified_table_name} (course_id, created_at)"
            )
        )
        await self.db.execute(
            text(
                f'CREATE INDEX IF NOT EXISTS "ix_resources_folder_id_created_at" '
                f"ON {self._qualified_table_name} (folder_id, created_at)"
            )
        )

    async def create(self, payload: dict[str, Any]) -> ResourceORM:
        await self._ensure_resource_columns()
        record = ResourceORM(**payload)
        self.db.add(record)
        return record

    async def get(self, resource_id: str) -> ResourceORM | None:
        if not resource_id:
            return None
        await self._ensure_resource_columns()
        return await self.db.get(ResourceORM, resource_id)

    async def list_all(self) -> Sequence[ResourceORM]:
        await self._ensure_resource_columns()
        result = await self.db.execute(select(ResourceORM))
        return list(result.scalars().all())

    async def list_platform(self) -> Sequence[ResourceORM]:
        await self._ensure_resource_columns()
        result = await self.db.execute(
            select(ResourceORM).where(ResourceORM.course_id.is_(None), ResourceORM.folder_id.is_(None))
        )
        return list(result.scalars().all())

    async def list_platform_by_owner(self, owner_username: str) -> Sequence[ResourceORM]:
        normalized_owner = str(owner_username or "").strip()
        if not normalized_owner:
            return []
        await self._ensure_resource_columns()
        result = await self.db.execute(
            select(ResourceORM).where(
                ResourceORM.course_id.is_(None),
                ResourceORM.folder_id.is_(None),
                ResourceORM.created_by == normalized_owner,
            )
        )
        return list(result.scalars().all())

    async def list_by_course(self, course_id: str) -> Sequence[ResourceORM]:
        normalized_course_id = str(course_id or "").strip()
        if not normalized_course_id:
            return []
        await self._ensure_resource_columns()
        result = await self.db.execute(select(ResourceORM).where(ResourceORM.course_id == normalized_course_id))
        return list(result.scalars().all())

    async def list_folder_resources(self) -> Sequence[ResourceORM]:
        await self._ensure_resource_columns()
        result = await self.db.execute(
            select(ResourceORM).where(ResourceORM.course_id.is_(None), ResourceORM.folder_id.is_not(None))
        )
        return list(result.scalars().all())

    async def list_by_folder(self, folder_id: str) -> Sequence[ResourceORM]:
        normalized_folder_id = str(folder_id or "").strip()
        if not normalized_folder_id:
            return []
        await self._ensure_resource_columns()
        result = await self.db.execute(
            select(ResourceORM).where(ResourceORM.course_id.is_(None), ResourceORM.folder_id == normalized_folder_id)
        )
        return list(result.scalars().all())

    async def count_by_folder(self, folder_id: str) -> int:
        normalized_folder_id = str(folder_id or "").strip()
        if not normalized_folder_id:
            return 0
        await self._ensure_resource_columns()
        stmt = select(func.count()).select_from(ResourceORM).where(
            ResourceORM.folder_id == normalized_folder_id,
        )
        value = await self.db.scalar(stmt)
        return int(value or 0)

    async def count(self) -> int:
        await self._ensure_resource_columns()
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
        await self._ensure_resource_columns()
        record = await self.get(resource_id)
        if record is None:
            return await self.create(payload)
        return await self.update(record, payload)

    async def delete(self, resource_id: str) -> ResourceORM | None:
        await self._ensure_resource_columns()
        record = await self.get(resource_id)
        if record is None:
            return None
        await self.db.delete(record)
        return record


class ResourceFolderRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def _table_schema(self) -> str:
        return str(ResourceFolderORM.__table__.schema or "public")

    @property
    def _qualified_table_name(self) -> str:
        schema = self._table_schema
        if schema and schema != "public":
            return f'"{schema}"."resource_folders"'
        return "resource_folders"

    async def _has_column(self, column_name: str) -> bool:
        value = await self.db.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = :table_schema
                      AND table_name = 'resource_folders'
                      AND column_name = :column_name
                )
                """
            ),
            {"table_schema": self._table_schema, "column_name": column_name},
        )
        return bool(value)

    async def _ensure_folder_columns(self) -> None:
        if not await self._has_column("course_id"):
            await self.db.execute(
                text(f"ALTER TABLE {self._qualified_table_name} ADD COLUMN IF NOT EXISTS course_id VARCHAR(64)")
            )
        await self.db.execute(text(f"ALTER TABLE {self._qualified_table_name} DROP CONSTRAINT IF EXISTS uq_resource_folders_owner_name"))
        await self.db.execute(
            text(
                f'CREATE UNIQUE INDEX IF NOT EXISTS "ux_resource_folders_owner_course_name_expr" '
                f"ON {self._qualified_table_name} (owner_username, COALESCE(course_id, ''), lower(name))"
            )
        )
        await self.db.execute(
            text(
                f'CREATE INDEX IF NOT EXISTS "ix_resource_folders_course_updated_at" '
                f"ON {self._qualified_table_name} (course_id, updated_at)"
            )
        )

    async def create(self, payload: dict[str, Any]) -> ResourceFolderORM:
        await self._ensure_folder_columns()
        record = ResourceFolderORM(**payload)
        self.db.add(record)
        return record

    async def get(self, folder_id: str) -> ResourceFolderORM | None:
        if not folder_id:
            return None
        await self._ensure_folder_columns()
        return await self.db.get(ResourceFolderORM, folder_id)

    async def list_all(self) -> Sequence[ResourceFolderORM]:
        await self._ensure_folder_columns()
        result = await self.db.execute(select(ResourceFolderORM))
        return list(result.scalars().all())

    async def list_by_owner(self, owner_username: str) -> Sequence[ResourceFolderORM]:
        normalized_owner = str(owner_username or "").strip()
        if not normalized_owner:
            return []
        await self._ensure_folder_columns()
        stmt = select(ResourceFolderORM).where(ResourceFolderORM.owner_username == normalized_owner)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_platform_all(self) -> Sequence[ResourceFolderORM]:
        await self._ensure_folder_columns()
        result = await self.db.execute(select(ResourceFolderORM).where(ResourceFolderORM.course_id.is_(None)))
        return list(result.scalars().all())

    async def list_platform_by_owner(self, owner_username: str) -> Sequence[ResourceFolderORM]:
        normalized_owner = str(owner_username or "").strip()
        if not normalized_owner:
            return []
        await self._ensure_folder_columns()
        stmt = select(ResourceFolderORM).where(
            ResourceFolderORM.owner_username == normalized_owner,
            ResourceFolderORM.course_id.is_(None),
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_course(self, course_id: str) -> Sequence[ResourceFolderORM]:
        normalized_course_id = str(course_id or "").strip()
        if not normalized_course_id:
            return []
        await self._ensure_folder_columns()
        stmt = select(ResourceFolderORM).where(ResourceFolderORM.course_id == normalized_course_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def find_by_owner_and_name(
        self,
        owner_username: str,
        name: str,
        course_id: str | None = None,
    ) -> ResourceFolderORM | None:
        normalized_owner = str(owner_username or "").strip()
        normalized_name = str(name or "").strip().lower()
        if not normalized_owner or not normalized_name:
            return None
        normalized_course_id = str(course_id or "").strip()
        await self._ensure_folder_columns()
        stmt = select(ResourceFolderORM).where(
            ResourceFolderORM.owner_username == normalized_owner,
            func.lower(ResourceFolderORM.name) == normalized_name,
        )
        if normalized_course_id:
            stmt = stmt.where(ResourceFolderORM.course_id == normalized_course_id)
        else:
            stmt = stmt.where(ResourceFolderORM.course_id.is_(None))
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def update(self, record: ResourceFolderORM, payload: dict[str, Any]) -> ResourceFolderORM:
        for key, value in payload.items():
            setattr(record, key, value)
        return record

    async def delete(self, folder_id: str) -> ResourceFolderORM | None:
        record = await self.get(folder_id)
        if record is None:
            return None
        await self.db.delete(record)
        return record
