from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from infrastructure.external.storageService import Base
from core.config import config as appConfig

from infrastructure.database.models import (
    userModel,
    streakModel,
    chatModel,
    messageModel,
    badgeModel,
    frendshipModel,
    userBedgesModel,
    auditLogsModel,
)

alembicConfig = context.config

if alembicConfig.config_file_name is not None:
    fileConfig(alembicConfig.config_file_name)

target_metadata = Base.metadata

# Usa a URL unpooled — pgbouncer (pooled) quebra o Alembic
MIGRATION_URL = appConfig.DATABASE_URL_UNPOOLED


def runMigrationsOffline() -> None:
    context.configure(
        url=MIGRATION_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def runMigrationsOnline() -> None:
    configuration = alembicConfig.get_section(alembicConfig.config_ini_section, {})
    configuration["sqlalchemy.url"] = MIGRATION_URL

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # NullPool é essencial para Neon/serverless
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    runMigrationsOffline()
else:
    runMigrationsOnline()