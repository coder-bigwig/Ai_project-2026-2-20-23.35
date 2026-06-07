import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import teacher_service


@dataclass
class StudentRecord:
    student_id: str
    username: str
    real_name: str
    class_name: str
    admission_year: str
    organization: str
    phone: str
    role: str
    created_by: str
    password_hash: str
    security_question: str
    security_answer_hash: str
    created_at: datetime
    updated_at: datetime


@dataclass
class ClassRecord:
    id: str
    name: str
    created_by: str
    created_at: datetime


class FakeUserRepository:
    def __init__(self, db):
        self.db = db

    async def list_classes(self):
        now = datetime(2026, 6, 7, tzinfo=timezone.utc)
        return [
            SimpleNamespace(id="class-owned", name="2024级计科1班", created_by="teacher_a", created_at=now),
            SimpleNamespace(id="class-other", name="2024级计算机科学与技术1班", created_by="teacher_b", created_at=now),
        ]

    async def list_by_role(self, role):
        now = datetime(2026, 6, 7, tzinfo=timezone.utc)
        return [
            SimpleNamespace(
                student_id="S001",
                username="student001",
                real_name="张三",
                class_name="2024级计算机科学与技术1班",
                admission_year="2024",
                organization="",
                phone="",
                created_by="teacher_b",
                password_hash="",
                security_question="",
                security_answer_hash="",
                created_at=now,
                updated_at=now,
                extra={
                    "shared_teachers": ["teacher_a"],
                    "teacher_class_names": {"teacher_a": "2024级计科1班"},
                },
            )
        ]


def test_teacher_publish_targets_excludes_classes_not_owned_by_teacher(monkeypatch):
    async def fake_ensure_teacher_or_admin(db, username):
        return username, "teacher"

    monkeypatch.setattr(teacher_service, "UserRepository", FakeUserRepository)
    monkeypatch.setattr(teacher_service, "ensure_teacher_or_admin", fake_ensure_teacher_or_admin)

    service = teacher_service.TeacherService(
        main_module=SimpleNamespace(StudentRecord=StudentRecord, ClassRecord=ClassRecord),
        db=object(),
    )

    payload = asyncio.run(service.get_teacher_publish_targets("teacher_a"))

    assert payload["students"] == [
        {"student_id": "S001", "real_name": "张三", "class_name": "2024级计科1班"}
    ]
    assert payload["classes"] == [{"id": "class-owned", "name": "2024级计科1班"}]
