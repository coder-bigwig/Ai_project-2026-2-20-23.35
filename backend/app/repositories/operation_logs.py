from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import OperationLogORM


class OperationLogRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, payload: dict[str, Any]) -> OperationLogORM:
        record = OperationLogORM(**payload)
        self.db.add(record)
        return record

    async def get(self, log_id: str) -> OperationLogORM | None:
        if not log_id:
            return None
        return await self.db.get(OperationLogORM, log_id)

    async def list_recent(self, limit: int = 200) -> Sequence[OperationLogORM]:
        safe_limit = max(1, min(int(limit or 200), 1000))
        stmt = select(OperationLogORM).order_by(desc(OperationLogORM.created_at)).limit(safe_limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> Sequence[OperationLogORM]:
        result = await self.db.execute(select(OperationLogORM).order_by(desc(OperationLogORM.created_at)))
        return list(result.scalars().all())

    async def count(self) -> int:
        stmt = select(func.count()).select_from(OperationLogORM)
        value = await self.db.scalar(stmt)
        return int(value or 0)

    async def delete_except_recent(self, keep_recent: int) -> int:
        safe_keep = max(0, min(int(keep_recent or 0), 1000))
        rows = await self.list_all()
        if safe_keep == 0:
            target_ids = [item.id for item in rows]
        else:
            target_ids = [item.id for item in rows[safe_keep:]]

        if not target_ids:
            return 0
        await self.db.execute(delete(OperationLogORM).where(OperationLogORM.id.in_(target_ids)))
        return len(target_ids)

    async def append(
        self,
        *,
        log_id: str,
        operator: str,
        action: str,
        target: str,
        detail: str = "",
        success: bool = True,
        created_at: datetime | None = None,
    ) -> OperationLogORM:
        payload = {
            "id": log_id,
            "operator": operator,
            "action": action,
            "target": target,
            "detail": detail,
            "success": bool(success),
            "created_at": created_at or datetime.now(),
        }
        return await self.create(payload)
