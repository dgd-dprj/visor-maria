# A instância só recebe tráfego do VPC origin do CloudFront, na porta do painel. O acesso por túnel e o deploy usam o
# Session Manager, que sai da instância e não precisa de entrada.
resource "aws_security_group" "painel" {
  name        = "visor-maria-painel"
  description = "Visor Maria: so o VPC origin do CloudFront entra; saida para a AWS e o GitHub pelo NAT"
  vpc_id      = data.aws_vpc.maria.id
}

# O CloudFront cria este grupo na conta quando liga o VPC origin à distribuição.
data "aws_security_group" "origem_do_cloudfront" {
  name   = "CloudFront-VPCOrigin-Service-SG"
  vpc_id = data.aws_vpc.maria.id

  depends_on = [aws_cloudfront_distribution.painel]
}

resource "aws_vpc_security_group_ingress_rule" "do_cloudfront" {
  security_group_id            = aws_security_group.painel.id
  description                  = "Painel, so a partir do VPC origin do CloudFront"
  ip_protocol                  = "tcp"
  from_port                    = 8050
  to_port                      = 8050
  referenced_security_group_id = data.aws_security_group.origem_do_cloudfront.id
}

resource "aws_vpc_security_group_egress_rule" "saida" {
  security_group_id = aws_security_group.painel.id
  description       = "HTTPS para a AWS e o GitHub"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}
