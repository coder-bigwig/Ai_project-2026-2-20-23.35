from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from .identity_service import normalize_text
from .kv_policy_service import get_kv_json, upsert_kv_json

USAGE_MONITOR_KV_KEY = "admin_usage_monitor_v1"
USAGE_MONITOR_VERSION = 1
SESSION_IDLE_TIMEOUT_SECONDS = 15 * 60
TRACKED_USAGE_ROLES = {"teacher", "student", "admin"}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value) -> datetime | None:
    raw = normalize_text(value)
    if not raw:
        return None
    try:
        text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _to_iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    normalized = dt.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


def _clamp_non_negative_int(value) -> int:
    try:
        parsed = int(value or 0)
    except Exception:
        parsed = 0
    return max(0, parsed)


def _clamp_non_negative_float(value) -> float:
    try:
        parsed = float(value or 0.0)
    except Exception:
        parsed = 0.0
    if parsed < 0:
        parsed = 0.0
    return round(parsed, 3)


def _default_state() -> dict:
    return {
        "version": USAGE_MONITOR_VERSION,
        "updated_at": "",
        "users": {},
    }


def _normalize_user_entry(raw: dict | None, *, role: str = "student") -> dict:
    payload = raw if isinstance(raw, dict) else {}
    normalized_role = normalize_text(payload.get("role") or role).lower() or "student"
    if normalized_role not in TRACKED_USAGE_ROLES:
        normalized_role = "student"
    return {
        "role": normalized_role,
        "session_count": _clamp_non_negative_int(payload.get("session_count")),
        "total_seconds": _clamp_non_negative_float(payload.get("total_seconds")),
        "active_session_started_at": normalize_text(payload.get("active_session_started_at")),
        "last_seen_at": normalize_text(payload.get("last_seen_at")),
        "updated_at": normalize_text(payload.get("updated_at")),
        "source": normalize_text(payload.get("source") or "jupyter"),
    }


async def load_usage_monitor_state(db: AsyncSession) -> dict:
    raw = await get_kv_json(db, USAGE_MONITOR_KV_KEY, _default_state())
    users_raw = raw.get("users", {}) if isinstance(raw, dict) else {}
    users: dict[str, dict] = {}
    if isinstance(users_raw, dict):
        for username, item in users_raw.items():
            normalized_username = normalize_text(username)
            if not normalized_username:
                continue
            users[normalized_username] = _normalize_user_entry(item)
    return {
        "version": USAGE_MONITOR_VERSION,
        "updated_at": normalize_text((raw or {}).get("updated_at")),
        "users": users,
    }


async def save_usage_monitor_state(db: AsyncSession, state: dict) -> None:
    users_raw = state.get("users", {}) if isinstance(state, dict) else {}
    serialized_users: dict[str, dict] = {}
    if isinstance(users_raw, dict):
        for username, item in users_raw.items():
            normalized_username = normalize_text(username)
            if not normalized_username:
                continue
            serialized_users[normalized_username] = _normalize_user_entry(item)
    payload = {
        "version": USAGE_MONITOR_VERSION,
        "updated_at": _to_iso(_now_utc()),
        "users": serialized_users,
    }
    await upsert_kv_json(db, USAGE_MONITOR_KV_KEY, payload)


def ensure_user_entry(state: dict, *, username: str, role: str) -> dict:
    normalized_username = normalize_text(username)
    normalized_role = normalize_text(role).lower() or "student"
    if normalized_role not in TRACKED_USAGE_ROLES:
        normalized_role = "student"
    users = state.setdefault("users", {})
    current = users.get(normalized_username)
    normalized = _normalize_user_entry(current, role=normalized_role)
    normalized["role"] = normalized_role
    users[normalized_username] = normalized
    return normalized


def set_last_seen(entry: dict, seen_at: datetime | None) -> bool:
    if seen_at is None:
        return False
    next_value = _to_iso(seen_at)
    if not next_value:
        return False
    current = _parse_dt(entry.get("last_seen_at"))
    if current and current >= seen_at:
        return False
    entry["last_seen_at"] = next_value
    entry["updated_at"] = _to_iso(_now_utc())
    return True


def ensure_active_session(entry: dict, *, started_at: datetime, source: str = "jupyter") -> bool:
    changed = False
    current_start = _parse_dt(entry.get("active_session_started_at"))
    if current_start is None:
        entry["active_session_started_at"] = _to_iso(started_at)
        entry["session_count"] = _clamp_non_negative_int(entry.get("session_count")) + 1
        changed = True
    elif started_at < current_start:
        entry["active_session_started_at"] = _to_iso(started_at)
        changed = True
    if normalize_text(entry.get("source")) != normalize_text(source):
        entry["source"] = normalize_text(source) or "jupyter"
        changed = True
    changed = set_last_seen(entry, started_at) or changed
    if changed:
        entry["updated_at"] = _to_iso(_now_utc())
    return changed


def close_active_session(entry: dict, *, ended_at: datetime | None) -> bool:
    start_dt = _parse_dt(entry.get("active_session_started_at"))
    if start_dt is None:
        if normalize_text(entry.get("active_session_started_at")):
            entry["active_session_started_at"] = ""
            entry["updated_at"] = _to_iso(_now_utc())
            return True
        return False
    end_dt = ended_at or _parse_dt(entry.get("last_seen_at")) or _now_utc()
    if end_dt < start_dt:
        end_dt = start_dt
    duration = max(0.0, (end_dt - start_dt).total_seconds())
    entry["total_seconds"] = round(_clamp_non_negative_float(entry.get("total_seconds")) + duration, 3)
    entry["active_session_started_at"] = ""
    if not entry.get("last_seen_at"):
        entry["last_seen_at"] = _to_iso(end_dt)
    entry["updated_at"] = _to_iso(_now_utc())
    return True


async def record_jupyter_session_start(
    db: AsyncSession,
    *,
    username: str,
    role: str,
    started_at: datetime | None = None,
) -> bool:
    normalized_username = normalize_text(username)
    normalized_role = normalize_text(role).lower()
    if not normalized_username or normalized_role not in TRACKED_USAGE_ROLES:
        return False

    state = await load_usage_monitor_state(db)
    entry = ensure_user_entry(state, username=normalized_username, role=normalized_role)
    changed = ensure_active_session(entry, started_at=started_at or _now_utc(), source="jupyter")
    if changed:
        await save_usage_monitor_state(db, state)
    return changed


def _active_session_seconds(entry: dict, *, now: datetime) -> float:
    started = _parse_dt(entry.get("active_session_started_at"))
    if started is None:
        return 0.0
    if now < started:
        return 0.0
    return round((now - started).total_seconds(), 3)


async def sync_and_build_jupyter_usage_report(
    db: AsyncSession,
    *,
    main_module,
    user_roles: dict[str, str],
    idle_timeout_seconds: int = SESSION_IDLE_TIMEOUT_SECONDS,
) -> tuple[dict, bool]:
    state = await load_usage_monitor_state(db)
    now = _now_utc()
    changed = False

    safe_roles: dict[str, str] = {}
    for username, role in (user_roles or {}).items():
        normalized_username = normalize_text(username)
        normalized_role = normalize_text(role).lower()
        if not normalized_username or normalized_role not in TRACKED_USAGE_ROLES:
            continue
        safe_roles[normalized_username] = normalized_role

    hub_map = {}
    if getattr(main_module, "_jupyterhub_enabled", None) and main_module._jupyterhub_enabled():
        try:
            hub_map = main_module._hub_user_state_map()
        except Exception:
            hub_map = {}

    usernames = set(state.get("users", {}).keys()) | set(safe_roles.keys())
    timeout_seconds = max(60, int(idle_timeout_seconds or SESSION_IDLE_TIMEOUT_SECONDS))

    live_rows: list[dict] = []

    for username in sorted(usernames):
        role = safe_roles.get(username)
        if not role:
            raw_state_role = normalize_text((state.get("users", {}).get(username) or {}).get("role")).lower()
            role = raw_state_role if raw_state_role in TRACKED_USAGE_ROLES else "student"

        entry = ensure_user_entry(state, username=username, role=role)

        raw_hub_state = {}
        if hasattr(main_module, "_extract_server_state"):
            try:
                raw_hub_state = main_module._extract_server_state((hub_map or {}).get(username)) or {}
            except Exception:
                raw_hub_state = {}

        server_running = bool(raw_hub_state.get("server_running"))
        server_pending = bool(raw_hub_state.get("server_pending"))
        hub_last_activity_dt = _parse_dt(raw_hub_state.get("last_activity"))
        hub_server_started_dt = _parse_dt(raw_hub_state.get("server_started"))

        if server_running or server_pending:
            session_start_dt = hub_server_started_dt or _parse_dt(entry.get("active_session_started_at")) or hub_last_activity_dt or now
            if ensure_active_session(entry, started_at=session_start_dt, source="jupyter"):
                changed = True
            if set_last_seen(entry, hub_last_activity_dt or now):
                changed = True
        else:
            if set_last_seen(entry, hub_last_activity_dt):
                changed = True
            if _parse_dt(entry.get("active_session_started_at")) is not None:
                ended_at = hub_last_activity_dt or _parse_dt(entry.get("last_seen_at")) or now
                if close_active_session(entry, ended_at=ended_at):
                    changed = True

        active_start_dt = _parse_dt(entry.get("active_session_started_at"))
        if active_start_dt is not None:
            last_seen_dt = _parse_dt(entry.get("last_seen_at"))
            if not server_running and not server_pending and last_seen_dt and (now - last_seen_dt).total_seconds() >= timeout_seconds:
                if close_active_session(entry, ended_at=last_seen_dt):
                    changed = True

        active_session_seconds = _active_session_seconds(entry, now=now)
        total_seconds = _clamp_non_negative_float(entry.get("total_seconds"))
        live_rows.append(
            {
                "username": username,
                "role": entry.get("role", role),
                "server_running": server_running,
                "server_pending": server_pending,
                "last_activity": normalize_text(raw_hub_state.get("last_activity")) or entry.get("last_seen_at", ""),
                "server_started": normalize_text(raw_hub_state.get("server_started")),
                "session_count": _clamp_non_negative_int(entry.get("session_count")),
                "total_seconds": total_seconds,
                "active_session_seconds": active_session_seconds,
                "total_with_active_seconds": round(total_seconds + active_session_seconds, 3),
                "active_session_started_at": entry.get("active_session_started_at", ""),
                "last_seen_at": entry.get("last_seen_at", ""),
            }
        )

    if changed:
        await save_usage_monitor_state(db, state)

    def _role_summary(target_role: str) -> dict:
        rows = [item for item in live_rows if item.get("role") == target_role]
        active_rows = [item for item in rows if item.get("server_running") or item.get("server_pending")]
        total_seconds = round(sum(float(item.get("total_seconds") or 0.0) for item in rows), 3)
        active_seconds = round(sum(float(item.get("active_session_seconds") or 0.0) for item in active_rows), 3)
        return {
            "tracked_users": len(rows),
            "active_users": len(active_rows),
            "session_count": int(sum(int(item.get("session_count") or 0) for item in rows)),
            "total_duration_seconds": total_seconds,
            "active_duration_seconds": active_seconds,
            "total_duration_with_active_seconds": round(total_seconds + active_seconds, 3),
        }

    by_role = {
        "teacher": _role_summary("teacher"),
        "student": _role_summary("student"),
        "admin": _role_summary("admin"),
    }
    summary = {
        "active_teachers": by_role["teacher"]["active_users"],
        "active_students": by_role["student"]["active_users"],
        "teacher_session_count": by_role["teacher"]["session_count"],
        "student_session_count": by_role["student"]["session_count"],
        "teacher_total_duration_seconds": by_role["teacher"]["total_duration_with_active_seconds"],
        "student_total_duration_seconds": by_role["student"]["total_duration_with_active_seconds"],
    }
    report = {
        "generated_at": _to_iso(now),
        "summary": summary,
        "by_role": by_role,
        "users": live_rows,
        "session_idle_timeout_seconds": timeout_seconds,
        "scope": "jupyter_sessions",
    }
    return report, changed
