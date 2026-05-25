from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import DEFAULT_RESOURCE_ROLE_LIMITS, DEFAULT_RESOURCE_TIER, RESOURCE_TIER_ORDER, RESOURCE_TIERS
from .identity_service import normalize_text
from .kv_policy_service import default_resource_policy_payload, get_kv_json, normalize_resource_quota, size_to_bytes, upsert_kv_json

ACTIVE_SESSION_KV_KEY = "active_experiment_sessions"
RESOURCE_POLICY_KV_KEY = "resource_policy"


def normalize_resource_tier(value: Any) -> str:
    normalized = normalize_text(value).lower()
    return normalized if normalized in RESOURCE_TIERS else DEFAULT_RESOURCE_TIER


def experiment_resource_tier(experiment: Any) -> str:
    explicit = normalize_text(getattr(experiment, "resource_tier", ""))
    if explicit:
        return normalize_resource_tier(explicit)
    resources = getattr(experiment, "resources", None)
    if isinstance(resources, dict):
        return normalize_resource_tier(resources.get("resource_tier") or resources.get("tier"))
    return DEFAULT_RESOURCE_TIER


def resource_tier_quota(tier_key: str) -> dict:
    tier = RESOURCE_TIERS[normalize_resource_tier(tier_key)]
    return {
        "cpu_limit": float(tier["cpu_limit"]),
        "memory_limit": normalize_text(tier["memory_limit"]) or "2G",
        "storage_limit": normalize_text(tier["storage_limit"]) or "2G",
    }


def public_resource_tiers() -> list[dict]:
    result = []
    for key in RESOURCE_TIER_ORDER:
        tier = RESOURCE_TIERS[key]
        result.append(
            {
                "key": key,
                "label": tier["label"],
                "cpu_limit": float(tier["cpu_limit"]),
                "memory_limit": tier["memory_limit"],
                "storage_limit": tier["storage_limit"],
            }
        )
    return result


def _quota_satisfies(current: dict | None, required: dict) -> bool:
    if not current:
        return False
    try:
        current_cpu = float(current.get("cpu_limit", 0) or 0)
        required_cpu = float(required.get("cpu_limit", 0) or 0)
    except (TypeError, ValueError):
        return False
    return (
        current_cpu >= required_cpu
        and size_to_bytes(str(current.get("memory_limit", ""))) >= size_to_bytes(str(required.get("memory_limit", "")))
        and size_to_bytes(str(current.get("storage_limit", ""))) >= size_to_bytes(str(required.get("storage_limit", "")))
    )


async def _load_sessions(db: AsyncSession) -> dict:
    payload = await get_kv_json(db, ACTIVE_SESSION_KV_KEY, {})
    return payload if isinstance(payload, dict) else {}


async def _save_sessions(db: AsyncSession, sessions: dict) -> None:
    await upsert_kv_json(db, ACTIVE_SESSION_KV_KEY, sessions)


def _active_state_for(main_module, username: str, hub_state: dict | None = None) -> dict:
    payload = (hub_state or {}).get(username)
    if not payload:
        return {"server_running": False, "server_pending": False}
    return main_module._extract_server_state(payload)


def _count_active_tier_users(main_module, sessions: dict, tier_key: str, *, exclude_username: str = "") -> int:
    hub_state = main_module._hub_user_state_map()
    total = 0
    for username, session in sessions.items():
        normalized_user = normalize_text(username)
        if not normalized_user or normalized_user == exclude_username:
            continue
        if normalize_resource_tier((session or {}).get("resource_tier")) != tier_key:
            continue
        state = _active_state_for(main_module, normalized_user, hub_state)
        if state.get("server_running") or state.get("server_pending"):
            total += 1
    return total


async def cleanup_active_experiment_session(db: AsyncSession, username: str) -> None:
    user = normalize_text(username)
    if not user:
        return

    sessions = await _load_sessions(db)
    existing_session = sessions.pop(user, None)
    if existing_session is None:
        return
    await _save_sessions(db, sessions)

    previous_override = existing_session.get("previous_override") if isinstance(existing_session, dict) else None
    policy = await get_kv_json(db, RESOURCE_POLICY_KV_KEY, default_resource_policy_payload())
    overrides = dict(policy.get("overrides", {}) if isinstance(policy.get("overrides"), dict) else {})
    if previous_override:
        overrides[user] = previous_override
    else:
        overrides.pop(user, None)
    policy["overrides"] = overrides
    await upsert_kv_json(db, RESOURCE_POLICY_KV_KEY, policy)


async def prepare_experiment_jupyter_quota(
    db: AsyncSession,
    *,
    main_module,
    username: str,
    experiment,
    role: str = "student",
    course_id: str = "",
    force_restart: bool = False,
) -> dict:
    user = normalize_text(username)
    if not user:
        raise HTTPException(status_code=400, detail="username不能为空")

    tier_key = experiment_resource_tier(experiment)
    tier = RESOURCE_TIERS[tier_key]
    required_quota = resource_tier_quota(tier_key)

    sessions = await _load_sessions(db)
    active_count = _count_active_tier_users(main_module, sessions, tier_key, exclude_username=user)
    if active_count >= int(tier["max_users"]):
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RESOURCE_LIMIT_REACHED",
                "message": "当前实验环境人数较多，请稍后再试",
                "resource_tier": tier_key,
            },
        )

    hub_state = main_module._hub_user_state_map()
    user_state = _active_state_for(main_module, user, hub_state)
    server_active = bool(user_state.get("server_running") or user_state.get("server_pending"))
    current_session = sessions.get(user) if isinstance(sessions.get(user), dict) else {}
    policy = await get_kv_json(db, RESOURCE_POLICY_KV_KEY, default_resource_policy_payload())
    overrides = dict(policy.get("overrides", {}) if isinstance(policy.get("overrides"), dict) else {})
    role_key = role if role in DEFAULT_RESOURCE_ROLE_LIMITS else "student"
    current_quota = (
        current_session.get("quota")
        if isinstance(current_session, dict) and current_session.get("quota")
        else overrides.get(user) or DEFAULT_RESOURCE_ROLE_LIMITS[role_key]
    )
    if server_active and not _quota_satisfies(current_quota, required_quota):
        if not force_restart:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "RESTART_REQUIRED",
                    "message": "当前实验需要更高资源，需要重启实验环境后进入",
                    "current_quota": current_quota or {},
                    "required_quota": required_quota,
                    "resource_tier": tier_key,
                },
            )
        if not main_module._stop_user_server(user):
            raise HTTPException(status_code=503, detail="JupyterHub user server failed to stop for resource update")
        await cleanup_active_experiment_session(db, user)
        sessions = await _load_sessions(db)

    previous_override = current_session.get("previous_override") if isinstance(current_session, dict) else overrides.get(user)
    normalized_quota = normalize_resource_quota(required_quota, role or "student")
    now_iso = datetime.now().isoformat()
    overrides[user] = {
        **normalized_quota,
        "updated_by": "system",
        "updated_at": now_iso,
        "note": f"active experiment quota: {tier_key}",
        "managed_by": "active_experiment_tier",
    }
    policy["overrides"] = overrides
    await upsert_kv_json(db, RESOURCE_POLICY_KV_KEY, policy)

    sessions[user] = {
        "course_id": normalize_text(course_id or getattr(experiment, "course_id", "")),
        "experiment_id": normalize_text(getattr(experiment, "id", "")),
        "resource_tier": tier_key,
        "quota": deepcopy(normalized_quota),
        "cpu_limit": normalized_quota["cpu_limit"],
        "memory_limit": normalized_quota["memory_limit"],
        "storage_limit": normalized_quota["storage_limit"],
        "started_at": current_session.get("started_at") if isinstance(current_session, dict) else now_iso,
        "updated_at": now_iso,
        "previous_override": deepcopy(previous_override) if previous_override else None,
    }
    await _save_sessions(db, sessions)
    await db.commit()
    return {
        "resource_tier": tier_key,
        "quota": normalized_quota,
    }
