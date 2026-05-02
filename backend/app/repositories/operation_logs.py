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

    @staticmethod
    def _apply_period_filters(stmt, *, start_at: datetime | None, end_at: datetime | None):
        if start_at is not None:
            stmt = stmt.where(OperationLogORM.created_at >= start_at)
        if end_at is not None:
            stmt = stmt.where(OperationLogORM.created_at < end_at)
        return stmt

    async def latest_created_at(self) -> datetime | None:
        stmt = select(func.max(OperationLogORM.created_at))
        return await self.db.scalar(stmt)

    async def count_grouped_by_action(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> dict[str, int]:
        stmt = select(OperationLogORM.action, func.count()).group_by(OperationLogORM.action)
        stmt = self._apply_period_filters(stmt, start_at=start_at, end_at=end_at)
        result = await self.db.execute(stmt)
        return {str(action or "unknown"): int(count or 0) for action, count in result.all()}

    async def count_grouped_by_success(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> dict[str, int]:
        stmt = select(OperationLogORM.success, func.count()).group_by(OperationLogORM.success)
        stmt = self._apply_period_filters(stmt, start_at=start_at, end_at=end_at)
        result = await self.db.execute(stmt)
        return {
            "true" if bool(success) else "false": int(count or 0)
            for success, count in result.all()
        }

    async def count_distinct_operators(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> int:
        stmt = select(func.count(func.distinct(OperationLogORM.operator))).where(
            OperationLogORM.operator.is_not(None),
            OperationLogORM.operator != "",
        )
        stmt = self._apply_period_filters(stmt, start_at=start_at, end_at=end_at)
        value = await self.db.scalar(stmt)
        return int(value or 0)

    async def count_in_period(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(OperationLogORM)
        stmt = self._apply_period_filters(stmt, start_at=start_at, end_at=end_at)
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
