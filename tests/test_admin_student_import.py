import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import admin_service


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class FakeUpload:
    filename = "students.csv"

    async def read(self):
        return b"ignored"


class FakeAuthUserRepository:
    def __init__(self, db):
        self.db = db

    async def upsert_by_email(self, payload):
        raise AssertionError("existing-student import should not create auth users")


class FakeUserRepository:
    rows = []

    def __init__(self, db):
        self.db = db

    async def list_classes(self):
        now = datetime(2026, 6, 7, tzinfo=timezone.utc)
        return [
            SimpleNamespace(id="class-a", name="A班", created_by="teacher_a", created_at=now),
            SimpleNamespace(id="class-full", name="FullClass", created_by="teacher_a", created_at=now),
        ]

    async def list_by_role(self, role):
        assert role == "student"
        return list(self.rows)

    async def upsert(self, payload):
        raise AssertionError("existing-student import should not create users")


def test_import_existing_students_reuses_loaded_rows_without_role_lookup_or_rewrite(monkeypatch):
    now = datetime(2026, 6, 7, tzinfo=timezone.utc)
    owned = SimpleNamespace(
        student_id="S001",
        username="S001",
        role="student",
        class_name="A班",
        created_by="teacher_a",
        extra={},
        updated_at=now,
    )
    already_shared = SimpleNamespace(
        student_id="S002",
        username="S002",
        role="student",
        class_name="A班",
        created_by="teacher_b",
        extra={"shared_teachers": ["teacher_a"], "teacher_class_names": {"teacher_a": "A班"}},
        updated_at=now,
    )
    FakeUserRepository.rows = [owned, already_shared]

    async def fake_ensure_teacher_or_admin(db, username):
        return username, "teacher"

    async def fail_resolve_user_role(db, username):
        raise AssertionError(f"unexpected per-row role lookup for existing student {username}")

    async def fake_append_operation_log(*args, **kwargs):
        return None

    monkeypatch.setattr(admin_service, "UserRepository", FakeUserRepository)
    monkeypatch.setattr(admin_service, "AuthUserRepository", FakeAuthUserRepository)
    monkeypatch.setattr(admin_service, "ensure_teacher_or_admin", fake_ensure_teacher_or_admin)
    monkeypatch.setattr(admin_service, "resolve_user_role", fail_resolve_user_role)
    monkeypatch.setattr(admin_service, "append_operation_log", fake_append_operation_log)

    service = admin_service.AdminService(
        main_module=SimpleNamespace(
            _parse_student_import_rows=lambda filename, content: [
                (2, ("S001", "张三", "A班", "学院", "13800000001", "2024")),
                (3, ("S002", "李四", "A班", "学院", "13800000002", "2024")),
            ],
            _hash_password=lambda password: "hash",
        ),
        db=FakeDb(),
    )

    result = asyncio.run(service.import_students("teacher_a", FakeUpload()))

    assert result["success_count"] == 2
    assert owned.extra == {}
    assert already_shared.extra == {"shared_teachers": ["teacher_a"], "teacher_class_names": {"teacher_a": "A班"}}
    assert owned.updated_at == now
    assert already_shared.updated_at == now


def test_import_existing_student_records_teacher_specific_class_alias(monkeypatch):
    now = datetime(2026, 6, 7, tzinfo=timezone.utc)
    existing = SimpleNamespace(
        student_id="S003",
        username="S003",
        role="student",
        class_name="ShortClass",
        created_by="teacher_b",
        extra={},
        updated_at=now,
    )
    FakeUserRepository.rows = [existing]

    async def fake_ensure_teacher_or_admin(db, username):
        return username, "teacher"

    async def fail_resolve_user_role(db, username):
        raise AssertionError(f"unexpected per-row role lookup for existing student {username}")

    async def fake_append_operation_log(*args, **kwargs):
        return None

    monkeypatch.setattr(admin_service, "UserRepository", FakeUserRepository)
    monkeypatch.setattr(admin_service, "AuthUserRepository", FakeAuthUserRepository)
    monkeypatch.setattr(admin_service, "ensure_teacher_or_admin", fake_ensure_teacher_or_admin)
    monkeypatch.setattr(admin_service, "resolve_user_role", fail_resolve_user_role)
    monkeypatch.setattr(admin_service, "append_operation_log", fake_append_operation_log)

    service = admin_service.AdminService(
        main_module=SimpleNamespace(
            _parse_student_import_rows=lambda filename, content: [
                (2, ("S003", "Alice", "FullClass", "School", "13800000003", "2024")),
            ],
            _hash_password=lambda password: "hash",
        ),
        db=FakeDb(),
    )

    result = asyncio.run(service.import_students("teacher_a", FakeUpload()))

    assert result["success_count"] == 1
    assert existing.extra == {
        "shared_teachers": ["teacher_a"],
        "teacher_class_names": {"teacher_a": "FullClass"},
    }
    assert existing.updated_at != now


def test_list_students_filters_and_displays_teacher_specific_class_alias(monkeypatch):
    now = datetime(2026, 6, 7, tzinfo=timezone.utc)
    FakeUserRepository.rows = [
        SimpleNamespace(
            student_id="S003",
            username="S003",
            real_name="Alice",
            role="student",
            class_name="ShortClass",
            admission_year="2024",
            organization="School",
            phone="13800000003",
            created_by="teacher_b",
            created_at=now,
            updated_at=now,
            extra={"shared_teachers": ["teacher_a"], "teacher_class_names": {"teacher_a": "FullClass"}},
        )
    ]

    async def fake_ensure_teacher_or_admin(db, username):
        return username, "teacher"

    monkeypatch.setattr(admin_service, "UserRepository", FakeUserRepository)
    monkeypatch.setattr(admin_service, "ensure_teacher_or_admin", fake_ensure_teacher_or_admin)

    service = admin_service.AdminService(main_module=SimpleNamespace(), db=FakeDb())

    payload = asyncio.run(service.list_admin_students("teacher_a", class_name="FullClass"))

    assert payload["total"] == 1
    assert payload["items"][0]["class_name"] == "FullClass"
