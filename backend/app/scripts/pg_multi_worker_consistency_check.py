from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..db.base import Base
from ..db import models  # noqa: F401
from ..repositories.postgres import CourseStore
from ..storage_config import DATABASE_URL, POSTGRES_SCHEMA


def _to_async_driver_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


async def _prepare_schema(engine) -> None:
    async with engine.begin() as conn:
        if POSTGRES_SCHEMA and POSTGRES_SCHEMA != "public":
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{POSTGRES_SCHEMA}"'))
        await conn.run_sync(Base.metadata.create_all)


async def run_check() -> None:
    async_url = _to_async_driver_url(DATABASE_URL)
    if not async_url:
        raise RuntimeError("DATABASE_URL is empty")

    engine = create_async_engine(async_url, pool_pre_ping=True, future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await _prepare_schema(engine)

    course_id = f"consistency-{uuid.uuid4()}"
    create_name = "multi-worker-create"
    update_name = "multi-worker-update"

    try:
        # A worker creates.
        async with session_maker() as worker_a:
            await CourseStore(worker_a).upsert(
                {
                    "id": course_id,
                    "name": create_name,
                    "description": "consistency check",
                    "created_by": "consistency_tester",
                    "created_at": datetime.now(),
                    "updated_at": datetime.now(),
                }
            )
            await worker_a.commit()

        # B worker reads newly created row immediately.
        async with session_maker() as worker_b:
            created = await CourseStore(worker_b).get_by_id(course_id)
            assert created is not None, "create consistency failed: worker_b cannot read row created by worker_a"
            assert created.name == create_name, "create consistency failed: unexpected initial value"

        # A worker updates.
        async with session_maker() as worker_a:
            await CourseStore(worker_a).upsert(
                {
                    "id": course_id,
                    "name": update_name,
                    "description": "consistency check updated",
                    "created_by": "consistency_tester",
                    "updated_at": datetime.now(),
                }
            )
            await worker_a.commit()

        # B worker reads updated value immediately.
        async with session_maker() as worker_b:
            updated = await CourseStore(worker_b).get_by_id(course_id)
            assert updated is not None, "update consistency failed: row disappeared unexpectedly"
            assert updated.name == update_name, "update consistency failed: worker_b did not see latest value"

        # A worker deletes.
        async with session_maker() as worker_a:
            await CourseStore(worker_a).delete(course_id)
            await worker_a.commit()

        # B worker confirms deletion immediately.
        async with session_maker() as worker_b:
            deleted = await CourseStore(worker_b).get_by_id(course_id)
            assert deleted is None, "delete consistency failed: worker_b still sees deleted row"

        print("PASS: PostgreSQL multi-worker consistency check passed (create/update/delete).")
    finally:
        async with session_maker() as cleanup:
            await CourseStore(cleanup).delete(course_id)
            await cleanup.commit()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_check())
