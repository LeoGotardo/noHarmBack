#!/usr/bin/env bash
#
# Send the recent SSH logins into the app's audit table.
#
#   */10 * * * * /opt/noharm/collect-ssh-access.sh >> /var/log/noharm-ssh.log 2>&1
#
# Runs on the **host**, from root's crontab — it needs the journal and the
# Docker socket, and the container has neither.
#
# ## The window overlaps on purpose
#
# Every 10 minutes it sends the last 15. The extra 5 cover a slow run or a
# minute of clock drift, and the duplicates cost nothing: `tb_15` has a unique
# index on (instant, address, user), so the database is the deduplicator.
#
# That is why there is no cursor file. A state file is a thing that can be lost,
# corrupted, or left behind by a restore — and its failure mode is silently
# skipping exactly the window where something happened.
#
# ## What it does not do
#
# Failed attempts are counted by the job and not stored: a public SSH port
# collects thousands a day and they would bury the few logins that matter.
#
# And none of this is proof. Anyone with root can edit the journal before this
# reads it.
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-/opt/noharm/compose.host.yaml}"
WINDOW="${WINDOW:--15 min}"
UNIT="${UNIT:-ssh}"

# Some distributions call it `sshd`. Fall back rather than silently reading an
# empty journal, which would look exactly like "nobody logged in".
if ! journalctl -u "$UNIT" -n 0 >/dev/null 2>&1; then
    UNIT="sshd"
fi

journalctl -u "$UNIT" --since "$WINDOW" -o short-iso --no-pager \
  | docker compose -f "$COMPOSE_FILE" exec -T app ingest-host-access
