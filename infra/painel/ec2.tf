resource "aws_cloudwatch_log_group" "painel" {
  name              = "/visor-maria/painel"
  retention_in_days = 30
}

# O valor é posto à mão (aws secretsmanager put-secret-value), para o token nunca entrar no estado do Terraform.
# Precisa de leitura do dgd-dprj/maria-langgraph-pp (Actions: read e Metadata: read), de uma conta de serviço.
resource "aws_secretsmanager_secret" "github" {
  name        = "visor-maria/github-token"
  description = "Token só de leitura do Actions do maria-langgraph-pp, usado pelo painel (GITHUB_TOKEN)"
}

# Uma instância pequena, na VPC padrão, que roda a imagem Docker do painel. O painel não
# guarda estado (o cache em disco é descartável), então a instância pode ser trocada à vontade.
resource "aws_instance" "painel" {
  ami                         = data.aws_ssm_parameter.ami.value
  instance_type               = var.tipo_da_instancia
  subnet_id                   = sort(data.aws_subnets.padrao.ids)[0]
  vpc_security_group_ids      = [aws_security_group.painel.id]
  iam_instance_profile        = aws_iam_instance_profile.painel.name
  associate_public_ip_address = true

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2 # o contêiner Docker também precisa alcançar o papel da instância
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 8
    encrypted   = true
  }

  user_data = templatefile("${path.module}/iniciar.sh.tftpl", {
    regiao   = var.regiao
    registro = split("/", aws_ecr_repository.painel.repository_url)[0]
    imagem   = "${aws_ecr_repository.painel.repository_url}:latest"
    segredo  = aws_secretsmanager_secret.github.name
    grupo    = aws_cloudwatch_log_group.painel.name
  })

  # A imagem do sistema muda a cada release do Amazon Linux: trocar a instância por isso, não. O script de subida
  # só roda na criação; para mudá-lo, recrie a instância (terraform apply -replace=aws_instance.painel).
  lifecycle {
    ignore_changes = [ami, user_data]
  }

  tags = {
    Name = "visor-maria"
  }
}

# IP fixo: sem ele, o endereço mudaria toda vez que a instância desliga à noite.
resource "aws_eip" "painel" {
  instance = aws_instance.painel.id
  domain   = "vpc"
}
