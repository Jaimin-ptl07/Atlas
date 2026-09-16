from app.core.config import Settings, get_settings

DEV_DATABASE_URL = "postgresql+psycopg://atlas:atlas@localhost:5432/atlas"


def test_database_url_read_from_atlas_env(monkeypatch, fresh_settings):
    monkeypatch.setenv(
        "ATLAS_DATABASE_URL", "postgresql+psycopg://user:pass@dbhost:5433/other"
    )

    assert get_settings().database_url == "postgresql+psycopg://user:pass@dbhost:5433/other"


def test_database_url_defaults_to_local_dev(monkeypatch):
    monkeypatch.delenv("ATLAS_DATABASE_URL", raising=False)

    # _env_file=None: the default must not depend on the developer's local .env
    settings = Settings(_env_file=None)

    assert settings.database_url == DEV_DATABASE_URL


def test_pool_settings_read_from_atlas_env(monkeypatch, fresh_settings):
    monkeypatch.setenv("ATLAS_POOL_SIZE", "90")
    monkeypatch.setenv("ATLAS_MAX_OVERFLOW", "10")

    settings = get_settings()

    assert settings.pool_size == 90
    assert settings.max_overflow == 10


def test_pool_settings_default_to_sqlalchemy_values(monkeypatch):
    monkeypatch.delenv("ATLAS_POOL_SIZE", raising=False)
    monkeypatch.delenv("ATLAS_MAX_OVERFLOW", raising=False)

    settings = Settings(_env_file=None)

    assert settings.pool_size == 5
    assert settings.max_overflow == 10
