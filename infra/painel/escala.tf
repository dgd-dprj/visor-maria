# Desliga o painel à noite e liga de manhã (uso interno, menos de dez pessoas): o Fargate só é cobrado
# enquanto há tarefa. Application Auto Scaling, com o fuso de Brasília.
resource "aws_appautoscaling_target" "painel" {
  count = var.horario_comercial ? 1 : 0

  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${aws_ecs_cluster.painel.name}/${aws_ecs_service.painel.name}"
  min_capacity       = var.instancias
  max_capacity       = var.instancias
}

resource "aws_appautoscaling_scheduled_action" "desligar" {
  count = var.horario_comercial ? 1 : 0

  name               = "visor-maria-desligar"
  service_namespace  = aws_appautoscaling_target.painel[0].service_namespace
  scalable_dimension = aws_appautoscaling_target.painel[0].scalable_dimension
  resource_id        = aws_appautoscaling_target.painel[0].resource_id
  schedule           = "cron(${var.hora_de_desligar})"
  timezone           = "America/Sao_Paulo"

  scalable_target_action {
    min_capacity = 0
    max_capacity = 0
  }
}

resource "aws_appautoscaling_scheduled_action" "ligar" {
  count = var.horario_comercial ? 1 : 0

  name               = "visor-maria-ligar"
  service_namespace  = aws_appautoscaling_target.painel[0].service_namespace
  scalable_dimension = aws_appautoscaling_target.painel[0].scalable_dimension
  resource_id        = aws_appautoscaling_target.painel[0].resource_id
  schedule           = "cron(${var.hora_de_ligar})"
  timezone           = "America/Sao_Paulo"

  scalable_target_action {
    min_capacity = var.instancias
    max_capacity = var.instancias
  }
}
