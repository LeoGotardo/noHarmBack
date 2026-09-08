from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from infrastructure.external.storageService import Base
from core.config import config as appConfig

# Imported only to register the tables on Base.metadata — without this,
# autogenerate does not see the model and starts treating the existing table as
# orphaned, emitting an op.drop_table() for it. refreshTokenModel (tb_8) and
# notificationModel (tb_9) were left out: an autogenerate run before this fix
# would have dropped the refresh tokens and the notifications.
# Must mirror the list in core/database.py.
from infrastructure.database.models import (
    friendshipModel,
    userBadgesModel,
    userModel,
    streakModel,
    chatModel,
    messageModel,
    badgeModel,
    auditLogsModel,
    refreshTokenModel,
    notificationModel,
)

alembicConfig = context.config

if alembicConfig.config_file_name is not None:
    fileConfig(alembicConfig.config_file_name)

target_metadata = Base.metadata

# Uses the unpooled URL — pgBouncer (pooled) breaks Alembic's DDL
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
        # A migration is a short, one-off process: a pool would outlive the
        # connection without ever being reused. NullPool opens and closes, and
        # avoids leaving an idle connection stuck in Postgres after the command
        # finishes.
        poolclass=pool.NullPool,
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