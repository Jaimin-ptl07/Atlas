from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Atlas API"
    environment: str = "development"
    debug: bool = False
    database_url: str = "postgresql+psycopg://atlas:atlas@localhost:5432/atlas"
    experiments_enabled: bool = False
    # Pool knobs — defaults match SQLAlchemy's; override via env for experiments.
    # Total connection ceiling per app process = pool_size + max_overflow.
    pool_size: int = 5
    max_overflow: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ATLAS_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()