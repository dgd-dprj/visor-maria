# Desliga a instância à noite e liga de manhã (uso interno): parada, a EC2 não cobra computação, só o disco de 8 GB.
# EventBridge Scheduler com o fuso de Brasília; o IP privado e o disco ficam, e o serviço sobe sozinho na ligada.
resource "aws_scheduler_schedule" "desligar" {
  count = var.horario_comercial ? 1 : 0

  name                         = "visor-maria-desligar"
  schedule_expression          = "cron(${var.hora_de_desligar})"
  schedule_expression_timezone = "America/Sao_Paulo"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:stopInstances"
    role_arn = aws_iam_role.agendador.arn
    input    = jsonencode({ InstanceIds = [aws_instance.painel.id] })
  }
}

resource "aws_scheduler_schedule" "ligar" {
  count = var.horario_comercial ? 1 : 0

  name                         = "visor-maria-ligar"
  schedule_expression          = "cron(${var.hora_de_ligar})"
  schedule_expression_timezone = "America/Sao_Paulo"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:startInstances"
    role_arn = aws_iam_role.agendador.arn
    input    = jsonencode({ InstanceIds = [aws_instance.painel.id] })
  }
}
