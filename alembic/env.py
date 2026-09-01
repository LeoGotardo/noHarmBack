from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from infrastructure.external.storageService import Base
from core.config import config as appConfig

# Importados apenas para registrar as tabelas em Base.metadata — sem isto o
# autogenerate não enxerga o model e passa a tratar a tabela existente como
# órfã, emitindo um op.drop_table() para ela. refreshTokenModel (tb_8) e
# notificationModel (tb_9) estavam de fora: um autogenerate rodado antes desta
# correção teria apagado os refresh tokens e as notificações.
# Deve espelhar a lista de core/database.py.
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
        # Migration é processo curto e único: um pool sobreviveria à conexão
        # sem nunca ser reusado. NullPool abre e fecha, e evita deixar
        # conexão ociosa presa no Postgres depois que o comando termina.
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