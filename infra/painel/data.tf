# Sem VPC própria nem da Maria: a instância usa a VPC padrão da conta (docs/decisoes.md, 2026-11-24).
data "aws_caller_identity" "atual" {}

data "aws_vpc" "padrao" {
  default = true
}

data "aws_subnets" "padrao" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.padrao.id]
  }
}

# O provedor OIDC do GitHub já existe na conta: só é consultado.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

# A imagem mais recente do Amazon Linux 2023 (Docker e AWS CLI vêm no repositório e na imagem).
data "aws_ssm_parameter" "ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  conta = data.aws_caller_identity.atual.account_id
}
