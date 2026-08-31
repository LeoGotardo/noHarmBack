#!/bin/sh
# Create the role the application connects as.
#
# POSTGRES_USER is a superuser — initdb makes it one, and there is no way to
# ask the image for anything else. A superuser ignores every row level security
# policy in migration 20260831_02, so an application connecting as it gets the
# policies as decoration: they exist, `pg_policies` lists them, and no query is
# ever filtered.
#
# So the app gets its own role instead: NOSUPERUSER, NOBYPASSRLS, DML only.
# Migrations keep using POSTGRES_USER through DATABASE_URL_UNPOOLED, because
# they need to own the tables to alter them; the app uses DATABASE_URL. That
# split already existed for pgBouncer's sake (alembic must not go through a
# pooler) and is reused here.
#
# Runs once, on an empty data directory — before any table exists. That is why
# ALTER DEFAULT PRIVILEGES matters more than the GRANTs: it is what makes every
# table a *future* migration creates readable by the app without anyone
# remembering to grant it. Without that, the next migration's table is
# invisible to the app and the failure shows up in production, not in the
# deploy.
set -e

: "${DATABASE_APP_PASSWORD:?set it in prod.env}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE noharm_app LOGIN PASSWORD '${DATABASE_APP_PASSWORD}'
    NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO noharm_app;
GRANT USAGE ON SCHEMA public TO noharm_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO noharm_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO noharm_app;

ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO noharm_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO noharm_app;
SQL
