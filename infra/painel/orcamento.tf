# README, item 9: aviso de gasto do painel, por causa do custo das consultas.
# O filtro usa a etiqueta de custo `projeto`, que precisa estar ativada no Billing (README, item 3).
resource "aws_budgets_budget" "painel" {
  name         = "visor-maria"
  budget_type  = "COST"
  limit_amount = tostring(var.orcamento_mensal_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:projeto$visor-maria"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.emails_do_orcamento
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.emails_do_orcamento
  }
}
