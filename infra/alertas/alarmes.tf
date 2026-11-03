# As 8 regras que o Grafana avaliava (grupo saude-operacional, apagado na #380 da
# Maria): 4 tipos, em produção e no release, com os mesmos limites (visor-maria#2).
# A mensagem só leva ambiente, métrica e valor, nunca dado de pessoa atendida.

resource "aws_cloudwatch_metric_alarm" "sem_host_saudavel" {
  for_each = local.ambientes

  alarm_name        = "visor-maria-${each.key}-sem-host-saudavel"
  alarm_description = "Maria (${each.value.nome}): nenhum container saudável atrás do balanceador por 2 minutos. Ninguém consegue ser atendido."
  namespace         = "AWS/ApplicationELB"
  metric_name       = "HealthyHostCount"
  statistic         = "Average"
  dimensions = {
    LoadBalancer = data.aws_lb.maria.arn_suffix
    TargetGroup  = each.value.grupo
  }
  period              = 60
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  # Sem dado também é alerta: o balanceador para de mandar a métrica quando não há nada atrás dele.
  treat_missing_data = "breaching"
  alarm_actions      = [aws_sns_topic.alertas.arn]
  ok_actions         = [aws_sns_topic.alertas.arn]
}

resource "aws_cloudwatch_metric_alarm" "erros_5xx" {
  for_each = local.ambientes

  alarm_name        = "visor-maria-${each.key}-erros-5xx"
  alarm_description = "Maria (${each.value.nome}): mais de 10 erros de servidor (5xx) em 5 minutos, duas vezes seguidas."
  namespace         = "AWS/ApplicationELB"
  metric_name       = "HTTPCode_Target_5XX_Count"
  statistic         = "Sum"
  dimensions = {
    LoadBalancer = data.aws_lb.maria.arn_suffix
    TargetGroup  = each.value.grupo
  }
  period              = 300
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 10
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alertas.arn]
  ok_actions          = [aws_sns_topic.alertas.arn]
}

resource "aws_cloudwatch_metric_alarm" "cpu_alta" {
  for_each = local.ambientes

  alarm_name        = "visor-maria-${each.key}-cpu-alta"
  alarm_description = "Maria (${each.value.nome}): CPU média do serviço acima de 80% por 5 minutos."
  namespace         = "AWS/ECS"
  metric_name       = "CPUUtilization"
  statistic         = "Average"
  dimensions = {
    ClusterName = var.projeto_da_maria
    ServiceName = each.value.servico
  }
  period              = 60
  evaluation_periods  = 5
  datapoints_to_alarm = 5
  comparison_operator = "GreaterThanThreshold"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alertas.arn]
  ok_actions          = [aws_sns_topic.alertas.arn]
}

resource "aws_cloudwatch_metric_alarm" "latencia_p99" {
  for_each = local.ambientes

  alarm_name         = "visor-maria-${each.key}-latencia-p99"
  alarm_description  = "Maria (${each.value.nome}): 1 em cada 100 respostas leva mais de 3 s, por 15 minutos."
  namespace          = "AWS/ApplicationELB"
  metric_name        = "TargetResponseTime"
  extended_statistic = "p99"
  dimensions = {
    LoadBalancer = data.aws_lb.maria.arn_suffix
    TargetGroup  = each.value.grupo
  }
  period              = 300
  evaluation_periods  = 3
  datapoints_to_alarm = 3
  comparison_operator = "GreaterThanThreshold"
  threshold           = 3
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alertas.arn]
  ok_actions          = [aws_sns_topic.alertas.arn]
}
