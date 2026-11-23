# Sem nenhuma entrada: o acesso é pelo túnel do Session Manager (ECS Exec), que não passa pelo grupo.
resource "aws_security_group" "painel" {
  name        = "visor-maria-painel"
  description = "Visor Maria: sem entrada, so saida (AWS e GitHub pelo NAT)"
  vpc_id      = data.aws_vpc.maria.id
}

resource "aws_vpc_security_group_egress_rule" "saida" {
  security_group_id = aws_security_group.painel.id
  description       = "HTTPS para a AWS e o GitHub"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}
