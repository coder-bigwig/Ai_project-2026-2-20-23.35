from __future__ import annotations

import mimetypes
import os
import shutil
import uuid
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import ALLOWED_RESOURCE_EXTENSIONS, UPLOAD_DIR
from ..repositories import (
    AttachmentRepository,
    AuthUserRepository,
    CourseRepository,
    ExperimentRepository,
    PasswordHashRepository,
    ResourceRepository,
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
        resources = dict(row.resources or {})
        return self.main.Experiment(
            id=row.id,
            course_id=row.course_id,
            course_name=row.course_name or "",
            title=row.title,
            description=row.description or "",
            difficulty=difficulty,
            tags=list(row.tags or []),
            notebook_path=row.notebook_path or "",
            resources=resources,
            resource_tier=resources.get("resource_tier") or "small",
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

    @staticmethod
    def _resource_preview_mode(file_type: str) -> str:
        normalized = normalize_text(file_type).lower().lstrip(".")
        if normalized == "pdf":
            return "pdf"
        if normalized in {"xls", "xlsx"}:
            return "sheet"
        if normalized in {"md", "markdown"}:
            return "markdown"
        if normalized in {"txt", "csv", "json", "py", "log"}:
            return "text"
        if normalized == "docx":
            return "docx"
        return "unsupported"

    def _course_resource_payload(self, row, course_id: str) -> dict:
        preview_mode = self._resource_preview_mode(row.file_type)
        route_prefix = f"/api/teacher/courses/{course_id}/resources"
        return {
            "id": row.id,
            "filename": row.filename,
            "file_type": row.file_type,
            "content_type": row.content_type,
            "size": row.size,
            "created_at": row.created_at,
            "created_by": row.created_by,
            "course_id": getattr(row, "course_id", None),
            "preview_mode": preview_mode,
            "previewable": preview_mode != "unsupported",
            "preview_url": f"{route_prefix}/{row.id}/preview",
            "download_url": f"{route_prefix}/{row.id}/download",
        }

    async def _ensure_owned_course(self, course_id: str, teacher_username: str):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        normalized_course_id = normalize_text(course_id)
        row = await CourseRepository(self.db).get(normalized_course_id)
        if not row or (role != "admin" and normalize_text(row.created_by) != normalized_teacher):
            raise HTTPException(status_code=404, detail="课程不存在")
        return row, normalized_teacher, role

    async def _get_course_resource_or_404(self, course_id: str, resource_id: str):
        normalized_course_id = normalize_text(course_id)
        row = await ResourceRepository(self.db).get(resource_id)
        if not row or normalize_text(getattr(row, "course_id", "")) != normalized_course_id:
            raise HTTPException(status_code=404, detail="资源文件不存在")
        if not os.path.exists(row.file_path):
            await ResourceRepository(self.db).delete(resource_id)
            await self._commit()
            raise HTTPException(status_code=404, detail="资源文件不存在")
        return row

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
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        course_repo = CourseRepository(self.db)
        course_rows = await course_repo.list_all() if role == "admin" else await course_repo.list_by_creator(normalized_teacher)
        experiment_rows = await ExperimentRepository(self.db).list_all()
        experiments = [self._to_experiment_model(item) for item in experiment_rows]

        payload = []
        for row in course_rows:
            course = self._to_course_record(row)
            owned = [
                item
                for item in experiments
                if normalize_text(item.course_id) == normalize_text(course.id)
                and (role == "admin" or normalize_text(item.created_by) == normalized_teacher)
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
        normalized_teacher, role = await self._ensure_teacher(payload.teacher_username)
        course_repo = CourseRepository(self.db)
        exp_repo = ExperimentRepository(self.db)
        row = await course_repo.get(course_id)
        course_owner = normalize_text(row.created_by) if row else ""
        if not row or (role != "admin" and course_owner != normalized_teacher):
            raise HTTPException(status_code=404, detail="课程不存在")

        next_name = normalize_text(payload.name) or row.name
        if normalize_text(next_name).lower() != normalize_text(row.name).lower():
            existing = await course_repo.find_by_teacher_and_name(course_owner, next_name)
            if existing and existing.id != row.id:
                raise HTTPException(status_code=409, detail="课程名称已存在")
            old_name = row.name
            row.name = next_name

            experiment_rows = await exp_repo.list_by_course_ids([course_id])
            for item in experiment_rows:
                if role != "admin" and normalize_text(item.created_by) != normalized_teacher:
                    continue
                if normalize_text(item.course_name) == normalize_text(old_name):
                    item.course_name = next_name

        if payload.description is not None:
            row.description = normalize_text(payload.description)
        row.updated_at = datetime.now()

        related_rows = await exp_repo.list_by_course_ids([course_id])
        related = [
            self._to_experiment_model(item)
            for item in related_rows
            if role == "admin" or normalize_text(item.created_by) == normalized_teacher
        ]
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
        normalized_teacher, role = await self._ensure_teacher(teacher_username)

        course_repo = CourseRepository(self.db)
        exp_repo = ExperimentRepository(self.db)
        att_repo = AttachmentRepository(self.db)
        course_row = await course_repo.get(course_id)
        if not course_row or (role != "admin" and normalize_text(course_row.created_by) != normalized_teacher):
            raise HTTPException(status_code=404, detail="课程不存在")

        exp_rows = [
            item
            for item in await exp_repo.list_by_course_ids([course_id])
            if role == "admin" or normalize_text(item.created_by) == normalized_teacher
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

        resource_repo = ResourceRepository(self.db)
        course_resources = await resource_repo.list_by_course(course_id)
        removed_resource_count = 0
        for resource in course_resources:
            if os.path.exists(resource.file_path):
                try:
                    os.remove(resource.file_path)
                except OSError:
                    pass
            await resource_repo.delete(resource.id)
            removed_resource_count += 1

        await course_repo.delete(course_id)
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="courses.delete",
            target=course_id,
            detail=f"delete_experiments={bool(delete_experiments)}, resources={removed_resource_count}",
        )
        await self._commit()
        return {"message": "课程已删除", "id": course_id}

    async def toggle_course_publish(self, course_id: str, teacher_username: str, published: bool):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        course_repo = CourseRepository(self.db)
        exp_repo = ExperimentRepository(self.db)
        course = await course_repo.get(course_id)
        if not course or (role != "admin" and normalize_text(course.created_by) != normalized_teacher):
            raise HTTPException(status_code=404, detail="课程不存在")

        related = [
            item
            for item in await exp_repo.list_by_course_ids([course_id])
            if role == "admin" or normalize_text(item.created_by) == normalized_teacher
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

    async def upload_course_resource_file(self, course_id: str, teacher_username: str, file: UploadFile):
        course, normalized_teacher, _ = await self._ensure_owned_course(course_id, teacher_username)
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        original_filename = os.path.basename(file.filename)
        extension = os.path.splitext(original_filename)[1].lower()
        if extension not in ALLOWED_RESOURCE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="暂不支持该文件类型")

        normalized_course_id = normalize_text(course.id)
        safe_filename = original_filename.replace(" ", "_").replace("/", "_").replace("\\", "_")
        resource_id = str(uuid.uuid4())
        course_upload_dir = os.path.join(UPLOAD_DIR, "course_resources", normalized_course_id)
        os.makedirs(course_upload_dir, exist_ok=True)
        file_path = os.path.join(course_upload_dir, f"resource_{resource_id}_{safe_filename}")
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"文件保存失败: {exc}") from exc

        file_size = os.path.getsize(file_path)
        if file_size <= 0:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(status_code=400, detail="上传文件为空")

        inferred_content_type = file.content_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
        now = datetime.now()
        row = await ResourceRepository(self.db).create(
            {
                "id": resource_id,
                "filename": original_filename,
                "file_path": file_path,
                "file_type": extension.lstrip("."),
                "content_type": inferred_content_type,
                "size": file_size,
                "created_at": now,
                "updated_at": now,
                "created_by": normalized_teacher,
                "course_id": normalized_course_id,
            }
        )
        course.updated_at = now
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="course_resources.upload",
            target=normalized_course_id,
            detail=f"resource_id={resource_id}, filename={original_filename}",
        )
        await self._commit()
        return self._course_resource_payload(row, normalized_course_id)

    async def list_course_resource_files(
        self,
        course_id: str,
        teacher_username: str,
        name: Optional[str] = None,
        file_type: Optional[str] = None,
    ):
        course, _, _ = await self._ensure_owned_course(course_id, teacher_username)
        normalized_course_id = normalize_text(course.id)
        normalized_name = normalize_text(name).lower()
        normalized_type = normalize_text(file_type).lower().lstrip(".")

        items = []
        for row in await ResourceRepository(self.db).list_by_course(normalized_course_id):
            if normalized_name and normalized_name not in normalize_text(row.filename).lower():
                continue
            if normalized_type and normalize_text(row.file_type).lower().lstrip(".") != normalized_type:
                continue
            if not os.path.exists(row.file_path):
                continue
            items.append(row)
        items.sort(key=lambda item: item.created_at or datetime.min, reverse=True)
        payload_items = [self._course_resource_payload(item, normalized_course_id) for item in items]
        return {"total": len(payload_items), "items": payload_items}

    async def get_course_resource_file_detail(self, course_id: str, resource_id: str, teacher_username: str):
        course, _, _ = await self._ensure_owned_course(course_id, teacher_username)
        normalized_course_id = normalize_text(course.id)
        row = await self._get_course_resource_or_404(normalized_course_id, resource_id)

        payload = self._course_resource_payload(row, normalized_course_id)
        preview_mode = payload["preview_mode"]
        if preview_mode in {"markdown", "text"}:
            payload["preview_text"] = self.main._read_text_preview(row.file_path)
        elif preview_mode == "docx":
            try:
                payload["preview_text"] = self.main._read_docx_preview(row.file_path)
            except HTTPException as exc:
                payload["preview_text"] = ""
                payload["preview_error"] = normalize_text(getattr(exc, "detail", "")) or "Word 文档预览解析失败"
            except Exception:
                payload["preview_text"] = ""
                payload["preview_error"] = "Word 文档预览解析失败"
        else:
            payload["preview_text"] = ""
        return payload

    async def delete_course_resource_file(self, course_id: str, resource_id: str, teacher_username: str):
        course, normalized_teacher, _ = await self._ensure_owned_course(course_id, teacher_username)
        normalized_course_id = normalize_text(course.id)
        row = await self._get_course_resource_or_404(normalized_course_id, resource_id)
        if os.path.exists(row.file_path):
            try:
                os.remove(row.file_path)
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"删除文件失败: {exc}") from exc
        await ResourceRepository(self.db).delete(resource_id)
        course.updated_at = datetime.now()
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="course_resources.delete",
            target=normalized_course_id,
            detail=f"resource_id={resource_id}, filename={row.filename}",
        )
        await self._commit()
        return {"message": "课程资料已删除", "id": resource_id}

    async def preview_course_resource_file(self, course_id: str, resource_id: str, teacher_username: str):
        course, _, _ = await self._ensure_owned_course(course_id, teacher_username)
        normalized_course_id = normalize_text(course.id)
        row = await self._get_course_resource_or_404(normalized_course_id, resource_id)
        if self._resource_preview_mode(row.file_type) != "pdf":
            raise HTTPException(status_code=400, detail="该文件类型不支持二进制在线预览")
        return FileResponse(
            path=row.file_path,
            filename="document.pdf",
            media_type="application/pdf",
            content_disposition_type="inline",
        )

    async def download_course_resource_file(self, course_id: str, resource_id: str, teacher_username: str):
        course, _, _ = await self._ensure_owned_course(course_id, teacher_username)
        normalized_course_id = normalize_text(course.id)
        row = await self._get_course_resource_or_404(normalized_course_id, resource_id)
        media_type = row.content_type or mimetypes.guess_type(row.filename)[0] or "application/octet-stream"
        return FileResponse(
            path=row.file_path,
            filename=row.filename,
            media_type=media_type,
            content_disposition_type="attachment",
        )

    async def get_all_student_progress(self, teacher_username: str):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)

        exp_rows = await ExperimentRepository(self.db).list_all()
        owned_experiment_ids = {
            item.id
            for item in exp_rows
            if role == "admin" or normalize_text(item.created_by) == normalized_teacher
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
