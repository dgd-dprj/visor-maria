# O painel na AWS: uma EC2 pequena atrás do CloudFront

O Visor roda numa **EC2 pequena** (`t3.micro`, subrede privada, sem endereço público) com a imagem Docker do painel, e abre
na internet por um **CloudFront** (HTTPS, endereço `*.cloudfront.net`) ligado direto à instância por um VPC origin, **sem
balanceador e sem ECS**. Para menos de dez pessoas isso custa uma fração de Fargate mais balanceador. Estado próprio
(`visor-maria/painel/terraform.tfstate`); a VPC e as subredes da Maria são só consultadas por nome, e nada é acrescentado
dentro de recurso dela (docs/decisoes.md, 2026-10-26).

| Recurso | Para quê (item do README principal) |
|---|---|
| `aws_instance.painel` | EC2 `t3.micro`, disco de 8 GB, IMDSv2; um serviço do systemd puxa a imagem e roda o contêiner (8) |
| `aws_cloudfront_distribution` / `aws_cloudfront_vpc_origin` | o endereço público HTTPS; sem cache, métodos completos (o Dash usa POST) |
| `aws_security_group.painel` | só o VPC origin do CloudFront entra, na porta 8050; saída HTTPS (8) |
| `aws_ecr_repository.painel` | repositório `visor-maria`, as 10 imagens mais novas (8) |
| `aws_secretsmanager_secret.github` | `visor-maria/github-token`, sem valor no estado (8) |
| `visor-maria-painel` | papel da instância, **só leitura**: Logs Insights, métricas, alarmes, ECR, o token do GitHub e o Session Manager (6) |
| `visor-maria-deploy` | papel do GitHub por OIDC (só a `main`): push no ECR do painel e `ssm:SendCommand` na instância (7) |
| `aws_scheduler_schedule` (2) | desliga às 21:00 e liga às 08:00, horário de Brasília |
| `aws_wafv2_web_acl` (opcional) | só os IPs de `ips_permitidos` |
| `aws_budgets_budget.painel` | aviso a 80% do gasto e a 100% da previsão de US$ 20 por mês (9) |

O papel da instância já inclui a leitura de `/ecs/visor-maria/renovador`, de onde a tela Credencial lê as renovações (#14).
`ce:GetCostAndUsage` só entra com `ler_custo = true`: é decisão do Ícaro (custo da conta toda, README principal, item 3).

## Sem login, o painel é público

Cognito e login ficam para depois (decisão do Ícaro, 24/11). Até lá, qualquer pessoa com o endereço abre o painel. Ele mostra
validade da credencial do Verde, gasto, infraestrutura e problemas da Maria, só agregados e nenhuma conversa. Cada abertura de
tela faz consultas pagas ao CloudWatch, então um painel aberto aceita visitantes que gastam dinheiro. Defesas, definidas no `apply`:

- `ips_permitidos` (**sem valor padrão**, para a escolha ser feita de propósito): lista de CIDRs que podem abrir o painel,
  com um WAF que bloqueia o resto (cerca de US$ 6 por mês). `[]` deixa aberto a qualquer pessoa.
- `paises_permitidos` (padrão `["BR"]`): quem estiver fora do país é bloqueado. `[]` libera o mundo.
- O alarme de orçamento avisa se o gasto subir.

## Custo (estimativa, sem conferir os preços de São Paulo)

Com a instância ligada 13 h por dia: EC2 `t3.micro` cerca de US$ 8, disco de 8 GB cerca de US$ 1, consultas ao CloudWatch
cerca de US$ 1 a 3, token no Secrets Manager US$ 0,40, CloudFront centavos. **Total na casa de US$ 10 a 14 por mês**, mais
cerca de US$ 6 se usar o WAF. Parada, a instância só cobra o disco.

## Como aplicar

**Quem aplica é o Ícaro.** Os e-mails e os IPs ficam num arquivo local, fora do git (o repositório é público):

```sh
cd infra/painel
cat > painel.auto.tfvars <<'EOF2'
emails_do_orcamento = ["equipe@exemplo.org"]
ips_permitidos      = ["203.0.113.4/32"]   # [] = aberto a qualquer pessoa
# ler_custo         = true                 # depois da decisão do item 3
EOF2
terraform init
terraform plan    # conferir: só recursos visor-maria*; na Maria, nada é alterado
terraform apply
```

O VPC origin leva uns 10 a 15 minutos no primeiro `apply`. O grupo de segurança que ele cria é achado por nome
(`CloudFront-VPCOrigin-Service-SG`): se o `apply` falhar nessa busca, rode de novo.

Depois do `apply`:

1. Guardar o token do GitHub (conta de serviço, só `Actions: read` e `Metadata: read` do `maria-langgraph-pp`):
   `aws secretsmanager put-secret-value --secret-id visor-maria/github-token --secret-string <token> --region sa-east-1`
2. Enviar a primeira imagem ao ECR (`terraform output repositorio_ecr`): `docker build`, `docker tag` e `docker push` com `:latest`.
   A instância tenta puxar a imagem a cada minuto e sobe sozinha quando ela existir.
3. Guardar `terraform output papel_de_deploy` na variável `AWS_ROLE_ARN_DEPLOY` do repositório, para o workflow de deploy.
4. Ativar a etiqueta de custo `projeto` no Billing, senão o orçamento não enxerga o gasto do painel.
5. Abrir `terraform output endereco_do_painel`.

Para atualizar o painel: enviar a imagem nova e reiniciar o serviço, que puxa a imagem mais nova:
`aws ssm send-command --document-name AWS-RunShellScript --parameters 'commands=["systemctl restart visor-maria"]' --instance-ids <id>`.
Para mudar o script de subida, recrie a instância: `terraform apply -replace=aws_instance.painel`.

## Horário

Desliga todo dia às 21:00 e liga às 08:00, no fuso de Brasília (`hora_de_desligar`, `hora_de_ligar`;
`horario_comercial = false` para ficar sempre ligado). Fora do horário, o CloudFront mostra a página de erro dele. Ao ligar, o
serviço sobe sozinho, e a tela abre com o cache frio.

## Acesso por túnel (para quem tem conta AWS)

```sh
aws ssm start-session --target <id-da-instancia> --document-name AWS-StartPortForwardingSession \
  --parameters portNumber=8050,localPortNumber=8050
```

Depois, `http://localhost:8050`. O id sai de `terraform output instancia`. Cada sessão fica no CloudTrail com o nome da pessoa.

## Não está aqui

- O **papel para aplicar o Terraform do painel** (item 5), restrito a `visor-maria*`, é da conta e fica com o Ícaro.
- O **workflow de deploy** (build, push e `ssm send-command` com `visor-maria-deploy`) fica para um PR próprio.
- A leitura do **banco da Maria** continua bloqueada até a #309.
