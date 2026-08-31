#!/usr/bin/env bash
# Fill the application secret in Secrets Manager from the local .secrets.toml.
#
# This is the step with the worst failure mode in the whole deploy: a typo in a
# key name is not an error anywhere. The task starts, `/health` says the
# database is connected, and only a login fails — because
# FIREBASE_SERVICE_ACCOUNT resolved to nothing and the app has no way to verify
# an ID token. The ECS task definition maps one JSON key to one environment
# variable by exact name, so the names below are a contract with infra/ecs.tf.
#
# Values are piped straight from the file into the AWS CLI: nothing is printed,
# nothing is written to a temporary file, and nothing lands in shell history.
#
#   cd infra && ./put-secrets.sh
#
set -euo pipefail

cd "$(dirname "$0")"

SECRETS_TOML="../.secrets.toml"
[[ -r "$SECRETS_TOML" ]] || { echo "missing $SECRETS_TOML" >&2; exit 1; }

command -v aws >/dev/null || { echo "the AWS CLI is not installed" >&2; exit 1; }
command -v terraform >/dev/null || { echo "terraform is not installed" >&2; exit 1; }

secretArn="$(terraform output -raw app_secret_arn)"
echo "target: $secretArn"

# The prod DATABASE_ENCRYPTION_KEY comes from [prod] and must NOT be the dev
# one — same key across environments means dev and production ciphertext are
# interchangeable. The other four are environment-independent.
payload="$(python3 - "$SECRETS_TOML" <<'PY'
import json, sys, tomllib

with open(sys.argv[1], "rb") as f:
    toml = tomllib.load(f)

default = toml.get("default", {})
prod = toml.get("prod", {})

payload = {
    "ENCRYPTION_KEY":           default["ENCRYPTION_KEY"],
    "JWT_SECRET_KEY":           default["JWT_SECRET_KEY"],
    "JWT_REFRESH_SECRET_KEY":   default["JWT_REFRESH_SECRET_KEY"],
    "FIREBASE_SERVICE_ACCOUNT": default["FIREBASE_SERVICE_ACCOUNT"],
    "DATABASE_ENCRYPTION_KEY":  prod["DATABASE_ENCRYPTION_KEY"],
}

for name, value in payload.items():
    if not value or value == "REPLACE_ME":
        sys.exit(f"{name} is empty or still a placeholder")

if payload["DATABASE_ENCRYPTION_KEY"] == toml.get("dev", {}).get("DATABASE_ENCRYPTION_KEY"):
    sys.exit("prod and dev share a DATABASE_ENCRYPTION_KEY — give prod its own")

if payload["JWT_SECRET_KEY"] == payload["JWT_REFRESH_SECRET_KEY"]:
    sys.exit("the two JWT keys are identical — a refresh token would pass as an access token")

json.loads(payload["FIREBASE_SERVICE_ACCOUNT"])  # fail here rather than at login
print(json.dumps(payload))
PY
)"

aws secretsmanager put-secret-value \
  --secret-id "$secretArn" \
  --secret-string "$payload" \
  --query 'VersionId' --output text >/dev/null

echo "wrote 5 keys"

# Read the names back — never the values — so a silent failure is visible now.
aws secretsmanager get-secret-value --secret-id "$secretArn" \
  --query SecretString --output text \
| python3 -c 'import json,sys; print("stored:", ", ".join(sorted(json.load(sys.stdin))))'
