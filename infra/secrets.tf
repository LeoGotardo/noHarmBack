# The application secret is created empty and filled outside Terraform.
#
# Putting the values here would put them in the state file, so what Terraform
# owns is the container and the permission to read it; the contents are written
# once with the CLI (see infra/README.md) and thereafter ignored — a `terraform
# apply` never overwrites a rotated value.
#
# One secret holding a JSON object, not six secrets: ECS can pull a single key
# out of a JSON secret (`arn:...:secret:name:key::`), so the task definition
# still maps one key to one environment variable, and there is one thing to
# rotate and one thing to grant.

resource "aws_secretsmanager_secret" "app" {
  name        = "${local.name}/app"
  description = "Application secrets for ${local.name}. Keys map 1:1 to env vars."

  # A deleted secret is recoverable for this many days. Zero would make a
  # mistaken destroy unrecoverable.
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id

  # Placeholders only, so the first apply produces a readable shape. Real values
  # go in with `aws secretsmanager put-secret-value`; the lifecycle block below
  # is what stops the next apply from putting these back.
  secret_string = jsonencode({
    ENCRYPTION_KEY           = "REPLACE_ME"
    DATABASE_ENCRYPTION_KEY  = "REPLACE_ME"
    BLIND_INDEX_KEY          = "REPLACE_ME"
    JWT_SECRET_KEY           = "REPLACE_ME"
    JWT_REFRESH_SECRET_KEY   = "REPLACE_ME"
    FIREBASE_SERVICE_ACCOUNT = "REPLACE_ME"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}
