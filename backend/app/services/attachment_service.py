from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories import AttachmentRepository, ExperimentRepository


class AttachmentService:
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
            raise HTTPException(status_code=500, detail="附件元数据写入失败") from exc

    @staticmethod
    def _to_model(main_module, row):
        return main_module.Attachment(
            id=row.id,
            experiment_id=row.experiment_id,
            filename=row.filename,
            file_path=row.file_path,
            content_type=row.content_type,
            size=row.size,
            created_at=row.created_at,
        )

    async def upload_attachments(self, experiment_id: str, files: list[UploadFile]):
        experiment = await ExperimentRepository(self.db).get(experiment_id)
        if not experiment:
            raise HTTPException(status_code=404, detail="实验不存在")

        repo = AttachmentRepository(self.db)
        uploaded: list = []
        created_paths: list[str] = []
        try:
            for file in files:
                if not file.filename:
                    continue
                att_id = str(uuid.uuid4())
                safe_filename = file.filename.replace(" ", "_")
                file_path = os.path.join(self.main.UPLOAD_DIR, f"{att_id}_{safe_filename}")
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                created_paths.append(file_path)

                payload = {
                    "id": att_id,
                    "experiment_id": experiment_id,
                    "filename": file.filename,
                    "file_path": file_path,
                    "content_type": file.content_type or "application/octet-stream",
                    "size": os.path.getsize(file_path),
                    "created_at": datetime.now(),
                    "updated_at": datetime.now(),
                }
                row = await repo.create(payload)
                uploaded.append(self._to_model(self.main, row))

            await self._commit()
        except Exception as exc:
            await self.db.rollback()
            for path in created_paths:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            raise HTTPException(status_code=500, detail=f"保存附件失败: {exc}") from exc

        return uploaded

    async def list_attachments(self, experiment_id: str):
        rows = await AttachmentRepository(self.db).list_by_experiment(experiment_id)
        return [self._to_model(self.main, row) for row in rows]

    async def get_attachment(self, attachment_id: str):
        row = await AttachmentRepository(self.db).get(attachment_id)
        if not row:
            raise HTTPException(status_code=404, detail="附件不存在")
        return self._to_model(self.main, row)

    async def find_paired_word_attachment(self, attachment_id: str):
        row = await AttachmentRepository(self.db).get(attachment_id)
        if not row:
            raise HTTPException(status_code=404, detail="附件不存在")

        lower_filename = row.filename.lower()
        is_pdf = row.content_type == "application/pdf" or lower_filename.endswith(".pdf")
        if not is_pdf:
            return self._to_model(self.main, row)

        base_name = os.path.splitext(row.filename)[0]
        candidates = await AttachmentRepository(self.db).list_by_experiment(row.experiment_id)
        matched = []
        for item in candidates:
            item_base = os.path.splitext(item.filename)[0]
            item_lower = item.filename.lower()
            if item.id == row.id:
                continue
            if item_base != base_name:
                continue
            if not (item_lower.endswith(".docx") or item_lower.endswith(".doc")):
                continue
            if not os.path.exists(item.file_path):
                continue
            matched.append(item)

        if not matched:
            return self._to_model(self.main, row)

        matched.sort(key=lambda item: 0 if item.filename.lower().endswith(".docx") else 1)
        return self._to_model(self.main, matched[0])


def build_attachment_service(main_module, db: Optional[AsyncSession] = None) -> AttachmentService:
    return AttachmentService(main_module=main_module, db=db)

