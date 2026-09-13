import pytest


@pytest.fixture(autouse=True)
def _clear_db_caches():
    """Reset cached settings/engines after each test so env overrides don't leak."""
    yield
    from app.core.config import get_settings
    from app.db import session as db_session

    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session.get_session_factory.cache_clear()


def _use_in_memory_sqlite(monkeypatch):
    from app.core.config import get_settings
    from app.db import session as db_session

    monkeypatch.setenv("ATLAS_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session.get_session_factory.cache_clear()


def test_get_db_yields_working_session_then_closes_it(monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from app.db.session import get_db

    closed = []
    original_close = Session.close
    monkeypatch.setattr(
        Session, "close", lambda self: (closed.append(True), original_close(self))
    )

    _use_in_memory_sqlite(monkeypatch)

    gen = get_db()
    db = next(gen)
    assert isinstance(db, Session)
    assert db.execute(text("SELECT 1")).scalar() == 1

    with pytest.raises(StopIteration):
        next(gen)  # dependency completes -> finally: db.close()

    assert closed == [True]


def test_get_db_rolls_back_when_request_fails(monkeypatch):
    from sqlalchemy.orm import Session

    from app.db.session import get_db

    rolled_back = []
    original_rollback = Session.rollback
    monkeypatch.setattr(
        Session, "rollback", lambda self: (rolled_back.append(True), original_rollback(self))
    )

    _use_in_memory_sqlite(monkeypatch)

    gen = get_db()
    next(gen)  # session yielded to the request

    # An exception propagating through the dependency must trigger rollback
    import pytest

    with pytest.raises(ValueError):
        gen.throw(ValueError("simulated request failure"))

    assert rolled_back == [True]


def test_engine_uses_configured_database_url(monkeypatch):
    from app.db.session import get_engine

    _use_in_memory_sqlite(monkeypatch)

    assert "sqlite" in str(get_engine().url)


def test_base_supports_declarative_models():
    from sqlalchemy.orm import Mapped, mapped_column

    from app.db.base import Base

    class Widget(Base):
        __tablename__ = "test_widgets"

        id: Mapped[int] = mapped_column(primary_key=True)

    assert "test_widgets" in Base.metadata.tables
