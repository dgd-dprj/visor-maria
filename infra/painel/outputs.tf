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
  description = "Onde o painel abre (HTTPS, com login Google): o endereço da distribuição do CloudFront."
  value       = "https://${aws_cloudfront_distribution.painel.domain_name}"
}

output "redirecionamento_para_o_google" {
  description = "Vai em \"URIs de redirecionamento autorizados\" do cliente OAuth, no Google Cloud Console."
  value       = "https://${var.dominio_do_login}/oauth2/idpresponse"
}

output "origem_para_o_google" {
  description = "Vai em \"Origens JavaScript autorizadas\" do mesmo cliente OAuth."
  value       = "https://${var.dominio_do_login}"
}

output "retorno_e_saida_no_cognito" {
  description = "Vão no cliente do aplicativo, no Cognito: URL de retorno permitida e URL de saída permitida."
  value = {
    retorno = "https://${aws_cloudfront_distribution.painel.domain_name}/auth/callback"
    saida   = "https://${aws_cloudfront_distribution.painel.domain_name}/saiu"
  }
}

output "lista_de_emails" {
  description = "Onde editar quem pode abrir o painel: Systems Manager > Parameter Store, na região do painel."
  value       = aws_ssm_parameter.emails_com_acesso.name
}

output "politica_para_editar_a_lista" {
  description = "Política que o Ícaro anexa ao usuário de quem cuida da lista de e-mails."
  value       = aws_iam_policy.editar_emails.arn
}
