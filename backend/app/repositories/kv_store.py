from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AppKVStoreORM


class KVStoreRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, key: str) -> AppKVStoreORM | None:
        if not key:
            return None
        return await self.db.get(AppKVStoreORM, key)

    async def upsert(self, key: str, value_json: dict[str, Any]) -> AppKVStoreORM:
        if not key:
            raise ValueError("kv key is required")

        payload = value_json or {}
        stmt = (
            insert(AppKVStoreORM)
            .values(key=key, value_json=payload)
            .on_conflict_do_update(
                index_elements=[AppKVStoreORM.key],
                set_={
                    "value_json": payload,
                    "updated_at": func.now(),
                },
            )
            .returning(AppKVStoreORM)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def list_all(self) -> list[AppKVStoreORM]:
        result = await self.db.execute(select(AppKVStoreORM))
        return list(result.scalars().all())

    async def list_by_prefix(self, prefix: str) -> list[AppKVStoreORM]:
        if not prefix:
            return []
        escaped_prefix = (
            prefix.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        result = await self.db.execute(
            select(AppKVStoreORM).where(AppKVStoreORM.key.like(f"{escaped_prefix}%", escape="\\"))
        )
        return list(result.scalars().all())

