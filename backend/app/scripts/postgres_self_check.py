import asyncio
import json
import uuid
from datetime import datetime

from ..db.session import close_db_engine, get_db, init_db_engine, init_db_schema
from ..repositories import (
    AttachmentRepository,
    AuthUserRepository,
    CourseRepository,
    ExperimentRepository,
    KVStoreRepository,
    OperationLogRepository,
    ResourceRepository,
    StudentExperimentRepository,
    SubmissionPdfRepository,
    UserRepository,
)


async def _run() -> int:
    ok = await init_db_engine(force=True)
    if not ok:
        print("self-check: PostgreSQL init failed")
        return 2
    await init_db_schema()

    token = str(uuid.uuid4())[:8]
    now = datetime.now()
    ids = {
        "class": f"selfcheck-class-{token}",
        "teacher": f"selfcheck-teacher-{token}",
        "student": f"selfcheck-student-{token}",
        "course": f"selfcheck-course-{token}",
        "experiment": f"selfcheck-exp-{token}",
        "submission": f"selfcheck-sub-{token}",
        "pdf": f"selfcheck-pdf-{token}",
        "resource": f"selfcheck-res-{token}",
        "attachment": f"selfcheck-att-{token}",
        "kv": f"selfcheck-kv-{token}",
        "log": f"selfcheck-log-{token}",
    }

    async for db in get_db():
        user_repo = UserRepository(db)
        auth_repo = AuthUserRepository(db)
        course_repo = CourseRepository(db)
        exp_repo = ExperimentRepository(db)
        sub_repo = StudentExperimentRepository(db)
        pdf_repo = SubmissionPdfRepository(db)
        resource_repo = ResourceRepository(db)
        attachment_repo = AttachmentRepository(db)
        kv_repo = KVStoreRepository(db)
        log_repo = OperationLogRepository(db)

        try:
            await user_repo.upsert_class(
                {"id": ids["class"], "name": f"SelfCheckClass-{token}", "created_by": ids["teacher"], "created_at": now}
            )
            await user_repo.upsert(
                {
                    "id": ids["teacher"],
                    "username": ids["teacher"],
                    "role": "teacher",
                    "real_name": "Self Check Teacher",
                    "student_id": None,
                    "class_name": "",
                    "admission_year": "",
                    "organization": "",
                    "phone": "",
                    "password_hash": "",
                    "security_question": "",
                    "security_answer_hash": "",
                    "created_by": "self-check",
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                    "extra": {},
                }
            )
            await user_repo.upsert(
                {
                    "id": ids["student"],
                    "username": ids["student"],
                    "role": "student",
                    "real_name": "Self Check Student",
                    "student_id": ids["student"],
                    "class_name": f"SelfCheckClass-{token}",
                    "admission_year": "2026",
                    "organization": "SE",
                    "phone": "000",
                    "password_hash": "x",
                    "security_question": "",
                    "security_answer_hash": "",
                    "created_by": ids["teacher"],
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                    "extra": {},
                }
            )
            await auth_repo.upsert_by_email(
                {
                    "id": str(uuid.uuid4()),
                    "email": ids["teacher"],
                    "username": ids["teacher"],
                    "role": "teacher",
                    "password_hash": "x",
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            await auth_repo.upsert_by_email(
                {
                    "id": str(uuid.uuid4()),
                    "email": ids["student"],
                    "username": ids["student"],
                    "role": "student",
                    "password_hash": "x",
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                }
            )

            await course_repo.upsert(
                {
                    "id": ids["course"],
                    "name": f"SelfCheckCourse-{token}",
                    "description": "self check",
                    "created_by": ids["teacher"],
                    "created_at": now,
                    "updated_at": now,
                }
            )
            await exp_repo.upsert(
                {
                    "id": ids["experiment"],
                    "course_id": ids["course"],
                    "course_name": f"SelfCheckCourse-{token}",
                    "title": "SelfCheck Experiment",
                    "description": "",
                    "difficulty": "beginner",
                    "tags": ["selfcheck"],
                    "notebook_path": "",
                    "resources": {"cpu": 1},
                    "deadline": None,
                    "created_by": ids["teacher"],
                    "published": True,
                    "publish_scope": "all",
                    "target_class_names": [],
                    "target_student_ids": [],
                    "created_at": now,
                    "updated_at": now,
                    "extra": {},
                }
            )
            await sub_repo.upsert(
                {
                    "id": ids["submission"],
                    "experiment_id": ids["experiment"],
                    "student_id": ids["student"],
                    "status": "submitted",
                    "start_time": now,
                    "submit_time": now,
                    "notebook_content": "{}",
                    "score": 90.0,
                    "ai_feedback": "",
                    "teacher_comment": "",
                    "created_at": now,
                    "updated_at": now,
                    "extra": {},
                }
            )
            await pdf_repo.upsert(
                {
                    "id": ids["pdf"],
                    "submission_id": ids["submission"],
                    "experiment_id": ids["experiment"],
                    "student_id": ids["student"],
                    "filename": "selfcheck.pdf",
                    "file_path": "/tmp/selfcheck.pdf",
                    "content_type": "application/pdf",
                    "size": 1,
                    "viewed": False,
                    "viewed_at": None,
                    "viewed_by": "",
                    "reviewed": False,
                    "reviewed_at": None,
                    "reviewed_by": "",
                    "annotations": [],
                    "created_at": now,
                    "updated_at": now,
                }
            )
            await resource_repo.upsert(
                {
                    "id": ids["resource"],
                    "filename": "selfcheck.txt",
                    "file_path": "/tmp/selfcheck.txt",
                    "file_type": "txt",
                    "content_type": "text/plain",
                    "size": 1,
                    "created_by": ids["teacher"],
                    "created_at": now,
                    "updated_at": now,
                }
            )
            await attachment_repo.upsert(
                {
                    "id": ids["attachment"],
                    "experiment_id": ids["experiment"],
                    "filename": "selfcheck.docx",
                    "file_path": "/tmp/selfcheck.docx",
                    "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "size": 1,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            await kv_repo.upsert(ids["kv"], {"ok": True, "token": token})
            await log_repo.append(
                log_id=ids["log"],
                operator="self-check",
                action="self_check.run",
                target=token,
                detail="postgres crud check",
                success=True,
                created_at=now,
            )
            await db.commit()

            checks = {
                "class": bool(await user_repo.get_class_by_name(f"SelfCheckClass-{token}")),
                "teacher": bool(await user_repo.get_by_username(ids["teacher"])),
                "student": bool(await user_repo.get_student_by_student_id(ids["student"])),
                "course": bool(await course_repo.get(ids["course"])),
                "experiment": bool(await exp_repo.get(ids["experiment"])),
                "submission": bool(await sub_repo.get(ids["submission"])),
                "pdf": bool(await pdf_repo.get(ids["pdf"])),
                "resource": bool(await resource_repo.get(ids["resource"])),
                "attachment": bool(await attachment_repo.get(ids["attachment"])),
                "kv": bool(await kv_repo.get(ids["kv"])),
                "log": bool(await log_repo.get(ids["log"])),
            }
            print(json.dumps({"self_check": "ok", "checks": checks}, ensure_ascii=False))
            if not all(checks.values()):
                return 1
            return 0
        finally:
            try:
                pdf = await pdf_repo.get(ids["pdf"])
                if pdf:
                    await pdf_repo.delete(ids["pdf"])
                submission = await sub_repo.get(ids["submission"])
                if submission:
                    await sub_repo.delete(ids["submission"])
                attachment = await attachment_repo.get(ids["attachment"])
                if attachment:
                    await attachment_repo.delete(ids["attachment"])
                resource = await resource_repo.get(ids["resource"])
                if resource:
                    await resource_repo.delete(ids["resource"])
                experiment = await exp_repo.get(ids["experiment"])
                if experiment:
                    await exp_repo.delete(ids["experiment"])
                course = await course_repo.get(ids["course"])
                if course:
                    await course_repo.delete(ids["course"])
                row = await kv_repo.get(ids["kv"])
                if row:
                    await db.delete(row)
                log = await log_repo.get(ids["log"])
                if log:
                    await db.delete(log)
                student = await user_repo.get_by_username(ids["student"])
                if student:
                    await user_repo.delete(student.id)
                teacher = await user_repo.get_by_username(ids["teacher"])
                if teacher:
                    await user_repo.delete(teacher.id)
                await auth_repo.delete_by_username(ids["student"])
                await auth_repo.delete_by_username(ids["teacher"])
                classes = await user_repo.list_classes()
                for item in classes:
                    if item.id == ids["class"]:
                        await db.delete(item)
                await db.commit()
            except Exception:
                await db.rollback()
        break
    return 2


def main() -> int:
    try:
        return asyncio.run(_run())
    finally:
        try:
            asyncio.run(close_db_engine())
        except RuntimeError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

