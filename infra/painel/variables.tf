variable "regiao" {
  description = "Região onde o painel roda: a da stack ativa da Maria (produção e release em São Paulo). O painel lê as duas regiões (a produção antiga ainda está em us-east-1) pelas permissões do papel."
  type        = string
  default     = "sa-east-1"
}

variable "vpc_da_maria" {
  description = "Nome (tag Name) da VPC da Maria onde as subredes privadas são achadas. Só é consultada: nada é alterado nela (docs/decisoes.md, 2026-10-26, regras 2 e 3)."
  type        = string
  default     = "maria-langgraph-pp-release-sp"
}

variable "subredes_privadas" {
  description = "Sufixos (tag Name = <vpc>-<sufixo>) das subredes privadas da tarefa. Precisam sair para a AWS e o GitHub pelo NAT que já existe."
  type        = list(string)
  default     = ["private-0", "private-1"]
}

variable "ler_custo" {
  description = "Libera ce:GetCostAndUsage (Cost Explorer) ao papel da tarefa, para a tela Relatório da Aplicação mostrar a fatura. Decisão do Ícaro (README, item 3): lê o custo da conta toda, com os outros projetos. Desligado por padrão."
  type        = bool
  default     = false
}

variable "sub_do_repositorio" {
  description = "Prefixo da claim `sub` do OIDC deste repositório (`gh api repos/dgd-dprj/visor-maria/actions/oidc/customization/sub`, campo sub_claim_prefix): a claim é a imutável, com os IDs."
  type        = string
  default     = "repo:dgd-dprj@337067883/visor-maria@1438801657"
}

variable "orcamento_mensal_usd" {
  description = "Limite do alarme de orçamento do painel, por mês."
  type        = number
  default     = 20
}

variable "emails_do_orcamento" {
  description = "Quem recebe o aviso do orçamento. Fica num arquivo local (*.auto.tfvars, fora do git), porque o repositório é público."
  type        = list(string)

  validation {
    condition     = length(var.emails_do_orcamento) > 0
    error_message = "Informe pelo menos um e-mail em emails_do_orcamento."
  }
}

variable "instancias" {
  description = "Quantas tarefas do painel rodam. Começa em 0: a imagem `latest` só existe no ECR depois do primeiro envio (README desta pasta), e sem ela a tarefa ficaria tentando subir. Depois do envio, aplique com 1."
  type        = number
  default     = 0
}

variable "horario_comercial" {
  description = "Desliga o painel à noite e liga de manhã (escala.tf). Com false, a tarefa fica ligada o tempo todo."
  type        = bool
  default     = true
}

variable "hora_de_desligar" {
  description = "Quando desligar, em cron do EventBridge (minuto hora dia mês dia-da-semana ano), no fuso de Brasília. Padrão: todo dia às 21:00."
  type        = string
  default     = "0 21 * * ? *"
}

variable "hora_de_ligar" {
  description = "Quando ligar, no mesmo formato e fuso. Padrão: todo dia às 08:00."
  type        = string
  default     = "0 8 * * ? *"
}

variable "ips_permitidos" {
  description = <<-EOT
    Quem pode abrir o painel pelo CloudFront, em CIDR (por exemplo "203.0.113.4/32"). Sem login (a autenticação fica
    para depois), **uma lista vazia deixa o painel aberto a qualquer pessoa na internet**: o painel mostra a validade da
    credencial do Verde, gasto, infraestrutura e problemas da Maria (só agregados, nenhuma conversa). Com IPs, um WAF
    bloqueia o resto (cerca de US$ 6 por mês). Sem valor padrão, para a escolha ser feita de propósito no apply.
  EOT
  type        = list(string)
}

variable "paises_permitidos" {
  description = "Países de onde o painel abre (código ISO de duas letras). Uma defesa a mais enquanto não há login; quem estiver fora (viagem, VPN) é bloqueado. Lista vazia libera o mundo."
  type        = list(string)
  default     = ["BR"]
}
