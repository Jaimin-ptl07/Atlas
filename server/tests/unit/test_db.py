import pytest


@pytest.fixture(autouse=True)
def _clear_db_caches():
    """Reset cached settings/engines after each test so env overrides don't leak."""
    yield
    from app.core.config import get_settings
    from app.db import session as db_session

    get_settings.cache_clear()
    db_session.get_async_engine.cache_clear()
    db_session.get_async_session_factory.cache_clear()


def _use_in_memory_sqlite(monkeypatch):
    from app.core.config import get_settings
    from app.db import session as db_session

    monkeypatch.setenv("ATLAS_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    get_settings.cache_clear()
    db_session.get_async_engine.cache_clear()
    db_session.get_async_session_factory.cache_clear()


async def test_get_db_yields_working_session_then_closes_it(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import get_db

    closed = []
    original_close = AsyncSession.close

    async def _spy_close(self):
        closed.append(True)
        await original_close(self)

    monkeypatch.setattr(AsyncSession, "close", _spy_close)

    _use_in_memory_sqlite(monkeypatch)

    gen = get_db()
    db = await gen.__anext__()
    assert isinstance(db, AsyncSession)
    assert (await db.execute(text("SELECT 1"))).scalar() == 1

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()  # dependency completes -> finally: await db.close()

    assert closed == [True]


async def test_get_db_rolls_back_when_request_fails(monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import get_db

    rolled_back = []
    original_rollback = AsyncSession.rollback

    async def _spy_rollback(self):
        rolled_back.append(True)
        await original_rollback(self)

    monkeypatch.setattr(AsyncSession, "rollback", _spy_rollback)

    _use_in_memory_sqlite(monkeypatch)

    gen = get_db()
    await gen.__anext__()  # session yielded to the request

    with pytest.raises(ValueError, match="simulated request failure"):
        await gen.athrow(ValueError("simulated request failure"))

    assert rolled_back == [True]


async def test_engine_uses_configured_database_url(monkeypatch):
    from app.db.session import get_async_engine

    _use_in_memory_sqlite(monkeypatch)

    assert "sqlite" in str(get_async_engine().url)


def test_base_supports_declarative_models():
    from sqlalchemy.orm import Mapped, mapped_column

    from app.db.base import Base

    class Widget(Base):
        __tablename__ = "test_widgets"

        id: Mapped[int] = mapped_column(primary_key=True)

    assert "test_widgets" in Base.metadata.tables


def test_engine_uses_configured_pool_limits(monkeypatch):
    from app.core.config import get_settings
    from app.db import session as db_session

    # Postgres URL: engine construction configures the pool but never
    # connects, so this test needs no live database.
    monkeypatch.setenv(
        "ATLAS_DATABASE_URL", "postgresql+psycopg_async://u:p@localhost:5433/nonexistent"
    )
    monkeypatch.setenv("ATLAS_POOL_SIZE", "7")
    monkeypatch.setenv("ATLAS_MAX_OVERFLOW", "3")
    get_settings.cache_clear()
    db_session.get_async_engine.cache_clear()
    db_session.get_async_session_factory.cache_clear()

    engine = db_session.get_async_engine()

    assert engine.pool.size() == 7
    assert engine.pool._max_overflow == 3
