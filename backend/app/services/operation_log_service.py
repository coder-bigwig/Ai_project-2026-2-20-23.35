from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories import OperationLogRepository
from .identity_service import normalize_text


async def append_operation_log(
    db: AsyncSession,
    *,
    operator: str,
    action: str,
    target: str,
    detail: str = "",
    success: bool = True,
) -> None:
    repo = OperationLogRepository(db)
    await repo.append(
        log_id=str(uuid.uuid4()),
        operator=normalize_text(operator) or "unknown",
        action=normalize_text(action) or "unknown",
        target=normalize_text(target) or "-",
        detail=normalize_text(detail)[:800],
        success=bool(success),
        created_at=datetime.now(),
    )

