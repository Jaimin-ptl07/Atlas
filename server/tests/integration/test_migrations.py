"""Migrations must reproduce exactly the schema the ORM models describe.

Guards against drift: if someone edits a model without a migration (or a
migration without the model), autogenerate against an `upgrade head`
database will report a difference and this test fails.
"""

from pathlib import Path

from sqlalchemy import create_engine, text

import app.models  # noqa: F401 - register models on Base.metadata
from app.db.base import Base

ALEMBIC_INI = Path(__file__).parents[2] / "alembic.ini"
SCRATCH_DB = "atlas_migration_test"


def test_upgrade_head_matches_models(admin_engine):
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext

    from alembic import command

    base_url = admin_engine.url.render_as_string(hide_password=False).rsplit("/", 1)[0]
    scratch_url = f"{base_url}/{SCRATCH_DB}"

    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB}"))
        conn.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", scratch_url)
    command.upgrade(config, "head")

    engine = create_engine(scratch_url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()
        with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB}"))

    assert diff == []
