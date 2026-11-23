# Os recursos da Maria são lidos por nome (docs/decisoes.md, 2026-10-26, regra 2),
# nunca pelo estado dela.

data "aws_lb" "maria" {
  name = "${var.projeto_da_maria}-alb"
}

data "aws_lb_target_group" "producao" {
  name = "${var.projeto_da_maria}-api"
}

data "aws_lb_target_group" "release" {
  name = "${var.projeto_da_maria}-api-release"
}

locals {
  ambientes = {
    producao = {
      nome         = "produção"
      grupo        = data.aws_lb_target_group.producao.arn_suffix
      servico      = "api"
      grupo_de_log = "/ecs/${var.projeto_da_maria}/api"
    }
    release = {
      nome         = "release"
      grupo        = data.aws_lb_target_group.release.arn_suffix
      servico      = "api-release"
      grupo_de_log = "/ecs/${var.projeto_da_maria}-release/api"
    }
  }
}
