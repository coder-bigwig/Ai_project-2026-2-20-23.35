from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ExperimentORM


class ExperimentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, payload: dict[str, Any]) -> ExperimentORM:
        record = ExperimentORM(**payload)
        self.db.add(record)
        return record

    async def get(self, experiment_id: str) -> ExperimentORM | None:
        if not experiment_id:
            return None
        return await self.db.get(ExperimentORM, experiment_id)

    async def list_all(self) -> Sequence[ExperimentORM]:
        result = await self.db.execute(select(ExperimentORM))
        return list(result.scalars().all())

    async def list_by_course_ids(self, course_ids: Sequence[str]) -> Sequence[ExperimentORM]:
        ids = [item for item in course_ids if item]
        if not ids:
            return []
        stmt = select(ExperimentORM).where(ExperimentORM.course_id.in_(ids))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_creator(self, created_by: str) -> Sequence[ExperimentORM]:
        stmt = select(ExperimentORM).where(ExperimentORM.created_by == created_by)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, record: ExperimentORM, payload: dict[str, Any]) -> ExperimentORM:
        for key, value in payload.items():
            setattr(record, key, value)
        return record

    async def upsert(self, payload: dict[str, Any]) -> ExperimentORM:
        experiment_id = str(payload.get("id") or "").strip()
        if not experiment_id:
            raise ValueError("experiment id is required")
        record = await self.get(experiment_id)
        if record is None:
            return await self.create(payload)
        return await self.update(record, payload)

    async def delete(self, experiment_id: str) -> ExperimentORM | None:
        record = await self.get(experiment_id)
        if record is None:
            return None
        await self.db.delete(record)
        return record
