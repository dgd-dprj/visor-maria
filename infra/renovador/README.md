# Renovação do token do Verde (visor-maria#14)

O papel e o agendamento diário do `python -m painel.renovador`. A decisão e as proteções estão em
`docs/decisoes.md` (2026-11-23).

- **Papel da tarefa** (`visor-maria-renovador`): `GetSecretValue` e `PutSecretValue` só em
  `maria-langgraph-pp-{prod,release}/app`; criar, descrever e apagar só as travas
  `visor-maria/trava-renovacao-*`; `ecs:UpdateService` só em `api-prod-sp` e `api-release-sp`.
- **Agendamento**: uma tarefa Fargate por dia, **desligado por padrão** (`agendamento_ligado = false`),
  sem nenhuma repetição automática: o refresh invalida o token antigo, e repetir às cegas pode
  perder o novo.

**Antes de ligar:** o workflow `verificar-token-verde.yml` da Maria (#187) também renova (com 7
dias ou menos). Ele age bem antes do 1 dia do Visor, então os dois não se pisam no dia a dia, mas
decidam se o workflow sai de vez. Dependências: cluster, imagem no ECR e subredes da etapa 1
(README principal, "Permissões", item 8), que ainda não existem.

## Como aplicar

**Quem aplica é o Ícaro**, com credencial que crie papéis IAM, tarefa ECS e agendamento:

```sh
cd infra/renovador
cat > renovador.auto.tfvars <<'EOF2'
cluster_do_visor   = "arn:aws:ecs:sa-east-1:<conta>:cluster/visor-maria"
imagem             = "<conta>.dkr.ecr.sa-east-1.amazonaws.com/visor-maria:<tag>"
subredes           = ["subnet-..."]
grupo_de_seguranca = "sg-..."
EOF2
terraform init
terraform plan    # conferir: só recursos visor-maria-*; nada na Maria
terraform apply
```
