from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.postgres import (
    AttachmentRepository,
    CourseRepository,
    ExperimentRepository,
    OperationLogRepository,
    ResourceRepository,
    SubmissionPdfRepository,
    SubmissionRepository,
    UserRepository,
)


async def load_state_from_postgres(main_module, db: AsyncSession) -> dict[str, int]:
    """Compatibility hook: report PostgreSQL row counts without mutating in-memory dicts."""
    del main_module

    user_repo = UserRepository(db)
    course_repo = CourseRepository(db)
    experiment_repo = ExperimentRepository(db)
    submission_repo = SubmissionRepository(db)
    submission_pdf_repo = SubmissionPdfRepository(db)
    resource_repo = ResourceRepository(db)
    attachment_repo = AttachmentRepository(db)
    operation_log_repo = OperationLogRepository(db)

    classes = await user_repo.list_classes()
    users = await user_repo.list_users()
    teachers = [item for item in users if str(item.role or "").strip().lower() == "teacher"]
    students = [item for item in users if str(item.role or "").strip().lower() == "student"]

    return {
        "classes": len(classes),
        "teachers": len(teachers),
        "students": len(students),
        "courses": len(await course_repo.list_all()),
        "experiments": len(await experiment_repo.list_all()),
        "submissions": len(await submission_repo.list_all()),
        "submission_pdfs": len(await submission_pdf_repo.list_all()),
        "resources": len(await resource_repo.list_all()),
        "attachments": len(await attachment_repo.list_all()),
        "operation_logs": len(await operation_log_repo.list_all()),
    }
