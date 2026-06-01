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
    AIInvocationLogRepository,
    AuthUserRepository,
    CourseRepository,
    OperationLogRepository,
    PasswordHashRepository,
    ResourceFolderRepository,
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

DEFAULT_RESOURCE_FOLDER_NAME = "默认文件夹"


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

    def _resource_payload(self, row, route_prefix: str = "/api/admin/resources", course=None) -> dict:
        normalized_prefix = route_prefix.rstrip("/")
        preview_mode = self._resource_preview_mode(row.file_type)
        course_id = getattr(row, "course_id", None)
        folder = None
        if isinstance(course, dict):
            folder = course.get("folder")
            course = course.get("course")
        folder_id = getattr(row, "folder_id", None)
        return {
            "id": row.id,
            "filename": row.filename,
            "file_type": row.file_type,
            "content_type": row.content_type,
            "size": row.size,
            "created_at": row.created_at,
            "created_by": row.created_by,
            "course_id": course_id,
            "course_name": getattr(course, "name", "") if course_id and course else "",
            "course_created_by": getattr(course, "created_by", "") if course_id and course else "",
            "folder_id": folder_id,
            "folder_name": getattr(folder, "name", "") if folder_id and folder else "",
            "owner_username": getattr(folder, "owner_username", "") if folder_id and folder else getattr(row, "created_by", ""),
            "preview_mode": preview_mode,
            "previewable": preview_mode != "unsupported",
            "preview_url": f"{normalized_prefix}/{row.id}/preview",
            "download_url": f"{normalized_prefix}/{row.id}/download",
        }

    @staticmethod
    def _folder_payload(folder, resource_count: int = 0) -> dict:
        return {
            "id": folder.id,
            "name": folder.name,
            "owner_username": folder.owner_username,
            "created_by": folder.created_by,
            "created_at": folder.created_at,
            "updated_at": folder.updated_at,
            "resource_count": resource_count,
            "is_default": normalize_text(folder.name) == DEFAULT_RESOURCE_FOLDER_NAME,
        }

    @staticmethod
    def _sanitize_resource_folder_name(name: str) -> str:
        normalized = normalize_text(name)
        if not normalized:
            raise HTTPException(status_code=400, detail="文件夹名称不能为空")
        if len(normalized) > 80:
            raise HTTPException(status_code=400, detail="文件夹名称不能超过 80 个字符")
        if any(ch in normalized for ch in "/\\"):
            raise HTTPException(status_code=400, detail="文件夹名称不能包含路径分隔符")
        return normalized

    async def _ensure_default_resource_folder(self, owner_username: str, created_by: str = "system"):
        owner = normalize_text(owner_username) or "admin"
        folder_repo = ResourceFolderRepository(self.db)
        existing = await folder_repo.find_by_owner_and_name(owner, DEFAULT_RESOURCE_FOLDER_NAME, course_id=None)
        if existing is not None:
            return existing
        now = datetime.now()
        folder = await folder_repo.create(
            {
                "id": str(uuid.uuid4()),
                "name": DEFAULT_RESOURCE_FOLDER_NAME,
                "owner_username": owner,
                "created_by": normalize_text(created_by) or owner,
                "created_at": now,
                "updated_at": now,
            }
        )
        await self._commit()
        return folder

    async def _migrate_legacy_platform_resources(self) -> None:
        # Root-level resources are now valid, so folderless rows should remain
        # alongside folders instead of being migrated into a default folder.
        return

    async def _folder_map(self, folder_ids: set[str]) -> dict[str, object]:
        if not folder_ids:
            return {}
        folder_repo = ResourceFolderRepository(self.db)
        folders = await folder_repo.list_all()
        return {item.id: item for item in folders if item.id in folder_ids}

    async def _ensure_resource_folder_access(self, folder_id: str, username: str, role: str):
        normalized_folder_id = normalize_text(folder_id)
        if not normalized_folder_id:
            raise HTTPException(status_code=400, detail="请选择资源文件夹")
        folder = await ResourceFolderRepository(self.db).get(normalized_folder_id)
        if folder is None:
            raise HTTPException(status_code=404, detail="资源文件夹不存在")
        if normalize_text(getattr(folder, "course_id", "")):
            raise HTTPException(status_code=404, detail="资源文件夹不存在")
        if role != "admin" and normalize_text(folder.owner_username) != username:
            raise HTTPException(status_code=403, detail="不能访问其他教师的资源文件夹")
        return folder

    async def _resource_row_with_access(self, resource_id: str, username: str, role: str):
        await self._migrate_legacy_platform_resources()
        row = await ResourceRepository(self.db).get(resource_id)
        if not row or getattr(row, "course_id", None):
            raise HTTPException(status_code=404, detail="资源文件不存在")
        folder_id = normalize_text(getattr(row, "folder_id", ""))
        folder = None
        if folder_id:
            folder = await self._ensure_resource_folder_access(folder_id, username, role)
        elif role != "admin" and normalize_text(getattr(row, "created_by", "")) != username:
            raise HTTPException(status_code=403, detail="不能访问其他教师的资源文件")
        if not os.path.exists(row.file_path):
            await ResourceRepository(self.db).delete(resource_id)
            await self._commit()
            raise HTTPException(status_code=404, detail="资源文件不存在")
        return row, folder

    async def _course_map_for_resources(self, rows) -> dict[str, object]:
        course_ids = {normalize_text(getattr(row, "course_id", "")) for row in rows if normalize_text(getattr(row, "course_id", ""))}
        if not course_ids:
            return {}
        course_rows = await CourseRepository(self.db).list_all()
        return {item.id: item for item in course_rows if item.id in course_ids}

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

    @staticmethod
    def _ai_invocation_log_to_dict(record) -> dict:
        return {
            "id": record.id,
            "source": record.source,
            "endpoint": record.endpoint,
            "username": record.username,
            "role": record.role,
            "model": record.model,
            "provider": record.provider,
            "success": bool(record.success),
            "status_code": record.status_code,
            "latency_ms": record.latency_ms,
            "prompt_chars": record.prompt_chars,
            "response_chars": record.response_chars,
            "history_count": record.history_count,
            "used_search": bool(record.used_search),
            "search_provider": record.search_provider,
            "search_depth": record.search_depth,
            "search_cached": bool(record.search_cached),
            "search_result_count": record.search_result_count,
            "cache_hit_count": record.cache_hit_count,
            "error": record.error,
            "request_id": record.request_id,
            "metadata": record.metadata_json or {},
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

    @staticmethod
    def _student_shared_teachers(student_row) -> set[str]:
        extra = getattr(student_row, "extra", {})
        if not isinstance(extra, dict):
            return set()
        raw_shared = extra.get("shared_teachers")
        if not isinstance(raw_shared, list):
            return set()
        return {normalized for item in raw_shared if (normalized := normalize_text(item))}

    @classmethod
    def _student_visible_to_teacher(cls, student_row, teacher_username: str, role: str, class_owner_map: dict[str, str]) -> bool:
        if role == "admin":
            return True
        if cls._student_owner_username(student_row, class_owner_map) == teacher_username:
            return True
        return teacher_username in cls._student_shared_teachers(student_row)

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
        target_class_name = normalize_text(class_record.name)
        for item in student_rows:
            if normalize_text(item.class_name) != target_class_name:
                continue
            owner = self._student_owner_username(item, class_owner_map)
            shared_teachers = self._student_shared_teachers(item)
            if owner == class_owner or class_owner in shared_teachers:
                raise HTTPException(status_code=409, detail="班级已被学生或共享关系使用，无法删除")

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
        existing_student_map = {
            normalize_text(item.student_id or item.username): item
            for item in await user_repo.list_by_role("student")
            if normalize_text(item.student_id or item.username)
        }
        existing_student_ids = set(existing_student_map.keys())
        file_student_ids = set()
        now = datetime.now()

        success_students = []
        errors = []
        skipped_count = 0
        reused_count = 0

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

            if student_id in file_student_ids:
                skipped_count += 1
                errors.append({"row": row_number, "student_id": student_id, "reason": "duplicate student id in system"})
                continue

            file_student_ids.add(student_id)
            if student_id in existing_student_ids:
                existing_row = existing_student_map.get(student_id)
                if existing_row is not None:
                    base_extra = existing_row.extra if isinstance(existing_row.extra, dict) else {}
                    shared_teachers = self._student_shared_teachers(existing_row)
                    shared_teachers.add(normalized_teacher)
                    next_extra = dict(base_extra)
                    next_extra["shared_teachers"] = sorted(shared_teachers)
                    existing_row.extra = next_extra
                    existing_row.updated_at = now
                reused_count += 1
                continue

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
            detail=f"success={len(success_students) + reused_count}, created={len(success_students)}, reused={reused_count}, skipped={skipped_count}, failed={len(errors) - skipped_count}",
        )
        await self._commit()
        failed_count = len(errors) - skipped_count
        return {
            "total_rows": len(parsed_rows),
            "success_count": len(success_students) + reused_count,
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

    async def list_admin_ai_invocation_logs(self, admin_username: str, limit: int = 200):
        await self._ensure_admin(admin_username)
        safe_limit = max(1, min(limit, 1000))
        repo = AIInvocationLogRepository(self.db)
        items = await repo.list_recent(safe_limit)
        total = await repo.count()
        return {
            "total": total,
            "limit": safe_limit,
            "items": [self._ai_invocation_log_to_dict(item) for item in items],
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

    async def list_resource_folders(self, teacher_username: str, owner_username: Optional[str] = None):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        await self._migrate_legacy_platform_resources()

        normalized_owner = normalize_text(owner_username)
        folder_repo = ResourceFolderRepository(self.db)
        if role == "admin":
            if normalized_owner:
                folders = await folder_repo.list_platform_by_owner(normalized_owner)
            else:
                folders = await folder_repo.list_platform_all()
        else:
            folders = await folder_repo.list_platform_by_owner(normalized_teacher)

        counts = {
            item.id: await ResourceRepository(self.db).count_by_folder(item.id)
            for item in folders
        }
        payload_items = [
            self._folder_payload(item, counts.get(item.id, 0))
            for item in folders
            if not (
                normalize_text(item.name) == DEFAULT_RESOURCE_FOLDER_NAME
                and counts.get(item.id, 0) == 0
            )
        ]
        payload_items.sort(key=lambda item: (item["owner_username"].lower(), not item["is_default"], item["name"].lower()))
        return {"total": len(payload_items), "items": payload_items}

    async def create_resource_folder(self, payload):
        normalized_teacher, role = await self._ensure_teacher(payload.teacher_username)
        owner = normalize_text(getattr(payload, "owner_username", "")) if role == "admin" else normalized_teacher
        owner = owner or normalized_teacher
        folder_name = self._sanitize_resource_folder_name(payload.name)

        folder_repo = ResourceFolderRepository(self.db)
        if await folder_repo.find_by_owner_and_name(owner, folder_name, course_id=None):
            raise HTTPException(status_code=409, detail="同名文件夹已存在")
        now = datetime.now()
        folder = await folder_repo.create(
            {
                "id": str(uuid.uuid4()),
                "name": folder_name,
                "owner_username": owner,
                "created_by": normalized_teacher,
                "course_id": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="resource_folders.create",
            target=folder.id,
            detail=f"owner={owner}, name={folder_name}",
        )
        await self._commit()
        return self._folder_payload(folder, 0)

    async def update_resource_folder(self, folder_id: str, payload):
        normalized_teacher, role = await self._ensure_teacher(payload.teacher_username)
        folder = await self._ensure_resource_folder_access(folder_id, normalized_teacher, role)
        folder_name = self._sanitize_resource_folder_name(payload.name)
        existing = await ResourceFolderRepository(self.db).find_by_owner_and_name(folder.owner_username, folder_name, course_id=None)
        if existing is not None and existing.id != folder.id:
            raise HTTPException(status_code=409, detail="同名文件夹已存在")
        folder.name = folder_name
        folder.updated_at = datetime.now()
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="resource_folders.rename",
            target=folder.id,
            detail=f"owner={folder.owner_username}, name={folder_name}",
        )
        await self._commit()
        count = await ResourceRepository(self.db).count_by_folder(folder.id)
        return self._folder_payload(folder, count)

    async def delete_resource_folder(self, folder_id: str, teacher_username: str):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        folder = await self._ensure_resource_folder_access(folder_id, normalized_teacher, role)
        count = await ResourceRepository(self.db).count_by_folder(folder.id)
        if count > 0:
            raise HTTPException(status_code=409, detail="文件夹内还有资源文件，不能删除")
        await ResourceFolderRepository(self.db).delete(folder.id)
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="resource_folders.delete",
            target=folder.id,
            detail=f"owner={folder.owner_username}, name={folder.name}",
        )
        await self._commit()
        return {"message": "资源文件夹已删除", "id": folder_id}

    async def upload_resource_file(
        self,
        teacher_username: str,
        file: UploadFile = File(...),
        folder_id: Optional[str] = None,
        owner_username: Optional[str] = None,
    ):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        await self._migrate_legacy_platform_resources()
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        folder = None
        owner = normalized_teacher
        if folder_id:
            folder = await self._ensure_resource_folder_access(folder_id, normalized_teacher, role)
        else:
            owner = normalize_text(owner_username) if role == "admin" else normalized_teacher
            owner = owner or normalized_teacher

        original_filename = os.path.basename(file.filename)
        extension = os.path.splitext(original_filename)[1].lower()
        if extension not in ALLOWED_RESOURCE_EXTENSIONS:
            raise HTTPException(status_code=400, detail="暂不支持该文件类型")

        safe_filename = original_filename.replace(" ", "_").replace("/", "_").replace("\\", "_")
        resource_id = str(uuid.uuid4())
        if folder is not None:
            upload_dir = os.path.join(UPLOAD_DIR, "resource_folders", folder.id)
        else:
            upload_dir = os.path.join(UPLOAD_DIR, "resource_root", owner)
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f"resource_{resource_id}_{safe_filename}")
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
                "created_by": owner if folder is None else normalized_teacher,
                "course_id": None,
                "folder_id": folder.id if folder is not None else None,
            }
        )
        if folder is not None:
            folder.updated_at = now
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="resources.upload",
            target=resource_id,
            detail=f"folder_id={getattr(folder, 'id', '')}, owner={getattr(folder, 'owner_username', owner)}, filename={original_filename}",
        )
        await self._commit()
        return self._resource_payload(row, course={"folder": folder})

    async def list_resource_files(
        self,
        teacher_username: str,
        name: Optional[str] = None,
        file_type: Optional[str] = None,
        creator: Optional[str] = None,
        course: Optional[str] = None,
        folder_id: Optional[str] = None,
        owner_username: Optional[str] = None,
    ):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        await self._migrate_legacy_platform_resources()

        normalized_name = normalize_text(name).lower()
        normalized_type = normalize_text(file_type).lower().lstrip(".")
        normalized_creator = normalize_text(creator).lower()
        normalized_folder_id = normalize_text(folder_id)
        normalized_owner = normalize_text(owner_username)

        items = []
        rows = [row for row in await ResourceRepository(self.db).list_all() if not getattr(row, "course_id", None)]
        folder_map = await self._folder_map({
            normalize_text(getattr(row, "folder_id", ""))
            for row in rows
            if normalize_text(getattr(row, "folder_id", ""))
        })
        for row in rows:
            row_folder_id = normalize_text(getattr(row, "folder_id", ""))
            folder = folder_map.get(row_folder_id) if row_folder_id else None
            if row_folder_id and folder is None:
                continue
            owner = normalize_text(getattr(folder, "owner_username", "")) if folder is not None else normalize_text(getattr(row, "created_by", ""))
            if role != "admin" and owner != normalized_teacher:
                continue
            if normalized_owner and owner != normalized_owner:
                continue
            if normalized_folder_id:
                if row_folder_id != normalized_folder_id:
                    continue
            elif row_folder_id:
                continue
            if normalized_name and normalized_name not in normalize_text(row.filename).lower():
                continue
            if normalized_type and normalize_text(row.file_type).lower().lstrip(".") != normalized_type:
                continue
            if normalized_creator and normalized_creator not in normalize_text(row.created_by).lower():
                continue
            if not os.path.exists(row.file_path):
                continue
            items.append(row)
        items.sort(key=lambda item: item.created_at or datetime.min, reverse=True)
        payload_items = [
            self._resource_payload(
                item,
                course={"folder": folder_map.get(normalize_text(getattr(item, "folder_id", "")))},
            )
            for item in items
        ]
        return {"total": len(payload_items), "items": payload_items}

    async def get_resource_file_detail(self, resource_id: str, teacher_username: str):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        row, folder = await self._resource_row_with_access(resource_id, normalized_teacher, role)
        payload = self._resource_payload(row, course={"folder": folder})
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
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        row, folder = await self._resource_row_with_access(resource_id, normalized_teacher, role)
        if os.path.exists(row.file_path):
            try:
                os.remove(row.file_path)
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"删除文件失败: {exc}") from exc
        await ResourceRepository(self.db).delete(resource_id)
        if folder is not None:
            folder.updated_at = datetime.now()
        await append_operation_log(
            self.db,
            operator=normalized_teacher,
            action="resources.delete",
            target=resource_id,
            detail=f"folder_id={getattr(folder, 'id', '')}, owner={getattr(folder, 'owner_username', getattr(row, 'created_by', ''))}, filename={row.filename}",
        )
        await self._commit()
        return {"message": "资源文件已删除", "id": resource_id}

    async def preview_resource_file(self, resource_id: str, teacher_username: str):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        row, _ = await self._resource_row_with_access(resource_id, normalized_teacher, role)
        if self._resource_preview_mode(row.file_type) != "pdf":
            raise HTTPException(status_code=400, detail="该文件类型不支持二进制在线预览")
        return FileResponse(
            path=row.file_path,
            filename="document.pdf",
            media_type="application/pdf",
            content_disposition_type="inline",
        )

    async def download_resource_file(self, resource_id: str, teacher_username: str):
        normalized_teacher, role = await self._ensure_teacher(teacher_username)
        row, _ = await self._resource_row_with_access(resource_id, normalized_teacher, role)
        media_type = row.content_type or mimetypes.guess_type(row.filename)[0] or "application/octet-stream"
        return FileResponse(
            path=row.file_path,
            filename=row.filename,
            media_type=media_type,
            content_disposition_type="attachment",
        )
