from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def _to_sync_url(url: str) -> str:
    """Alembic/seed/admin tooling runs sync — same driver, sync adapter."""
    return url.replace("+psycopg_async", "+psycopg")


@lru_cache
def get_async_engine() -> AsyncEngine:
    """The async Engine is a process-wide factory+pool of DB connections.

    Creating it does NOT connect — connections are opened lazily and held
    in the engine's connection pool. Pool sizing comes from Settings
    (pool_size + max_overflow), so experiments can change it via env
    without code changes. pool_timeout stays at SQLAlchemy's 30s default.
    """
    settings = get_settings()
    pool_kwargs: dict = {"pool_pre_ping": True}
    if not settings.database_url.startswith("sqlite"):
        # QueuePool sizing applies to real DB backends; SQLite's StaticPool
        # (test/CI convenience) rejects these args.
        pool_kwargs |= {
            "pool_size": settings.pool_size,
            "max_overflow": settings.max_overflow,
        }
    engine = create_async_engine(settings.database_url, **pool_kwargs)

    if settings.experiments_enabled:
        from app.experiments.metrics import attach_instrumentation, experiment_metrics

        attach_instrumentation(engine, experiment_metrics)

    return engine


@lru_cache
def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=get_async_engine(), expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency: one AsyncSession per request, closed afterwards.

    Session lifecycle: request starts -> AsyncSession created (no
    connection yet) -> awaited by service/repository -> commit/rollback
    inside the service -> close() returns the connection to the pool.
    """
    db = get_async_session_factory()()
    try:
        yield db
    except Exception:
        await db.rollback()  # undo any uncommitted work before releasing
        raise
    finally:
        await db.close()  # returns the connection to the engine's pool


@lru_cache
def get_engine() -> Engine:
    """Sync engine for tooling only (seed scripts, admin tasks).

    The request path is fully async; Alembic migrations also run sync
    (see alembic/env.py) — psycopg's sync and async adapters share one
    wire protocol, so only the URL scheme differs.
    """
    settings = get_settings()
    return create_engine(_to_sync_url(settings.database_url), pool_pre_ping=True)
