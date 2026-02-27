from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import ClassroomORM, UserORM
from ..attachments import AttachmentRepository
from ..courses import CourseRepository
from ..experiments import ExperimentRepository
from ..student_experiments import StudentExperimentRepository
from ..submission_pdfs import SubmissionPdfRepository
from ..users import UserRepository


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _user_payload(role: str, payload: dict[str, Any], existing: UserORM | None) -> dict[str, Any]:
    now = datetime.now()
    username = _normalize_text(payload.get("username") or (existing.username if existing else ""))
    student_id = _normalize_text(payload.get("student_id") or (existing.student_id if existing else ""))
    if role == "student" and not student_id:
        student_id = username

    return {
        "id": _normalize_text(payload.get("id") or (existing.id if existing else "")) or str(uuid.uuid4()),
        "username": username,
        "role": role,
        "real_name": _normalize_text(payload.get("real_name") or (existing.real_name if existing else "")) or username,
        "student_id": student_id if role == "student" else None,
        "class_name": _normalize_text(payload.get("class_name") or (existing.class_name if existing else "")),
        "admission_year": _normalize_text(payload.get("admission_year") or (existing.admission_year if existing else "")),
        "organization": _normalize_text(payload.get("organization") or (existing.organization if existing else "")),
        "phone": _normalize_text(payload.get("phone") or (existing.phone if existing else "")),
        "password_hash": _normalize_text(payload.get("password_hash") or (existing.password_hash if existing else "")),
        "security_question": _normalize_text(payload.get("security_question") or (existing.security_question if existing else "")),
        "security_answer_hash": _normalize_text(
            payload.get("security_answer_hash") or (existing.security_answer_hash if existing else "")
        ),
        "created_by": _normalize_text(payload.get("created_by") or (existing.created_by if existing else "system")),
        "is_active": bool(payload.get("is_active", existing.is_active if existing is not None else True)),
        "created_at": payload.get("created_at") or (existing.created_at if existing else now),
        "updated_at": payload.get("updated_at") or now,
        "extra": payload.get("extra", existing.extra if existing is not None else {}),
    }


class TeacherStore:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def get_by_id(self, teacher_username: str) -> UserORM | None:
        username = _normalize_text(teacher_username)
        if not username:
            return None
        row = await self.user_repo.get_by_username(username)
        if row is None:
            return None
        return row if _normalize_text(row.role).lower() == "teacher" else None

    async def list(self) -> list[UserORM]:
        return list(await self.user_repo.list_by_role("teacher"))

    async def upsert(self, payload: dict[str, Any]) -> UserORM:
        username = _normalize_text(payload.get("username"))
        if not username:
            raise ValueError("teacher username is required")
        existing = await self.user_repo.get_by_username(username)
        return await self.user_repo.upsert(_user_payload("teacher", payload, existing))

    async def delete(self, teacher_username: str) -> UserORM | None:
        row = await self.get_by_id(teacher_username)
        if row is None:
            return None
        return await self.user_repo.delete(row.id)


class StudentStore:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def get_by_id(self, student_id: str) -> UserORM | None:
        normalized = _normalize_text(student_id)
        if not normalized:
            return None
        row = await self.user_repo.get_student_by_student_id(normalized)
        if row is None:
            row = await self.user_repo.get_by_username(normalized)
        if row is None:
            return None
        return row if _normalize_text(row.role).lower() == "student" else None

    async def list(self) -> list[UserORM]:
        return list(await self.user_repo.list_by_role("student"))

    async def upsert(self, payload: dict[str, Any]) -> UserORM:
        normalized_student_id = _normalize_text(payload.get("student_id"))
        normalized_username = _normalize_text(payload.get("username"))
        if not normalized_student_id and not normalized_username:
            raise ValueError("student_id or username is required")

        existing = None
        if normalized_student_id:
            existing = await self.user_repo.get_student_by_student_id(normalized_student_id)
        if existing is None and normalized_username:
            existing = await self.user_repo.get_by_username(normalized_username)
        upsert_payload = dict(payload)
        if not _normalize_text(upsert_payload.get("username")):
            upsert_payload["username"] = normalized_student_id
        return await self.user_repo.upsert(_user_payload("student", upsert_payload, existing))

    async def delete(self, student_id: str) -> UserORM | None:
        row = await self.get_by_id(student_id)
        if row is None:
            return None
        return await self.user_repo.delete(row.id)


class ClassStore:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def get_by_id(self, class_id: str) -> ClassroomORM | None:
        normalized = _normalize_text(class_id)
        if not normalized:
            return None
        return await self.db.get(ClassroomORM, normalized)

    async def list(self) -> list[ClassroomORM]:
        return list(await self.user_repo.list_classes())

    async def upsert(self, payload: dict[str, Any]) -> ClassroomORM:
        class_id = _normalize_text(payload.get("id"))
        if not class_id:
            raise ValueError("class id is required")
        now = datetime.now()
        existing = await self.get_by_id(class_id)
        upsert_payload = {
            "id": class_id,
            "name": _normalize_text(payload.get("name") or (existing.name if existing else "")),
            "created_by": _normalize_text(payload.get("created_by") or (existing.created_by if existing else "")),
            "created_at": payload.get("created_at") or (existing.created_at if existing else now),
        }
        if not upsert_payload["name"]:
            raise ValueError("class name is required")
        if not upsert_payload["created_by"]:
            raise ValueError("class created_by is required")
        return await self.user_repo.upsert_class(upsert_payload)

    async def delete(self, class_id: str) -> ClassroomORM | None:
        row = await self.get_by_id(class_id)
        if row is None:
            return None
        await self.db.delete(row)
        return row


class CourseStore:
    def __init__(self, db: AsyncSession):
        self.repo = CourseRepository(db)

    async def get_by_id(self, course_id: str):
        return await self.repo.get(course_id)

    async def list(self):
        return await self.repo.list_all()

    async def upsert(self, payload: dict[str, Any]):
        return await self.repo.upsert(payload)

    async def delete(self, course_id: str):
        return await self.repo.delete(course_id)


class ExperimentStore:
    def __init__(self, db: AsyncSession):
        self.repo = ExperimentRepository(db)

    async def get_by_id(self, experiment_id: str):
        return await self.repo.get(experiment_id)

    async def list(self):
        return await self.repo.list_all()

    async def upsert(self, payload: dict[str, Any]):
        return await self.repo.upsert(payload)

    async def delete(self, experiment_id: str):
        return await self.repo.delete(experiment_id)


class SubmissionStore:
    def __init__(self, db: AsyncSession):
        self.repo = StudentExperimentRepository(db)

    async def get_by_id(self, submission_id: str):
        return await self.repo.get(submission_id)

    async def list(self):
        return await self.repo.list_all()

    async def upsert(self, payload: dict[str, Any]):
        return await self.repo.upsert(payload)

    async def delete(self, submission_id: str):
        return await self.repo.delete(submission_id)


class SubmissionPdfStore:
    def __init__(self, db: AsyncSession):
        self.repo = SubmissionPdfRepository(db)

    async def get_by_id(self, pdf_id: str):
        return await self.repo.get(pdf_id)

    async def list(self):
        return await self.repo.list_all()

    async def upsert(self, payload: dict[str, Any]):
        return await self.repo.upsert(payload)

    async def delete(self, pdf_id: str):
        return await self.repo.delete(pdf_id)


class AttachmentStore:
    def __init__(self, db: AsyncSession):
        self.repo = AttachmentRepository(db)

    async def get_by_id(self, attachment_id: str):
        return await self.repo.get(attachment_id)

    async def list(self):
        return await self.repo.list_all()

    async def upsert(self, payload: dict[str, Any]):
        return await self.repo.upsert(payload)

    async def delete(self, attachment_id: str):
        return await self.repo.delete(attachment_id)
