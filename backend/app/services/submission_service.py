from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime
from typing import Optional

from fastapi import File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories import (
    ExperimentRepository,
    StudentExperimentRepository,
    SubmissionPdfRepository,
    UserRepository,
)
from .identity_service import ensure_teacher_or_admin, normalize_text, resolve_user_role


class SubmissionService:
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
            raise HTTPException(status_code=500, detail="提交记录写入失败") from exc

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

    def _pdf_status(self, row) -> str:
        if row.reviewed:
            return "已批阅"
        if row.viewed:
            return "已查看"
        return "未查看"

    def _pdf_to_payload(self, row) -> dict:
        annotations = []
        for ann in list(row.annotations or []):
            if not isinstance(ann, dict):
                continue
            annotations.append(
                {
                    "id": ann.get("id") or "",
                    "teacher_username": ann.get("teacher_username") or "",
                    "content": ann.get("content") or "",
                    "created_at": ann.get("created_at"),
                }
            )
        return {
            "id": row.id,
            "student_exp_id": row.submission_id,
            "experiment_id": row.experiment_id,
            "student_id": row.student_id,
            "filename": row.filename,
            "content_type": row.content_type,
            "size": row.size,
            "created_at": row.created_at,
            "download_url": f"/api/student-submissions/{row.id}/download",
            "viewed": row.viewed,
            "viewed_at": row.viewed_at,
            "viewed_by": row.viewed_by,
            "reviewed": row.reviewed,
            "reviewed_at": row.reviewed_at,
            "reviewed_by": row.reviewed_by,
            "review_status": self._pdf_status(row),
            "annotations": annotations,
        }

    async def _ensure_teacher(self, username: str) -> str:
        normalized, _ = await ensure_teacher_or_admin(self.db, username)
        return normalized

    async def start_experiment(self, experiment_id: str, student_id: str):
        student_id = normalize_text(student_id)
        if not student_id:
            raise HTTPException(status_code=400, detail="student_id不能为空")

        exp_row = await ExperimentRepository(self.db).get(experiment_id)
        if not exp_row:
            raise HTTPException(status_code=404, detail="实验不存在")
        student_row = await UserRepository(self.db).get_student_by_student_id(student_id)
        if not student_row:
            raise HTTPException(status_code=404, detail="学生不存在")

        experiment = self._to_experiment_model(exp_row)
        student = self._to_student_record(student_row)
        existing = await StudentExperimentRepository(self.db).get_by_student_and_experiment(student_id, experiment_id)
        student_exp = self._to_student_experiment_model(existing) if existing else None

        if not self.main._is_experiment_visible_to_student(experiment, student):
            raise HTTPException(status_code=403, detail="该实验当前未发布给你")

        user_notebook_name = f"{student_id}_{experiment_id[:8]}.ipynb"
        notebook_relpath = f"work/{user_notebook_name}"

        if student_exp is None:
            payload = {
                "id": str(uuid.uuid4()),
                "experiment_id": experiment_id,
                "student_id": student_id,
                "status": self.main.ExperimentStatus.IN_PROGRESS.value,
                "start_time": datetime.now(),
                "notebook_content": user_notebook_name,
                "submit_time": None,
                "score": None,
                "ai_feedback": "",
                "teacher_comment": "",
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
            row = await StudentExperimentRepository(self.db).create(payload)
            await self._commit()
            student_exp = self._to_student_experiment_model(row)

        user_token_for_url = None
        if self.main._jupyterhub_enabled():
            try:
                if self.main._ensure_user_server_running(student_id):
                    user_token = self.main._create_short_lived_user_token(student_id)
                    if user_token:
                        user_token_for_url = user_token
                        dir_resp = self.main._user_contents_request(student_id, user_token, "GET", "work", params={"content": 0})
                        if dir_resp.status_code == 404:
                            self.main._user_contents_request(student_id, user_token, "PUT", "work", json={"type": "directory"})

                        exists_resp = self.main._user_contents_request(
                            student_id, user_token, "GET", notebook_relpath, params={"content": 0}
                        )
                        if exists_resp.status_code == 404:
                            notebook_json = None
                            template_path = normalize_text(experiment.notebook_path or "")
                            if template_path:
                                tpl_resp = self.main._user_contents_request(
                                    student_id,
                                    user_token,
                                    "GET",
                                    template_path,
                                    params={"content": 1},
                                )
                                if tpl_resp.status_code == 200:
                                    tpl_payload = tpl_resp.json() or {}
                                    if tpl_payload.get("type") == "notebook" and tpl_payload.get("content"):
                                        notebook_json = tpl_payload.get("content")
                            if notebook_json is None:
                                notebook_json = self.main._empty_notebook_json()
                            self.main._user_contents_request(
                                student_id,
                                user_token,
                                "PUT",
                                notebook_relpath,
                                json={"type": "notebook", "format": "json", "content": notebook_json},
                            )
            except Exception as exc:
                print(f"JupyterHub integration error: {exc}")

        jupyter_url = self.main._build_user_lab_url(student_id, path=notebook_relpath, token=user_token_for_url)
        return {"student_experiment_id": student_exp.id, "jupyter_url": jupyter_url, "message": "实验环境已启动"}

    async def submit_experiment(self, student_exp_id: str, submission):
        row = await StudentExperimentRepository(self.db).get(student_exp_id)
        if not row:
            raise HTTPException(status_code=404, detail="学生实验记录不存在")
        student_exp = self._to_student_experiment_model(row)

        try:
            if self.main._jupyterhub_enabled():
                student_id = normalize_text(student_exp.student_id)
                if not student_id:
                    raise ValueError("student_id missing")
                if not self.main._ensure_user_server_running(student_id):
                    raise RuntimeError("JupyterHub server not running")
                user_token = self.main._create_short_lived_user_token(student_id)
                if not user_token:
                    raise RuntimeError("Failed to create user API token")

                target_path = ""
                list_resp = self.main._user_contents_request(student_id, user_token, "GET", "work", params={"content": 1})
                if list_resp.status_code == 200:
                    listing = list_resp.json() or {}
                    entries = listing.get("content") if isinstance(listing, dict) else None
                    if isinstance(entries, list):
                        notebook_entries = []
                        for entry in entries:
                            if not isinstance(entry, dict):
                                continue
                            name = (entry.get("name") or "").lower()
                            etype = entry.get("type") or ""
                            if etype == "notebook" or name.endswith(".ipynb"):
                                modified = entry.get("last_modified") or entry.get("created")
                                dt_value = datetime.min
                                if isinstance(modified, str):
                                    text = modified.replace("Z", "+00:00")
                                    try:
                                        dt_value = datetime.fromisoformat(text)
                                    except ValueError:
                                        dt_value = datetime.min
                                notebook_entries.append((dt_value, entry.get("path") or ""))
                        notebook_entries.sort(key=lambda item: item[0], reverse=True)
                        if notebook_entries and notebook_entries[0][1]:
                            target_path = notebook_entries[0][1]

                if not target_path:
                    assigned_name = f"{student_id}_{student_exp.experiment_id[:8]}.ipynb"
                    target_path = f"work/{assigned_name}"

                file_resp = self.main._user_contents_request(student_id, user_token, "GET", target_path, params={"content": 1})
                if file_resp.status_code != 200:
                    raise RuntimeError(f"Failed to read notebook ({file_resp.status_code})")

                file_payload = file_resp.json() or {}
                notebook_content = file_payload.get("content")
                if isinstance(notebook_content, dict):
                    row.notebook_content = json.dumps(notebook_content, ensure_ascii=False)
                else:
                    row.notebook_content = json.dumps(file_payload, ensure_ascii=False)
            elif submission and submission.notebook_content:
                row.notebook_content = submission.notebook_content
            else:
                row.notebook_content = "Error: JupyterHub not configured, and no notebook content provided"
        except Exception as exc:
            row.notebook_content = f"Error reading notebook: {exc}"
            print(f"Error reading notebook: {exc}")

        row.status = self.main.ExperimentStatus.SUBMITTED.value
        row.submit_time = datetime.now()
        row.updated_at = datetime.now()
        await self._commit()
        return {"message": "实验已提交", "submit_time": row.submit_time}

    async def upload_submission_pdf(self, student_exp_id: str, file: UploadFile = File(...)):
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        is_pdf = file.filename.lower().endswith(".pdf") or (file.content_type or "").lower() == "application/pdf"
        if not is_pdf:
            raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

        row = await StudentExperimentRepository(self.db).get(student_exp_id)
        if not row:
            raise HTTPException(status_code=404, detail="学生实验记录不存在")

        pdf_id = str(uuid.uuid4())
        safe_filename = file.filename.replace(" ", "_")
        file_path = os.path.join(self.main.UPLOAD_DIR, f"submission_{pdf_id}_{safe_filename}")
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"保存PDF失败: {exc}") from exc
        file_size = os.path.getsize(file_path)
        if file_size <= 0:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(status_code=400, detail="PDF文件为空")

        now = datetime.now()
        pdf_row = await SubmissionPdfRepository(self.db).create(
            {
                "id": pdf_id,
                "submission_id": student_exp_id,
                "experiment_id": row.experiment_id,
                "student_id": row.student_id,
                "filename": file.filename,
                "file_path": file_path,
                "content_type": "application/pdf",
                "size": file_size,
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
        await self._commit()
        return {
            "id": pdf_row.id,
            "student_exp_id": pdf_row.submission_id,
            "filename": pdf_row.filename,
            "size": pdf_row.size,
            "created_at": pdf_row.created_at,
            "review_status": self._pdf_status(pdf_row),
            "download_url": f"/api/student-submissions/{pdf_row.id}/download",
        }

    async def list_submission_pdfs(self, student_exp_id: str):
        student_exp = await StudentExperimentRepository(self.db).get(student_exp_id)
        if not student_exp:
            raise HTTPException(status_code=404, detail="学生实验记录不存在")
        rows = await SubmissionPdfRepository(self.db).list_by_submission(student_exp_id)
        return [self._pdf_to_payload(item) for item in rows]

    async def mark_submission_pdf_viewed(self, pdf_id: str, teacher_username: str):
        normalized_teacher = await self._ensure_teacher(teacher_username)
        row = await SubmissionPdfRepository(self.db).get(pdf_id)
        if not row:
            raise HTTPException(status_code=404, detail="提交 PDF 不存在")
        row.viewed = True
        row.viewed_at = datetime.now()
        row.viewed_by = normalized_teacher
        row.updated_at = datetime.now()
        await self._commit()
        return self._pdf_to_payload(row)

    async def add_submission_pdf_annotation(self, pdf_id: str, payload):
        normalized_teacher = await self._ensure_teacher(payload.teacher_username)
        content = normalize_text(payload.content)
        if not content:
            raise HTTPException(status_code=400, detail="批注内容不能为空")

        row = await SubmissionPdfRepository(self.db).get(pdf_id)
        if not row:
            raise HTTPException(status_code=404, detail="提交 PDF 不存在")
        if not row.viewed:
            row.viewed = True
            row.viewed_at = datetime.now()
            row.viewed_by = normalized_teacher
        annotations = list(row.annotations or [])
        annotations.append(
            {
                "id": str(uuid.uuid4()),
                "teacher_username": normalized_teacher,
                "content": content,
                "created_at": datetime.now().isoformat(),
            }
        )
        row.annotations = annotations
        row.updated_at = datetime.now()
        await self._commit()
        return self._pdf_to_payload(row)

    async def get_student_experiments(self, student_id: str):
        rows = await StudentExperimentRepository(self.db).list_by_student(student_id)
        return [self._to_student_experiment_model(row) for row in rows]

    async def get_student_experiment_detail(self, student_exp_id: str):
        row = await StudentExperimentRepository(self.db).get(student_exp_id)
        if not row:
            raise HTTPException(status_code=404, detail="学生实验记录不存在")
        return self._to_student_experiment_model(row)

    async def get_submission_pdf_row(self, pdf_id: str):
        row = await SubmissionPdfRepository(self.db).get(pdf_id)
        if not row:
            raise HTTPException(status_code=404, detail="提交 PDF 不存在")
        return row

    async def download_submission_pdf(self, pdf_id: str, teacher_username: Optional[str] = None):
        row = await SubmissionPdfRepository(self.db).get(pdf_id)
        if not row:
            raise HTTPException(status_code=404, detail="提交 PDF 不存在")
        if teacher_username:
            role = await resolve_user_role(self.db, teacher_username)
            if role in {"teacher", "admin"}:
                row.viewed = True
                row.viewed_at = datetime.now()
                row.viewed_by = normalize_text(teacher_username)
                row.updated_at = datetime.now()
                await self._commit()
        return row

    async def get_experiment_submissions(self, experiment_id: str):
        exp_rows = await StudentExperimentRepository(self.db).list_by_experiment(experiment_id)
        student_rows = await UserRepository(self.db).list_by_role("student")
        student_ids = {normalize_text(item.student_id or item.username) for item in student_rows}

        submissions = []
        pdf_repo = SubmissionPdfRepository(self.db)
        for row in exp_rows:
            if normalize_text(row.student_id) not in student_ids:
                continue
            model = self._to_student_experiment_model(row)
            payload = model.dict()
            pdf_rows = await pdf_repo.list_by_submission(row.id)
            payload["pdf_attachments"] = [self._pdf_to_payload(item) for item in pdf_rows]
            payload["pdf_count"] = len(pdf_rows)
            submissions.append(payload)
        return submissions

    async def grade_experiment(self, student_exp_id: str, score: float, comment: Optional[str], teacher_username: Optional[str]):
        if not (0 <= score <= 100):
            raise HTTPException(status_code=400, detail="分数必须在 0-100 之间")

        reviewer = "teacher"
        if teacher_username:
            role = await resolve_user_role(self.db, teacher_username)
            if role in {"teacher", "admin"}:
                reviewer = normalize_text(teacher_username)

        student_row = await StudentExperimentRepository(self.db).get(student_exp_id)
        if not student_row:
            raise HTTPException(status_code=404, detail="学生实验记录不存在")
        student_row.score = score
        student_row.teacher_comment = comment
        student_row.status = self.main.ExperimentStatus.GRADED.value
        student_row.updated_at = datetime.now()

        pdf_repo = SubmissionPdfRepository(self.db)
        now = datetime.now()
        for item in await pdf_repo.list_by_submission(student_exp_id):
            item.reviewed = True
            item.reviewed_at = now
            item.reviewed_by = reviewer
            if not item.viewed:
                item.viewed = True
                item.viewed_at = now
                item.viewed_by = reviewer
            item.updated_at = now
        await self._commit()
        return {"message": "评分成功", "score": score}


def build_submission_service(main_module, db: Optional[AsyncSession] = None) -> SubmissionService:
    return SubmissionService(main_module=main_module, db=db)

