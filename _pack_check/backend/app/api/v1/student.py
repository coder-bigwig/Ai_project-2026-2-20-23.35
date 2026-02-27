import mimetypes
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db
from ...repositories import ResourceRepository
from ...services.identity_service import ensure_student_user, normalize_text
from ...services.student_service import build_student_service


def _get_main_module():
    from ... import main
    return main


main = _get_main_module()
router = APIRouter()


async def get_student_courses_with_status(
    student_id: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_student_service(main_module=main, db=db)
    return await service.get_student_courses_with_status(student_id=student_id)


async def get_student_profile(
    student_id: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_student_service(main_module=main, db=db)
    return await service.get_student_profile(student_id=student_id)


async def upsert_student_security_question(
    payload: main.StudentSecurityQuestionUpdateRequest,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_student_service(main_module=main, db=db)
    return await service.upsert_student_security_question(payload=payload)


async def change_student_password(
    payload: main.StudentPasswordChangeRequest,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_student_service(main_module=main, db=db)
    return await service.change_student_password(payload=payload)


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


async def list_student_resource_files(
    student_id: str,
    name: Optional[str] = None,
    file_type: Optional[str] = None,
    db: Optional[AsyncSession] = Depends(get_db),
):
    if db is None:
        raise HTTPException(status_code=503, detail="PostgreSQL session unavailable")
    await ensure_student_user(db, student_id)

    normalized_name = normalize_text(name).lower()
    normalized_type = normalize_text(file_type).lower().lstrip(".")
    rows = await ResourceRepository(db).list_all()

    payload_items = []
    for row in rows:
        if normalized_name and normalized_name not in normalize_text(row.filename).lower():
            continue
        if normalized_type and normalize_text(row.file_type).lower().lstrip(".") != normalized_type:
            continue
        if not main.os.path.exists(row.file_path):
            continue
        preview_mode = _resource_preview_mode(row.file_type)
        payload_items.append(
            {
                "id": row.id,
                "filename": row.filename,
                "file_type": row.file_type,
                "content_type": row.content_type,
                "size": row.size,
                "created_at": row.created_at,
                "created_by": row.created_by,
                "preview_mode": preview_mode,
                "previewable": preview_mode != "unsupported",
                "preview_url": f"/api/student/resources/{row.id}/preview",
                "download_url": f"/api/student/resources/{row.id}/download",
            }
        )
    payload_items.sort(key=lambda item: item.get("created_at"), reverse=True)
    return {"total": len(payload_items), "items": payload_items}


async def get_student_resource_file_detail(
    resource_id: str,
    student_id: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    if db is None:
        raise HTTPException(status_code=503, detail="PostgreSQL session unavailable")
    await ensure_student_user(db, student_id)
    row = await ResourceRepository(db).get(resource_id)
    if not row or not main.os.path.exists(row.file_path):
        raise HTTPException(status_code=404, detail="资源文件不存在")

    preview_mode = _resource_preview_mode(row.file_type)
    payload = {
        "id": row.id,
        "filename": row.filename,
        "file_type": row.file_type,
        "content_type": row.content_type,
        "size": row.size,
        "created_at": row.created_at,
        "created_by": row.created_by,
        "preview_mode": preview_mode,
        "previewable": preview_mode != "unsupported",
        "preview_url": f"/api/student/resources/{row.id}/preview",
        "download_url": f"/api/student/resources/{row.id}/download",
    }
    if preview_mode in {"markdown", "text"}:
        payload["preview_text"] = main._read_text_preview(row.file_path)
    elif preview_mode == "docx":
        try:
            payload["preview_text"] = main._read_docx_preview(row.file_path)
        except HTTPException as exc:
            payload["preview_text"] = ""
            payload["preview_error"] = normalize_text(getattr(exc, "detail", "")) or "Word 文档预览解析失败"
        except Exception:
            payload["preview_text"] = ""
            payload["preview_error"] = "Word 文档预览解析失败"
    else:
        payload["preview_text"] = ""
    return payload


async def preview_student_resource_file(
    resource_id: str,
    student_id: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    if db is None:
        raise HTTPException(status_code=503, detail="PostgreSQL session unavailable")
    await ensure_student_user(db, student_id)
    row = await ResourceRepository(db).get(resource_id)
    if not row or not main.os.path.exists(row.file_path):
        raise HTTPException(status_code=404, detail="资源文件不存在")

    if _resource_preview_mode(row.file_type) != "pdf":
        raise HTTPException(status_code=400, detail="该文件类型不支持二进制在线预览")

    return FileResponse(
        path=row.file_path,
        filename="document.pdf",
        media_type="application/pdf",
        content_disposition_type="inline",
    )


async def download_student_resource_file(
    resource_id: str,
    student_id: str,
    db: Optional[AsyncSession] = Depends(get_db),
):
    if db is None:
        raise HTTPException(status_code=503, detail="PostgreSQL session unavailable")
    await ensure_student_user(db, student_id)
    row = await ResourceRepository(db).get(resource_id)
    if not row or not main.os.path.exists(row.file_path):
        raise HTTPException(status_code=404, detail="资源文件不存在")

    media_type = row.content_type or mimetypes.guess_type(row.filename)[0] or "application/octet-stream"
    return FileResponse(
        path=row.file_path,
        filename=row.filename,
        media_type=media_type,
        content_disposition_type="attachment",
    )


router.add_api_route("/api/student/courses-with-status", get_student_courses_with_status, methods=["GET"])
router.add_api_route("/api/student/profile", get_student_profile, methods=["GET"])
router.add_api_route("/api/student/profile/security-question", upsert_student_security_question, methods=["POST"])
router.add_api_route("/api/student/profile/change-password", change_student_password, methods=["POST"])
router.add_api_route("/api/student/resources", list_student_resource_files, methods=["GET"])
router.add_api_route("/api/student/resources/{resource_id}", get_student_resource_file_detail, methods=["GET"])
router.add_api_route("/api/student/resources/{resource_id}/preview", preview_student_resource_file, methods=["GET"])
router.add_api_route("/api/student/resources/{resource_id}/download", download_student_resource_file, methods=["GET"])
