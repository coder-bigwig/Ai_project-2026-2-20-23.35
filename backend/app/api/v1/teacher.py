from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db
from ...services.teacher_service import build_teacher_service


def _get_main_module():
    from ... import main
    return main


main = _get_main_module()
router = APIRouter()


async def upsert_teacher_security_question(
    payload: main.TeacherSecurityQuestionUpdateRequest,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_teacher_service(main_module=main, db=db)
    return await service.upsert_teacher_security_question(payload=payload)


async def change_teacher_password(
    payload: main.TeacherPasswordChangeRequest,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_teacher_service(main_module=main, db=db)
    return await service.change_teacher_password(payload=payload)


async def get_teacher_courses(
    teacher_username: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_teacher_service(main_module=main, db=db)
    return await service.get_teacher_courses(teacher_username=teacher_username)


async def get_teacher_publish_targets(
    teacher_username: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_teacher_service(main_module=main, db=db)
    return await service.get_teacher_publish_targets(teacher_username=teacher_username)


async def create_teacher_course(
    payload: main.CourseCreateRequest,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_teacher_service(main_module=main, db=db)
    return await service.create_teacher_course(payload=payload)


async def update_teacher_course(
    course_id: str,
    payload: main.CourseUpdateRequest,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_teacher_service(main_module=main, db=db)
    return await service.update_teacher_course(course_id=course_id, payload=payload)


async def delete_teacher_course(
    course_id: str,
    teacher_username: str,
    delete_experiments: bool = False,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_teacher_service(main_module=main, db=db)
    return await service.delete_teacher_course(
        course_id=course_id,
        teacher_username=teacher_username,
        delete_experiments=delete_experiments,
    )


async def toggle_course_publish(
    course_id: str,
    teacher_username: str,
    published: bool,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_teacher_service(main_module=main, db=db)
    return await service.toggle_course_publish(
        course_id=course_id,
        teacher_username=teacher_username,
        published=published,
    )


async def get_all_student_progress(
    teacher_username: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_teacher_service(main_module=main, db=db)
    return await service.get_all_student_progress(teacher_username=teacher_username)


async def get_statistics(db: Optional[AsyncSession] = Depends(get_db)):
    service = build_teacher_service(main_module=main, db=db)
    return await service.get_statistics()


router.add_api_route("/api/teacher/profile/security-question", upsert_teacher_security_question, methods=["POST"])
router.add_api_route("/api/teacher/profile/change-password", change_teacher_password, methods=["POST"])
router.add_api_route("/api/teacher/courses", get_teacher_courses, methods=["GET"])
router.add_api_route("/api/teacher/publish-targets", get_teacher_publish_targets, methods=["GET"])
router.add_api_route("/api/teacher/courses", create_teacher_course, methods=["POST"])
router.add_api_route("/api/teacher/courses/{course_id}", update_teacher_course, methods=["PATCH"])
router.add_api_route("/api/teacher/courses/{course_id}", delete_teacher_course, methods=["DELETE"])
router.add_api_route("/api/teacher/courses/{course_id}/publish", toggle_course_publish, methods=["PATCH"])
router.add_api_route("/api/teacher/progress", get_all_student_progress, methods=["GET"])
router.add_api_route("/api/teacher/statistics", get_statistics, methods=["GET"])
