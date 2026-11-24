output "repositorio_ecr" {
  description = "Onde o deploy envia a imagem."
  value       = aws_ecr_repository.painel.repository_url
}

output "instancia" {
  description = "A EC2 do painel (túnel: aws ssm start-session --target <id>)."
  value       = aws_instance.painel.id
}

output "papel_de_deploy" {
  description = "ARN do papel de deploy: vai na variável AWS_ROLE_ARN_DEPLOY do repositório."
  value       = aws_iam_role.deploy.arn
}

output "segredo_do_github" {
  description = "Onde pôr o token do GitHub (put-secret-value)."
  value       = aws_secretsmanager_secret.github.name
}

output "endereco_do_painel" {
  description = "Onde o painel abre (HTTP, sem login)."
  value       = "http://${aws_eip.painel.public_ip}"
}
