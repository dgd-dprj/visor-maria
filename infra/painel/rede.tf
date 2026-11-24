# A tarefa só recebe tráfego do balanceador interno, na porta do painel. O túnel do Session Manager (ECS Exec)
# não passa pelo grupo.
resource "aws_security_group" "painel" {
  name        = "visor-maria-painel"
  description = "Visor Maria: so o balanceador entra; saida para a AWS e o GitHub pelo NAT"
  vpc_id      = data.aws_vpc.maria.id
}

resource "aws_vpc_security_group_ingress_rule" "do_balanceador" {
  security_group_id            = aws_security_group.painel.id
  description                  = "Painel, so a partir do balanceador"
  ip_protocol                  = "tcp"
  from_port                    = 8050
  to_port                      = 8050
  referenced_security_group_id = aws_security_group.balanceador.id
}

# O balanceador é interno: só o CloudFront (VPC origin) chega a ele.
resource "aws_security_group" "balanceador" {
  name        = "visor-maria-balanceador"
  description = "Visor Maria: balanceador interno, so o VPC origin do CloudFront entra"
  vpc_id      = data.aws_vpc.maria.id
}

# O CloudFront cria este grupo na conta quando o VPC origin sobe; o balanceador precisa aceitá-lo.
data "aws_security_group" "origem_do_cloudfront" {
  name   = "CloudFront-VPCOrigin-Service-SG"
  vpc_id = data.aws_vpc.maria.id

  # O grupo aparece quando o CloudFront liga o VPC origin à distribuição.
  depends_on = [aws_cloudfront_distribution.painel]
}

resource "aws_vpc_security_group_ingress_rule" "do_cloudfront" {
  security_group_id            = aws_security_group.balanceador.id
  description                  = "HTTP so a partir do VPC origin do CloudFront"
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
  referenced_security_group_id = data.aws_security_group.origem_do_cloudfront.id
}

resource "aws_vpc_security_group_egress_rule" "do_balanceador_para_o_painel" {
  security_group_id            = aws_security_group.balanceador.id
  description                  = "Balanceador para o painel"
  ip_protocol                  = "tcp"
  from_port                    = 8050
  to_port                      = 8050
  referenced_security_group_id = aws_security_group.painel.id
}

resource "aws_vpc_security_group_egress_rule" "saida" {
  security_group_id = aws_security_group.painel.id
  description       = "HTTPS para a AWS e o GitHub"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}
