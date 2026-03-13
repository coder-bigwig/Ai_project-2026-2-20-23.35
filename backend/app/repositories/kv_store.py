from typing import Any

from sqlalchemy import select
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

        record = await self.get(key)
        if record is None:
            record = AppKVStoreORM(key=key, value_json=value_json or {})
            self.db.add(record)
            return record

        record.value_json = value_json or {}
        return record

    async def list_all(self) -> list[AppKVStoreORM]:
        result = await self.db.execute(select(AppKVStoreORM))
        return list(result.scalars().all())

