# O papel e o agendamento da renovação do token do Verde (visor-maria#14).
# Os recursos da Maria são tratados só por nome e por ARN montado: nada é lido do estado dela.

data "aws_caller_identity" "atual" {}

locals {
  conta = data.aws_caller_identity.atual.account_id

  # O Secrets Manager acrescenta um sufixo aleatório ao ARN do segredo.
  arns_dos_segredos = [for amb in keys(var.servicos_por_ambiente) : "arn:aws:secretsmanager:${var.regiao}:${local.conta}:secret:${var.projeto_da_maria}-${amb}/app-*"]
  arns_das_travas   = ["arn:aws:secretsmanager:${var.regiao}:${local.conta}:secret:visor-maria/trava-renovacao-*"]
  arns_dos_servicos = [for s in values(var.servicos_por_ambiente) : "arn:aws:ecs:${var.regiao}:${local.conta}:service/${var.cluster_da_maria}/${s}"]
}

resource "aws_cloudwatch_log_group" "renovador" {
  name              = "/ecs/visor-maria/renovador"
  retention_in_days = 90
}

# ── Papel da tarefa: o único do Visor que escreve num segredo ────────────

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "renovador" {
  name               = "visor-maria-renovador"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
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
}

resource "aws_iam_role_policy" "renovador" {
  name   = "renovacao-do-token-do-verde"
  role   = aws_iam_role.renovador.id
  policy = data.aws_iam_policy_document.renovador.json
}

# O papel de execução só puxa a imagem e escreve o log.
resource "aws_iam_role" "execucao" {
  name               = "visor-maria-renovador-execucao"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execucao" {
  role       = aws_iam_role.execucao.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ── Tarefa e agendamento ─────────────────────────────────────────────────

resource "aws_ecs_task_definition" "renovador" {
  family                   = "visor-maria-renovador"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  task_role_arn            = aws_iam_role.renovador.arn
  execution_role_arn       = aws_iam_role.execucao.arn

  container_definitions = jsonencode([{
    name      = "renovador"
    image     = var.imagem
    essential = true
    command   = ["python", "-m", "painel.renovador"]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.renovador.name
        awslogs-region        = var.regiao
        awslogs-stream-prefix = "renovador"
      }
    }
  }])
}

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
  name               = "visor-maria-renovador-agendador"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "agendador" {
  statement {
    actions   = ["ecs:RunTask"]
    resources = [aws_ecs_task_definition.renovador.arn_without_revision, "${aws_ecs_task_definition.renovador.arn_without_revision}:*"]
  }
  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.renovador.arn, aws_iam_role.execucao.arn]
  }
}

resource "aws_iam_role_policy" "agendador" {
  name   = "disparar-a-renovacao"
  role   = aws_iam_role.agendador.id
  policy = data.aws_iam_policy_document.agendador.json
}

resource "aws_scheduler_schedule" "renovador" {
  name                = "visor-maria-renovador"
  description         = "Renova o token do Verde quando falta 1 dia para vencer (visor-maria#14). Uma tarefa por dia."
  schedule_expression = var.horario_utc
  state               = var.agendamento_ligado ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = var.cluster_do_visor
    role_arn = aws_iam_role.agendador.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.renovador.arn_without_revision
      launch_type         = "FARGATE"
      task_count          = 1

      network_configuration {
        subnets          = var.subredes
        security_groups  = [var.grupo_de_seguranca]
        assign_public_ip = false
      }
    }

    retry_policy {
      maximum_retry_attempts = 0 # nunca repetir sozinho: o refresh invalida o token antigo
    }
  }
}
