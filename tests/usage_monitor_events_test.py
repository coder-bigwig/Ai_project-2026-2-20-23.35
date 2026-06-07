import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import usage_monitor_service


class MemoryKVStoreRepository:
    store = {}

    def __init__(self, db):
        self.db = db

    async def get(self, key):
        value = self.store.get(key)
        if value is None:
            return None
        return SimpleNamespace(key=key, value_json=deepcopy(value))

    async def upsert(self, key, value_json):
        self.store[key] = deepcopy(value_json)
        return SimpleNamespace(key=key, value_json=deepcopy(value_json))

    async def list_by_prefix(self, prefix):
        return [
            SimpleNamespace(key=key, value_json=deepcopy(value))
            for key, value in sorted(self.store.items())
            if key.startswith(prefix)
        ]


async def fake_get_kv_json(db, key, default):
    value = MemoryKVStoreRepository.store.get(key)
    return deepcopy(value) if isinstance(value, dict) else deepcopy(default)


def setup_memory_kv(monkeypatch):
    MemoryKVStoreRepository.store = {}
    monkeypatch.setattr(usage_monitor_service, "KVStoreRepository", MemoryKVStoreRepository)
    monkeypatch.setattr(usage_monitor_service, "get_kv_json", fake_get_kv_json)


def usage_events():
    prefix = "admin_usage_monitor_v1:event:"
    return [
        value
        for key, value in sorted(MemoryKVStoreRepository.store.items())
        if key.startswith(prefix)
    ]


def test_record_jupyter_session_start_appends_platform_start_event(monkeypatch):
    setup_memory_kv(monkeypatch)
    started_at = datetime(2026, 6, 6, 8, 30, tzinfo=timezone.utc)

    changed = asyncio.run(
        usage_monitor_service.record_jupyter_session_start(
            object(),
            username="student1",
            role="student",
            started_at=started_at,
        )
    )

    assert changed is True
    events = usage_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "platform_start"
    assert events[0]["username"] == "student1"
    assert events[0]["role"] == "student"
    assert events[0]["source"] == "jupyter"
    assert events[0]["started_at"] == "2026-06-06T08:30:00Z"


def test_hub_reconcile_start_appends_event_when_hub_running_but_ledger_not_active(monkeypatch):
    setup_memory_kv(monkeypatch)
    now = datetime(2026, 6, 6, 8, 45, tzinfo=timezone.utc)
    monkeypatch.setattr(usage_monitor_service, "_now_utc", lambda: now)

    class FakeMain:
        @staticmethod
        def _jupyterhub_enabled():
            return True

        @staticmethod
        def _hub_user_state_map():
            return {"student1": object()}

        @staticmethod
        def _extract_server_state(raw):
            return {
                "server_running": True,
                "server_pending": False,
                "server_started": "2026-06-06T08:00:00Z",
                "last_activity": "2026-06-06T08:10:00Z",
            }

    report, changed = asyncio.run(
        usage_monitor_service.sync_and_build_jupyter_usage_report(
            object(),
            main_module=FakeMain(),
            user_roles={"student1": "student"},
        )
    )

    assert changed is True
    assert report["summary"]["active_students"] == 1
    events = usage_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "hub_reconcile_start"
    assert events[0]["username"] == "student1"
    assert events[0]["server_running"] is True
    assert events[0]["server_started"] == "2026-06-06T08:00:00Z"
    assert events[0]["hub_last_activity"] == "2026-06-06T08:10:00Z"


def test_hub_reconcile_stop_appends_event_when_hub_stopped_but_ledger_active(monkeypatch):
    setup_memory_kv(monkeypatch)
    now = datetime(2026, 6, 6, 8, 45, tzinfo=timezone.utc)
    monkeypatch.setattr(usage_monitor_service, "_now_utc", lambda: now)
    MemoryKVStoreRepository.store["admin_usage_monitor_v1:user:student1"] = {
        "role": "student",
        "session_count": 1,
        "total_seconds": 0.0,
        "active_session_started_at": "2026-06-06T08:00:00Z",
        "last_seen_at": "2026-06-06T08:05:00Z",
        "updated_at": "2026-06-06T08:05:00Z",
        "source": "jupyter",
    }

    class FakeMain:
        @staticmethod
        def _jupyterhub_enabled():
            return True

        @staticmethod
        def _hub_user_state_map():
            return {"student1": object()}

        @staticmethod
        def _extract_server_state(raw):
            return {
                "server_running": False,
                "server_pending": False,
                "last_activity": "2026-06-06T08:10:00Z",
            }

    report, changed = asyncio.run(
        usage_monitor_service.sync_and_build_jupyter_usage_report(
            object(),
            main_module=FakeMain(),
            user_roles={"student1": "student"},
        )
    )

    assert changed is True
    assert report["summary"]["active_students"] == 0
    events = usage_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "hub_reconcile_stop"
    assert events[0]["username"] == "student1"
    assert events[0]["duration_seconds"] == 600.0
    assert events[0]["hub_last_activity"] == "2026-06-06T08:10:00Z"
