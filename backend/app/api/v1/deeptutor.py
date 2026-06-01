"""DeepTutor SSO endpoints — mint dt_token cookie, clear on logout."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db
from ...services import deeptutor_sso_service
from ...services.identity_service import normalize_text, resolve_user_role

logger = logging.getLogger(__name__)

router = APIRouter()


class SSORequest(BaseModel):
    username: str


def _build_cookie_kwargs() -> dict:
    return {
        "key": deeptutor_sso_service.DEEPTUTOR_COOKIE_NAME,
        "httponly": True,
        "samesite": "lax",
        "path": "/",
    }


@router.post("/api/deeptutor/sso")
async def deeptutor_sso(
    payload: SSORequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Mint a dt_token cookie for the given portal user.

    The caller is the portal frontend, which has just verified the user is
    logged in. We map portal role -> DeepTutor role, ensure the user is
    registered in DeepTutor's users.json, sign a JWT with DEEPTUTOR_AUTH_SECRET,
    and set the same-origin cookie that DeepTutor expects.
    """
    if not deeptutor_sso_service.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="DeepTutor SSO not configured (missing DEEPTUTOR_AUTH_SECRET or shared volume)",
        )

    username = normalize_text(payload.username)
    if not username:
        raise HTTPException(status_code=400, detail="username 不能为空")

    portal_role = await resolve_user_role(db, username)
    if not portal_role:
        raise HTTPException(status_code=404, detail="账号不存在")

    dt_role = deeptutor_sso_service.map_role(portal_role)
    uid = deeptutor_sso_service.derive_user_id(username)

    try:
        deeptutor_sso_service.ensure_user_registered(username, uid, dt_role)
    except OSError as exc:
        logger.exception("Failed to write DeepTutor users.json")
        raise HTTPException(status_code=500, detail=f"无法写入 DeepTutor 用户库: {exc}") from exc

    try:
        token = deeptutor_sso_service.mint_token(username, dt_role, uid)
    except Exception as exc:
        logger.exception("Failed to mint DeepTutor SSO token")
        raise HTTPException(status_code=500, detail=f"签发 SSO Token 失败: {exc}") from exc

    response.set_cookie(
        value=token,
        max_age=deeptutor_sso_service.cookie_max_age_seconds(),
        **_build_cookie_kwargs(),
    )
    logger.info("DeepTutor SSO minted for username=%s role=%s uid=%s", username, dt_role, uid)
    return {
        "ok": True,
        "username": username,
        "role": dt_role,
        "uid": uid,
        "frontend_url": "/chat",
    }


@router.post("/api/deeptutor/logout")
async def deeptutor_logout(
    response: Response,
    username: Optional[str] = Query(None, description="可选，仅用于审计日志"),
):
    """Clear the dt_token cookie. Idempotent — always 200."""
    response.set_cookie(
        value="",
        max_age=0,
        **_build_cookie_kwargs(),
    )
    if username:
        logger.info("DeepTutor SSO cookie cleared for username=%s", normalize_text(username))
    return {"ok": True}
