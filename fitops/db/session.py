from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fitops.config.settings import get_settings


def _get_engine():
    db_path = get_settings().db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, echo=False, future=True)

    # WAL lets readers proceed while a writer holds a lock; without it, every
    # write transaction (e.g. a migration) blocks every concurrent SELECT.
    # synchronous=NORMAL is safe under WAL and faster than FULL.
    # busy_timeout makes SQLite wait briefly instead of returning SQLITE_BUSY.
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA busy_timeout=5000")
        finally:
            cur.close()

    return engine


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _get_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Alias — `get_session` and `get_async_session` are the same thing.
get_session = get_async_session
