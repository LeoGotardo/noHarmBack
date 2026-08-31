# Redis is load-bearing, not a cache: the JWT blacklist lives here (a logout
# that does not reach it leaves the token valid until it expires), so do the
# rate-limit buckets and the Socket.IO fan-out between tasks. Losing it is an
# outage, not a slowdown.

resource "aws_elasticache_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.data[*].id
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = local.name
  description          = "${local.name} — blacklist, rate limits, socket.io"

  engine         = "redis"
  engine_version = "7.1"
  node_type      = var.redis_node_type
  port           = 6379

  # One node. A second one only helps if automatic_failover is on, which needs
  # at least two — raise both together when the blacklist stops being something
  # a restart can rebuild.
  num_cache_clusters         = 1
  automatic_failover_enabled = false

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  # rediss:// in REDIS_URL — see ecs.tf. No auth token: the security group is
  # the boundary, and a token in the URL would be a second secret to rotate.
  transit_encryption_enabled = true

  parameter_group_name = aws_elasticache_parameter_group.main.name

  maintenance_window       = "mon:07:00-mon:08:00"
  snapshot_retention_limit = 1
  snapshot_window          = "04:00-05:00"

  apply_immediately = false

  tags = { Name = local.name }
}

# Evicting a blacklist entry early would silently un-revoke a token, and
# dropping a rate-limit bucket resets an attacker's budget. Refuse writes
# instead of choosing a key to lose.
resource "aws_elasticache_parameter_group" "main" {
  # No name_prefix on this resource type, so a family change means replacing it
  # by name rather than rolling one in beside the other.
  name   = "${local.name}-redis7"
  family = "redis7"

  parameter {
    name  = "maxmemory-policy"
    value = "noeviction"
  }
}
