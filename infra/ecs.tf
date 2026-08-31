locals {
  container_name = "app"

  # Values that are not secret. Everything config.py marks as required has to
  # be here or in container_secrets, or the app raises at import and the task
  # dies before nginx ever answers.
  container_env = [
    { name = "APP_ENV", value = var.environment },
    { name = "EXEC_MODE", value = var.environment },
    { name = "DEBUG", value = "false" },
    { name = "PORT", value = "8080" },

    # TLS ends at the ALB; nginx serves plain :80. See docker/entrypoint.sh.
    { name = "TLS_MODE", value = "alb" },

    # nginx restores the client address from X-Forwarded-For for peers in this
    # range — the load balancer's ENIs. Anything wider hands the whole VPC the
    # ability to forge it.
    { name = "TRUSTED_PROXY_CIDRS", value = var.vpc_cidr },

    # And uvicorn trusts only nginx, on loopback, because that is the only peer
    # that can reach it: run.py binds 127.0.0.1.
    { name = "TRUSTED_PROXIES", value = jsonencode(["127.0.0.1/32", "::1/128"]) },

    # The web bundle is same-origin with the API, so CORS only ever applies to
    # the Capacitor app. The https origin is here for a browser hitting the API
    # from the site itself after a future split.
    { name = "ALLOWED_ORIGINS", value = jsonencode(concat(["https://${var.domain_name}"], var.mobile_origins)) },

    { name = "STATUS_CODES", value = jsonencode({
      disabled = 0, enabled = 1, deleted = 2, blocked = 3, pending = 4,
      accepted = 5, ignored = 6, unread = 7, read = 8, banned = 9
    }) },

    { name = "JWT_ALGORITHM", value = "HS256" },
    { name = "ACCESS_TOKEN_EXPIRE_MINUTES", value = "15" },
    { name = "REFRESH_TOKEN_EXPIRE_DAYS", value = "7" },

    # The entrypoint composes DATABASE_URL and DATABASE_URL_UNPOOLED from these
    # plus DATABASE_PASSWORD, which comes from the secret RDS manages.
    { name = "DATABASE_HOST", value = aws_db_instance.main.address },
    { name = "DATABASE_PORT", value = tostring(aws_db_instance.main.port) },
    { name = "DATABASE_NAME", value = var.db_name },
    { name = "DATABASE_USER", value = var.db_username },
    { name = "DATABASE_SSLMODE", value = "require" },

    # rediss:// — the replication group has transit encryption on.
    { name = "REDIS_URL", value = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:${aws_elasticache_replication_group.main.port}/0" },

    # Never true on the service. Migrations run as their own task — a scale-out
    # would otherwise race N containers through the same upgrade.
    { name = "RUN_MIGRATIONS", value = "false" },
  ]

  container_secrets = [
    for key in [
      "ENCRYPTION_KEY",
      "DATABASE_ENCRYPTION_KEY",
      "JWT_SECRET_KEY",
      "JWT_REFRESH_SECRET_KEY",
      "FIREBASE_SERVICE_ACCOUNT",
      ] : {
      name      = key
      valueFrom = "${aws_secretsmanager_secret.app.arn}:${key}::"
    }
  ]

  # RDS owns and rotates this one, so it is pulled from its secret rather than
  # copied into ours.
  db_password_secret = {
    name      = "DATABASE_PASSWORD"
    valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:password::"
  }
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_cluster" "main" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = local.container_name
      image     = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
      essential = true

      portMappings = [
        { containerPort = 80, protocol = "tcp" }
      ]

      environment = local.container_env
      secrets     = concat(local.container_secrets, [local.db_password_secret])

      # The image's own HEALTHCHECK is a Docker directive Fargate ignores; this
      # is the same command as an ECS-level check, so a task whose backend died
      # is replaced without waiting for the ALB to notice.
      healthCheck = {
        command     = ["CMD-SHELL", "curl -fs http://127.0.0.1/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "app"
        }
      }
    }
  ])
}

# Same image, same configuration, one difference: it runs `migrate` and exits.
# Kept as its own family so `aws ecs run-task` can name it without overrides,
# and so a migration never inherits a change made to the service's revision.
resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "migrate"
      image     = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
      essential = true
      command   = ["migrate"]

      # TLS_MODE never applies: the entrypoint handles `migrate` before it looks
      # at either TLS branch, so no certificate and no CIDR list are needed.
      environment = local.container_env
      secrets     = concat(local.container_secrets, [local.db_password_secret])

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "migrate"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "app" {
  name            = local.name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  # A task with no public IP in a subnet with no NAT cannot pull its own image.
  # The security group is what keeps it unreachable — see network.tf.
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = local.container_name
    container_port   = 80
  }

  # Long enough for migrations-then-boot on a cold database; without it a slow
  # first start is killed by the health check before it can pass one.
  health_check_grace_period_seconds = 120

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # 100/200 means the new tasks come up before the old ones go away: a deploy
  # never drops below full capacity.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  # CI registers a new task definition revision and updates the service, so the
  # revision recorded here goes stale by design.
  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.https]
}
