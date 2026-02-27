from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AttachmentORM


class AttachmentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, payload: dict[str, Any]) -> AttachmentORM:
        record = AttachmentORM(**payload)
        self.db.add(record)
        return record

    async def get(self, attachment_id: str) -> AttachmentORM | None:
        if not attachment_id:
            return None
        return await self.db.get(AttachmentORM, attachment_id)

    async def list_all(self) -> Sequence[AttachmentORM]:
        result = await self.db.execute(select(AttachmentORM))
        return list(result.scalars().all())

    async def list_by_experiment(self, experiment_id: str) -> Sequence[AttachmentORM]:
        stmt = select(AttachmentORM).where(AttachmentORM.experiment_id == experiment_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, record: AttachmentORM, payload: dict[str, Any]) -> AttachmentORM:
        for key, value in payload.items():
            setattr(record, key, value)
        return record

    async def upsert(self, payload: dict[str, Any]) -> AttachmentORM:
        attachment_id = str(payload.get("id") or "").strip()
        if not attachment_id:
            raise ValueError("attachment id is required")
        record = await self.get(attachment_id)
        if record is None:
            return await self.create(payload)
        return await self.update(record, payload)

    async def delete(self, attachment_id: str) -> AttachmentORM | None:
        record = await self.get(attachment_id)
        if record is None:
            return None
        await self.db.delete(record)
        return record

    async def delete_many(self, attachment_ids: Sequence[str]) -> None:
        cleaned_ids = [item for item in attachment_ids if item]
        if not cleaned_ids:
            return
        await self.db.execute(delete(AttachmentORM).where(AttachmentORM.id.in_(cleaned_ids)))
