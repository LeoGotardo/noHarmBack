> [!WARNING]
> **This is not the current deployment.** Nothing here is provisioned — no
> `terraform apply` has run against this configuration.
>
> The live site is a single EC2 instance (`34.225.81.236`, `noharm.site`)
> running `docker/compose.host.yaml`: the app, Postgres and Redis as containers,
> with nginx terminating TLS using a Let's Encrypt certificate. It is deployed
> with `docker/deploy-host.sh` and costs about US$8/month against the ~US$62 of
> the stack below. Its runbook is [`../docs/operations.md`](../docs/operations.md).
>
> That address is an Elastic IP. An earlier `ec2-*.compute-1.amazonaws.com`
> hostname is in older notes and is dead: that name encodes the address it was
> issued for, so attaching the Elastic IP retired it.
>
> Running `terraform apply` today would build a second, parallel environment —
> an ALB, an RDS instance and an ElastiCache cluster with nothing pointing at
> them — and bill for it. Keep this configuration for the day the single
> instance stops being enough; do not apply it by accident.

# infra — NoHarm on AWS

Terraform for the whole deployed stack: VPC, RDS, ElastiCache, ECR, ALB, ECS
Fargate, Secrets Manager and the OIDC role GitHub Actions deploys with.

One image holds both the front-end bundle and the API (see `docker/Dockerfile`),
so there is one service, one target group and one origin — which is why the web
build needs no CORS and no cross-origin socket URL.

```
internet ──443──▶ ALB (ACM cert, TLS ends here)
                   │  http :80
                   ▼
              Fargate task ── nginx ──▶ uvicorn (127.0.0.1:8080)
                   │                        │
                   │                        ├──▶ RDS Postgres  (data subnet)
                   │                        └──▶ ElastiCache   (data subnet)
                   └── public subnet, security group admits the ALB only
```

## What Terraform does not do

- **Fill the application secret.** It creates `noharm-prod/app` with
  `REPLACE_ME` placeholders and then ignores its contents forever, so a
  rotation is never reverted by an apply. Step 3 below fills it.
- **Build or push an image.** The service points at `:latest` on the first
  apply and has nothing to run until CI pushes one. Expect zero healthy tasks
  between step 2 and step 5.
- **Set the Firebase authorised domain.** Google sign-in fails on a domain the
  Firebase console does not list. Step 6.

## First deploy

### 1. Choose the DNS path

Either Route 53 holds the zone — set `route53_zone_id` and Terraform issues the
certificate, validates it and creates the A record — or DNS lives elsewhere, in
which case issue an ACM certificate in the same region by hand, set
`acm_certificate_arn`, and point the record at the `alb_dns_name` output
yourself.

```bash
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars
```

### 2. Apply

```bash
terraform init
terraform apply
```

Twenty minutes, most of it RDS. `create_github_oidc_provider = false` if the
account already has the GitHub OIDC provider — there is only one per account
and a second one fails the apply.

### 3. Fill the application secret

Six values, none of which Terraform should ever see — the six `infra/ecs.tf`
maps into the container. `DATABASE_PASSWORD` is not among them: RDS generates
and rotates it in its own secret, and the task definition reads it from there.

The normal way is `put-secrets.sh`, which reads them from your local
`.secrets.toml` and pipes them straight to Secrets Manager (nothing printed,
nothing in shell history). It also refuses the mistakes that have no other
symptom: an empty or `REPLACE_ME` value, a production `DATABASE_ENCRYPTION_KEY`
or `BLIND_INDEX_KEY` shared with dev, and a blind-index key equal to the column
key.

```bash
cd infra && ./put-secrets.sh
```

Where the values come from:

| Key | Section of `.secrets.toml` | Notes |
|-----|---------------------------|-------|
| `DATABASE_ENCRYPTION_KEY` | `[prod]` | The AES-GCM column key. **Losing it makes every encrypted column unreadable** — there is no recovery path |
| `BLIND_INDEX_KEY` | `[prod]` | HMAC key for the lookup indexes. Must differ from the one above; rotating it means re-running migration `20260902_01` |
| `ENCRYPTION_KEY` | `[default]` | |
| `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY` | `[default]` | Two **distinct** keys. One key for both makes a 7-day refresh token acceptable as a 15-minute access token |
| `FIREBASE_SERVICE_ACCOUNT` | `[default]` | The whole service-account JSON as one string. Without it every login and registration fails — it is what verifies Firebase ID tokens |

To generate a fresh key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. Point CI at the account

From the outputs, into the backend repo's Actions settings:

| Where | Name | Value |
|---|---|---|
| Variable | `AWS_ROLE_ARN` | `terraform output -raw github_deploy_role_arn` |
| Variable | `TASK_SUBNET_IDS` | `terraform output -json task_subnet_ids \| jq -r 'join(",")'` |
| Variable | `APP_SECURITY_GROUP_ID` | `terraform output -raw app_security_group_id` |
| Variable | `VITE_FIREBASE_*` | the six web-config values, baked into the bundle at build time |
| Secret | `FRONTEND_REPO_TOKEN` | PAT with read access to `LeoGotardo/noHarm` |

The frontend token is not optional: the image's first build stage compiles
`noHarm/`, and `GITHUB_TOKEN` is scoped to the repo running the workflow and
cannot check out the other one.

### 5. Deploy

Run the `deploy` workflow by hand (Actions → deploy → Run workflow). Its `push` trigger is commented out in `.github/workflows/deploy.yml` while this stack is not the deployment; restore it to deploy on every push to `main`. It builds the image from
both repos, pushes it under the commit SHA, runs the migration task and waits
for it, then rolls the service.

To migrate without a deploy:

```bash
aws ecs run-task \
  --cluster "$(terraform output -raw ecs_cluster_name)" \
  --task-definition "$(terraform output -raw migrate_task_family)" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
      subnets=[$(terraform output -json task_subnet_ids | jq -r 'join(",")')],
      securityGroups=[$(terraform output -raw app_security_group_id)],
      assignPublicIp=ENABLED}"
```

The service never migrates on boot (`RUN_MIGRATIONS=false`): N tasks starting
together would race the same upgrade.

### 6. Firebase console

Add the domain under **Authentication → Settings → Authorised domains**, or
Google sign-in fails on it. If the Firebase project ever changes, the
`firebaseapp.com` host in `docker/security_headers.conf` has to change with it
— sign-in plants a hidden iframe there, and CSP blocks it with no symptom but a
console error.

## Cost

Roughly, us-east-1, on-demand, at the defaults:

| | |
|---|---|
| Fargate 0.5 vCPU / 1 GB, 1 task | ~$18 |
| RDS db.t4g.micro, 20 GB gp3, single-AZ | ~$15 |
| ElastiCache cache.t4g.micro | ~$12 |
| ALB | ~$17 + traffic |
| **Total** | **~$62/month** |

`db_multi_az = true` adds about $15 and is the first thing to turn on once
there is data worth an outage. There is no NAT gateway on purpose — that would
be another $33 for egress the tasks get from a public IP behind a closed
security group.

## Decisions worth knowing

**Tasks sit in public subnets.** A Fargate task must reach ECR, Secrets Manager
and CloudWatch; the alternatives are a NAT gateway or a set of VPC endpoints,
both around $33/month. The security group admits the ALB and nothing else, so
the public IP buys egress only. RDS and ElastiCache are in subnets with no
internet route at all.

**`TRUSTED_PROXY_CIDRS` is the VPC range.** nginx restores the client address
from `X-Forwarded-For` for peers in it, so anything inside the VPC could forge
that header. Widen it and the rate limiter starts keying on whatever a caller
claims.

**Sticky sessions are on.** Socket.IO opens with HTTP long-polling before it
upgrades, and those requests must reach the same task. The Redis manager fans
messages out between tasks; it does not make a session portable.

**RLS is inert for a BYPASSRLS role.** Migration `20260831_02` puts row level
security on nine tables, and `FORCE ROW LEVEL SECURITY` makes it apply to the
table owner — but not to a role carrying the `BYPASSRLS` attribute or real
superuser rights. The task currently connects as the RDS master user. Check it
once after the first deploy:

```sql
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'noharm';
```

If either column is true, the policies are decoration: create a dedicated role
(`NOSUPERUSER NOBYPASSRLS`, with DML grants on the tables) and point
`DATABASE_USER`/`DATABASE_PASSWORD` at it. The migration prints a warning in the
deploy log when it detects this.

**Redis is not a cache.** The JWT blacklist lives there — a logout that does
not reach it leaves the token valid until it expires — as do the rate-limit
buckets. `maxmemory-policy` is `noeviction` for that reason: refusing a write
is safer than silently un-revoking a token.

## Teardown

`deletion_protection` is on for both the RDS instance and the ALB, so a
`terraform destroy` stops rather than deleting a database by accident. Clear it
deliberately:

```bash
terraform apply -var db_multi_az=false   # no-op; just to be on a clean plan
aws rds modify-db-instance --db-instance-identifier noharm-prod \
  --no-deletion-protection --apply-immediately
aws elbv2 modify-load-balancer-attributes --load-balancer-arn <arn> \
  --attributes Key=deletion_protection.enabled,Value=false
terraform destroy
```

A final snapshot is taken on destroy and is not managed by Terraform — it
outlives the stack and costs storage until deleted.

## Files

| File | What it provisions |
|------|--------------------|
| `versions.tf` | Terraform and provider versions; `.terraform.lock.hcl` pins the provider builds |
| `variables.tf` | Inputs (region, sizes, domain, `ALLOWED_ORIGINS`, …); `terraform.tfvars.example` is the template, `terraform.tfvars` is gitignored |
| `network.tf` | VPC, public subnets for the tasks, data subnets for RDS and Redis |
| `security_groups.tf` | ALB open to 80/443; tasks reachable from the ALB only; RDS and Redis from the tasks only |
| `alb.tf` | Load balancer, HTTPS listener with the ACM certificate, HTTP → HTTPS redirect, target group on `/health` |
| `ecr.tf` | The image repository |
| `ecs.tf` | Cluster, service and task definitions — the app, and the `migrate` task |
| `iam.tf` | Task execution and task roles (read the secrets, write logs) |
| `rds.tf` | Postgres, with its password generated and rotated in its own RDS secret |
| `redis.tf` | ElastiCache Redis |
| `secrets.tf` | The `noharm-prod/app` secret (`REPLACE_ME` placeholders, filled by `put-secrets.sh`) |
| `github_oidc.tf` | The OIDC provider and the role GitHub Actions assumes to deploy |
| `outputs.tf` | What steps 3–5 above read: ARNs, subnets, cluster and task names |
| `put-secrets.sh` | Fills the app secret from `.secrets.toml`, refusing shared or placeholder keys |
