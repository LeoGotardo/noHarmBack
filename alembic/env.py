from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os

# Adiciona o src/ no path para os imports funcionarem
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Importa o Base e o config do projeto
from infrastructure.external.storageService import Base
from core.config import config as appConfig

# Importa todos os models para o Alembic detectar as tabelas
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

# Config do Alembic
alembicConfig = context.config

if alembicConfig.config_file_name is not None:
    fileConfig(alembicConfig.config_file_name)

# Aponta para o metadata do projeto (onde estão as tabelas)
target_metadata = Base.metadata

# Monta a URL do banco a partir do config do projeto
DATABASE_URI = (
    f"{appConfig.DATABASE_URL}://"
    f"{appConfig.DATABASE_USER}:{appConfig.DATABASE_PASSWORD}"
    f"@{appConfig.DATABASE_HOST}/{appConfig.DATABASE_NAME}"
)


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URI,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = alembicConfig.get_section(alembicConfig.config_ini_section, {})
    configuration["sqlalchemy.url"] = DATABASE_URI

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
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
    run_migrations_offline()
else:
    run_migrations_online()