from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db
from ...repositories.experiments import ExperimentRepository
from ...repositories.users import UserRepository
from ...services.identity_service import normalize_text, resolve_user_role
from ...services.usage_monitor_service import record_jupyter_session_start, sync_and_build_jupyter_usage_report


def _get_main_module():
    from ... import main

    return main


router = APIRouter()


def _to_experiment_model(main, row):
    difficulty = row.difficulty or main.DifficultyLevel.BEGINNER.value
    publish_scope = row.publish_scope or main.PublishScope.ALL.value
    try:
        difficulty = main.DifficultyLevel(difficulty)
    except ValueError:
        difficulty = main.DifficultyLevel.BEGINNER
    try:
        publish_scope = main.PublishScope(publish_scope)
    except ValueError:
        publish_scope = main.PublishScope.ALL

    return main.Experiment(
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


def _to_student_record(main, row):
    student_id = row.student_id or row.username
    return main.StudentRecord(
        student_id=student_id,
        username=row.username,
        real_name=row.real_name or student_id,
        class_name=row.class_name or "",
        admission_year=row.admission_year or "",
        organization=row.organization or "",
        phone=row.phone or "",
        role="student",
        created_by=row.created_by or "",
        password_hash=row.password_hash or main._hash_password(main.DEFAULT_PASSWORD),
        security_question=row.security_question or "",
        security_answer_hash=row.security_answer_hash or "",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def get_jupyterhub_auto_login_url(
    username: str,
    experiment_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return a tokenized JupyterLab URL so portal users don't need a second Hub login."""
    main = _get_main_module()
    user = normalize_text(username)
    if not user:
        raise HTTPException(status_code=400, detail="username不能为空")
    resolved_role = await resolve_user_role(db, user) or ""

    target_experiment = None
    notebook_relpath = None
    normalized_experiment_id = normalize_text(experiment_id)
    if normalized_experiment_id:
        exp_row = await ExperimentRepository(db).get(normalized_experiment_id)
        if not exp_row:
            raise HTTPException(status_code=404, detail="实验不存在")
        target_experiment = _to_experiment_model(main, exp_row)

        if resolved_role not in {"teacher", "admin"}:
            user_repo = UserRepository(db)
            student_row = await user_repo.get_student_by_student_id(user)
            if student_row is None:
                student_row = await user_repo.get_by_username(user)
            if student_row is None or normalize_text(student_row.role).lower() != "student":
                raise HTTPException(status_code=404, detail="学生不存在")

            student = _to_student_record(main, student_row)
            if not main._is_experiment_visible_to_student(target_experiment, student):
                raise HTTPException(status_code=403, detail="该实验当前未发布给你")

        notebook_relpath = f"work/{user}_{normalized_experiment_id[:8]}.ipynb"

    if not main._jupyterhub_enabled():
        payload = main._build_workspace_launch_payload(user, path=notebook_relpath)
        if not payload.get("jupyter_url"):
            payload["jupyter_url"] = f"{main.JUPYTERHUB_PUBLIC_URL}/hub/home"
        payload.update({
            "tokenized": False,
            "message": "JupyterHub token integration is disabled",
        })
        return payload

    if not main._ensure_user_server_running(user):
        raise HTTPException(status_code=503, detail="JupyterHub user server failed to start")
    if resolved_role in {"teacher", "student", "admin"}:
        try:
            changed = await record_jupyter_session_start(db, username=user, role=resolved_role)
            if changed:
                await db.commit()
        except Exception as exc:
            try:
                await db.rollback()
            except Exception:
                pass
            print(f"Usage monitor record start error: {exc}")

    token = main._create_short_lived_user_token(user)
    if target_experiment and token:
        try:
            dir_resp = main._user_contents_request(user, token, "GET", "work", params={"content": 0})
            if dir_resp.status_code == 404:
                main._user_contents_request(user, token, "PUT", "work", json={"type": "directory"})

            exists_resp = main._user_contents_request(user, token, "GET", notebook_relpath, params={"content": 0})
            if exists_resp.status_code == 404:
                notebook_json = None
                template_path = main._normalize_text(target_experiment.notebook_path or "")
                if template_path:
                    tpl_resp = main._user_contents_request(
                        user, token, "GET", template_path, params={"content": 1}
                    )
                    if tpl_resp.status_code == 200:
                        tpl_payload = tpl_resp.json() or {}
                        if tpl_payload.get("type") == "notebook" and tpl_payload.get("content"):
                            notebook_json = tpl_payload.get("content")

                if notebook_json is None:
                    notebook_json = main._empty_notebook_json()

                put_resp = main._user_contents_request(
                    user,
                    token,
                    "PUT",
                    notebook_relpath,
                    json={"type": "notebook", "format": "json", "content": notebook_json},
                )
                if put_resp.status_code not in {200, 201}:
                    print(
                        f"Failed to create notebook via Jupyter API ({put_resp.status_code}): {put_resp.text[:200]}"
                    )
            elif exists_resp.status_code != 200:
                print(
                    f"Failed to access notebook via Jupyter API ({exists_resp.status_code}): {exists_resp.text[:200]}"
                )
        except Exception as exc:
            print(f"JupyterHub auto-login notebook preparation error: {exc}")

    if not token:
        payload = main._build_workspace_launch_payload(user, path=notebook_relpath)
        payload.update({
            "tokenized": False,
            "message": "Failed to mint user token, fell back to non-token URL",
        })
        return payload

    payload = main._build_workspace_launch_payload(user, path=notebook_relpath, token=token)
    payload.update({
        "tokenized": True,
        "message": "ok",
    })
    return payload


async def stop_jupyterhub_user_server(
    username: str,
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Best-effort stop for a user's Jupyter server (for logout/page-close cleanup)."""
    main = _get_main_module()
    user = normalize_text(username)
    if not user:
        raise HTTPException(status_code=400, detail="username不能为空")

    resolved_role = (await resolve_user_role(db, user) or "").lower()
    if resolved_role not in {"teacher", "student", "admin"}:
        raise HTTPException(status_code=404, detail="用户不存在")

    if not main._jupyterhub_enabled():
        return {
            "username": user,
            "role": resolved_role,
            "stopped": False,
            "noop": True,
            "message": "JupyterHub is disabled",
            "reason": normalize_text(reason) or "client_cleanup",
        }

    stopped = bool(main._stop_user_server(user))

    # Best-effort refresh usage monitor state so admin metrics converge faster after cleanup.
    try:
        report, changed = await sync_and_build_jupyter_usage_report(
            db,
            main_module=main,
            user_roles={user: resolved_role},
        )
        if changed:
            await db.commit()
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            pass
        print(f"Usage monitor sync after stop error: {exc}")

    return {
        "username": user,
        "role": resolved_role,
        "stopped": stopped,
        "noop": False,
        "message": "ok" if stopped else "stop request failed or server already unavailable",
        "reason": normalize_text(reason) or "client_cleanup",
    }


router.add_api_route("/api/jupyterhub/auto-login-url", get_jupyterhub_auto_login_url, methods=["GET"])
router.add_api_route("/api/jupyterhub/stop-server", stop_jupyterhub_user_server, methods=["POST"])
