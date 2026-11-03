terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Estado próprio do Visor (docs/decisoes.md, 2026-10-26): a chave é só do Visor,
  # nunca a da Maria (maria-langgraph-pp/terraform.tfstate), e a trava é o arquivo
  # do próprio S3, sem a tabela de trava da Maria.
  backend "s3" {
    bucket       = "maria-tfstate-185327115563"
    key          = "visor-maria/alertas/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.regiao

  default_tags {
    tags = {
      projeto     = "visor-maria"
      gerenciado  = "terraform"
      repositorio = "dgd-dprj/visor-maria"
    }
  }
}
