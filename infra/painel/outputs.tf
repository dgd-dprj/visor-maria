output "repositorio_ecr" {
  description = "Onde o deploy envia a imagem."
  value       = aws_ecr_repository.painel.repository_url
}

output "cluster" {
  value = aws_ecs_cluster.painel.name
}

output "servico" {
  value = aws_ecs_service.painel.name
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
  description = "Onde o painel abre (HTTPS)."
  value       = "https://${aws_cloudfront_distribution.painel.domain_name}"
}
