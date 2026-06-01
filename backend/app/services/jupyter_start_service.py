from __future__ import annotations

import asyncio
import os
from typing import Any

from .identity_service import normalize_text


def _start_concurrency() -> int:
    raw = os.getenv("JUPYTER_START_CONCURRENCY", "8")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 8
    return max(1, min(value, 64))


_start_semaphore = asyncio.Semaphore(_start_concurrency())
_inflight_lock = asyncio.Lock()
_inflight_starts: dict[str, asyncio.Task[bool]] = {}


async def ensure_user_server_running_async(main_module: Any, username: str) -> bool:
    """Run slow JupyterHub spawn polling outside the event loop.

    Singleflight coalesces duplicate start requests for one user. The semaphore
    is a bulkhead so a class entering at once cannot consume unlimited threads.
    """
    user = normalize_text(username)
    if not user:
        return False

    async with _inflight_lock:
        task = _inflight_starts.get(user)
        if task is None or task.done():
            task = asyncio.create_task(_start_under_bulkhead(main_module, user))
            _inflight_starts[user] = task

    try:
        return await task
    finally:
        if task.done():
            async with _inflight_lock:
                if _inflight_starts.get(user) is task:
                    _inflight_starts.pop(user, None)


async def _start_under_bulkhead(main_module: Any, username: str) -> bool:
    async with _start_semaphore:
        return bool(await asyncio.to_thread(main_module._ensure_user_server_running, username))
