from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories import AuthUserRepository, UserRepository


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def role_value(value: Any) -> str:
    if hasattr(value, "value"):
        return normalize_text(getattr(value, "value")).lower()
    return normalize_text(value).lower()


async def resolve_user_role(db: AsyncSession, username: str) -> str:
    normalized = normalize_text(username)
    if not normalized:
        return ""

    auth_row = await AuthUserRepository(db).get_by_login_identifier(normalized)
    if auth_row is not None:
        role = role_value(auth_row.role)
        if role:
            return role

    user_repo = UserRepository(db)
    user = await user_repo.get_by_username(normalized)
    if user is None:
        user = await user_repo.get_student_by_student_id(normalized)
    if user is None:
        return ""
    return normalize_text(user.role).lower() or "student"


async def ensure_admin(db: AsyncSession, username: str) -> str:
    normalized = normalize_text(username)
    if not normalized:
        raise HTTPException(status_code=403, detail="权限不足，需要管理员账号")
    role = await resolve_user_role(db, normalized)
    if role != "admin":
        raise HTTPException(status_code=403, detail="权限不足，需要管理员账号")
    return normalized


async def ensure_teacher_or_admin(db: AsyncSession, username: str) -> tuple[str, str]:
    normalized = normalize_text(username)
    if not normalized:
        raise HTTPException(status_code=403, detail="权限不足")
    role = await resolve_user_role(db, normalized)
    if role not in {"teacher", "admin"}:
        raise HTTPException(status_code=403, detail="权限不足")
    return normalized, role


async def ensure_student_user(db: AsyncSession, student_id_or_username: str):
    normalized = normalize_text(student_id_or_username)
    if not normalized:
        raise HTTPException(status_code=404, detail="学生不存在")

    repo = UserRepository(db)
    row = await repo.get_student_by_student_id(normalized)
    if row is None:
        row = await repo.get_by_username(normalized)
    if row is None or normalize_text(row.role).lower() != "student":
        raise HTTPException(status_code=404, detail="学生不存在")
    return row

