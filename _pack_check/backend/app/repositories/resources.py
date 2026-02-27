from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ResourceORM


class ResourceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, payload: dict[str, Any]) -> ResourceORM:
        record = ResourceORM(**payload)
        self.db.add(record)
        return record

    async def get(self, resource_id: str) -> ResourceORM | None:
        if not resource_id:
            return None
        return await self.db.get(ResourceORM, resource_id)

    async def list_all(self) -> Sequence[ResourceORM]:
        result = await self.db.execute(select(ResourceORM))
        return list(result.scalars().all())

    async def update(self, record: ResourceORM, payload: dict[str, Any]) -> ResourceORM:
        for key, value in payload.items():
            setattr(record, key, value)
        return record

    async def upsert(self, payload: dict[str, Any]) -> ResourceORM:
        resource_id = str(payload.get("id") or "").strip()
        if not resource_id:
            raise ValueError("resource id is required")
        record = await self.get(resource_id)
        if record is None:
            return await self.create(payload)
        return await self.update(record, payload)

    async def delete(self, resource_id: str) -> ResourceORM | None:
        record = await self.get(resource_id)
        if record is None:
            return None
        await self.db.delete(record)
        return record

