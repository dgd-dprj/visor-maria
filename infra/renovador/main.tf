# O papel do GitHub Actions que renova o token do Verde (visor-maria#14).
# Os recursos da Maria são tratados só por nome e por ARN montado: nada é lido do estado dela
# e nada é acrescentado dentro dela (docs/decisoes.md, 2026-10-26).

data "aws_caller_identity" "atual" {}

# O provedor OIDC do GitHub já existe na conta (é o do deploy da Maria): só é consultado.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

locals {
  conta = data.aws_caller_identity.atual.account_id

  # O Secrets Manager acrescenta um sufixo aleatório ao ARN do segredo.
  arns_dos_segredos = [for amb in keys(var.servicos_por_ambiente) : "arn:aws:secretsmanager:${var.regiao}:${local.conta}:secret:${var.projeto_da_maria}-${amb}/app-*"]
  arns_das_travas   = ["arn:aws:secretsmanager:${var.regiao}:${local.conta}:secret:visor-maria/trava-renovacao-*"]
  arns_dos_servicos = [for s in values(var.servicos_por_ambiente) : "arn:aws:ecs:${var.regiao}:${local.conta}:service/${var.cluster_da_maria}/${s}"]
}

# Onde o comando grava a linha diária (validade, sem token) que a tela Credencial lê.
resource "aws_cloudwatch_log_group" "renovador" {
  name              = "/ecs/visor-maria/renovador"
  retention_in_days = 90
}

data "aws_iam_policy_document" "confianca_do_github" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Só a branch main deste repositório (o agendamento e o disparo manual rodam nela).
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:dgd-dprj/visor-maria:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "renovador" {
  name               = "visor-maria-renovador"
  assume_role_policy = data.aws_iam_policy_document.confianca_do_github.json
}

data "aws_iam_policy_document" "renovador" {
  statement {
    sid       = "LerEGravarSoOTokenDosAmbientes"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue"]
    resources = local.arns_dos_segredos
  }

  statement {
    sid       = "TravaContraDuploDisparo"
    actions   = ["secretsmanager:CreateSecret", "secretsmanager:DescribeSecret", "secretsmanager:DeleteSecret"]
    resources = local.arns_das_travas
  }

  statement {
    sid       = "RedeploySoNosServicosDaMaria"
    actions   = ["ecs:UpdateService"]
    resources = local.arns_dos_servicos
  }

  statement {
    sid       = "RegistrarSoNoGrupoDoRenovador"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.renovador.arn}:*"]
  }
}

resource "aws_iam_role_policy" "renovador" {
  name   = "renovacao-do-token-do-verde"
  role   = aws_iam_role.renovador.id
  policy = data.aws_iam_policy_document.renovador.json
}
