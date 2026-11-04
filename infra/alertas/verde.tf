# A credencial do Verde recusada (#308 da Maria): em 22 e 23/10, 283 de 283 consultas
# ao Verde voltaram 401 por 23 horas, e ninguém foi avisado. O aviso conta as
# respostas 401 e 403 no evento verde_chamada dos logs da Maria.
#
# Única peça que encosta num recurso da Maria: o filtro de métrica fica dentro do
# grupo de logs dela. Ligada por decisão da Nicole (2026-11-03), com o menor custo:
# - só nos ambientes de var.ambientes_do_verde (por padrão, só produção: o release
#   não tem uso);
# - uma métrica por ambiente, sem dimensões (cada dimensão vira métrica cobrada);
# - sem default_value: o filtro só grava quando há recusa, e a falta de dado conta
#   como normal (treat_missing_data).
# Custo: cerca de US$ 0,30 por métrica e US$ 0,10 por alarme, por mês.

locals {
  ambientes_do_verde = var.alerta_do_verde ? { for k, v in local.ambientes : k => v if contains(var.ambientes_do_verde, k) } : {}
}

resource "aws_cloudwatch_log_metric_filter" "verde_recusou" {
  for_each = local.ambientes_do_verde

  name           = "visor-maria-${each.key}-verde-recusou"
  log_group_name = each.value.grupo_de_log
  pattern        = "{ ($.evento = \"verde_chamada\") && (($.status = 401) || ($.status = 403)) }"

  metric_transformation {
    name      = "VerdeRecusou"
    namespace = "VisorMaria/${each.key}"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "verde_recusou" {
  for_each = local.ambientes_do_verde

  alarm_name        = "visor-maria-${each.key}-verde-recusou"
  alarm_description = "Maria (${each.value.nome}): o Verde recusou a credencial (401 ou 403) em pelo menos uma consulta nos últimos 10 minutos (a Maria tenta cada consulta 3 vezes). As consultas de RG e de processo falham, e a pessoa ouve que não foi encontrada. Volta ao normal depois de 2 horas sem recusa."
  namespace         = "VisorMaria/${each.key}"
  metric_name       = "VerdeRecusou"
  statistic         = "Sum"
  period            = 600
  # Dispara com 1 janela de 10 min em violação e só volta ao normal com as 12 últimas
  # (2 horas) limpas. Testado contra os logs de 22 e 23/10: de noite, com pouco tráfego,
  # as recusas caem abaixo de 3 linhas por janela, ou seja, nenhuma consulta inteira (a
  # Maria tenta cada consulta 3 vezes), e com 1 de 1 o alarme abriria e fecharia 16 vezes
  # no incidente; com 1 de 12, cerca de 4.
  evaluation_periods  = 12
  datapoints_to_alarm = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 3
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alertas.arn]
  ok_actions          = [aws_sns_topic.alertas.arn]

  depends_on = [aws_cloudwatch_log_metric_filter.verde_recusou]
}
