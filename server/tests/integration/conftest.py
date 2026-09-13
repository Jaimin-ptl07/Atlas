"""Integration fixtures: real PostgreSQL, real SQLAlchemy, no mocks.

Tests run against a DEDICATED database (atlas_test), created and dropped
per session. The developer's atlas database is never touched except by
administrative CREATE/DROP DATABASE statements — schema changes in the
dev database are owned by Alembic migrations alone.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 - imports register ORM models on Base.metadata
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db

TEST_DB = "atlas_test"


def _admin_url() -> str:
    """Settings URL with the password included (str(url) masks it)."""
    return get_settings().database_url


def _database_url(database: str) -> str:
    base = create_engine(_admin_url()).url.render_as_string(hide_password=False)
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


@pytest.fixture(scope="session")
def pg_engine(admin_engine: Engine) -> Engine:
    """Engine bound to the isolated atlas_test database."""
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB}"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))

    engine = create_engine(_database_url(TEST_DB))
    # Test-setup schema creation; the application itself never does this.
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()

    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB}"))
    admin_engine.dispose()


@pytest.fixture
def db_session(pg_engine: Engine) -> Session:
    factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    session = factory()

    # Each test starts from a clean table (identifiers reset too).
    session.execute(text("TRUNCATE TABLE documents RESTART IDENTITY"))
    session.commit()

    yield session
    session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """API client whose requests use THIS test's session, hitting real PostgreSQL."""
    from app.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
