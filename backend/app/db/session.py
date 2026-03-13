from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..storage_config import DATABASE_URL, POSTGRES_SCHEMA

_engine: Optional[AsyncEngine] = None
_session_maker: Optional[async_sessionmaker[AsyncSession]] = None
_postgres_ready = False


def _to_async_driver_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


async def init_db_engine(force: bool = False) -> bool:
    global _engine, _session_maker, _postgres_ready
    if _engine is not None and _session_maker is not None:
        return True

    if not DATABASE_URL:
        return False

    async_url = _to_async_driver_url(DATABASE_URL)
    engine = create_async_engine(
        async_url,
        pool_pre_ping=True,
        future=True,
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        await engine.dispose()
        return False

    _engine = engine
    _session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    _postgres_ready = True
    return True


async def init_db_schema() -> None:
    if _engine is None:
        raise RuntimeError("PostgreSQL engine is not initialized.")

    from .base import Base
    from . import models  # noqa: F401

    async with _engine.begin() as conn:
        if POSTGRES_SCHEMA and POSTGRES_SCHEMA != "public":
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{POSTGRES_SCHEMA}"'))
        await conn.run_sync(Base.metadata.create_all)


async def close_db_engine() -> None:
    global _engine, _session_maker, _postgres_ready
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_maker = None
    _postgres_ready = False


def is_postgres_ready() -> bool:
    return _postgres_ready and _session_maker is not None


def storage_backend_name() -> str:
    return "postgres"


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if _session_maker is None:
        raise RuntimeError("PostgreSQL session factory is unavailable. Startup should fail fast.")

    async with _session_maker() as session:
        yield session
