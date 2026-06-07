import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import student_service


class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"


class PublishScope(str, Enum):
    ALL = "all"
    CLASS = "class"


class ExperimentStatus(str, Enum):
    NOT_STARTED = "not_started"


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
class Experiment:
    id: str
    course_id: str
    course_name: str
    title: str
    description: str
    difficulty: DifficultyLevel
    tags: list
    notebook_path: str
    resources: dict
    resource_tier: str
    deadline: object
    created_at: datetime
    created_by: str
    published: bool
    publish_scope: PublishScope
    target_class_names: list
    target_student_ids: list


class FakeExperimentRepository:
    def __init__(self, db):
        self.db = db

    async def list_all(self):
        now = datetime(2026, 6, 7, tzinfo=timezone.utc)
        return [
            SimpleNamespace(
                id="exp-1",
                course_id="course-1",
                course_name="Course",
                title="Experiment",
                description="",
                difficulty=DifficultyLevel.BEGINNER.value,
                tags=[],
                notebook_path="",
                resources={},
                deadline=None,
                created_at=now,
                created_by="teacher_a",
                published=True,
                publish_scope=PublishScope.CLASS.value,
                target_class_names=["FullClass"],
                target_student_ids=[],
            )
        ]


class FakeStudentExperimentRepository:
    def __init__(self, db):
        self.db = db

    async def list_by_student(self, student_id):
        return []


def test_student_courses_use_experiment_teacher_class_alias(monkeypatch):
    now = datetime(2026, 6, 7, tzinfo=timezone.utc)

    async def fake_ensure_student_user(db, student_id):
        return SimpleNamespace(
            student_id=student_id,
            username=student_id,
            real_name="Alice",
            class_name="ShortClass",
            admission_year="2024",
            organization="School",
            phone="13800000003",
            created_by="teacher_b",
            password_hash="",
            security_question="",
            security_answer_hash="",
            created_at=now,
            updated_at=now,
            extra={"teacher_class_names": {"teacher_a": "FullClass"}},
        )

    fake_main = SimpleNamespace(
        StudentRecord=StudentRecord,
        Experiment=Experiment,
        DifficultyLevel=DifficultyLevel,
        PublishScope=PublishScope,
        ExperimentStatus=ExperimentStatus,
        DEFAULT_PASSWORD="123456",
        _hash_password=lambda password: "hash",
        _is_experiment_visible_to_student=lambda experiment, student: student.class_name
        in experiment.target_class_names,
    )

    monkeypatch.setattr(student_service, "ensure_student_user", fake_ensure_student_user)
    monkeypatch.setattr(student_service, "ExperimentRepository", FakeExperimentRepository)
    monkeypatch.setattr(student_service, "StudentExperimentRepository", FakeStudentExperimentRepository)

    service = student_service.StudentService(main_module=fake_main, db=object())

    payload = asyncio.run(service.get_student_courses_with_status("S003"))

    assert [item["course"].id for item in payload] == ["exp-1"]
