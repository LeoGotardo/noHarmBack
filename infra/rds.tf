resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.data[*].id

  tags = { Name = local.name }
}

# force_ssl is the reason this exists: without it a plaintext session is
# accepted, and the entrypoint's sslmode=require would be a claim rather than
# an enforced property. Postgres also gets a slow-query log worth having on
# day one — pg_stat_statements is off by default and expensive to enable later
# under load.
resource "aws_db_parameter_group" "main" {
  name_prefix = "${local.name}-pg16-"
  family      = "postgres16"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "main" {
  identifier = local.name

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  db_name  = var.db_name
  username = var.db_username

  # RDS generates the password, stores it in its own Secrets Manager secret and
  # rotates it. Nothing else ever holds a copy: the task definition points at
  # that secret's `password` key and the entrypoint composes DATABASE_URL from
  # it at boot. A password written here would live in the Terraform state.
  manage_master_user_password = true

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  multi_az               = var.db_multi_az
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  parameter_group_name   = aws_db_parameter_group.main.name

  backup_retention_period = 7
  backup_window           = "05:00-06:00"
  maintenance_window      = "Mon:06:00-Mon:07:00"
  copy_tags_to_snapshot   = true

  auto_minor_version_upgrade = true
  apply_immediately          = false

  # Every row of user data in this app is encrypted at the column level too
  # (AES-256, see security/encryption.py), but the audit log, the indexes and
  # the WAL are not — the snapshot is what protects those.
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name}-final-${formatdate("YYYYMMDDhhmm", timestamp())}"

  enabled_cloudwatch_logs_exports = ["postgresql"]

  lifecycle {
    # The snapshot name embeds a timestamp, which would otherwise show as a
    # diff on every plan.
    ignore_changes = [final_snapshot_identifier]
  }

  tags = { Name = local.name }
}
