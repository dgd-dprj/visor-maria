# A porta 443 (HTTPS) fica aberta para quem estiver em var.cidrs_permitidos (por padrão, todo mundo). O acesso por túnel e o deploy
# usam o Session Manager, que sai da instância e não precisa de entrada.
resource "aws_security_group" "painel" {
  name        = "visor-maria-painel"
  description = "Visor Maria: porta 443 para os CIDRs permitidos; saida livre"
  vpc_id      = data.aws_vpc.padrao.id
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  for_each = toset(var.cidrs_permitidos)

  security_group_id = aws_security_group.painel.id
  description       = "Painel (HTTPS)"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = each.value
}

resource "aws_vpc_security_group_egress_rule" "saida" {
  security_group_id = aws_security_group.painel.id
  description       = "Saida para a AWS e o GitHub"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}
