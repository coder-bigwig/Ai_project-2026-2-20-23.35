from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories import AuthUserRepository, ExperimentRepository, StudentExperimentRepository, UserRepository
from .identity_service import ensure_student_user, normalize_text


class StudentService:
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
            raise HTTPException(status_code=500, detail="学生资料写入失败") from exc

    def _to_student_record(self, row):
        student_id = row.student_id or row.username
        return self.main.StudentRecord(
            student_id=student_id,
            username=row.username,
            real_name=row.real_name or student_id,
            class_name=row.class_name or "",
            admission_year=row.admission_year or "",
            organization=row.organization or "",
            phone=row.phone or "",
            role="student",
            created_by=row.created_by or "",
            password_hash=row.password_hash or self.main._hash_password(self.main.DEFAULT_PASSWORD),
            security_question=row.security_question or "",
            security_answer_hash=row.security_answer_hash or "",
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

    def _to_student_experiment_model(self, row):
        status_value = row.status or self.main.ExperimentStatus.NOT_STARTED.value
        try:
            status_value = self.main.ExperimentStatus(status_value)
        except ValueError:
            status_value = self.main.ExperimentStatus.NOT_STARTED
        return self.main.StudentExperiment(
            id=row.id,
            experiment_id=row.experiment_id,
            student_id=row.student_id,
            status=status_value,
            start_time=row.start_time,
            submit_time=row.submit_time,
            notebook_content=row.notebook_content or "",
            score=row.score,
            ai_feedback=row.ai_feedback or "",
            teacher_comment=row.teacher_comment or "",
        )

    async def _update_auth_password(self, username: str, new_hash: str):
        auth_repo = AuthUserRepository(self.db)
        auth_user = await auth_repo.get_by_login_identifier(username)
        if auth_user is not None:
            auth_user.password_hash = new_hash
            auth_user.updated_at = datetime.now()

    async def get_student_courses_with_status(self, student_id: str):
        normalized_student_id = normalize_text(student_id)
        if not normalized_student_id:
            raise HTTPException(status_code=404, detail="学生不存在")

        student_row = await ensure_student_user(self.db, normalized_student_id)
        student = self._to_student_record(student_row)

        exp_rows = await ExperimentRepository(self.db).list_all()
        visible_courses = []
        for row in exp_rows:
            exp_model = self._to_experiment_model(row)
            if self.main._is_experiment_visible_to_student(exp_model, student):
                visible_courses.append(exp_model)

        se_rows = await StudentExperimentRepository(self.db).list_by_student(student.student_id)
        student_records = {}
        for row in se_rows:
            item = self._to_student_experiment_model(row)
            student_records[item.experiment_id] = item

        courses_with_status = []
        for course in visible_courses:
            record = student_records.get(course.id)
            courses_with_status.append(
                {
                    "course": course,
                    "status": record.status.value if record else "未开始",
                    "start_time": record.start_time if record else None,
                    "submit_time": record.submit_time if record else None,
                    "score": record.score if record else None,
                    "student_exp_id": record.id if record else None,
                }
            )
        return courses_with_status

    async def get_student_profile(self, student_id: str):
        row = await ensure_student_user(self.db, student_id)
        student = self._to_student_record(row)
        return {
            "student_id": student.student_id,
            "real_name": student.real_name,
            "class_name": student.class_name,
            "organization": student.organization,
            "major": student.organization,
            "admission_year": self.main._normalize_admission_year(student.admission_year),
            "admission_year_label": self.main._format_admission_year_label(student.admission_year),
            "security_question": self.main._normalize_security_question(student.security_question or ""),
            "security_question_set": bool(self.main._normalize_security_question(student.security_question or "")),
        }

    async def upsert_student_security_question(self, payload):
        student_id = normalize_text(payload.student_id)
        question = self.main._normalize_security_question(payload.security_question or "")
        answer = payload.security_answer or ""

        if not student_id or not question or not answer:
            raise HTTPException(status_code=400, detail="学号、密保问题和答案不能为空")
        if len(question) < 2:
            raise HTTPException(status_code=400, detail="密保问题至少2个字符")
        if len(self.main._normalize_security_answer(answer)) < 2:
            raise HTTPException(status_code=400, detail="密保答案至少2个字符")

        repo = UserRepository(self.db)
        student = await repo.get_student_by_student_id(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="学生不存在")
        student.security_question = question
        student.security_answer_hash = self.main._hash_security_answer(answer)
        student.updated_at = datetime.now()
        await self._commit()
        return {"message": "密保问题已保存"}

    async def change_student_password(self, payload):
        student_id = normalize_text(payload.student_id)
        old_password = payload.old_password or ""
        new_password = payload.new_password or ""

        if not student_id or not old_password or not new_password:
            raise HTTPException(status_code=400, detail="学号、旧密码和新密码不能为空")
        if len(new_password) < 6:
            raise HTTPException(status_code=400, detail="新密码长度不能少于6位")
        if old_password == new_password:
            raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")

        repo = UserRepository(self.db)
        student = await repo.get_student_by_student_id(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="学生不存在")
        if student.password_hash != self.main._hash_password(old_password):
            raise HTTPException(status_code=401, detail="旧密码错误")

        new_hash = self.main._hash_password(new_password)
        student.password_hash = new_hash
        student.updated_at = datetime.now()
        await self._update_auth_password(student.username or student.student_id, new_hash)
        await self._commit()
        return {"message": "密码修改成功"}


def build_student_service(main_module, db: Optional[AsyncSession] = None) -> StudentService:
    return StudentService(main_module=main_module, db=db)

