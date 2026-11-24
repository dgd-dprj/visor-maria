# ── Papel da instância: só leitura (README, "Permissões", item 6) ────────

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "painel" {
  name               = "visor-maria-painel"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# O Session Manager (túnel e deploy) pede este papel gerenciado.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.painel.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "painel" {
  statement {
    sid     = "ConsultarOsLogsDaMariaEDoRenovador"
    actions = ["logs:StartQuery"]
    resources = [
      "arn:aws:logs:*:${local.conta}:log-group:/ecs/maria-langgraph-pp*",
      "arn:aws:logs:*:${local.conta}:log-group:/ecs/maria-langgraph-pp*:*",
      "arn:aws:logs:*:${local.conta}:log-group:/ecs/visor-maria/renovador",
      "arn:aws:logs:*:${local.conta}:log-group:/ecs/visor-maria/renovador:*",
    ]
  }

  statement {
    sid       = "ResultadosDasConsultas"
    actions   = ["logs:GetQueryResults", "logs:StopQuery", "logs:DescribeLogGroups"]
    resources = ["*"]
  }

  statement {
    sid       = "MetricasDoCloudWatch"
    actions   = ["cloudwatch:GetMetricData", "cloudwatch:ListMetrics"]
    resources = ["*"] # GetMetricData exige "*"
  }

  statement {
    sid       = "AlarmesDoVisor"
    actions   = ["cloudwatch:DescribeAlarms", "cloudwatch:DescribeAlarmHistory"]
    resources = ["*"]
  }

  # O Docker da instância grava o log do painel no grupo dele.
  statement {
    sid       = "LogDoPainel"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.painel.arn}:*"]
  }

  statement {
    sid       = "PuxarAImagemDoPainel"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [aws_ecr_repository.painel.arn]
  }

  statement {
    sid       = "LoginNoEcr"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid       = "TokenDoGitHub"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.github.arn]
  }

  dynamic "statement" {
    for_each = var.ler_custo ? [1] : []
    content {
      sid       = "CustoDaConta"
      actions   = ["ce:GetCostAndUsage"]
      resources = ["*"]
    }
  }
}

resource "aws_iam_role_policy" "painel" {
  name   = "leitura"
  role   = aws_iam_role.painel.id
  policy = data.aws_iam_policy_document.painel.json
}

resource "aws_iam_instance_profile" "painel" {
  name = "visor-maria-painel"
  role = aws_iam_role.painel.name
}

# ── Papel de deploy do GitHub (README, item 7): só a main deste repositório ─

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
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${var.sub_do_repositorio}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "visor-maria-deploy"
  assume_role_policy = data.aws_iam_policy_document.confianca_do_github.json
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "LoginNoEcr"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EnviarSoParaORepositorioDoPainel"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.painel.arn]
  }

  # O deploy manda a instância reiniciar o serviço, que puxa a imagem nova.
  statement {
    sid     = "ReiniciarOPainelPeloSessionManager"
    actions = ["ssm:SendCommand"]
    resources = [
      aws_instance.painel.arn,
      "arn:aws:ssm:${var.regiao}::document/AWS-RunShellScript",
    ]
  }

  statement {
    sid       = "AcompanharOComando"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy-do-painel"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

# ── Liga e desliga agendado (escala.tf) ──────────────────────────────────

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "agendador" {
  name               = "visor-maria-painel-agendador"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "agendador" {
  statement {
    actions   = ["ec2:StartInstances", "ec2:StopInstances"]
    resources = [aws_instance.painel.arn]
  }
}

resource "aws_iam_role_policy" "agendador" {
  name   = "ligar-e-desligar-o-painel"
  role   = aws_iam_role.agendador.id
  policy = data.aws_iam_policy_document.agendador.json
}
