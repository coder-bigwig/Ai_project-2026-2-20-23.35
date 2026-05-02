from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db
from ...services.admin_service import AdminService


def _get_main_module():
    from ... import main
    return main


main = _get_main_module()
router = APIRouter()


def _service(db: AsyncSession) -> AdminService:
    return AdminService(main_module=main, db=db)


async def list_admin_teachers(admin_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).list_admin_teachers(admin_username=admin_username)


async def create_admin_teacher(payload: main.TeacherCreateRequest, db: AsyncSession = Depends(get_db)):
    return await _service(db).create_admin_teacher(payload=payload)


async def delete_admin_teacher(teacher_username: str, admin_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).delete_admin_teacher(teacher_username=teacher_username, admin_username=admin_username)


async def list_admin_classes(teacher_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).list_admin_classes(teacher_username=teacher_username)


async def download_class_template(teacher_username: str, format: str = "xlsx", db: AsyncSession = Depends(get_db)):
    return await _service(db).download_class_template(teacher_username=teacher_username, format=format)


async def import_admin_classes(teacher_username: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    return await _service(db).import_admin_classes(teacher_username=teacher_username, file=file)


async def create_admin_class(payload: main.ClassCreateRequest, db: AsyncSession = Depends(get_db)):
    return await _service(db).create_admin_class(payload=payload)


async def delete_admin_class(class_id: str, teacher_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).delete_admin_class(class_id=class_id, teacher_username=teacher_username)


async def download_student_template(teacher_username: str, format: str = "xlsx", db: AsyncSession = Depends(get_db)):
    return await _service(db).download_student_template(teacher_username=teacher_username, format=format)


async def import_students(teacher_username: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    return await _service(db).import_students(teacher_username=teacher_username, file=file)


async def list_admin_students(
    teacher_username: str,
    keyword: str = "",
    class_name: str = "",
    admission_year: str = "",
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    return await _service(db).list_admin_students(
        teacher_username=teacher_username,
        keyword=keyword,
        class_name=class_name,
        admission_year=admission_year,
        page=page,
        page_size=page_size,
    )


async def list_admission_year_options(teacher_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).list_admission_year_options(teacher_username=teacher_username)


async def reset_student_password(student_id: str, teacher_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).reset_student_password(student_id=student_id, teacher_username=teacher_username)


async def delete_student(student_id: str, teacher_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).delete_student(student_id=student_id, teacher_username=teacher_username)


async def batch_delete_students(teacher_username: str, class_name: str = "", db: AsyncSession = Depends(get_db)):
    return await _service(db).batch_delete_students(teacher_username=teacher_username, class_name=class_name)


async def get_resource_control_overview(admin_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).get_resource_control_overview(admin_username=admin_username)


async def get_admin_usage_monitor(admin_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).get_admin_usage_monitor(admin_username=admin_username)


async def upsert_user_resource_quota(
    username: str,
    payload: main.ResourceQuotaUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _service(db).upsert_user_resource_quota(username=username, payload=payload)


async def delete_user_resource_quota_override(username: str, admin_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).delete_user_resource_quota_override(username=username, admin_username=admin_username)


async def update_resource_budget(payload: main.ResourceBudgetUpdateRequest, db: AsyncSession = Depends(get_db)):
    return await _service(db).update_resource_budget(payload=payload)


async def list_admin_operation_logs(admin_username: str, limit: int = 200, db: AsyncSession = Depends(get_db)):
    return await _service(db).list_admin_operation_logs(admin_username=admin_username, limit=limit)


async def cleanup_admin_operation_logs(admin_username: str, keep_recent: int = 200, db: AsyncSession = Depends(get_db)):
    return await _service(db).cleanup_admin_operation_logs(admin_username=admin_username, keep_recent=keep_recent)


async def upload_resource_file(
    teacher_username: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    return await _service(db).upload_resource_file(teacher_username=teacher_username, file=file)


async def list_resource_files(
    teacher_username: str,
    name: Optional[str] = None,
    file_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    return await _service(db).list_resource_files(teacher_username=teacher_username, name=name, file_type=file_type)


async def get_resource_file_detail(resource_id: str, teacher_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).get_resource_file_detail(resource_id=resource_id, teacher_username=teacher_username)


async def delete_resource_file(resource_id: str, teacher_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).delete_resource_file(resource_id=resource_id, teacher_username=teacher_username)


async def preview_resource_file(resource_id: str, teacher_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).preview_resource_file(resource_id=resource_id, teacher_username=teacher_username)


async def download_resource_file(resource_id: str, teacher_username: str, db: AsyncSession = Depends(get_db)):
    return await _service(db).download_resource_file(resource_id=resource_id, teacher_username=teacher_username)


router.add_api_route("/api/admin/teachers", list_admin_teachers, methods=["GET"])
router.add_api_route("/api/admin/teachers", create_admin_teacher, methods=["POST"])
router.add_api_route("/api/admin/teachers/{teacher_username}", delete_admin_teacher, methods=["DELETE"])
router.add_api_route("/api/admin/classes", list_admin_classes, methods=["GET"], response_model=list[main.ClassRecord])
router.add_api_route("/api/admin/classes/template", download_class_template, methods=["GET"])
router.add_api_route("/api/admin/classes/import", import_admin_classes, methods=["POST"])
router.add_api_route("/api/admin/classes", create_admin_class, methods=["POST"], response_model=main.ClassRecord)
router.add_api_route("/api/admin/classes/{class_id}", delete_admin_class, methods=["DELETE"])
router.add_api_route("/api/admin/students/template", download_student_template, methods=["GET"])
router.add_api_route("/api/admin/students/import", import_students, methods=["POST"])
router.add_api_route("/api/admin/students", list_admin_students, methods=["GET"])
router.add_api_route("/api/admin/students/admission-years", list_admission_year_options, methods=["GET"])
router.add_api_route("/api/admin/students/{student_id}/reset-password", reset_student_password, methods=["POST"])
router.add_api_route("/api/admin/students/{student_id}", delete_student, methods=["DELETE"])
router.add_api_route("/api/admin/students", batch_delete_students, methods=["DELETE"])
router.add_api_route("/api/admin/resource-control/overview", get_resource_control_overview, methods=["GET"])
router.add_api_route("/api/admin/usage-monitor", get_admin_usage_monitor, methods=["GET"])
router.add_api_route("/api/admin/resource-control/users/{username}", upsert_user_resource_quota, methods=["PUT"])
router.add_api_route("/api/admin/resource-control/users/{username}", delete_user_resource_quota_override, methods=["DELETE"])
router.add_api_route("/api/admin/resource-control/budget", update_resource_budget, methods=["PUT"])
router.add_api_route("/api/admin/operation-logs", list_admin_operation_logs, methods=["GET"])
router.add_api_route("/api/admin/operation-logs", cleanup_admin_operation_logs, methods=["DELETE"])
router.add_api_route("/api/admin/resources/upload", upload_resource_file, methods=["POST"])
router.add_api_route("/api/admin/resources", list_resource_files, methods=["GET"])
router.add_api_route("/api/admin/resources/{resource_id}", get_resource_file_detail, methods=["GET"])
router.add_api_route("/api/admin/resources/{resource_id}", delete_resource_file, methods=["DELETE"])
router.add_api_route("/api/admin/resources/{resource_id}/preview", preview_resource_file, methods=["GET"])
router.add_api_route("/api/admin/resources/{resource_id}/download", download_resource_file, methods=["GET"])
