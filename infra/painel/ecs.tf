resource "aws_cloudwatch_log_group" "painel" {
  name              = "/ecs/visor-maria/painel"
  retention_in_days = 30
}

# O valor é posto à mão (aws secretsmanager put-secret-value), para o token nunca entrar no estado do Terraform.
# Precisa de leitura do dgd-dprj/maria-langgraph-pp (Actions: read e Metadata: read), de uma conta de serviço.
resource "aws_secretsmanager_secret" "github" {
  name        = "visor-maria/github-token"
  description = "Token só de leitura do Actions do maria-langgraph-pp, usado pelo painel (GITHUB_TOKEN)"
}

# Sem Container Insights: custo extra sem uso (README, "Custo mensal").
resource "aws_ecs_cluster" "painel" {
  name = "visor-maria"

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_ecs_task_definition" "painel" {
  family                   = "visor-maria"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  task_role_arn            = aws_iam_role.tarefa.arn
  execution_role_arn       = aws_iam_role.execucao.arn

  container_definitions = jsonencode([{
    name         = "painel"
    image        = "${aws_ecr_repository.painel.repository_url}:latest"
    essential    = true
    portMappings = [{ containerPort = 8050, protocol = "tcp" }]
    environment = [
      { name = "PAINEL_FONTE", value = "real" },
      { name = "AWS_REGION", value = var.regiao },
      { name = "PAINEL_CACHE", value = "/tmp/visor-maria-cache" },
    ]
    secrets = [{ name = "GITHUB_TOKEN", valueFrom = aws_secretsmanager_secret.github.arn }]
    # O ECS Exec grava no /tmp do container; o painel não guarda estado fora do cache.
    linuxParameters = { initProcessEnabled = true }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.painel.name
        awslogs-region        = var.regiao
        awslogs-stream-prefix = "painel"
      }
    }
  }])
}

resource "aws_ecs_service" "painel" {
  name                   = "visor-maria"
  cluster                = aws_ecs_cluster.painel.id
  task_definition        = aws_ecs_task_definition.painel.arn
  desired_count          = var.instancias
  launch_type            = "FARGATE"
  enable_execute_command = true # o túnel do Session Manager

  load_balancer {
    target_group_arn = aws_lb_target_group.painel.arn
    container_name   = "painel"
    container_port   = 8050
  }

  # A primeira abertura de uma tela com o cache vazio faz as consultas reais de uma vez (README principal).
  health_check_grace_period_seconds = 120

  network_configuration {
    subnets          = data.aws_subnets.privadas.ids
    security_groups  = [aws_security_group.painel.id]
    assign_public_ip = false # sem endereço público
  }

  # O deploy troca a imagem por fora (workflow), então a revisão da tarefa não é do Terraform; e o
  # agendamento (escala.tf) liga e desliga o serviço, então a quantidade de tarefas também não.
  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}
