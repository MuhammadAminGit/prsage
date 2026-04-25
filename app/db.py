"""Async SQLAlchemy engine and session machinery.

We default to a local SQLite file for dev; Postgres in prod (set
``DATABASE_URL`` to a ``postgresql+asyncpg://...`` URL).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_settings = get_settings()


def _to_async_url(url: str) -> str:
    """Auto-upgrade common sync URLs to their async counterparts.

    Hosts like Railway expose Postgres as ``postgresql://...``. We need
    ``postgresql+asyncpg://...`` to use the async driver. This avoids forcing
    operators to remember the prefix.
    """
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


engine = create_async_engine(_to_async_url(_settings.database_url), future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
