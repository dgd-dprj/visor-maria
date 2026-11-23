output "papel_da_renovacao" {
  description = "ARN do papel: vai na variável AWS_ROLE_ARN_RENOVADOR do repositório (Settings > Variables)."
  value       = aws_iam_role.renovador.arn
}

output "grupo_de_logs" {
  description = "Grupo que a tela Credencial lê."
  value       = aws_cloudwatch_log_group.renovador.name
}
