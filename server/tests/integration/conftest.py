"""Integration fixtures: real PostgreSQL, real async SQLAlchemy, no mocks.

Tests run against a DEDICATED database (atlas_test), created and dropped
per session. The developer's atlas database is never touched except by
administrative CREATE/DROP DATABASE statements — schema changes in the
dev database are owned by Alembic migrations alone.
"""

import httpx
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.models  # noqa: F401 - register ORM models on Base.metadata
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db

TEST_DB = "atlas_test"


def _to_sync_url(url: str) -> str:
    """Alembic/seed/admin tooling runs sync — same driver, sync adapter."""
    return url.replace("+psycopg_async", "+psycopg")


def _admin_url() -> str:
    return _to_sync_url(get_settings().database_url)


def _database_url(database: str, *, sync: bool) -> str:
    settings_url = get_settings().database_url if not sync else _to_sync_url(get_settings().database_url)
    base = create_engine(_to_sync_url(settings_url)).url.render_as_string(hide_password=False)
    return base.rsplit("/", 1)[0] + f"/{database}"


@pytest.fixture(scope="session")
def admin_engine() -> Engine:
    """Connection to the settings database — for admin statements only."""
    engine = create_engine(_admin_url(), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any failure means "DB unavailable"
        pytest.skip(f"PostgreSQL not reachable: {exc}")
    return engine


@pytest.fixture
async def pg_engine(admin_engine: Engine) -> AsyncEngine:
    """Async engine bound to the isolated atlas_test database."""
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB}"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))

    engine = create_async_engine(_database_url(TEST_DB, sync=False))
    # Test-setup schema creation; the application itself never does this.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB}"))


@pytest.fixture
async def db_session(pg_engine: AsyncEngine) -> AsyncSession:
    factory = async_sessionmaker(bind=pg_engine, expire_on_commit=False)
    session = factory()

    # Each test starts from a clean table (identifiers reset too).
    await session.execute(text("TRUNCATE TABLE documents RESTART IDENTITY"))
    await session.commit()

    yield session
    await session.close()


@pytest.fixture
async def client(db_session: AsyncSession):
    """Async API client whose requests use THIS test's session, on real PostgreSQL."""
    from app.main import app

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()
