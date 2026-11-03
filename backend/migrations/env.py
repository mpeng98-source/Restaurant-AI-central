from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.config import settings
from app.db import Base
import app.models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata
migration_url = settings.migration_database_url
if not migration_url:
    raise RuntimeError("MIGRATION_DATABASE_URL is required; migrations must use the separate migration-owner account")


def run_migrations_offline():
    context.configure(url=migration_url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config({"sqlalchemy.url": migration_url}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
