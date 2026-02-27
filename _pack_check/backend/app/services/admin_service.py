from __future__ import annotations

import mimetypes
import os
import shutil
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Optional
import io

from fastapi import File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import (
    ALLOWED_RESOURCE_EXTENSIONS,
    DEFAULT_ADMISSION_YEAR_OPTIONS,
    DEFAULT_PASSWORD,
    DEFAULT_RESOURCE_ROLE_LIMITS,
    UPLOAD_DIR,
)
from ..repositories import (
    AuthUserRepository,
    OperationLogRepository,
    PasswordHashRepository,
    ResourceRepository,
    SecurityQuestionRepository,
    StudentExperimentRepository,
    SubmissionPdfRepository,
    UserRepository,
)
from .identity_service import ensure_admin, ensure_teacher_or_admin, normalize_text, resolve_user_role
from .kv_policy_service import (
    default_resource_policy_payload,
    get_kv_json,
    normalize_resource_budget,
    normalize_resource_quota,
    size_to_bytes,
    upsert_kv_json,
)
from .operation_log_service import append_operation_log
from .usage_monitor_service import sync_and_build_jupyter_usage_report


class AdminService:
    def __init__(self, main_module, db: AsyncSession):
        self.main = main_module
        self.db = db

    async def _commit(self):
        try:
            await self.db.commit()
        except Exception as exc:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail="管理员操作写入失败") from exc

    async def _ensure_admin(self, username: str) -> str:
        return await ensure_admin(self.db, username)

    async def _ensure_teacher(self, username: str) -> tuple[str, str]:
        return await ensure_teacher_or_admin(self.db, username)

    @staticmethod
    def _admission_year(value) -> str:
        raw = normalize_text(value)
        if not raw:
            return ""
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) == 4 and digits.startswith("20"):
            return digits
        if len(digits) == 2:
            return f"20{digits}"
        return ""

    @staticmethod
    def _infer_admission_year(student_id: str) -> str:
        normalized = normalize_text(student_id)
        if len(normalized) >= 2 and normalized[:2].isdigit():
            return f"20{normalized[:2]}"
        return ""

    @staticmethod
    def _build_class_name(admission_year: str, major_name: str, class_name: str) -> str:
        year = AdminService._admission_year(admission_year)
        major = normalize_text(major_name)
        name = normalize_text(class_name)
        if not (year and major and name):
            return ""
        return f"{year}级{major}{name}"

    @staticmethod
    def _format_admission_year_label(admission_year: str) -> str:
        normalized = AdminService._admission_year(admission_year)
        return f"{normalized}级" if normalized else ""

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

    def _resource_payload(self, row, route_prefix: str = "/api/admin/resources") -> dict:
        normalized_prefix = route_prefix.rstrip("/")
        preview_mode = self._resource_preview_mode(row.file_type)
        return {
            "id": row.id,
            "filename": row.filename,
            "file_type": row.file_type,
            "content_type": row.content_type,
            "size": row.size,
            "created_at": row.created_at,
            "created_by": row.created_by,
            "preview_mode": preview_mode,
            "previewable": preview_mode != "unsupported",
            "preview_url": f"{normalized_prefix}/{row.id}/preview",
            "download_url": f"{normalized_prefix}/{row.id}/download",
        }

    @staticmethod
    def _operation_log_to_dict(record) -> dict:
        return {
            "id": record.id,
            "operator": record.operator,
            "action": record.action,
            "target": record.target,
            "detail": record.detail,
            "success": bool(record.success),
            "created_at": record.created_at.isoformat() if record.created_at else "",
        }

    async def _list_classes(self):
        return await UserRepository(self.db).list_classes()

    async def _accessible_classes(self, teacher_username: str, role: str):
        rows = await self._list_classes()
        if role == "admin":
            return list(rows)
        return [item for item in rows if normalize_text(item.created_by) == teacher_username]

    async def _student_rows(self):
        return await UserRepository(self.db).list_by_role("student")

    async def _class_owner_map(self) -> dict[str, str]:
        rows = await self._list_classes()
        mapping: dict[str, str] = {}
        for row in rows:
            if normalize_text(row.name):
                mapping[row.name] = normalize_text(row.created_by)
        return mapping

    @staticmethod
    def _student_owner_username(student_row, class_owner_map: dict[str, str]) -> str:
        owner = normalize_text(student_row.created_by)
        if owner:
            return owner
        return normalize_text(class_owner_map.get(student_row.class_name, ""))

    @classmethod
    def _student_visible_to_teacher(cls, student_row, teacher_username: str, role: str, class_owner_map: dict[str, str]) -> bool:
        if role == "admin":
            return True
        return cls._student_owner_username(student_row, class_owner_map) == teacher_username

    async def _load_resource_policy(self) -> dict:
        payload = await get_kv_json(self.db, "resource_policy", default_resource_policy_payload())
        defaults = {}
        raw_defaults = payload.get("defaults", {}) if isinstance(payload, dict) else {}
        for role in DEFAULT_RESOURCE_ROLE_LIMITS:
            defaults[role] = normalize_resource_quota((raw_defaults or {}).get(role), role)
        budget = normalize_resource_budget((payload or {}).get("budget", {}))
        overrides = {}
        raw_overrides = (payload or {}).get("overrides", {})
        if isinstance(raw_overrides, dict):
            for username, quota in raw_overrides.items():
                normalized_username = normalize_text(username)
                if not normalized_username:
                    continue
                role_name = await resolve_user_role(self.db, normalized_username) or "student"
                normalized_quota = normalize_resource_quota(quota, role_name)
                normalized_quota["updated_by"] = normalize_text((quota or {}).get("updated_by")) or "system"
                normalized_quota["updated_at"] = normalize_text((quota or {}).get("updated_at")) or datetime.now().isoformat()
                normalized_quota["note"] = normalize_text((quota or {}).get("note"))[:200]
                overrides[normalized_username] = normalized_quota
        return {"defaults": defaults, "budget": budget, "overrides": overrides}

    async def _save_resource_policy(self, payload: dict) -> None:
        await upsert_kv_json(self.db, "resource_policy", payload)

    async def _managed_users(self) -> list[dict]:
        auth_repo = AuthUserRepository(self.db)
        user_repo = UserRepository(self.db)

        users: list[dict] = []
        seen: set[str] = set()

        for row in await auth_repo.list_all():
            username = normalize_text(row.username or row.email)
            role = normalize_text(getattr(row.role, "value", row.role)).lower() or "student"
            if not username or username in seen:
                continue
            seen.add(username)
            users.append(
                {
                    "username": username,
                    "role": role,
                    "real_name": username,
                    "student_id": "",
                    "class_name": "",
                    "organization": "",
                }
            )

        for row in await user_repo.list_by_role("teacher"):
            username = normalize_text(row.username)
            if not username or username in seen:
                continue
            seen.add(username)
            users.append(
                {
                    "username": username,
                    "role": "teacher",
                    "real_name": normalize_text(row.real_name) or username,
                    "student_id": "",
                    "class_name": "",
                    "organization": "",
                }
            )

        for row in await user_repo.list_by_role("student"):
            username = normalize_text(row.username or row.student_id)
            if not username or username in seen:
                continue
            seen.add(username)
            users.append(
                {
                    "username": username,
                    "role": "student",
                    "real_name": normalize_text(row.real_name) or username,
                    "student_id": normalize_text(row.student_id),
                    "class_name": normalize_text(row.class_name),
                    "organization": normalize_text(row.organization),
                }
            )

        role_order = {"admin": 0, "teacher": 1, "student": 2}
        users.sort(key=lambda item: (role_order.get(item["role"], 9), item["username"]))
        return users

    @staticmethod
    def _quota_from_policy(username: str, role: str, policy: dict) -> tuple[dict, str, dict]:
        defaults = policy.get("defaults", {})
        role_key = role if role in DEFAULT_RESOURCE_ROLE_LIMITS else "student"
        base = normalize_resource_quota(defaults.get(role_key), role_key)
        overrides = policy.get("overrides", {})
        custom = overrides.get(username) if isinstance(overrides, dict) else None
        if isinstance(custom, dict):
            quota = normalize_resource_quota(custom, role_key)
            return quota, "custom", {
                "updated_by": normalize_text(custom.get("updated_by")) or "unknown",
                "updated_at": normalize_text(custom.get("updated_at")),
                "note": normalize_text(custom.get("note")),
            }
        return base, "default", {"updated_by": "system", "updated_at": "", "note": ""}

    def _resource_assignment_summary(self, rows: list[dict], budget: dict) -> dict:
        assigned_cpu = 0.0
        assigned_memory = 0
        assigned_storage = 0
        active_cpu = 0.0
        active_memory = 0
        active_storage = 0
        running_servers = 0

        for item in rows:
            quota = item.get("quota", {})
            cpu = float(quota.get("cpu_limit", 0.0) or 0.0)
            memory = size_to_bytes(str(quota.get("memory_limit", "0B")))
            storage = size_to_bytes(str(quota.get("storage_limit", "0B")))
            assigned_cpu += cpu
            assigned_memory += memory
            assigned_storage += storage
            if item.get("server_running"):
                running_servers += 1
                active_cpu += cpu
                active_memory += memory
                active_storage += storage

        budget_cpu = float(budget.get("max_total_cpu", 0.0) or 0.0)
        budget_memory = size_to_bytes(str(budget.get("max_total_memory", "0B")))
        budget_storage = size_to_bytes(str(budget.get("max_total_storage", "0B")))
        return {
            "total_users": len(rows),
            "teachers": len([item for item in rows if item["role"] == "teacher"]),
            "students": len([item for item in rows if item["role"] == "student"]),
            "admins": len([item for item in rows if item["role"] == "admin"]),
            "running_servers": running_servers,
            "assigned_cpu": round(assigned_cpu, 3),
            "assigned_memory_bytes": assigned_memory,
            "assigned_storage_bytes": assigned_storage,
            "active_cpu": round(active_cpu, 3),
            "active_memory_bytes": active_memory,
            "active_storage_bytes": active_storage,
            "budget_cpu": budget_cpu,
            "budget_memory_bytes": budget_memory,
            "budget_storage_bytes": budget_storage,
            "assigned_cpu_ratio": round((assigned_cpu / budget_cpu) if budget_cpu > 0 else 0.0, 4),
            "assigned_memory_ratio": round((assigned_memory / budget_memory) if budget_memory > 0 else 0.0, 4),
            "assigned_storage_ratio": round((assigned_storage / budget_storage) if budget_storage > 0 else 0.0, 4),
        }

    @staticmethod
    def _validate_budget(summary: dict, budget: dict):
        if not budget.get("enforce_budget"):
            return
        if summary["assigned_cpu"] > summary["budget_cpu"] + 1e-9:
            raise HTTPException(status_code=409, detail="分配失败：CPU总配额超出服务器预算")
        if summary["assigned_memory_bytes"] > summary["budget_memory_bytes"]:
            raise HTTPException(status_code=409, detail="分配失败：内存总配额超出服务器预算")
        if summary["assigned_storage_bytes"] > summary["budget_storage_bytes"]:
            raise HTTPException(status_code=409, detail="分配失败：存储总配额超出服务器预算")

    async def _collect_resource_control_users(self, policy: dict) -> list[dict]:
        users = await self._managed_users()
        hub_map = self.main._hub_user_state_map()
        rows = []
        for item in users:
            username = item["username"]
            role = item["role"]
            quota, source, meta = self._quota_from_policy(username, role, policy)
            hub_state = self.main._extract_server_state(hub_map.get(username))
            rows.append(
                {
                    **item,
                    "quota": quota,
                    "quota_source": source,
                    "quota_updated_by": meta.get("updated_by", ""),
                    "quota_updated_at": meta.get("updated_at", ""),
                    "quota_note": meta.get("note", ""),
                    **hub_state,
                }
            )
        return rows
    async def list_admin_teachers(self, admin_username: str):
        await self._ensure_admin(admin_username)
        user_rows = await UserRepository(self.db).list_by_role("teacher")
        auth_rows = await AuthUserRepository(self.db).list_by_role("teacher")
        auth_usernames = {normalize_text(item.username or item.email) for item in auth_rows if normalize_text(item.username or item.email)}

        teachers = {}
        for row in user_rows:
            username = normalize_text(row.username)
            if not username:
                continue
            teachers[username] = {
                "username": username,
                "real_name": normalize_text(row.real_name) or username,
                "source": "registry",
                "created_by": normalize_text(row.created_by) or "system",
                "created_at": row.created_at,
            }
        for username in sorted(auth_usernames):
            teachers.setdefault(
                username,
                {
                    "username": username,
                    "real_name": username,
                    "source": "registry",
                    "created_by": "system",
                    "created_at": None,
                },
            )
        return sorted(teachers.values(), key=lambda item: item["username"])

    async def create_admin_teacher(self, payload):
        admin_username = await self._ensure_admin(payload.admin_username)
        teacher_username = normalize_text(payload.username)
        real_name = normalize_text(payload.real_name) or teacher_username
        if not teacher_username:
            raise HTTPException(status_code=400, detail="教师账号不能为空")

        if await resolve_user_role(self.db, teacher_username) == "admin":
            raise HTTPException(status_code=409, detail="账号与管理员冲突")

        user_repo = UserRepository(self.db)
        if await user_repo.get_student_by_student_id(teacher_username):
            raise HTTPException(status_code=409, detail="账号与学生学号冲突")
        existing_teacher = await user_repo.get_by_username(teacher_username)
        if existing_teacher and normalize_text(existing_teacher.role).lower() == "teacher":
            raise HTTPException(status_code=409, detail="教师账号已存在")

        now = datetime.now()
        teacher_row = await user_repo.upsert(
            {
                "id": existing_teacher.id if existing_teacher else str(uuid.uuid4()),
                "username": teacher_username,
                "role": "teacher",
                "real_name": real_name,
                "student_id": None,
                "class_name": "",
                "admission_year": "",
                "organization": "",
                "phone": "",
                "password_hash": "",
                "security_question": "",
                "security_answer_hash": "",
                "created_by": admin_username,
                "is_active": True,
                "created_at": existing_teacher.created_at if existing_teacher else now,
                "updated_at": now,
                "extra": {},
            }
        )

        default_hash = self.main._hash_password(DEFAULT_PASSWORD)
        auth_repo = AuthUserRepository(self.db)
        await auth_repo.upsert_by_email(
            {
                "id": str(uuid.uuid4()),
                "email": teacher_username,
                "username": teacher_username,
                "role": "teacher",
                "password_hash": default_hash,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )

        await append_operation_log(
            self.db,
            operator=admin_username,
            action="teachers.create",
            target=teacher_username,
            detail=f"real_name={real_name}",
        )
        await self._commit()
        return {
            "message": "教师账号已创建",
            "teacher": {
                "username": teacher_username,
                "real_name": real_name,
                "source": "registry",
                "created_by": admin_username,
                "created_at": teacher_row.created_at,
            },
        }

    async def delete_admin_teacher(self, teacher_username: str, admin_username: str):
        normalized_admin = await self._ensure_admin(admin_username)
        normalized_teacher = normalize_text(teacher_username)
        if not normalized_teacher:
            raise HTTPException(status_code=400, detail="教师账号不能为空")

        user_repo = UserRepository(self.db)
        teacher_row = await user_repo.get_by_username(normalized_teacher)
        if teacher_row is None or normalize_text(teacher_row.role).lower() != "teacher":
            raise HTTPException(status_code=404, detail="教师账号不存在")

        await user_repo.delete(teacher_row.id)
        await AuthUserRepository(self.db).delete_by_username(normalized_teacher)
        await PasswordHashRepository(self.db).delete_by_username(normalized_teacher)
        sec_repo = SecurityQuestionRepository(self.db)
        sec_row = await sec_repo.get_by_username(normalized_teacher)
        if sec_row is not None:
            await self.db.delete(sec_row)

        policy = await self._load_resource_policy()
        overrides = policy.get("overrides", {})
        if isinstance(overrides, dict) and normalized_teacher in overrides:
            overrides.pop(normalized_teacher, None)
            policy["overrides"] = overrides
            await self._save_resource_policy(policy)

        await append_operation_log(
            self.db,
            operator=normalized_admin,
            action="teachers.delete",
            target=normalized_teacher,
        )
        await self._commit()
        return {"message": "教师账号已删除", "username": normalized_teacher}

    async def list_admin_classes(self, teacher_username: str):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        rows = await self._accessible_classes(normalized_teacher, role)
        payload = [
            self.main.ClassRecord(id=row.id, name=row.name, created_by=row.created_by, created_at=row.created_at)
            for row in rows
        ]
        payload.sort(key=lambda item: item.name)
        return payload

    async def download_class_template(self, teacher_username: str, format: str = "xlsx"):
        await self._ensure_teacher(teacher_username)
        template_format = format.lower()
        if template_format == "csv":
            payload = self.main._build_class_csv_template()
            return StreamingResponse(
                io.BytesIO(payload),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": "attachment; filename=class_import_template.csv"},
            )
        if template_format == "xlsx":
            payload = self.main._build_class_xlsx_template()
            return StreamingResponse(
                io.BytesIO(payload),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": "attachment; filename=class_import_template.xlsx"},
            )
        raise HTTPException(status_code=400, detail="format 必须是 xlsx 或 csv")

    async def import_admin_classes(self, teacher_username: str, file: UploadFile = File(...)):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        file_content = await file.read()
        parsed_rows = self.main._parse_class_import_rows(file.filename, file_content)
        now = datetime.now()

        existing_rows = await self._accessible_classes(normalized_teacher, role)
        existing_class_names = {item.name for item in existing_rows}
        file_class_names = set()
        success_classes = []
        errors = []
        skipped_count = 0

        for row_number, row in parsed_rows:
            admission_year_raw, major_name, class_name = row
            normalized_year = self._admission_year(admission_year_raw)
            normalized_major = normalize_text(major_name)
            normalized_class = normalize_text(class_name)

            if not all([normalized_year, normalized_major, normalized_class]):
                errors.append({"row": row_number, "reason": "required fields cannot be empty"})
                continue

            merged_class_name = self._build_class_name(normalized_year, normalized_major, normalized_class)
            if not merged_class_name:
                errors.append({"row": row_number, "reason": "班级名称格式无效"})
                continue

            if merged_class_name in existing_class_names:
                skipped_count += 1
                errors.append({"row": row_number, "reason": f"班级重复（系统中已存在）: {merged_class_name}"})
                continue
            if merged_class_name in file_class_names:
                skipped_count += 1
                errors.append({"row": row_number, "reason": f"班级重复（文件内）: {merged_class_name}"})
                continue

            file_class_names.add(merged_class_name)
            success_classes.append(
                {
                    "id": str(uuid.uuid4()),
                    "name": merged_class_name,
                    "created_by": normalized_teacher,
                    "created_at": now,
                }
            )

        user_repo = UserRepository(self.db)
        for payload in success_classes:
            await user_repo.upsert_class(payload)

        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="classes.import",
            target="classes",
            detail=f"success={len(success_classes)}, skipped={skipped_count}, failed={len(errors) - skipped_count}",
        )
        await self._commit()
        failed_count = len(errors) - skipped_count
        return {
            "total_rows": len(parsed_rows),
            "success_count": len(success_classes),
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "errors": errors,
        }

    async def create_admin_class(self, payload):
        normalized_teacher, role = await self._ensure_teacher(payload.teacher_username)
        class_name = normalize_text(payload.name)
        if not class_name:
            raise HTTPException(status_code=400, detail="班级名称不能为空")

        existing_rows = await self._accessible_classes(normalized_teacher, role)
        if any(item.name == class_name for item in existing_rows):
            raise HTTPException(status_code=400, detail="班级已存在")

        record = {
            "id": str(uuid.uuid4()),
            "name": class_name,
            "created_by": normalized_teacher,
            "created_at": datetime.now(),
        }
        await UserRepository(self.db).upsert_class(record)
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="classes.create",
            target=class_name,
            detail=f"class_id={record['id']}",
        )
        await self._commit()
        return self.main.ClassRecord(**record)

    async def delete_admin_class(self, class_id: str, teacher_username: str):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        class_rows = await self._list_classes()
        class_record = next((item for item in class_rows if item.id == class_id), None)
        if class_record is None:
            raise HTTPException(status_code=404, detail="班级不存在")

        class_owner = normalize_text(class_record.created_by)
        if role != "admin" and class_owner != normalized_teacher:
            raise HTTPException(status_code=403, detail="不能删除其他教师创建的班级")

        class_owner_map = await self._class_owner_map()
        student_rows = await self._student_rows()
        for item in student_rows:
            owner = self._student_owner_username(item, class_owner_map)
            if item.class_name == class_record.name and owner == class_owner:
                raise HTTPException(status_code=409, detail="班级已被学生使用，无法删除")

        await self.db.delete(class_record)
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="classes.delete",
            target=class_record.name,
            detail=f"class_id={class_id}",
        )
        await self._commit()
        return {"message": "班级已删除"}

    async def download_student_template(self, teacher_username: str, format: str = "xlsx"):
        await self._ensure_teacher(teacher_username)
        template_format = format.lower()
        if template_format == "csv":
            payload = self.main._build_csv_template()
            return StreamingResponse(
                io.BytesIO(payload),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": "attachment; filename=student_import_template.csv"},
            )
        if template_format == "xlsx":
            payload = self.main._build_xlsx_template()
            return StreamingResponse(
                io.BytesIO(payload),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": "attachment; filename=student_import_template.xlsx"},
            )
        raise HTTPException(status_code=400, detail="format 必须是 xlsx 或 csv")

    async def import_students(self, teacher_username: str, file: UploadFile = File(...)):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        file_content = await file.read()
        parsed_rows = self.main._parse_student_import_rows(file.filename, file_content)

        class_names = {item.name for item in await self._accessible_classes(normalized_teacher, role)}
        user_repo = UserRepository(self.db)
        existing_student_ids = {normalize_text(item.student_id or item.username) for item in await user_repo.list_by_role("student")}
        file_student_ids = set()
        now = datetime.now()

        success_students = []
        errors = []
        skipped_count = 0

        for row_number, row in parsed_rows:
            student_id, real_name, class_name, organization, phone, admission_year_raw = row
            admission_year = self._admission_year(admission_year_raw) or self._infer_admission_year(student_id)
            if not all([student_id, real_name, class_name, organization, phone]):
                errors.append({"row": row_number, "student_id": student_id, "reason": "字段不能为空"})
                continue
            if not admission_year:
                errors.append({"row": row_number, "student_id": student_id, "reason": "入学年级无效"})
                continue
            if class_name not in class_names:
                errors.append({"row": row_number, "student_id": student_id, "reason": "class does not exist"})
                continue

            role_value = await resolve_user_role(self.db, student_id)
            if role_value in {"teacher", "admin"}:
                errors.append({"row": row_number, "student_id": student_id, "reason": "student id conflicts with teacher account"})
                continue

            if student_id in existing_student_ids:
                skipped_count += 1
                errors.append({"row": row_number, "student_id": student_id, "reason": "学号重复（系统中已存在）"})
                continue
            if student_id in file_student_ids:
                skipped_count += 1
                errors.append({"row": row_number, "student_id": student_id, "reason": "duplicate student id in system"})
                continue

            file_student_ids.add(student_id)
            success_students.append(
                {
                    "id": str(uuid.uuid4()),
                    "username": student_id,
                    "role": "student",
                    "real_name": real_name,
                    "student_id": student_id,
                    "class_name": class_name,
                    "admission_year": admission_year,
                    "organization": organization,
                    "phone": phone,
                    "password_hash": self.main._hash_password(DEFAULT_PASSWORD),
                    "security_question": "",
                    "security_answer_hash": "",
                    "created_by": normalized_teacher,
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                    "extra": {},
                }
            )

        auth_repo = AuthUserRepository(self.db)
        default_hash = self.main._hash_password(DEFAULT_PASSWORD)
        for payload in success_students:
            await user_repo.upsert(payload)
            await auth_repo.upsert_by_email(
                {
                    "id": str(uuid.uuid4()),
                    "email": payload["username"],
                    "username": payload["username"],
                    "role": "student",
                    "password_hash": default_hash,
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                }
            )

        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="students.import",
            target="students",
            detail=f"success={len(success_students)}, skipped={skipped_count}, failed={len(errors) - skipped_count}",
        )
        await self._commit()
        failed_count = len(errors) - skipped_count
        return {
            "total_rows": len(parsed_rows),
            "success_count": len(success_students),
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "errors": errors,
        }

    async def list_admin_students(
        self,
        teacher_username: str,
        keyword: str = "",
        class_name: str = "",
        admission_year: str = "",
        page: int = 1,
        page_size: int = 20,
    ):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        page = max(page, 1)
        page_size = max(1, min(page_size, 100))

        normalized_keyword = normalize_text(keyword).lower()
        normalized_class_name = normalize_text(class_name)
        normalized_admission_year = self._admission_year(admission_year)
        class_owner_map = await self._class_owner_map()
        students = [
            item
            for item in await self._student_rows()
            if self._student_visible_to_teacher(item, normalized_teacher, role, class_owner_map)
        ]

        if normalized_keyword:
            students = [
                item
                for item in students
                if normalized_keyword in normalize_text(item.student_id).lower()
                or normalized_keyword in normalize_text(item.real_name).lower()
            ]

        if normalized_class_name:
            students = [item for item in students if item.class_name == normalized_class_name]
        if normalized_admission_year:
            students = [
                item for item in students if self._admission_year(item.admission_year) == normalized_admission_year
            ]

        students.sort(key=lambda item: item.created_at or datetime.min, reverse=True)
        total = len(students)
        start = (page - 1) * page_size
        end = start + page_size
        paged_students = students[start:end]
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "student_id": item.student_id,
                    "username": item.username,
                    "real_name": item.real_name,
                    "class_name": item.class_name,
                    "admission_year": self._admission_year(item.admission_year),
                    "admission_year_label": self._format_admission_year_label(item.admission_year),
                    "organization": item.organization,
                    "phone": item.phone,
                    "role": item.role,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                }
                for item in paged_students
            ],
        }

    async def list_admission_year_options(self, teacher_username: str):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        class_owner_map = await self._class_owner_map()
        year_set = {year for year in DEFAULT_ADMISSION_YEAR_OPTIONS}
        for item in await self._student_rows():
            if not self._student_visible_to_teacher(item, normalized_teacher, role, class_owner_map):
                continue
            normalized = self._admission_year(item.admission_year)
            if normalized:
                year_set.add(normalized)
        years = sorted(year_set)
        return [{"value": year, "label": f"{year}级"} for year in years]

    async def _delete_student_related_rows(self, student_row):
        pdf_repo = SubmissionPdfRepository(self.db)
        for pdf in await pdf_repo.list_by_student(student_row.student_id or student_row.username):
            if pdf.file_path and os.path.exists(pdf.file_path):
                try:
                    os.remove(pdf.file_path)
                except OSError:
                    pass
            await pdf_repo.delete(pdf.id)
        await StudentExperimentRepository(self.db).delete_by_student(student_row.student_id or student_row.username)

    async def reset_student_password(self, student_id: str, teacher_username: str):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        repo = UserRepository(self.db)
        student = await repo.get_student_by_student_id(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="学生不存在")

        class_owner_map = await self._class_owner_map()
        if not self._student_visible_to_teacher(student, normalized_teacher, role, class_owner_map):
            raise HTTPException(status_code=403, detail="不能操作其他教师的学生")

        new_hash = self.main._hash_password(DEFAULT_PASSWORD)
        student.password_hash = new_hash
        student.updated_at = datetime.now()

        auth_repo = AuthUserRepository(self.db)
        auth_user = await auth_repo.get_by_login_identifier(student.username or student.student_id)
        if auth_user is not None:
            auth_user.password_hash = new_hash
            auth_user.updated_at = datetime.now()

        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="students.reset_password",
            target=student_id,
            detail="密码重置为默认密码",
        )
        await self._commit()
        return {"message": "密码已重置", "student_id": student_id}

    async def delete_student(self, student_id: str, teacher_username: str):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        repo = UserRepository(self.db)
        student = await repo.get_student_by_student_id(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="学生不存在")

        class_owner_map = await self._class_owner_map()
        if not self._student_visible_to_teacher(student, normalized_teacher, role, class_owner_map):
            raise HTTPException(status_code=403, detail="不能删除其他教师的学生")

        await self._delete_student_related_rows(student)
        await repo.delete(student.id)
        await AuthUserRepository(self.db).delete_by_username(student.username or student.student_id)

        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="students.delete",
            target=student_id,
            detail="删除学生账号",
        )
        await self._commit()
        return {"message": "学生已删除", "student_id": student_id}

    async def batch_delete_students(self, teacher_username: str, class_name: str = ""):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        normalized_class_name = normalize_text(class_name)
        if not normalized_class_name:
            raise HTTPException(status_code=400, detail="class_name不能为空")

        class_owner_map = await self._class_owner_map()
        target_records = [
            item
            for item in await self._student_rows()
            if item.class_name == normalized_class_name
            and self._student_visible_to_teacher(item, normalized_teacher, role, class_owner_map)
        ]
        target_ids = [item.student_id for item in target_records]

        user_repo = UserRepository(self.db)
        auth_repo = AuthUserRepository(self.db)
        for student in target_records:
            await self._delete_student_related_rows(student)
            await user_repo.delete(student.id)
            await auth_repo.delete_by_username(student.username or student.student_id)

        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="students.batch_delete",
            target=normalized_class_name,
            detail=f"class_name={normalized_class_name}, deleted={len(target_ids)}",
        )
        await self._commit()
        return {
            "message": "批量删除完成",
            "class_name": normalized_class_name,
            "deleted_count": len(target_ids),
            "deleted_student_ids": target_ids,
        }
    async def get_resource_control_overview(self, admin_username: str):
        await self._ensure_admin(admin_username)
        policy = await self._load_resource_policy()
        budget = normalize_resource_budget(policy.get("budget", {}))
        users = await self._collect_resource_control_users(policy)
        summary = self._resource_assignment_summary(users, budget)
        return {
            "budget": budget,
            "summary": summary,
            "defaults": policy.get("defaults", deepcopy(DEFAULT_RESOURCE_ROLE_LIMITS)),
            "users": users,
        }

    async def get_admin_usage_monitor(self, admin_username: str):
        await self._ensure_admin(admin_username)
        managed_users = await self._managed_users()
        user_roles = {
            item["username"]: item["role"]
            for item in managed_users
            if item.get("role") in {"teacher", "student", "admin"} and normalize_text(item.get("username"))
        }
        report, changed = await sync_and_build_jupyter_usage_report(
            self.db,
            main_module=self.main,
            user_roles=user_roles,
        )
        if changed:
            await self._commit()
        return report

    async def upsert_user_resource_quota(self, username: str, payload):
        normalized_admin = await self._ensure_admin(payload.admin_username)
        target_user = normalize_text(username)
        if not target_user:
            raise HTTPException(status_code=400, detail="username不能为空")

        policy = await self._load_resource_policy()
        user_map = {item["username"]: item for item in await self._managed_users()}
        user_item = user_map.get(target_user)
        if not user_item:
            raise HTTPException(status_code=404, detail="用户不存在，无法设置资源配额")

        role = user_item["role"]
        quota = normalize_resource_quota(
            {
                "cpu_limit": payload.cpu_limit,
                "memory_limit": payload.memory_limit,
                "storage_limit": payload.storage_limit,
            },
            role,
        )
        now_iso = datetime.now().isoformat()
        next_override = {
            **quota,
            "updated_by": normalized_admin,
            "updated_at": now_iso,
            "note": normalize_text(payload.note)[:200],
        }

        simulated = deepcopy(policy)
        simulated_overrides = dict(simulated.get("overrides", {}))
        simulated_overrides[target_user] = next_override
        simulated["overrides"] = simulated_overrides
        simulated["budget"] = normalize_resource_budget(simulated.get("budget", {}))

        simulated_rows = await self._collect_resource_control_users(simulated)
        simulated_summary = self._resource_assignment_summary(simulated_rows, simulated["budget"])
        self._validate_budget(simulated_summary, simulated["budget"])

        await self._save_resource_policy(simulated)
        await append_operation_log(
            self.db,
            operator=normalized_admin,
            action="resource_quota.update",
            target=target_user,
            detail=f"cpu={quota['cpu_limit']}, memory={quota['memory_limit']}, storage={quota['storage_limit']}",
        )
        await self._commit()
        target_row = next((item for item in simulated_rows if item["username"] == target_user), None)
        return {
            "message": "资源配额已更新",
            "item": target_row,
            "summary": simulated_summary,
        }

    async def delete_user_resource_quota_override(self, username: str, admin_username: str):
        normalized_admin = await self._ensure_admin(admin_username)
        target_user = normalize_text(username)
        if not target_user:
            raise HTTPException(status_code=400, detail="username不能为空")

        if target_user not in {item["username"] for item in await self._managed_users()}:
            raise HTTPException(status_code=404, detail="用户不存在")

        policy = await self._load_resource_policy()
        simulated = deepcopy(policy)
        simulated_overrides = dict(simulated.get("overrides", {}))
        simulated_overrides.pop(target_user, None)
        simulated["overrides"] = simulated_overrides
        simulated["budget"] = normalize_resource_budget(simulated.get("budget", {}))

        simulated_rows = await self._collect_resource_control_users(simulated)
        simulated_summary = self._resource_assignment_summary(simulated_rows, simulated["budget"])
        self._validate_budget(simulated_summary, simulated["budget"])

        await self._save_resource_policy(simulated)
        await append_operation_log(
            self.db,
            operator=normalized_admin,
            action="resource_quota.reset",
            target=target_user,
            detail="恢复默认资源配额",
        )
        await self._commit()
        return {
            "message": "该用户已恢复默认资源配额",
            "username": target_user,
            "summary": simulated_summary,
        }

    async def update_resource_budget(self, payload):
        normalized_admin = await self._ensure_admin(payload.admin_username)
        policy = await self._load_resource_policy()
        budget = normalize_resource_budget(
            {
                "max_total_cpu": payload.max_total_cpu,
                "max_total_memory": payload.max_total_memory,
                "max_total_storage": payload.max_total_storage,
                "enforce_budget": payload.enforce_budget,
                "updated_by": normalized_admin,
                "updated_at": datetime.now().isoformat(),
            }
        )

        rows = await self._collect_resource_control_users(policy)
        summary = self._resource_assignment_summary(rows, budget)
        self._validate_budget(summary, budget)
        policy["budget"] = budget
        await self._save_resource_policy(policy)

        await append_operation_log(
            self.db,
            operator=normalized_admin,
            action="resource_budget.update",
            target="server-budget",
            detail=(
                f"cpu={budget['max_total_cpu']}, memory={budget['max_total_memory']}, "
                f"storage={budget['max_total_storage']}, enforce={budget['enforce_budget']}"
            ),
        )
        await self._commit()
        return {"message": "服务器资源预算已更新", "budget": budget, "summary": summary}

    async def list_admin_operation_logs(self, admin_username: str, limit: int = 200):
        await self._ensure_admin(admin_username)
        safe_limit = max(1, min(limit, 1000))
        repo = OperationLogRepository(self.db)
        items = await repo.list_recent(safe_limit)
        total = await repo.count()
        return {
            "total": total,
            "limit": safe_limit,
            "items": [self._operation_log_to_dict(item) for item in items],
        }

    async def cleanup_admin_operation_logs(self, admin_username: str, keep_recent: int = 200):
        normalized_admin = await self._ensure_admin(admin_username)
        safe_keep = max(0, min(keep_recent, 1000))
        repo = OperationLogRepository(self.db)
        removed_count = await repo.delete_except_recent(safe_keep)
        await append_operation_log(
            self.db,
            operator=normalized_admin,
            action="operation_logs.cleanup",
            target="operation-logs",
            detail=f"removed={removed_count}, keep_recent={safe_keep}",
        )
        await self._commit()
        remaining = await repo.count()
        return {
            "message": "操作日志清理完成",
            "removed_count": removed_count,
            "remaining": remaining,
        }

    async def upload_resource_file(self, teacher_username: str, file: UploadFile = File(...)):
        normalized_teacher, _ = await self._ensure_teacher(teacher_username)
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        original_filename = os.path.basename(file.filename)
        extension = os.path.splitext(original_filename)[1].lower()
        if extension not in ALLOWED_RESOURCE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="暂不支持该文件类型")

        safe_filename = original_filename.replace(" ", "_").replace("/", "_").replace("\\", "_")
        resource_id = str(uuid.uuid4())
        file_path = os.path.join(UPLOAD_DIR, f"resource_{resource_id}_{safe_filename}")
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
        row = await ResourceRepository(self.db).create(
            {
                "id": resource_id,
                "filename": original_filename,
                "file_path": file_path,
                "file_type": extension.lstrip("."),
                "content_type": inferred_content_type,
                "size": file_size,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "created_by": normalized_teacher,
            }
        )
        await self._commit()
        return self._resource_payload(row)

    async def list_resource_files(self, teacher_username: str, name: Optional[str] = None, file_type: Optional[str] = None):
        await self._ensure_teacher(teacher_username)
        normalized_name = normalize_text(name).lower()
        normalized_type = normalize_text(file_type).lower().lstrip(".")

        items = []
        for row in await ResourceRepository(self.db).list_all():
            if normalized_name and normalized_name not in normalize_text(row.filename).lower():
                continue
            if normalized_type and normalize_text(row.file_type).lower().lstrip(".") != normalized_type:
                continue
            if not os.path.exists(row.file_path):
                continue
            items.append(row)
        items.sort(key=lambda item: item.created_at or datetime.min, reverse=True)
        payload_items = [self._resource_payload(item) for item in items]
        return {"total": len(payload_items), "items": payload_items}

    async def get_resource_file_detail(self, resource_id: str, teacher_username: str):
        await self._ensure_teacher(teacher_username)
        row = await ResourceRepository(self.db).get(resource_id)
        if not row:
            raise HTTPException(status_code=404, detail="资源文件不存在")
        if not os.path.exists(row.file_path):
            await ResourceRepository(self.db).delete(resource_id)
            await self._commit()
            raise HTTPException(status_code=404, detail="资源文件不存在")

        payload = self._resource_payload(row)
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

    async def delete_resource_file(self, resource_id: str, teacher_username: str):
        await self._ensure_teacher(teacher_username)
        row = await ResourceRepository(self.db).get(resource_id)
        if not row:
            raise HTTPException(status_code=404, detail="资源文件不存在")
        if os.path.exists(row.file_path):
            try:
                os.remove(row.file_path)
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"删除文件失败: {exc}") from exc
        await ResourceRepository(self.db).delete(resource_id)
        await self._commit()
        return {"message": "资源文件已删除", "id": resource_id}

    async def preview_resource_file(self, resource_id: str, teacher_username: str):
        await self._ensure_teacher(teacher_username)
        row = await ResourceRepository(self.db).get(resource_id)
        if not row or not os.path.exists(row.file_path):
            raise HTTPException(status_code=404, detail="资源文件不存在")
        if self._resource_preview_mode(row.file_type) != "pdf":
            raise HTTPException(status_code=400, detail="该文件类型不支持二进制在线预览")
        return FileResponse(
            path=row.file_path,
            filename="document.pdf",
            media_type="application/pdf",
            content_disposition_type="inline",
        )

    async def download_resource_file(self, resource_id: str, teacher_username: str):
        await self._ensure_teacher(teacher_username)
        row = await ResourceRepository(self.db).get(resource_id)
        if not row or not os.path.exists(row.file_path):
            raise HTTPException(status_code=404, detail="资源文件不存在")
        media_type = row.content_type or mimetypes.guess_type(row.filename)[0] or "application/octet-stream"
        return FileResponse(
            path=row.file_path,
            filename=row.filename,
            media_type=media_type,
            content_disposition_type="attachment",
        )
