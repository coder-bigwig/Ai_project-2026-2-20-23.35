from __future__ import annotations

import uuid
from datetime import datetime
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import ADMIN_ACCOUNTS, DEFAULT_PASSWORD, TEACHER_ACCOUNTS
from ..repositories.user_repository import AuthUserRepository


async def ensure_default_auth_accounts(
    db: AsyncSession,
    *,
    password_hasher: Callable[[str], str],
) -> dict[str, int]:
    repo = AuthUserRepository(db)
    default_hash = password_hasher(DEFAULT_PASSWORD)
    created_count = 0
    updated_count = 0

    async def upsert_user(username: str, role: str) -> None:
        nonlocal created_count, updated_count
        normalized = str(username or "").strip()
        if not normalized:
            return

        existing = await repo.get_by_login_identifier(normalized)
        if existing is not None:
            changed = False
            current_role = str(getattr(existing.role, "value", existing.role) or "").strip().lower()
            if current_role != role:
                existing.role = role
                changed = True
            if not str(existing.password_hash or "").strip():
                existing.password_hash = default_hash
                changed = True
            if not bool(existing.is_active):
                existing.is_active = True
                changed = True
            if not str(existing.username or "").strip():
                existing.username = normalized
                changed = True
            if changed:
                existing.updated_at = datetime.now()
                updated_count += 1
            return

        await repo.upsert_by_email(
            {
                "id": str(uuid.uuid4()),
                "email": f"{normalized}@local.test",
                "username": normalized,
                "role": role,
                "password_hash": default_hash,
                "is_active": True,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
        )
        created_count += 1

    for username in ADMIN_ACCOUNTS:
        await upsert_user(username, "admin")
    for username in TEACHER_ACCOUNTS:
        await upsert_user(username, "teacher")

    if created_count or updated_count:
        await db.commit()

    return {"created": created_count, "updated": updated_count}
