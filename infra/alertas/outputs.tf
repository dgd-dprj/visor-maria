output "topico" {
  description = "Tópico SNS dos alertas."
  value       = aws_sns_topic.alertas.arn
}

output "alarmes" {
  description = "Nome de cada alarme criado."
  value = concat(
    [for a in aws_cloudwatch_metric_alarm.sem_host_saudavel : a.alarm_name],
    [for a in aws_cloudwatch_metric_alarm.erros_5xx : a.alarm_name],
    [for a in aws_cloudwatch_metric_alarm.cpu_alta : a.alarm_name],
    [for a in aws_cloudwatch_metric_alarm.latencia_p99 : a.alarm_name],
    [for a in aws_cloudwatch_metric_alarm.verde_recusou : a.alarm_name],
  )
}
