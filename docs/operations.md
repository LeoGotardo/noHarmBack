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
30 4 * * * cd /home/ec2-user/noHarmBack/docker && docker compose -f compose.host.yaml --env-file prod.env run --rm app purge-accounts >> /home/ec2-user/purge.log 2>&1
45 4 * * 0 cd /home/ec2-user/noHarmBack/docker && docker compose -f compose.host.yaml --env-file prod.env run --rm app purge-evidence >> /home/ec2-user/purge.log 2>&1
```

All four are UTC. The backup runs nightly at 04:00; the certificate renewal
runs Mondays at 03:00 — weekly against a 90-day certificate, so roughly twelve
chances to notice a failure before anything expires.

### The account purge

The third one is the only thing in the system that permanently deletes a user.
Deleting an account from the app is a soft delete plus a clock
(`tb_0.cl_0f`); this job is what stops the clock, `ACCOUNT_DELETION_GRACE_DAYS`
(default 30) after the request. Until it runs, the user can sign in and restore
everything — which is exactly what the delete confirmation screen promises them.

**If this cron is not installed, nothing is ever really deleted.** The app keeps
telling users their data is erased after 30 days and it never is. That is the
failure mode to watch for, and it is silent: the API behaves identically either
way, because a deleted account past its window already answers "Account not
found." to everyone.

It runs at 04:30, half an hour after the backup, so the night's dump still
contains the accounts about to be destroyed — one more day of recovery room if a
purge turns out to have been wrong.

Exit code 0 means every eligible account was purged, or there were none;
1 means at least one failed, and `~/purge.log` names it. A failing account does
not block the others.

To see what the next run would destroy, without destroying it:

```bash
docker exec postgres_db psql -U <owner> -d noharm-db -c \
  "SELECT cl_0a, cl_0f FROM tb_0 WHERE cl_0e = 2 AND cl_0f <= NOW() - INTERVAL '30 days';"
```

Run it by hand the same way cron does:

```bash
cd ~/noHarmBack/docker
docker compose -f compose.host.yaml --env-file prod.env run --rm app purge-accounts
```

### The evidence retention sweep

The fourth entry deletes the **evidence** captured with a report — copied
private messages and a profile snapshot — once a moderator has had the report
closed for `REPORT_EVIDENCE_RETENTION_DAYS` (default 180). Weekly is enough:
nothing about it is urgent, and the window is measured in months.

What it never touches: the report itself (reason, status, the account it named)
and any report still open, however old. An open report whose evidence was swept
would be a complaint nobody can judge any more — if unreviewed reports are
ageing past the window, the answer is a moderator, not a shorter retention.

Not installing this cron is the mirror image of the account purge: nothing
breaks, and the system quietly keeps two users' conversation for ever, long
after the purpose that justified copying it. Check what is eligible with:

```bash
docker exec postgres_db psql -U <owner> -d noharm-db -c \
  "SELECT count(*) FROM tb_11 e JOIN tb_10 r ON r.cl_10a = e.cl_11b
     WHERE r.cl_10f IN (5, 6) AND r.updated_at <= NOW() - INTERVAL '180 days';"
```

Run it by hand:

```bash
cd ~/noHarmBack/docker
docker compose -f compose.host.yaml --env-file prod.env run --rm app purge-evidence
```

### Reading a report as a moderator

Moderation is the `ADMIN_USER_IDS` allowlist in `prod.env` and nothing else —
a JSON array of Firebase UIDs, empty by default. It is read when the config
singleton is built, so adding a uid needs the app restarted:

```bash
cd ~/noHarmBack/docker
# edit prod.env: ADMIN_USER_IDS=["<firebase-uid>"]
docker compose -f compose.host.yaml --env-file prod.env up -d
```

A moderator finds their own uid by signing in and reading `id` from
`GET /users/me`.

**The normal way in is the app itself.** Sign in at https://noharm.site,
Profile → gear → **Reports**: the queue, each report with the conversation
captured behind it, and the two buttons that close it or suspend the account.
The row is not rendered for anyone not on the allowlist. What follows is the
same thing over curl, for a shell or a script:

```
GET    /reports?status=4            # the open queue, newest first
GET    /reports?status=4&sort=priority   # self-harm first, then by reporter standing
POST   /reports/{id}/claim          # take it, so a second moderator does not
GET    /reports/{id}/evidence       # what was captured when it was filed
PUT    /reports/{id}/resolve/accepted|ignored
DELETE /reports/{id}/claim          # put it back undecided
```

Every row carries two things the report cannot say for itself. `reporter_standing`
is how that reporter's past reports were decided — `weight` near 0.5 means no
history, low means their complaints are usually dismissed, high means they have
been right before. `open_against_reported` counts the open reports naming that
account, and `looks_coordinated` marks it passing `REPORT_BRIGADING_THRESHOLD`
(5). **Both are reasons to look closer, never grounds on their own.** A pile of
reports is what a coordinated group is trying to buy, and it is also what one
genuinely bad week looks like; the two are told apart by reading the evidence.

`sort=priority` puts `self_harm` first regardless of who filed it — a frightened
friend with a poor record is still a frightened friend — and nothing is ever
hidden from the queue, only ordered later in it.

**Your decisions bind the reporter.** Dismissing a report stops that person
reporting that same user for `REPORT_DISMISSED_COOLDOWN_DAYS` (30); resolving it
as actioned does not, and also frees one of their five open-report slots. So
`ignored` is the right answer for a complaint you looked at and found baseless,
not a way to clear the queue of something you have not read — a wrongly
dismissed report costs the reporter a month of being unable to escalate.

Claim before you read, whenever there is more than one of you. A live claim
makes the other moderator's claim, release **and resolve** answer 409, which is
what stops one offence being punished twice. It expires after
`REPORT_LOCK_MINUTES` (30), so a closed tab never parks a report for good.

Resolving never changes an account. Acting on one is its own call, and the
ladder starts below a suspension:

```
POST /users/{id}/warn    {"reason": "harassment", "message": "..."}   # nothing changes
PUT  /users/{id}/suspend {"days": 7, "reason": "harassment", "message": "..."}
PUT  /users/{id}/suspend {"days": null, "reason": "..."}              # permanent
PUT  /users/{id}/status/1                                            # lift it early
```

**A warning is where most cases should stop.** It changes nothing about the
account: the user is told once, on their next open, and acknowledges it. An app
that can only ban has to either overreact or do nothing, and does nothing far
more often. `message` is shown to them verbatim — never name who reported them
in it, because the promise that a reported user is never told is what makes
reports fileable at all.

`self_harm` is refused as a warning reason (400). That report is usually a
frightened friend; the answer is crisis resources, then closing it as actioned.

A suspension is the same `banned` status plus an end date, and it lifts itself
the first time that account signs in afterwards — there is no cron for it and
nothing to remember. `days: null` is written out on purpose: a permanent ban
should never be the result of a field somebody forgot.

The split is deliberate: a queue where closing a report also punishes someone
makes the two decisions one, and the pressure then runs the wrong way.

Every read of `/evidence` writes an audit entry of type 11 naming the
moderator. That is not bookkeeping — it is other people's private messages, and
the log is what makes reading them reviewable. Warnings and suspension notices
are type 12.

### Appeals

Every notice and every refused sign-in tells the user to write to
`VITE_SUPPORT_EMAIL` (the app's copy; keep it a mailbox somebody reads). The
policy that line is promising:

- **A different moderator reviews it** than the one who decided. With two
  moderators that is a rule you keep by hand; nothing in the code enforces it,
  and pretending otherwise would be worse than saying so here.
- **Within 30 days.** Past that the evidence may already be swept
  (`REPORT_EVIDENCE_RETENTION_DAYS`, 180 days after the report was closed) —
  which is the outer bound on how long an appeal can be judged on anything but
  the record of the decision.
- **Lifting is one call**: `PUT /users/{id}/status/1` clears the ban and its end
  date. A warning cannot be withdrawn — `tb_12` has no DELETE policy — so an
  upheld appeal is answered by the reply and the note on file, not by erasing
  what was said.
- If an appeal succeeds, say so in the reply. The person has been told once by
  a system; being told the opposite by silence is not an answer.

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
