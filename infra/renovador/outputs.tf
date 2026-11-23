output "papel_da_renovacao" {
  description = "Papel da tarefa: o que a policy permite está em main.tf."
  value       = aws_iam_role.renovador.arn
}

output "agendamento" {
  description = "Estado do agendamento (DISABLED até alguém ligar)."
  value       = aws_scheduler_schedule.renovador.state
}
