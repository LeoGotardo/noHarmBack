# Operations — the live deployment

Everything here describes the machine actually serving `https://noharm.site`.
For the unprovisioned Terraform stack see [`../infra/README.md`](../infra/README.md);
for how the container is built and configured see the Deployment section of
[`../CLAUDE.md`](../CLAUDE.md).

## The box

| | |
|---|---|
| Host | `ec2-user@34.225.81.236` — an **Elastic IP**, not the `ec2-*.compute-1.amazonaws.com` name |
| Instance | t3.micro (913 MB RAM, 8 GB EBS), `us-east-1` |
| Security group | admits `22`, `80` and `443`; nothing else |
| DNS | Route 53 hosted zone for `noharm.site` → the Elastic IP |
| Access | `ssh -i noharm-ssh.pem ec2-user@34.225.81.236` |
| Stack | `~/noHarmBack/docker/compose.host.yaml` — `noharm`, `noharm-postgres`, `noharm-redis` |

The account-scoped identifiers — instance ID, security group ID, hosted zone ID
— are deliberately not written down here: this repository is public, and they
are recon material that grants nothing on its own. Look them up when you need
them, from an account that already has credentials:

```bash
aws ec2 describe-instances --filters Name=ip-address,Values=34.225.81.236 \
  --query 'Reservations[].Instances[].[InstanceId,SecurityGroups[].GroupId]'
aws route53 list-hosted-zones-by-name --dns-name noharm.site
```

The hostname matters. `ec2-*.compute-1.amazonaws.com` encodes the address it was
issued for, so it dies the moment the instance gets a different one — which is
exactly what happened when the Elastic IP was attached. Address the Elastic IP.

Two things do not fit in 913 MB and are deliberately not done here: `vite build`
(Node gets OOM-killed, and the error names a heap limit, not the machine) and
anything that runs a second Postgres. There is 2 GB of swap to absorb the rest.

## Scheduled work

`crontab -l` as `ec2-user`:

```
0 4 * * * /home/ec2-user/noHarmBack/docker/backup-db.sh >> /home/ec2-user/backup.log 2>&1
0 3 * * 1 /home/ec2-user/noHarmBack/docker/issue-cert.sh <email> >> /home/ec2-user/noHarmBack/docker/certbot.log 2>&1
```

Both are UTC. The backup runs nightly at 04:00; the certificate renewal runs
Mondays at 03:00 — weekly against a 90-day certificate, so roughly twelve
chances to notice a failure before anything expires.

## Deploying

From the directory holding **both** repos, on a developer machine:

```bash
./noHarmBack/docker/deploy-host.sh
```

It builds the image locally, ships it over SSH (`docker save | ssh docker load`,
~600 MB on the wire — minutes, not seconds), restarts the stack and waits for
health. No registry, no credentials on the box.

Overrides: `NOHARM_HOST`, `NOHARM_SSH_KEY`.

`.github/workflows/deploy.yml` does **not** drive this. It targets the ECS stack
that nothing has provisioned, and its `push` trigger is disabled so it cannot
fail on every commit.

### Migrations

They do not run on container start. Run them explicitly after a deploy that adds
one:

```bash
ssh -i noharm-ssh.pem ec2-user@34.225.81.236
cd ~/noHarmBack/docker
sudo docker compose --env-file prod.env -f compose.host.yaml run --rm app migrate
```

`APP_ENV` defaults to `prod`. An unset or misspelled value silently targets
production — which on this box is the only database there is.

## TLS

Let's Encrypt, issued over the webroot challenge so the app stays up during
renewal. `issue-cert.sh` refuses to run unless DNS already resolves to this
host — the check exists because a failed HTTP-01 against the wrong address
burns rate limit for nothing.

The live pair sits in `~/noHarmBack/docker/certs/{fullchain,privkey}.pem`,
copied there from `letsencrypt/live/noharm.site/` by the script; nginx reads the
copies. Current certificate expires **29 Nov 2026**.

## Backups

`backup-db.sh` writes `~/backups/noharm-<UTC timestamp>.dump`, keeps
`KEEP_DAYS=7`, and logs a line per run to `~/backup.log`.

Two details that are load-bearing:

- It dumps as the **owner** role (`noharm`, from `DATABASE_USER`), never as
  `noharm_app` — the app role's reads are filtered by RLS, so a dump taken as it
  would be silently partial rather than an error. See Row Level Security below.
- It writes to `.partial` and renames on success, and verifies the result by
  mounting the directory into a throwaway `postgres:16-alpine` container.
  `pg_restore --list` from a pipe cannot work: the custom format needs to seek.

Restore is destructive and asks for confirmation:

```bash
cd ~/noHarmBack/docker && ./restore-db.sh ~/backups/noharm-<stamp>.dump
```

It stops `app` first (`pg_restore --clean` cannot drop what is in use) and
re-runs the grants from `postgres-init/10-app-role.sh` afterwards — `pg_restore`
does not recreate `ALTER DEFAULT PRIVILEGES`, and without that step the app
comes back up unable to read its own tables.

> **The backups sit on the same EBS volume as the database they protect.** They
> cover "someone deleted the wrong rows", not "the volume is gone". Moving them
> to S3 needs an instance role — there are deliberately no AWS credentials on
> this box.

## Row Level Security

**There are two database roles, and `prod.env` points the two URLs at different
ones.** This is the single most confusable thing on the box:

| | Role | Used by | Why |
|---|---|---|---|
| `DATABASE_URL` | `noharm_app` | the running app | `NOSUPERUSER`, `NOBYPASSRLS` — the 16 RLS policies actually constrain it |
| `DATABASE_URL_UNPOOLED` | `noharm` | Alembic | owner and superuser; DDL needs that, and RLS must not filter a migration |

`noharm` is `POSTGRES_USER` — a superuser, so it ignores every policy. That is
correct for migrations and dumps and wrong for serving traffic. `noharm_app` is
created by `postgres-init/10-app-role.sh` when the volume is first initialised.

Point the app's URL at `noharm` and everything still works, silently, with RLS
switched off. To confirm it is enforced rather than merely installed:

```bash
sudo docker compose --env-file prod.env -f compose.host.yaml exec postgres \
  psql -U noharm -d noharm \
  -c "select rolname, rolsuper, rolbypassrls from pg_roles where rolname='noharm_app'" \
  -c "select count(*) from pg_policies"
```

Expected: `noharm_app | f | f`, and 16 policies (across 9 tables). The migration
that installs them also warns at upgrade time when `DATABASE_USER` names a role
that would bypass them.

## Health checks

```bash
curl -sI https://noharm.site/health
ssh -i noharm-ssh.pem ec2-user@34.225.81.236 \
  'docker ps --format "{{.Names}}\t{{.Status}}"; free -m | tail -2; df -h /'
```

All three containers should report `(healthy)`. Logs rotate at 10 MB × 3 per
container (`x-logging` in `compose.host.yaml`) — the disk is 8 GB, and an
unrotated container log fills it.

## Known risks

Accepted for a single-instance deployment at ~US$8/month, listed so nobody
mistakes them for oversights:

- **No redundancy.** A reboot is downtime; there is one of everything.
- **Backups share the database's disk.** See above.
- **No monitoring or alerting.** A container that dies at 03:00 is noticed by a
  person, not a pager. The failure modes worth a cron of their own are the
  certificate renewal and the nightly dump, both of which only log.
- **Disk pressure is real.** 8 GB total, ~5 GB used, and nothing prunes. Every
  deploy loads another ~600 MB image and the old one stays. Run
  `docker image prune -f` on the box when `df -h /` gets uncomfortable; that is
  a manual step today, not something the deploy script does.
