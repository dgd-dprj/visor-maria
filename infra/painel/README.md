# Etapa 1: o painel na AWS, acesso por túnel (README principal, "Permissões")

O que o Visor precisa para rodar na AWS, sem endereço público: ECR, cluster e serviço ECS (Fargate, subrede privada,
sem Container Insights), grupo de segurança sem entrada, grupo de logs, segredo do token do GitHub, os papéis e o
alarme de orçamento. Estado próprio (`visor-maria/painel/terraform.tfstate`); a VPC e as subredes da Maria são só
consultadas por nome, e nada é acrescentado dentro de recurso dela (docs/decisoes.md, 2026-10-26).

| Recurso | Para quê (item do README) |
|---|---|
| `aws_ecr_repository.painel` | repositório `visor-maria`, as 10 imagens mais novas (8) |
| `aws_ecs_cluster` / `aws_ecs_task_definition` / `aws_ecs_service` | cluster próprio, 0,25 vCPU e 0,5 GB, ECS Exec ligado (8) |
| `aws_security_group.painel` | nenhuma entrada, só saída HTTPS (8) |
| `aws_secretsmanager_secret.github` | `visor-maria/github-token`, sem valor no estado (8) |
| `visor-maria-painel` | papel da tarefa, **só leitura**: Logs Insights, métricas, alarmes e o túnel (6) |
| `visor-maria-painel-execucao` | puxa a imagem, escreve o log e lê o token do GitHub (8) |
| `visor-maria-deploy` | papel do GitHub por OIDC (só a `main`): push no ECR do painel e `ecs:UpdateService` no serviço dele (7) |
| `aws_budgets_budget.painel` | aviso a 80% do gasto e a 100% da previsão de US$ 20 por mês (9) |

O papel da tarefa já inclui a leitura de `/ecs/visor-maria/renovador`, de onde a tela Credencial lê as renovações (#14).
`ce:GetCostAndUsage` só entra com `ler_custo = true`: é decisão do Ícaro (custo da conta toda, README, item 3).

## Como aplicar

**Quem aplica é o Ícaro.** Os e-mails ficam num arquivo local, fora do git (o repositório é público):

```sh
cd infra/painel
cat > painel.auto.tfvars <<'EOF2'
emails_do_orcamento = ["equipe@exemplo.org"]
# ler_custo         = true   # depois da decisão do item 3
EOF2
terraform init
terraform plan    # conferir: só recursos visor-maria*; na Maria, nada é alterado
terraform apply
```

O serviço nasce com `instancias = 0`. Para ligar:

1. Guardar o token do GitHub (conta de serviço, só `Actions: read` e `Metadata: read` do `maria-langgraph-pp`):
   `aws secretsmanager put-secret-value --secret-id visor-maria/github-token --secret-string <token> --region sa-east-1`
2. Enviar a primeira imagem ao ECR (`terraform output repositorio_ecr`): `docker build`, `docker tag` e `docker push` com `:latest`.
3. `terraform apply -var instancias=1` (ou `instancias = 1` no `.auto.tfvars`).
4. Guardar `terraform output papel_de_deploy` na variável `AWS_ROLE_ARN_DEPLOY` do repositório, para o workflow de deploy.
5. Ativar a etiqueta de custo `projeto` no Billing, senão o orçamento não enxerga o gasto do painel.

## Acesso

```sh
aws ssm start-session --target ecs:visor-maria_<id-da-tarefa>_<id-do-container> \
  --document-name AWS-StartPortForwardingSession --parameters portNumber=8050,localPortNumber=8050
```

Depois, `http://localhost:8050`. O id da tarefa sai de `aws ecs list-tasks --cluster visor-maria --region sa-east-1`.

## Não está aqui

- O **papel para aplicar o Terraform do painel** (item 5), restrito a `visor-maria*`, é da conta e fica com o Ícaro.
- O **workflow de deploy** (build, push e `update-service` com `visor-maria-deploy`) fica para um PR próprio.
- A leitura do **banco da Maria** continua bloqueada até a #309.
