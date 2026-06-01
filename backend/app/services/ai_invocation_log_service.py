from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories import AIInvocationLogRepository
from .identity_service import normalize_text


def _clamp_int(value, *, default: int = 0, min_value: int = 0, max_value: int = 2_147_483_647) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(min_value, min(parsed, max_value))


def _clamp_float(value, *, min_value: float = 0.0, max_value: float = 86_400_000.0) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except Exception:
        return None
    return max(min_value, min(parsed, max_value))


def normalize_ai_invocation_log_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    metadata = source.get("metadata_json")
    if not isinstance(metadata, dict):
        metadata = source.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        "id": normalize_text(source.get("id")) or str(uuid.uuid4()),
        "source": normalize_text(source.get("source"))[:64] or "platform",
        "endpoint": normalize_text(source.get("endpoint"))[:128] or "-",
        "username": normalize_text(source.get("username"))[:128],
        "role": normalize_text(source.get("role"))[:32],
        "model": normalize_text(source.get("model"))[:128],
        "provider": normalize_text(source.get("provider"))[:128],
        "success": bool(source.get("success", True)),
        "status_code": _clamp_int(source.get("status_code"), default=200, min_value=0, max_value=999)
        if source.get("status_code") is not None
        else None,
        "latency_ms": _clamp_float(source.get("latency_ms")),
        "prompt_chars": _clamp_int(source.get("prompt_chars")),
        "response_chars": _clamp_int(source.get("response_chars")),
        "history_count": _clamp_int(source.get("history_count"), max_value=10000),
        "used_search": bool(source.get("used_search", False)),
        "search_provider": normalize_text(source.get("search_provider"))[:128],
        "search_depth": normalize_text(source.get("search_depth"))[:32],
        "search_cached": bool(source.get("search_cached", False)),
        "search_result_count": _clamp_int(source.get("search_result_count"), max_value=10000),
        "cache_hit_count": _clamp_int(source.get("cache_hit_count"), max_value=10000),
        "error": normalize_text(source.get("error"))[:2000],
        "request_id": normalize_text(source.get("request_id"))[:128],
        "metadata_json": metadata,
        "created_at": datetime.now(),
    }


async def append_ai_invocation_log(db: AsyncSession, payload: dict[str, Any] | None) -> None:
    await AIInvocationLogRepository(db).create(normalize_ai_invocation_log_payload(payload))
