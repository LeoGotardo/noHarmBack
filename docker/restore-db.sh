#!/usr/bin/env bash
# Restore a dump made by backup-db.sh. DESTRUCTIVE: drops what is there first.
#
#   ./restore-db.sh ~/backups/noharm-20260831T040000Z.dump
#
# Restores as the owner role, then re-runs the grants the application role
# depends on — pg_restore does not recreate the ALTER DEFAULT PRIVILEGES from
# postgres-init/10-app-role.sh, so without this step the app comes back up
# unable to read its own tables.
set -euo pipefail
cd "$(dirname "$0")"

dump="${1:?usage: ./restore-db.sh <arquivo.dump>}"
[[ -r "$dump" ]] || { echo "not readable: $dump" >&2; exit 1; }

read -rp "This wipes the current database and restores $dump. Type 'yes': " confirm
[[ "$confirm" == "yes" ]] || { echo "aborted"; exit 1; }

user="$(grep '^DATABASE_USER=' prod.env | cut -d= -f2-)"
password="$(grep '^DATABASE_PASSWORD=' prod.env | cut -d= -f2-)"
database="$(grep '^DATABASE_NAME=' prod.env | cut -d= -f2-)"

# The app holds connections; pg_restore --clean cannot drop what is in use.
sudo docker compose --env-file prod.env -f compose.host.yaml stop app

sudo docker exec -i -e PGPASSWORD="$password" noharm-postgres \
    pg_restore -U "$user" -d "$database" --clean --if-exists --no-owner < "$dump"

sudo docker exec -i -e PGPASSWORD="$password" noharm-postgres \
    psql -v ON_ERROR_STOP=1 -U "$user" -d "$database" <<SQL
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO noharm_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO noharm_app;
SQL

sudo docker compose --env-file prod.env -f compose.host.yaml start app
echo "restored"
