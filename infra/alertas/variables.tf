variable "regiao" {
  description = "Região da conta da Maria."
  type        = string
  default     = "us-east-1"
}

variable "projeto_da_maria" {
  description = "Prefixo dos recursos da Maria (var.project no Terraform dela). Só é usado para achar os recursos por nome."
  type        = string
  default     = "maria-langgraph-pp"
}

variable "destinatarios" {
  description = "E-mails que recebem os alertas. Cada um precisa confirmar a inscrição no e-mail que a AWS manda."
  type        = list(string)

  validation {
    condition     = length(var.destinatarios) > 0
    error_message = "Informe pelo menos um e-mail em destinatarios."
  }
}

variable "alerta_do_verde" {
  description = "Liga o alerta da credencial do Verde recusada. Ele cria um filtro de métrica dentro do grupo de logs da Maria: é a única peça que encosta num recurso dela (exceção aceita pela Nicole em 2026-11-03)."
  type        = bool
  default     = true
}

variable "ambientes_do_verde" {
  description = "Onde o alerta do Verde roda. Só produção por padrão: o release não tem uso, e cada ambiente soma uma métrica e um alarme na conta."
  type        = list(string)
  default     = ["producao"]

  validation {
    condition     = alltrue([for a in var.ambientes_do_verde : contains(["producao", "release"], a)])
    error_message = "ambientes_do_verde aceita só \"producao\" e \"release\"."
  }
}
