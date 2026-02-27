from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db, is_postgres_ready, storage_backend_name
from ...repositories import (
    AttachmentRepository,
    CourseRepository,
    ExperimentRepository,
    KVStoreRepository,
    OperationLogRepository,
    ResourceRepository,
    UserRepository,
)
from ...services.kv_policy_service import default_resource_policy_payload

router = APIRouter()


@router.get("/")
def root():
    return {"message": "福州理工学院AI编程实战教学平台 API", "version": "1.0.0"}


@router.get("/api/health")
def api_health():
    return {
        "status": "ok",
        "service": "experiment-manager",
        "storage_backend": storage_backend_name(),
        "postgres_ready": is_postgres_ready(),
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(db: AsyncSession = Depends(get_db)):
    user_repo = UserRepository(db)
    kv_repo = KVStoreRepository(db)
    policy_row = await kv_repo.get("resource_policy")
    policy = policy_row.value_json if policy_row and isinstance(policy_row.value_json, dict) else default_resource_policy_payload()
    overrides = policy.get("overrides", {}) if isinstance(policy, dict) else {}
    override_count = len(overrides) if isinstance(overrides, dict) else 0

    students = await user_repo.list_by_role("student")
    classes = await user_repo.list_classes()
    courses = await CourseRepository(db).list_all()
    experiments = await ExperimentRepository(db).list_all()
    attachments = await AttachmentRepository(db).list_all()
    resources = await ResourceRepository(db).list_all()
    operation_logs = await OperationLogRepository(db).list_all()

    lines = [
        "# HELP training_backend_up Backend process up status (1=up).",
        "# TYPE training_backend_up gauge",
        "training_backend_up 1",
        "# HELP training_backend_students_total Total students stored in PostgreSQL.",
        "# TYPE training_backend_students_total gauge",
        f"training_backend_students_total {len(students)}",
        "# HELP training_backend_classes_total Total classes stored in PostgreSQL.",
        "# TYPE training_backend_classes_total gauge",
        f"training_backend_classes_total {len(classes)}",
        "# HELP training_backend_courses_total Total courses stored in PostgreSQL.",
        "# TYPE training_backend_courses_total gauge",
        f"training_backend_courses_total {len(courses)}",
        "# HELP training_backend_experiments_total Total experiments stored in PostgreSQL.",
        "# TYPE training_backend_experiments_total gauge",
        f"training_backend_experiments_total {len(experiments)}",
        "# HELP training_backend_attachments_total Total attachments stored in PostgreSQL.",
        "# TYPE training_backend_attachments_total gauge",
        f"training_backend_attachments_total {len(attachments)}",
        "# HELP training_backend_resources_total Total uploaded resources stored in PostgreSQL.",
        "# TYPE training_backend_resources_total gauge",
        f"training_backend_resources_total {len(resources)}",
        "# HELP training_backend_resource_quota_overrides_total Total custom user resource overrides in PostgreSQL KV.",
        "# TYPE training_backend_resource_quota_overrides_total gauge",
        f"training_backend_resource_quota_overrides_total {override_count}",
        "# HELP training_backend_operation_logs_total Total operation logs stored in PostgreSQL.",
        "# TYPE training_backend_operation_logs_total gauge",
        f"training_backend_operation_logs_total {len(operation_logs)}",
    ]
    return "\n".join(lines) + "\n"

