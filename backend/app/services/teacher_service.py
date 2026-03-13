from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories import (
    AttachmentRepository,
    AuthUserRepository,
    CourseRepository,
    ExperimentRepository,
    PasswordHashRepository,
    SecurityQuestionRepository,
    StudentExperimentRepository,
    UserRepository,
)
from .identity_service import ensure_teacher_or_admin, normalize_text
from .operation_log_service import append_operation_log


class TeacherService:
    def __init__(self, main_module, db: Optional[AsyncSession] = None):
        if db is None:
            raise HTTPException(status_code=503, detail="PostgreSQL session unavailable")
        self.main = main_module
        self.db = db

    async def _commit(self):
        try:
            await self.db.commit()
        except Exception as exc:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail="教师端数据写入失败") from exc

    def _to_course_record(self, row):
        return self.main.CourseRecord(
            id=row.id,
            name=row.name,
            description=row.description or "",
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_experiment_model(self, row):
        difficulty = row.difficulty or self.main.DifficultyLevel.BEGINNER.value
        publish_scope = row.publish_scope or self.main.PublishScope.ALL.value
        try:
            difficulty = self.main.DifficultyLevel(difficulty)
        except ValueError:
            difficulty = self.main.DifficultyLevel.BEGINNER
        try:
            publish_scope = self.main.PublishScope(publish_scope)
        except ValueError:
            publish_scope = self.main.PublishScope.ALL
        return self.main.Experiment(
            id=row.id,
            course_id=row.course_id,
            course_name=row.course_name or "",
            title=row.title,
            description=row.description or "",
            difficulty=difficulty,
            tags=list(row.tags or []),
            notebook_path=row.notebook_path or "",
            resources=dict(row.resources or {}),
            deadline=row.deadline,
            created_at=row.created_at,
            created_by=row.created_by,
            published=bool(row.published),
            publish_scope=publish_scope,
            target_class_names=list(row.target_class_names or []),
            target_student_ids=list(row.target_student_ids or []),
        )

    def _course_payload(self, course, experiments: list):
        ordered_experiments = sorted(
            experiments,
            key=lambda item: item.created_at or datetime.min,
            reverse=True,
        )
        published_count = sum(1 for item in ordered_experiments if item.published)
        latest_experiment_at = ordered_experiments[0].created_at if ordered_experiments else None
        tags = sorted({tag for item in ordered_experiments for tag in (item.tags or []) if normalize_text(tag)})
        return {
            "id": course.id,
            "name": course.name,
            "description": course.description or "",
            "created_by": course.created_by,
            "created_at": course.created_at,
            "updated_at": course.updated_at,
            "experiment_count": len(ordered_experiments),
            "published_count": published_count,
            "latest_experiment_at": latest_experiment_at,
            "tags": tags,
            "experiments": ordered_experiments,
        }

    async def _ensure_teacher(self, username: str) -> tuple[str, str]:
        return await ensure_teacher_or_admin(self.db, username)

    async def _update_auth_password(self, username: str, new_hash: str):
        auth_repo = AuthUserRepository(self.db)
        auth_user = await auth_repo.get_by_login_identifier(username)
        if auth_user is not None:
            auth_user.password_hash = new_hash
            auth_user.updated_at = datetime.now()

    async def upsert_teacher_security_question(self, payload):
        teacher_username = normalize_text(payload.teacher_username)
        question = self.main._normalize_security_question(payload.security_question or "")
        answer = payload.security_answer or ""

        if not teacher_username or not question or not answer:
            raise HTTPException(status_code=400, detail="账号、密保问题和答案不能为空")
        if len(question) < 2:
            raise HTTPException(status_code=400, detail="密保问题至少 2 个字")
        if len(self.main._normalize_security_answer(answer)) < 2:
            raise HTTPException(status_code=400, detail="密保答案至少 2 个字")

        normalized_teacher, _ = await self._ensure_teacher(teacher_username)
        repo = SecurityQuestionRepository(self.db)
        existing = await repo.get_by_username(normalized_teacher)
        await repo.upsert(
            {
                "id": existing.id if existing else str(uuid.uuid4()),
                "username": normalized_teacher,
                "role": "teacher",
                "question": question,
                "answer_hash": self.main._hash_security_answer(answer),
                "created_at": existing.created_at if existing else datetime.now(),
                "updated_at": datetime.now(),
            }
        )
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="accounts.update_security_question",
            target=normalized_teacher,
            detail="教师/管理员更新密保问题",
        )
        await self._commit()
        return {"message": "密保问题已保存"}

    async def change_teacher_password(self, payload):
        teacher_username = normalize_text(payload.teacher_username)
        old_password = payload.old_password or ""
        new_password = payload.new_password or ""

        if not teacher_username or not old_password or not new_password:
            raise HTTPException(status_code=400, detail="账号、旧密码和新密码不能为空")
        await self._ensure_teacher(teacher_username)
        if len(new_password) < 6:
            raise HTTPException(status_code=400, detail="新密码长度不能少于6位")
        if old_password == new_password:
            raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")

        repo = PasswordHashRepository(self.db)
        current_row = await repo.get_by_username(teacher_username)
        current_hash = current_row.password_hash if current_row else self.main._default_password_hash()
        if current_hash != self.main._hash_password(old_password):
            raise HTTPException(status_code=401, detail="旧密码错误")

        new_hash = self.main._hash_password(new_password)
        if new_hash == self.main._default_password_hash():
            await repo.delete_by_username(teacher_username)
        else:
            await repo.upsert(
                {
                    "id": current_row.id if current_row else str(uuid.uuid4()),
                    "username": teacher_username,
                    "role": "teacher",
                    "password_hash": new_hash,
                    "created_at": current_row.created_at if current_row else datetime.now(),
                    "updated_at": datetime.now(),
                }
            )

        await self._update_auth_password(teacher_username, new_hash)
        await append_operation_log(
            self.db,
            operator=teacher_username,
            action="accounts.change_password",
            target=teacher_username,
            detail="教师端修改密码",
        )
        await self._commit()
        return {"message": "密码修改成功"}

    async def get_teacher_courses(self, teacher_username: str):
        normalized_teacher, _ = await self._ensure_teacher(teacher_username)
        course_rows = await CourseRepository(self.db).list_by_creator(normalized_teacher)
        experiment_rows = await ExperimentRepository(self.db).list_all()
        experiments = [self._to_experiment_model(item) for item in experiment_rows]

        payload = []
        for row in course_rows:
            course = self._to_course_record(row)
            owned = [
                item
                for item in experiments
                if normalize_text(item.created_by) == normalized_teacher
                and normalize_text(item.course_id) == normalize_text(course.id)
            ]
            payload.append(self._course_payload(course, owned))
        payload.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or datetime.min, reverse=True)
        return payload

    async def get_teacher_publish_targets(self, teacher_username: str):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        user_repo = UserRepository(self.db)
        class_rows = await user_repo.list_classes()
        student_rows = await user_repo.list_by_role("student")

        classes = []
        for row in class_rows:
            if role == "admin" or normalize_text(row.created_by) == normalized_teacher:
                classes.append(self.main.ClassRecord(id=row.id, name=row.name, created_by=row.created_by, created_at=row.created_at))
        classes.sort(key=lambda item: item.name)

        class_owner_map = {}
        for item in classes:
            class_owner_map[item.name] = normalize_text(item.created_by)

        students = []
        for row in student_rows:
            student = self.main.StudentRecord(
                student_id=row.student_id or row.username,
                username=row.username,
                real_name=row.real_name or row.username,
                class_name=row.class_name or "",
                admission_year=row.admission_year or "",
                organization=row.organization or "",
                phone=row.phone or "",
                role="student",
                created_by=row.created_by or "",
                password_hash=row.password_hash or "",
                security_question=row.security_question or "",
                security_answer_hash=row.security_answer_hash or "",
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            if role == "admin":
                students.append(student)
                continue
            owner = normalize_text(student.created_by) or class_owner_map.get(student.class_name, "")
            if owner == normalized_teacher:
                students.append(student)
        students.sort(key=lambda item: (item.class_name, item.student_id))

        return {
            "classes": [{"id": item.id, "name": item.name} for item in classes],
            "students": [
                {"student_id": item.student_id, "real_name": item.real_name, "class_name": item.class_name}
                for item in students
            ],
        }

    async def create_teacher_course(self, payload):
        normalized_teacher, _ = await self._ensure_teacher(payload.teacher_username)
        course_name = normalize_text(payload.name)
        if not course_name:
            raise HTTPException(status_code=400, detail="课程名称不能为空")

        repo = CourseRepository(self.db)
        if await repo.find_by_teacher_and_name(normalized_teacher, course_name):
            raise HTTPException(status_code=409, detail="课程名称已存在")

        now = datetime.now()
        row = await repo.create(
            {
                "id": str(uuid.uuid4()),
                "name": course_name,
                "description": normalize_text(payload.description or ""),
                "created_by": normalized_teacher,
                "created_at": now,
                "updated_at": now,
            }
        )
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="courses.create",
            target=course_name,
            detail=f"course_id={row.id}",
        )
        await self._commit()
        course = self._to_course_record(row)
        return self._course_payload(course, [])

    async def update_teacher_course(self, course_id: str, payload):
        normalized_teacher, _ = await self._ensure_teacher(payload.teacher_username)
        course_repo = CourseRepository(self.db)
        exp_repo = ExperimentRepository(self.db)
        row = await course_repo.get(course_id)
        if not row or normalize_text(row.created_by) != normalized_teacher:
            raise HTTPException(status_code=404, detail="课程不存在")

        next_name = normalize_text(payload.name) or row.name
        if normalize_text(next_name).lower() != normalize_text(row.name).lower():
            existing = await course_repo.find_by_teacher_and_name(normalized_teacher, next_name)
            if existing and existing.id != row.id:
                raise HTTPException(status_code=409, detail="课程名称已存在")
            old_name = row.name
            row.name = next_name

            experiment_rows = await exp_repo.list_by_course_ids([course_id])
            for item in experiment_rows:
                if normalize_text(item.created_by) != normalized_teacher:
                    continue
                if normalize_text(item.course_name) == normalize_text(old_name):
                    item.course_name = next_name

        if payload.description is not None:
            row.description = normalize_text(payload.description)
        row.updated_at = datetime.now()

        related_rows = await exp_repo.list_by_course_ids([course_id])
        related = [self._to_experiment_model(item) for item in related_rows if normalize_text(item.created_by) == normalized_teacher]
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="courses.update",
            target=course_id,
            detail=f"name={row.name}",
        )
        await self._commit()
        return self._course_payload(self._to_course_record(row), related)

    async def delete_teacher_course(self, course_id: str, teacher_username: str, delete_experiments: bool = False):
        normalized_teacher, _ = await self._ensure_teacher(teacher_username)

        course_repo = CourseRepository(self.db)
        exp_repo = ExperimentRepository(self.db)
        att_repo = AttachmentRepository(self.db)
        course_row = await course_repo.get(course_id)
        if not course_row or normalize_text(course_row.created_by) != normalized_teacher:
            raise HTTPException(status_code=404, detail="课程不存在")

        exp_rows = [
            item
            for item in await exp_repo.list_by_course_ids([course_id])
            if normalize_text(item.created_by) == normalized_teacher
        ]
        if exp_rows and not delete_experiments:
            raise HTTPException(status_code=409, detail="课程下存在实验，请先删除实验或传入 delete_experiments=true")

        if delete_experiments:
            for exp in exp_rows:
                attachments = await att_repo.list_by_experiment(exp.id)
                for att in attachments:
                    if os.path.exists(att.file_path):
                        try:
                            os.remove(att.file_path)
                        except OSError:
                            pass
                    await att_repo.delete(att.id)
                await exp_repo.delete(exp.id)

        await course_repo.delete(course_id)
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="courses.delete",
            target=course_id,
            detail=f"delete_experiments={bool(delete_experiments)}",
        )
        await self._commit()
        return {"message": "课程已删除", "id": course_id}

    async def toggle_course_publish(self, course_id: str, teacher_username: str, published: bool):
        normalized_teacher, _ = await self._ensure_teacher(teacher_username)
        course_repo = CourseRepository(self.db)
        exp_repo = ExperimentRepository(self.db)
        course = await course_repo.get(course_id)
        if not course or normalize_text(course.created_by) != normalized_teacher:
            raise HTTPException(status_code=404, detail="课程不存在")

        related = [
            item
            for item in await exp_repo.list_by_course_ids([course_id])
            if normalize_text(item.created_by) == normalized_teacher
        ]
        if not related:
            return {"message": "课程下暂无实验", "published": published, "updated": 0}

        for item in related:
            item.published = published
        course.updated_at = datetime.now()
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="courses.toggle_publish",
            target=course_id,
            detail=f"published={bool(published)}",
        )
        await self._commit()
        return {
            "message": f"Course publish state updated: {'published' if published else 'unpublished'}",
            "published": published,
            "updated": len(related),
        }

    async def get_all_student_progress(self, teacher_username: str):
        normalized_teacher, _ = await self._ensure_teacher(teacher_username)

        exp_rows = await ExperimentRepository(self.db).list_all()
        owned_experiment_ids = {
            item.id
            for item in exp_rows
            if normalize_text(item.created_by) == normalized_teacher
        }

        student_rows = await UserRepository(self.db).list_by_role("student")
        student_ids = {normalize_text(item.student_id or item.username) for item in student_rows}

        submissions = await StudentExperimentRepository(self.db).list_all()
        payload = []
        for row in submissions:
            if row.experiment_id not in owned_experiment_ids:
                continue
            if normalize_text(row.student_id) not in student_ids:
                continue
            status_value = row.status or self.main.ExperimentStatus.NOT_STARTED.value
            payload.append(
                {
                    "student_id": row.student_id,
                    "experiment_id": row.experiment_id,
                    "status": status_value,
                    "start_time": row.start_time,
                    "submit_time": row.submit_time,
                    "score": row.score,
                }
            )
        return payload

    async def get_statistics(self):
        experiments = await ExperimentRepository(self.db).list_all()
        submissions = await StudentExperimentRepository(self.db).list_all()
        status_count = {}
        for row in submissions:
            status_value = row.status or self.main.ExperimentStatus.NOT_STARTED.value
            status_count[status_value] = status_count.get(status_value, 0) + 1
        return {
            "total_experiments": len(experiments),
            "total_submissions": len(submissions),
            "status_distribution": status_count,
        }


def build_teacher_service(main_module, db: Optional[AsyncSession] = None) -> TeacherService:
    return TeacherService(main_module=main_module, db=db)
