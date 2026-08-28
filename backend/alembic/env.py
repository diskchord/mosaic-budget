from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, event, pool

from app.config import get_settings
from app.db import Base
from app import models  # noqa: F401

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    if connectable.dialect.name == "sqlite":
        @event.listens_for(connectable, "connect")
        def _sqlite_date_part(dbapi_connection, _connection_record) -> None:
            # Alembic creates its own engine, so app.db's SQLite test helper is
            # not attached here. Production uses PostgreSQL; this keeps local
            # migration verification faithful to the model constraints.
            def date_part(part: str, value: object) -> int:
                if str(part).casefold() != "day":
                    return 0
                text = str(value)
                try:
                    return int(text[8:10])
                except (ValueError, IndexError):
                    return 0

            dbapi_connection.create_function("date_part", 2, date_part)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
