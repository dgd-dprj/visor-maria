# O aviso sai do CloudWatch, e não do Visor: o Visor só consulta com a tela aberta,
# e um alerta precisa ser avaliado o tempo todo (visor-maria#2).

resource "aws_sns_topic" "alertas" {
  name = "visor-maria-alertas"
}

resource "aws_sns_topic_subscription" "email" {
  for_each = toset(var.destinatarios)

  topic_arn = aws_sns_topic.alertas.arn
  protocol  = "email"
  endpoint  = each.value
}
