# Renovação do token do Verde (visor-maria#14)

O papel IAM e o grupo de logs do `python -m painel.renovador`, que roda no workflow
`.github/workflows/renovar-token-verde.yml` (Actions do visor-maria, com o provedor OIDC do GitHub que já existe na conta).
A decisão e as proteções estão em `docs/decisoes.md` (2026-11-23).

- **Papel** (`visor-maria-renovador`): só a branch `main` deste repositório o assume (a claim `sub` é a imutável, com os IDs; ver `sub_do_repositorio`). `Get/PutSecretValue` só em
  `maria-langgraph-pp-{prod,release}/app`; criar, descrever e apagar só as travas `visor-maria/trava-renovacao-*`;
  `ecs:UpdateService` só em `api-prod-sp` e `api-release-sp`; escrever só no grupo de logs abaixo.
- **Grupo de logs** `/ecs/visor-maria/renovador`: a linha diária (validade, sem token) que a tela Credencial lê.

## Ligar

O agendamento fica **desligado**: o workflow só roda por agenda quando a variável do repositório
`RENOVADOR_LIGADO` vale `true`. O disparo manual (`workflow_dispatch`) existe sempre e começa em modo simulação.

1. `terraform apply` (abaixo) e copiar `papel_da_renovacao` para a variável `AWS_ROLE_ARN_RENOVADOR` do repositório.
2. Testar com o disparo manual em simulação (lê o segredo, decide e registra; não chama o Verde nem grava).
3. Decidir o que fazer com o workflow da Maria (#187): ele também renova (com 7 dias ou menos). Os dois não se
   pisam no dia a dia, porque o dele age bem antes do 1 dia do Visor, mas duas renovações ao mesmo tempo
   invalidariam o token uma da outra. Só então criar `RENOVADOR_LIGADO = true`.

## Como aplicar

**Quem aplica é o Ícaro**, com credencial que crie papéis IAM e grupo de logs:

```sh
cd infra/renovador
terraform init
terraform plan    # conferir: só recursos visor-maria-*; nada na Maria
terraform apply
```
