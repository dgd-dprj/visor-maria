variable "regiao" {
  description = "Região onde o painel roda: a da stack ativa da Maria (produção e release em São Paulo). O painel lê as duas regiões (a produção antiga ainda está em us-east-1) pelas permissões do papel."
  type        = string
  default     = "sa-east-1"
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







variable "dominio_do_login" {
  description = "Domínio do grupo de usuários do Cognito, sem https://. É o coilab-users (us-east-1), que já tem o Google: o Visor usa um cliente próprio nele, sem tocar no do CoiLab."
  type        = string
  default     = "coilab-auth.auth.us-east-1.amazoncognito.com"
}

variable "cliente_do_login" {
  description = "ID do cliente \"visor-maria\" no coilab-users (criado pelo console em 24/11; público, sem segredo: o painel usa PKCE). Não é segredo: aparece no endereço de login."
  type        = string
  default     = "5f9m55vv6uo9g8m1gsp9raemmh"

  validation {
    condition     = can(regex("^[a-z0-9]{20,32}$", var.cliente_do_login))
    error_message = "Use o ID do cliente do aplicativo no Cognito (letras minúsculas e números)."
  }
}

variable "emails_com_acesso" {
  description = "Primeira versão da lista de quem pode abrir o painel. Depois do primeiro apply, a lista é editada no Parameter Store (/visor-maria/emails-com-acesso), e o apply não a desfaz. Fica no *.auto.tfvars local: o repositório é público."
  type        = list(string)

  validation {
    condition     = length(var.emails_com_acesso) > 0 && alltrue([for e in var.emails_com_acesso : can(regex("^[^@,\\s]+@[^@,\\s]+\\.[^@,\\s]+$", e))])
    error_message = "Informe pelo menos um e-mail, sem vírgula nem espaço dentro dele."
  }
}

variable "tipo_da_instancia" {
  description = "Tipo da EC2 do painel. t3.micro (2 vCPU, 1 GB) atende a menos de dez pessoas; o painel guarda o cache em disco, sem estado. A imagem do CI é x86; um tipo ARM (t4g) exigiria construir a imagem para ARM."
  type        = string
  default     = "t3.micro"
}

variable "horario_comercial" {
  description = "Desliga a instância à noite e liga de manhã (escala.tf). Com false, ela fica ligada o tempo todo."
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

