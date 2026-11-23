data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ── Papel da tarefa: só leitura (README, "Permissões", item 6) ───────────

resource "aws_iam_role" "tarefa" {
  name               = "visor-maria-painel"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "tarefa" {
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

  # O túnel (ECS Exec) usa os canais do Session Manager.
  statement {
    sid       = "TunelDoSessionManager"
    actions   = ["ssmmessages:CreateControlChannel", "ssmmessages:CreateDataChannel", "ssmmessages:OpenControlChannel", "ssmmessages:OpenDataChannel"]
    resources = ["*"]
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

resource "aws_iam_role_policy" "tarefa" {
  name   = "leitura"
  role   = aws_iam_role.tarefa.id
  policy = data.aws_iam_policy_document.tarefa.json
}

# ── Papel de execução: puxa a imagem, escreve o log e lê o token do GitHub ─

resource "aws_iam_role" "execucao" {
  name               = "visor-maria-painel-execucao"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execucao" {
  role       = aws_iam_role.execucao.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execucao" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.github.arn]
  }
}

resource "aws_iam_role_policy" "execucao" {
  name   = "token-do-github"
  role   = aws_iam_role.execucao.id
  policy = data.aws_iam_policy_document.execucao.json
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

  statement {
    sid       = "AtualizarSoOServicoDoPainel"
    actions   = ["ecs:UpdateService", "ecs:DescribeServices"]
    resources = [aws_ecs_service.painel.id]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy-do-painel"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
