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

variable "sub_do_repositorio" {
  description = "Prefixo da claim `sub` do OIDC deste repositório. Vem de `gh api repos/dgd-dprj/visor-maria/actions/oidc/customization/sub` (campo sub_claim_prefix): o repositório usa a claim imutável, com os IDs da organização e do repositório, e não o nome."
  type        = string
  default     = "repo:dgd-dprj@337067883/visor-maria@1438801657"
}
