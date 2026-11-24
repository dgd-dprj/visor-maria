# O painel online: CloudFront (HTTPS, endereço xxxx.cloudfront.net, certificado da AWS) -> a EC2, pela porta 80.
# Sem domínio nosso. O login com Google é conferido pelo próprio painel (login.tf e src/painel/login.py).

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

  origin {
    domain_name = aws_eip.painel.public_dns
    origin_id   = "painel"

    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_protocol_policy   = "http-only"
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = 60 # as consultas de uma tela com o cache frio podem demorar
      origin_keepalive_timeout = 30
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
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
