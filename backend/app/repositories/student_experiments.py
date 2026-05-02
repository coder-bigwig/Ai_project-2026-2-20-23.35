from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import StudentExperimentORM


class StudentExperimentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, payload: dict[str, Any]) -> StudentExperimentORM:
        record = StudentExperimentORM(**payload)
        self.db.add(record)
        return record

    async def get(self, student_experiment_id: str) -> StudentExperimentORM | None:
        if not student_experiment_id:
            return None
        return await self.db.get(StudentExperimentORM, student_experiment_id)

    async def get_by_student_and_experiment(self, student_id: str, experiment_id: str) -> StudentExperimentORM | None:
        if not student_id or not experiment_id:
            return None
        stmt = select(StudentExperimentORM).where(
            StudentExperimentORM.student_id == student_id,
            StudentExperimentORM.experiment_id == experiment_id,
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_latest_by_student_and_experiment(self, student_id: str, experiment_id: str) -> StudentExperimentORM | None:
        if not student_id or not experiment_id:
            return None
        stmt = (
            select(StudentExperimentORM)
            .where(
                StudentExperimentORM.student_id == student_id,
                StudentExperimentORM.experiment_id == experiment_id,
            )
            .order_by(desc(StudentExperimentORM.start_time), desc(StudentExperimentORM.created_at))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_all(self) -> Sequence[StudentExperimentORM]:
        result = await self.db.execute(select(StudentExperimentORM))
        return list(result.scalars().all())

    async def list_by_student(self, student_id: str) -> Sequence[StudentExperimentORM]:
        stmt = select(StudentExperimentORM).where(StudentExperimentORM.student_id == student_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_experiment(self, experiment_id: str) -> Sequence[StudentExperimentORM]:
        stmt = select(StudentExperimentORM).where(StudentExperimentORM.experiment_id == experiment_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(self, record: StudentExperimentORM, payload: dict[str, Any]) -> StudentExperimentORM:
        for key, value in payload.items():
            setattr(record, key, value)
        return record

    async def upsert(self, payload: dict[str, Any]) -> StudentExperimentORM:
        student_experiment_id = str(payload.get("id") or "").strip()
        if not student_experiment_id:
            raise ValueError("student experiment id is required")
        record = await self.get(student_experiment_id)
        if record is None:
            return await self.create(payload)
        return await self.update(record, payload)

    async def delete(self, student_experiment_id: str) -> StudentExperimentORM | None:
        record = await self.get(student_experiment_id)
        if record is None:
            return None
        await self.db.delete(record)
        return record

    async def delete_by_student(self, student_id: str) -> int:
        normalized = str(student_id or "").strip()
        if not normalized:
            return 0
        result = await self.db.execute(delete(StudentExperimentORM).where(StudentExperimentORM.student_id == normalized))
        return int(result.rowcount or 0)
