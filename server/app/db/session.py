from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """The Engine is a process-wide factory+pool of DB connections.

    Creating it does NOT connect — connections are opened lazily and held
    in the engine's connection pool. Pool tuning knobs (pool_size,
    max_overflow, pool_timeout) are deliberately left at defaults for now.
    """
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    if settings.experiments_enabled:
        from app.experiments.metrics import attach_instrumentation, experiment_metrics

        attach_instrumentation(engine, experiment_metrics)

    return engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Generator[Session]:
    """FastAPI dependency: one Session per request, closed afterwards.

    Session lifecycle: request starts -> Session created (no connection
    yet) -> used by service/repository -> commit/rollback inside the
    service -> close() returns the connection to the pool.
    """
    db = get_session_factory()()
    try:
        yield db
    except Exception:
        db.rollback()  # undo any uncommitted work before releasing
        raise
    finally:
        db.close()  # returns the connection to the engine's pool
