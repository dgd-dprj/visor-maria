resource "aws_ecr_repository" "painel" {
  name                 = "visor-maria"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "painel" {
  repository = aws_ecr_repository.painel.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Guarda só as 10 imagens mais novas"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}
