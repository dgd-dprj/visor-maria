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
  description = "Onde o painel abre (HTTPS, sem login): o IP fixo escrito como <ip-com-hifens>.sslip.io, que o Caddy da instância usa para pedir o certificado."
  value       = "https://${replace(aws_eip.painel.public_ip, ".", "-")}.sslip.io"
}
