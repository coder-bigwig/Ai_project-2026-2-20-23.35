from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import DEFAULT_RESOURCE_ROLE_LIMITS, DEFAULT_SERVER_RESOURCE_BUDGET
from ..repositories import KVStoreRepository
from .identity_service import normalize_text

_SIZE_FACTORS = {
    "B": 1,
    "K": 1024,
    "M": 1024 ** 2,
    "G": 1024 ** 3,
    "T": 1024 ** 4,
}


def _size_unit(default_value: str) -> str:
    raw = normalize_text(default_value).upper()
    if raw.endswith("KB") or raw.endswith("K"):
        return "K"
    if raw.endswith("MB") or raw.endswith("M"):
        return "M"
    if raw.endswith("GB") or raw.endswith("G"):
        return "G"
    if raw.endswith("TB") or raw.endswith("T"):
        return "T"
    return "B"


def normalize_size_limit(value: Any, default_value: str) -> str:
    raw = normalize_text(value)
    if not raw:
        return default_value

    text = raw.upper().replace(" ", "")
    number = ""
    unit = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            number += ch
        else:
            unit += ch
    if not number:
        raise HTTPException(status_code=400, detail=f"资源大小格式无效: {raw}")
    try:
        size = float(number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"资源大小格式无效: {raw}") from exc
    if size <= 0:
        raise HTTPException(status_code=400, detail=f"资源大小必须大于 0: {raw}")

    if unit in {"", "B"}:
        resolved_unit = _size_unit(default_value)
    elif unit in {"K", "KB"}:
        resolved_unit = "K"
    elif unit in {"M", "MB"}:
        resolved_unit = "M"
    elif unit in {"G", "GB"}:
        resolved_unit = "G"
    elif unit in {"T", "TB"}:
        resolved_unit = "T"
    else:
        raise HTTPException(status_code=400, detail=f"资源大小格式无效: {raw}")

    if size.is_integer():
        number_text = str(int(size))
    else:
        number_text = str(round(size, 3)).rstrip("0").rstrip(".")
    return number_text if resolved_unit == "B" else f"{number_text}{resolved_unit}"


def size_to_bytes(value: str) -> int:
    raw = normalize_text(value).upper().replace(" ", "")
    if not raw:
        return 0
    number = ""
    unit = ""
    for ch in raw:
        if ch.isdigit() or ch == ".":
            number += ch
        else:
            unit += ch
    if not number:
        return 0
    try:
        parsed = float(number)
    except ValueError:
        return 0
    if unit in {"", "B"}:
        factor = _SIZE_FACTORS["B"]
    elif unit in {"K", "KB"}:
        factor = _SIZE_FACTORS["K"]
    elif unit in {"M", "MB"}:
        factor = _SIZE_FACTORS["M"]
    elif unit in {"G", "GB"}:
        factor = _SIZE_FACTORS["G"]
    elif unit in {"T", "TB"}:
        factor = _SIZE_FACTORS["T"]
    else:
        factor = _SIZE_FACTORS["B"]
    return int(parsed * factor)


def default_resource_policy_payload() -> dict:
    now_iso = datetime.now().isoformat()
    return {
        "defaults": deepcopy(DEFAULT_RESOURCE_ROLE_LIMITS),
        "budget": {
            **deepcopy(DEFAULT_SERVER_RESOURCE_BUDGET),
            "updated_by": "system",
            "updated_at": now_iso,
        },
        "overrides": {},
    }


def normalize_resource_quota(raw: dict | None, role: str) -> dict:
    role_key = role if role in DEFAULT_RESOURCE_ROLE_LIMITS else "student"
    base = DEFAULT_RESOURCE_ROLE_LIMITS[role_key]
    source = raw or {}

    try:
        cpu_limit = float(source.get("cpu_limit", base["cpu_limit"]))
    except (TypeError, ValueError):
        cpu_limit = float(base["cpu_limit"])
    cpu_limit = round(max(0.1, min(cpu_limit, 128.0)), 3)

    memory_limit = normalize_size_limit(source.get("memory_limit", base["memory_limit"]), base["memory_limit"])
    storage_limit = normalize_size_limit(source.get("storage_limit", base["storage_limit"]), base["storage_limit"])
    return {
        "cpu_limit": cpu_limit,
        "memory_limit": memory_limit,
        "storage_limit": storage_limit,
    }


def normalize_resource_budget(raw: dict | None) -> dict:
    source = raw or {}
    base = DEFAULT_SERVER_RESOURCE_BUDGET
    try:
        max_total_cpu = float(source.get("max_total_cpu", base["max_total_cpu"]))
    except (TypeError, ValueError):
        max_total_cpu = float(base["max_total_cpu"])
    max_total_cpu = round(max(0.1, min(max_total_cpu, 1024.0)), 3)
    return {
        "max_total_cpu": max_total_cpu,
        "max_total_memory": normalize_size_limit(source.get("max_total_memory", base["max_total_memory"]), base["max_total_memory"]),
        "max_total_storage": normalize_size_limit(source.get("max_total_storage", base["max_total_storage"]), base["max_total_storage"]),
        "enforce_budget": bool(source.get("enforce_budget", base["enforce_budget"])),
        "updated_by": normalize_text(source.get("updated_by")) or "system",
        "updated_at": normalize_text(source.get("updated_at")) or datetime.now().isoformat(),
    }


async def get_kv_json(db: AsyncSession, key: str, default: dict) -> dict:
    repo = KVStoreRepository(db)
    row = await repo.get(key)
    payload = row.value_json if row is not None and isinstance(row.value_json, dict) else None
    return deepcopy(payload) if payload is not None else deepcopy(default)


async def upsert_kv_json(db: AsyncSession, key: str, payload: dict) -> None:
    repo = KVStoreRepository(db)
    await repo.upsert(key, deepcopy(payload))

