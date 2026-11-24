# Login do painel com a conta Google, pelo Amazon Cognito (docs/decisoes.md, 2026-11-24, "login com Google").
#
# O grupo de usuários é o coilab-users (us-east-1), que já tem o Google (decisão da Nicole, 24/11): o Visor tem um
# cliente próprio nele, criado pelo console, e não toca no cliente do CoiLab. Aqui ficam só a configuração que o
# painel lê, a lista de e-mails e as permissões. O painel (src/painel/login.py) só abre para os e-mails de
# /visor-maria/emails-com-acesso, relidos a cada minuto; os usuários do CoiLab no mesmo grupo não entram por isso.

# O que o painel precisa para montar o login (lido do Parameter Store). Nada aqui é segredo: o cliente é público (PKCE).
resource "aws_ssm_parameter" "login" {
  name = "/visor-maria/login"
  type = "String"
  value = jsonencode({
    dominio  = var.dominio_do_login
    cliente  = var.cliente_do_login
    endereco = "https://${aws_cloudfront_distribution.painel.domain_name}"
  })
}

# Quem pode abrir o painel: e-mails separados por vírgula. O Terraform só grava a primeira versão; daí em diante a
# lista é editada no console (Systems Manager > Parameter Store), e o apply não desfaz a edição.
resource "aws_ssm_parameter" "emails_com_acesso" {
  name  = "/visor-maria/emails-com-acesso"
  type  = "StringList"
  value = join(",", var.emails_com_acesso)

  lifecycle {
    ignore_changes = [value]
  }
}

# Para quem cuida da lista (a Nicole): ler e editar só este parâmetro. O Ícaro anexa ao usuário dela.
data "aws_iam_policy_document" "editar_emails" {
  statement {
    sid       = "EditarAListaDeEmails"
    actions   = ["ssm:GetParameter", "ssm:GetParameterHistory", "ssm:PutParameter"]
    resources = [aws_ssm_parameter.emails_com_acesso.arn]
  }

  statement {
    sid       = "AcharOParametroNoConsole"
    actions   = ["ssm:DescribeParameters"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "editar_emails" {
  name        = "visor-maria-editar-emails"
  description = "Ler e editar a lista de e-mails com acesso ao Visor Maria (/visor-maria/emails-com-acesso)."
  policy      = data.aws_iam_policy_document.editar_emails.json
}
