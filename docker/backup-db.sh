#!/usr/bin/env bash
# Nightly Postgres dump, kept on the instance's own disk.
#
# WHAT THIS PROTECTS AGAINST: a dropped volume, a bad migration, someone
# deleting rows. NOT the instance going away — the dumps live on the same EBS
# volume as the database. Off-box copies need an IAM role on the instance and
# `aws s3 cp`; there is a commented line at the bottom for the day that exists.
#
# The dump runs as the OWNER role (DATABASE_URL_UNPOOLED), never as the
# application role, and that is not a detail: the app role is subject to the
# row level security policies from migration 20260831_02, so a dump taken as
# noharm_app would come back with only the rows visible to an empty user
# context — a backup that restores cleanly and is missing almost everything.
#
#   ./backup-db.sh          # one dump now
#   0 4 * * *  /home/ec2-user/noHarmBack/docker/backup-db.sh >> ~/backup.log 2>&1
#
set -euo pipefail
cd "$(dirname "$0")"

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
CONTAINER="${CONTAINER:-noharm-postgres}"

user="$(grep '^DATABASE_USER=' prod.env | cut -d= -f2-)"
password="$(grep '^DATABASE_PASSWORD=' prod.env | cut -d= -f2-)"
database="$(grep '^DATABASE_NAME=' prod.env | cut -d= -f2-)"

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_DIR/noharm-$stamp.dump"

# Custom format: compressed, and restorable table by table with pg_restore.
sudo docker exec -e PGPASSWORD="$password" "$CONTAINER" \
    pg_dump -U "$user" -d "$database" --format=custom --no-owner \
    > "$target.partial"

# Rename only after pg_dump exits 0, so a dump killed halfway never looks like
# a good backup. A truncated file that sorts newest is worse than no file.
mv "$target.partial" "$target"
chmod 600 "$target"

# Prove it is readable now rather than discovering it is not during a restore.
#
# Through a throwaway container with the directory MOUNTED, not piped on stdin:
# a custom-format archive has a table of contents that pg_restore seeks to, and
# a pipe cannot seek. Reading it from stdin fails with "did not find magic
# string in file header" on a dump that is perfectly good — a false alarm that
# would have this script cry wolf every night.
if ! sudo docker run --rm -v "$BACKUP_DIR:/backups:ro" postgres:16-alpine \
        pg_restore --list "/backups/$(basename "$target")" > /dev/null 2>&1; then
    echo "WARNING: $target is not a readable dump" >&2
    exit 1
fi

find "$BACKUP_DIR" -name 'noharm-*.dump' -mtime "+$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name '*.partial' -mtime +1 -delete

echo "$(date -u +%FT%TZ) ok $(basename "$target") $(du -h "$target" | cut -f1) | $(find "$BACKUP_DIR" -name 'noharm-*.dump' | wc -l) dumps, $(du -sh "$BACKUP_DIR" | cut -f1) total"

# Off-box copy, once the instance has an IAM role that allows it:
# aws s3 cp "$target" "s3://SEU-BUCKET/noharm/" --storage-class STANDARD_IA
