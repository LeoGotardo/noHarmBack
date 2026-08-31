variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "noharm"
}

variable "environment" {
  description = "Environment tag and name suffix."
  type        = string
  default     = "prod"
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

# ── Networking ──────────────────────────────────────────────────────────────

variable "vpc_cidr" {
  description = <<-EOT
    VPC range. Also what the container trusts as a proxy: TRUSTED_PROXY_CIDRS
    is set to this, so every address inside the VPC can set X-Forwarded-For.
    Keep it tight — the load balancer's ENIs are the only reason it exists.
  EOT
  type        = string
  default     = "10.20.0.0/16"
}

variable "az_count" {
  description = "How many AZs to spread across. RDS and the ALB both want 2."
  type        = number
  default     = 2
}

# ── DNS / TLS ───────────────────────────────────────────────────────────────

variable "domain_name" {
  description = "Public hostname for the app, e.g. app.noharm.com.br."
  type        = string
}

variable "route53_zone_id" {
  description = <<-EOT
    Hosted zone for domain_name. When set, Terraform creates the ACM
    certificate, validates it by DNS and points an alias record at the ALB.
    Leave empty and supply acm_certificate_arn instead if DNS lives elsewhere —
    then the A record is yours to create by hand.
  EOT
  type        = string
  default     = ""
}

variable "acm_certificate_arn" {
  description = "Existing certificate to use instead of creating one. Must be in var.region."
  type        = string
  default     = ""
}

# ── Data stores ─────────────────────────────────────────────────────────────

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "GiB. Storage autoscaling raises it up to db_max_allocated_storage."
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Ceiling for storage autoscaling."
  type        = number
  default     = 100
}

variable "db_name" {
  description = "Initial database name. Postgres rejects a dash here."
  type        = string
  default     = "noharm"
}

variable "db_username" {
  description = "Master user. Its password is generated and rotated by RDS."
  type        = string
  default     = "noharm"
}

variable "db_multi_az" {
  description = "Standby in a second AZ. Doubles the bill; halves the outage."
  type        = bool
  default     = false
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

# ── Service ─────────────────────────────────────────────────────────────────

variable "image_tag" {
  description = <<-EOT
    Tag of the image in ECR to run. CI pushes the commit SHA and updates this
    through the service's task definition, so the default only matters for the
    very first apply — before any image exists, the service will sit at zero
    healthy tasks until CI pushes one.
  EOT
  type        = string
  default     = "latest"
}

variable "desired_count" {
  description = "Number of tasks. Socket.IO is fine above 1 (Redis manager + sticky sessions)."
  type        = number
  default     = 1
}

variable "task_cpu" {
  description = "Fargate CPU units. 512 = 0.5 vCPU."
  type        = number
  default     = 512
}

variable "task_memory" {
  description = "Fargate memory, MiB. Must pair with task_cpu per Fargate's table."
  type        = number
  default     = 1024
}

variable "log_retention_days" {
  description = "CloudWatch retention for the container's stdout."
  type        = number
  default     = 30
}

variable "mobile_origins" {
  description = <<-EOT
    Cross-origin callers that are not the web bundle. The web build is served
    from the same origin as the API and needs no entry; the Capacitor app is
    the only client CORS applies to, and it presents these two.
  EOT
  type        = list(string)
  default     = ["capacitor://localhost", "http://localhost"]
}
