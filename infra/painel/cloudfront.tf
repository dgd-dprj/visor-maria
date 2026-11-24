# O painel online: CloudFront (HTTPS, endereço *.cloudfront.net) -> VPC origin -> a instância EC2, sem balanceador.
# Sem login por enquanto (a autenticação fica para depois); ver var.ips_permitidos.

resource "aws_cloudfront_vpc_origin" "painel" {
  vpc_origin_endpoint_config {
    name                   = "visor-maria"
    arn                    = aws_instance.painel.arn
    http_port              = 8050
    https_port             = 443
    origin_protocol_policy = "http-only"

    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1
    }
  }
}

# Políticas gerenciadas da AWS: sem cache (o painel é dinâmico) e todos os cabeçalhos, cookies e a query vão à origem.
data "aws_cloudfront_cache_policy" "sem_cache" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "tudo" {
  name = "Managed-AllViewer"
}

resource "aws_cloudfront_distribution" "painel" {
  enabled         = true
  comment         = "Visor Maria"
  is_ipv6_enabled = true
  price_class     = "PriceClass_All" # o público está no Brasil
  web_acl_id      = length(var.ips_permitidos) > 0 ? aws_wafv2_web_acl.painel[0].arn : null

  origin {
    domain_name = aws_instance.painel.private_dns
    origin_id   = "painel"

    vpc_origin_config {
      vpc_origin_id = aws_cloudfront_vpc_origin.painel.id
    }
  }

  default_cache_behavior {
    target_origin_id         = "painel"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"] # o Dash usa POST nos callbacks
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.sem_cache.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.tudo.id
  }

  restrictions {
    geo_restriction {
      restriction_type = length(var.paises_permitidos) > 0 ? "whitelist" : "none"
      locations        = var.paises_permitidos
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# ── WAF: só os IPs permitidos (quando a lista não é vazia) ───────────────

resource "aws_wafv2_ip_set" "permitidos" {
  count    = length(var.ips_permitidos) > 0 ? 1 : 0
  provider = aws.us_east_1

  name               = "visor-maria-permitidos"
  scope              = "CLOUDFRONT"
  ip_address_version = "IPV4"
  addresses          = var.ips_permitidos
}

resource "aws_wafv2_web_acl" "painel" {
  count    = length(var.ips_permitidos) > 0 ? 1 : 0
  provider = aws.us_east_1

  name  = "visor-maria"
  scope = "CLOUDFRONT"

  default_action {
    block {}
  }

  rule {
    name     = "permitir-ips"
    priority = 1

    action {
      allow {}
    }

    statement {
      ip_set_reference_statement {
        arn = aws_wafv2_ip_set.permitidos[0].arn
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "visor-maria-permitidos"
      sampled_requests_enabled   = false
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "visor-maria"
    sampled_requests_enabled   = false
  }
}
