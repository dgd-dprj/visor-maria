variable "regiao" {
  description = "Região dos segredos e dos serviços da Maria (produção e release rodam em São Paulo)."
  type        = string
  default     = "sa-east-1"
}

variable "projeto_da_maria" {
  description = "Prefixo dos recursos da Maria. Só serve para achar segredos e serviços por nome."
  type        = string
  default     = "maria-langgraph-pp"
}

variable "cluster_da_maria" {
  description = "Cluster ECS onde rodam os serviços da Maria (o painel não o altera, só força o redeploy)."
  type        = string
  default     = "maria-langgraph-pp-sp"
}

variable "servicos_por_ambiente" {
  description = "Serviço ECS da Maria de cada ambiente."
  type        = map(string)
  default = {
    prod    = "api-prod-sp"
    release = "api-release-sp"
  }
}

variable "cluster_do_visor" {
  description = "ARN do cluster ECS do Visor (etapa 1 do acesso), onde a tarefa agendada roda."
  type        = string
}

variable "imagem" {
  description = "Imagem do Visor no ECR, com a tag. É a mesma do painel: o comando muda."
  type        = string
}

variable "subredes" {
  description = "Subredes privadas da tarefa. Ela precisa sair para o Verde e para a AWS."
  type        = list(string)
}

variable "grupo_de_seguranca" {
  description = "Grupo de segurança sem entrada, só com saída."
  type        = string
}

variable "agendamento_ligado" {
  description = <<-EOT
    Liga o agendamento diário. Fica desligado por padrão: o workflow verificar-token-verde.yml da
    Maria (#187) também renova, e duas renovações ao mesmo tempo invalidam o token uma da outra.
    Só ligue depois de desativar o workflow, ou como rede de segurança sabendo que o do workflow
    age primeiro (7 dias contra 1).
  EOT
  type        = bool
  default     = false
}

variable "horario_utc" {
  description = "Expressão cron do agendamento (EventBridge Scheduler). Padrão: 13:00 UTC, 10:00 em Brasília, depois da conferência da Maria."
  type        = string
  default     = "cron(0 13 * * ? *)"
}
