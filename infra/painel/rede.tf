# A porta 80 da instância só aceita os IPs do CloudFront (lista gerenciada pela AWS), e quem o público alcança é o CloudFront,
# na 443. O acesso à máquina e o deploy usam o Session Manager, que sai da instância e não precisa de entrada.
resource "aws_security_group" "painel" {
  name = "visor-maria-painel"
  # A descrição não pode mudar sem recriar o grupo (com a instância dentro): fica a do começo, de quando era a 443.
  description = "Visor Maria: porta 443 para os CIDRs permitidos; saida livre"
  vpc_id      = data.aws_vpc.padrao.id
}

data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_vpc_security_group_ingress_rule" "do_cloudfront" {
  security_group_id = aws_security_group.painel.id
  description       = "Painel (HTTP), so os IPs do CloudFront"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
}

resource "aws_vpc_security_group_egress_rule" "saida" {
  security_group_id = aws_security_group.painel.id
  description       = "Saida para a AWS e o GitHub"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}
