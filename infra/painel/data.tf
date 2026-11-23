# Os recursos da Maria são consultados por nome (docs/decisoes.md, 2026-10-26, regra 2), nunca pelo estado dela.

data "aws_caller_identity" "atual" {}

data "aws_vpc" "maria" {
  filter {
    name   = "tag:Name"
    values = [var.vpc_da_maria]
  }
}

data "aws_subnets" "privadas" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.maria.id]
  }
  filter {
    name   = "tag:Name"
    values = [for s in var.subredes_privadas : "${var.vpc_da_maria}-${s}"]
  }
}

# O provedor OIDC do GitHub já existe na conta: só é consultado.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

locals {
  conta = data.aws_caller_identity.atual.account_id
}
