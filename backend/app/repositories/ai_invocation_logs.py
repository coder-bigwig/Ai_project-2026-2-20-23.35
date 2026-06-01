from collections.abc import Sequence
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AIInvocationLogORM


class AIInvocationLogRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, payload: dict[str, Any]) -> AIInvocationLogORM:
        record = AIInvocationLogORM(**payload)
        self.db.add(record)
        return record

    async def list_recent(self, limit: int = 200) -> Sequence[AIInvocationLogORM]:
        safe_limit = max(1, min(int(limit or 200), 1000))
        stmt = select(AIInvocationLogORM).order_by(desc(AIInvocationLogORM.created_at)).limit(safe_limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        stmt = select(func.count()).select_from(AIInvocationLogORM)
        value = await self.db.scalar(stmt)
        return int(value or 0)
