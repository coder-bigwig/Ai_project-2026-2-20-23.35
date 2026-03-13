from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db
from ...repositories.security import SecurityQuestionRepository
from ...repositories.users import UserRepository
from ...services.auth_service import AuthService
from ...services.identity_service import normalize_text, resolve_user_role
from ...services.operation_log_service import append_operation_log

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class ForgotPasswordResetRequest(BaseModel):
    username: str
    security_answer: str
    new_password: str


def _get_main_module():
    from ... import main

    return main


def _role_value(role) -> str:
    if hasattr(role, "value"):
        return str(role.value or "")
    return str(role or "")


async def _postgres_login_or_none(main, db: AsyncSession, username: str, password: str):
    service = AuthService(db=db, password_hasher=main._hash_password)
    auth_user = await service.authenticate(identifier=username, password=password)
    if auth_user is None:
        return None

    account_username = normalize_text(auth_user.username or auth_user.email)
    role = _role_value(auth_user.role).lower()
    if role in {"admin", "teacher"}:
        return {
            "username": account_username,
            "role": role,
            "ai_session_token": main._create_ai_session_token(account_username),
            "force_security_setup": False,
        }

    user_repo = UserRepository(db)
    student = await user_repo.get_by_username(account_username)
    if student is None:
        student = await user_repo.get_student_by_student_id(account_username)
    if student is None:
        return None

    security_question_set = bool(main._normalize_security_question(student.security_question or ""))
    student_username = normalize_text(student.username or student.student_id or account_username)
    student_id = normalize_text(student.student_id or student_username)
    return {
        "username": student_username,
        "role": "student",
        "ai_session_token": main._create_ai_session_token(student_username),
        "student_id": student_id,
        "real_name": student.real_name,
        "class_name": student.class_name,
        "organization": student.organization,
        "major": student.organization,
        "admission_year": main._normalize_admission_year(student.admission_year),
        "security_question_set": security_question_set,
        "force_security_setup": not security_question_set,
    }


async def _append_reset_password_log(db: AsyncSession, username: str, role: str):
    normalized_role = normalize_text(role).lower()
    if normalized_role in {"teacher", "admin"}:
        await append_operation_log(
            db,
            operator=username,
            action="accounts.reset_password_with_security",
            target=username,
            detail="教师/管理员通过密保重置密码",
        )
        return
    await append_operation_log(
        db,
        operator=username,
        action="students.reset_password_with_security",
        target=username,
        detail="学生通过密保重置密码",
    )


@router.post("/api/auth/login")
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """统一登录入口"""
    main = _get_main_module()
    username = normalize_text(payload.username)
    password = payload.password or ""
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")

    result = await _postgres_login_or_none(main, db=db, username=username, password=password)
    if result is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return result


@router.get("/api/auth/security-question")
async def get_security_question(username: str, db: AsyncSession = Depends(get_db)):
    main = _get_main_module()
    normalized_username = normalize_text(username)
    if not normalized_username:
        raise HTTPException(status_code=400, detail="用户名不能为空")

    auth_service = AuthService(db=db, password_hasher=main._hash_password)
    auth_user = await auth_service.get_user_by_identifier(normalized_username)

    if auth_user is not None:
        account_username = normalize_text(auth_user.username or auth_user.email or normalized_username)
        role = _role_value(auth_user.role).lower()
        if role in {"teacher", "admin"}:
            sec_repo = SecurityQuestionRepository(db)
            row = await sec_repo.get_by_username(account_username)
            question = main._normalize_security_question(row.question if row else "")
            if not question:
                raise HTTPException(status_code=404, detail="该账号未设置密保问题")
            return {
                "username": account_username,
                "role": "admin" if role == "admin" else "teacher",
                "security_question": question,
            }

    user_repo = UserRepository(db)
    student = await user_repo.get_student_by_student_id(normalized_username)
    if student is None:
        student = await user_repo.get_by_username(normalized_username)
    if student is None or normalize_text(student.role).lower() != "student":
        raise HTTPException(status_code=404, detail="账号不存在")

    question = main._normalize_security_question(student.security_question or "")
    if not question:
        raise HTTPException(status_code=404, detail="该账号未设置密保问题")
    return {"username": student.username, "role": "student", "security_question": question}


@router.post("/api/auth/forgot-password-reset")
async def reset_password_with_security_question(
    payload: ForgotPasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    main = _get_main_module()
    normalized_username = normalize_text(payload.username)
    security_answer = payload.security_answer or ""
    new_password = payload.new_password or ""

    if not normalized_username or not security_answer or not new_password:
        raise HTTPException(status_code=400, detail="账号、密保答案和新密码不能为空")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于6位")

    service = AuthService(db=db, password_hasher=main._hash_password)
    user_repo = UserRepository(db)
    sec_repo = SecurityQuestionRepository(db)

    auth_user = await service.get_user_by_identifier(normalized_username)
    student_row = None
    if auth_user is None:
        student_row = await user_repo.get_student_by_student_id(normalized_username)
        if student_row is not None:
            resolved_username = normalize_text(student_row.username or student_row.student_id)
            auth_user = await service.get_user_by_identifier(resolved_username)

    if auth_user is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    account_username = normalize_text(auth_user.username or auth_user.email or normalized_username)
    role = _role_value(auth_user.role).lower()

    if role in {"teacher", "admin"}:
        sec_row = await sec_repo.get_by_username(account_username)
        question = main._normalize_security_question(sec_row.question if sec_row else "")
        answer_hash = normalize_text(sec_row.answer_hash if sec_row else "")
        if not question or not answer_hash:
            raise HTTPException(status_code=400, detail="该账号未设置密保问题")
        if not main._verify_security_answer(answer_hash, security_answer):
            raise HTTPException(status_code=401, detail="密保答案错误")
    else:
        if student_row is None:
            student_row = await user_repo.get_by_username(account_username)
        if student_row is None:
            student_row = await user_repo.get_student_by_student_id(account_username)
        if student_row is None or normalize_text(student_row.role).lower() != "student":
            raise HTTPException(status_code=404, detail="账号不存在")

        question = main._normalize_security_question(student_row.security_question or "")
        answer_hash = normalize_text(student_row.security_answer_hash or "")
        if not question or not answer_hash:
            raise HTTPException(status_code=400, detail="该账号未设置密保问题")
        if not main._verify_security_answer(answer_hash, security_answer):
            raise HTTPException(status_code=401, detail="密保答案错误")

    new_hash = main._hash_password(new_password)
    changed = await service.set_password(auth_user.id, new_hash)
    if changed is None:
        raise HTTPException(status_code=500, detail="密码重置失败")

    await _append_reset_password_log(db, account_username, role if role in {"teacher", "admin"} else "student")
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="密码重置失败")

    return {"message": "密码重置成功"}


async def check_role(username: str, db: AsyncSession = Depends(get_db)):
    """检查用户角色"""
    normalized = normalize_text(username)
    role = await resolve_user_role(db, normalized) or "student"
    return {"username": normalized, "role": role}


router.add_api_route("/api/check-role", check_role, methods=["GET"])
