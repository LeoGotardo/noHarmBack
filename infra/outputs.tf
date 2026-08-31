output "alb_dns_name" {
  description = "Point the domain here if Route 53 is not managing it."
  value       = aws_lb.main.dns_name
}

output "app_url" {
  value = "https://${var.domain_name}"
}

output "ecr_repository_url" {
  description = "docker push target. CI needs this as ECR_REPOSITORY."
  value       = aws_ecr_repository.app.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  value = aws_ecs_service.app.name
}

output "migrate_task_family" {
  description = "aws ecs run-task --task-definition <this> — see infra/README.md."
  value       = aws_ecs_task_definition.migrate.family
}

output "app_secret_arn" {
  description = "Fill this one in by hand before the first deploy."
  value       = aws_secretsmanager_secret.app.arn
}

output "db_master_secret_arn" {
  description = "RDS-managed. Read it if you need to connect by hand; never copy it."
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}

output "db_endpoint" {
  value = aws_db_instance.main.address
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "task_subnet_ids" {
  description = "run-task needs these for its network configuration."
  value       = aws_subnet.public[*].id
}

output "app_security_group_id" {
  description = "run-task needs this too."
  value       = aws_security_group.app.id
}
