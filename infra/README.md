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

Five values, none of which Terraform should ever see. `DATABASE_PASSWORD` is
not among them: RDS generates and rotates it in its own secret, and the task
definition reads it from there.

```bash
# Fernet key for the column-level encryption. LOSING IT MAKES EVERY ENCRYPTED
# FIELD UNREADABLE — there is no recovery path.
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Two DISTINCT JWT keys. One key for both makes a 7-day refresh token
# acceptable as a 15-minute access token.
python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"

aws secretsmanager put-secret-value \
  --secret-id "$(terraform output -raw app_secret_arn)" \
  --secret-string "$(jq -n \
      --arg enc "$ENCRYPTION_KEY" \
      --arg dbenc "$DATABASE_ENCRYPTION_KEY" \
      --arg jwt "$JWT_SECRET_KEY" \
      --arg jwtr "$JWT_REFRESH_SECRET_KEY" \
      --arg fb "$(cat firebase-service-account.json)" \
      '{ENCRYPTION_KEY:$enc, DATABASE_ENCRYPTION_KEY:$dbenc,
        JWT_SECRET_KEY:$jwt, JWT_REFRESH_SECRET_KEY:$jwtr,
        FIREBASE_SERVICE_ACCOUNT:$fb}')"
```

`FIREBASE_SERVICE_ACCOUNT` is the whole service-account JSON as a single
string. Without it every login and registration fails — it is what verifies
Firebase ID tokens.

### 4. Point CI at the account

From the outputs, into the backend repo's Actions settings:

| Where | Name | Value |
|---|---|---|
| Variable | `AWS_ROLE_ARN` | `terraform output -raw github_deploy_role_arn` |
| Variable | `TASK_SUBNET_IDS` | `terraform output -json task_subnet_ids \| jq -r 'join(",")'` |
| Variable | `APP_SECURITY_GROUP_ID` | `terraform output -raw app_security_group_id` |
| Variable | `VITE_FIREBASE_*` | the seven web-config values, baked into the bundle at build time |
| Secret | `FRONTEND_REPO_TOKEN` | PAT with read access to `LeoGotardo/noHarm` |

The frontend token is not optional: the image's first build stage compiles
`noHarm/`, and `GITHUB_TOKEN` is scoped to the repo running the workflow and
cannot check out the other one.

### 5. Deploy

Push to `main`, or run the `deploy` workflow by hand. It builds the image from
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
