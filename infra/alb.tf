locals {
  # Either Terraform issues the certificate (route53_zone_id given) or one is
  # handed to it. Exactly one of the two must be set; the check below says so
  # at plan time instead of failing halfway through an apply.
  create_certificate = var.route53_zone_id != "" && var.acm_certificate_arn == ""
  certificate_arn    = local.create_certificate ? aws_acm_certificate_validation.main[0].certificate_arn : var.acm_certificate_arn
}

resource "terraform_data" "dns_inputs_check" {
  lifecycle {
    precondition {
      condition     = var.route53_zone_id != "" || var.acm_certificate_arn != ""
      error_message = "Set route53_zone_id (Terraform issues the certificate) or acm_certificate_arn (you already have one)."
    }
  }
}

resource "aws_acm_certificate" "main" {
  count = local.create_certificate ? 1 : 0

  domain_name               = var.domain_name
  subject_alternative_names = var.additional_domain_names
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = local.create_certificate ? {
    for option in aws_acm_certificate.main[0].domain_validation_options :
    option.domain_name => option
  } : {}

  zone_id = var.route53_zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  records = [each.value.resource_record_value]
  ttl     = 60

  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "main" {
  count = local.create_certificate ? 1 : 0

  certificate_arn         = aws_acm_certificate.main[0].arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

resource "aws_lb" "main" {
  name               = local.name
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  # A WebSocket that goes quiet must not be culled. The backend's own
  # proxy_read_timeout is an hour; this is the hop in front of it.
  idle_timeout = 3600

  enable_deletion_protection = true
  drop_invalid_header_fields = true

  tags = { Name = local.name }
}

resource "aws_lb_target_group" "app" {
  name        = local.name
  port        = 80
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id

  # /health goes through nginx to the backend, so a passing check means the
  # whole chain answers — same reasoning as the container's HEALTHCHECK.
  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  # Socket.IO opens with an HTTP long-polling handshake before it upgrades, and
  # those first requests must all land on the same task or the handshake fails
  # with "Session ID unknown". The Redis manager fans out *messages* between
  # tasks; it does not make a session portable.
  stickiness {
    type            = "lb_cookie"
    cookie_duration = 86400
    enabled         = true
  }

  # Long enough for an in-flight request, short enough that a deploy is not a
  # five-minute wait.
  deregistration_delay = 30
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = local.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

# The container never redirects to https itself — it cannot tell, since the ALB
# forwards over plain HTTP and a redirect there would loop. This listener is
# where the upgrade happens.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# One alias record per hostname. `A` with an alias rather than a CNAME because
# the apex of a zone cannot hold a CNAME — that is a DNS rule, not an AWS one,
# and the alias is Route 53's way around it.
resource "aws_route53_record" "app" {
  for_each = var.route53_zone_id != "" ? toset(concat([var.domain_name], var.additional_domain_names)) : toset([])

  zone_id = var.route53_zone_id
  name    = each.value
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}
