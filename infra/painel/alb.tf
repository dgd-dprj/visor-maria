# Balanceador INTERNO (sem endereço público): quem chega a ele é o VPC origin do CloudFront.
resource "aws_lb" "painel" {
  name               = "visor-maria"
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.balanceador.id]
  subnets            = data.aws_subnets.privadas.ids
  idle_timeout       = 120 # as consultas de uma tela com o cache frio podem demorar
}

resource "aws_lb_target_group" "painel" {
  name                 = "visor-maria"
  port                 = 8050
  protocol             = "HTTP"
  vpc_id               = data.aws_vpc.maria.id
  target_type          = "ip"
  deregistration_delay = 30

  health_check {
    path                = "/"
    matcher             = "200-399"
    interval            = 30
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.painel.arn
  port              = 80
  protocol          = "HTTP" # o HTTPS termina no CloudFront; entre os dois, a rede privada

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.painel.arn
  }
}
