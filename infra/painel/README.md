# O painel na AWS: uma EC2 pequena com Docker, atrás do CloudFront

O Visor roda numa **EC2 pequena** (`t3.micro`, Amazon Linux 2023) na **VPC padrão** da conta, com um IP fixo, rodando a
imagem Docker do painel que está no **ECR**. Na frente dela, um **CloudFront** dá o endereço `https://xxxx.cloudfront.net` e o
certificado HTTPS (da AWS, sem domínio nosso). A porta 80 da instância só aceita os IPs do CloudFront. Sem balanceador, sem
ECS, sem VPC própria e sem Caddy. Estado próprio (`visor-maria/painel/terraform.tfstate`); nada é acrescentado dentro de
recurso da Maria (docs/decisoes.md, 2026-10-26).

| Recurso | Para quê (item do README principal) |
|---|---|
| `aws_instance.painel` | EC2 `t3.micro`, disco de 8 GB, IMDSv2; um serviço do systemd puxa a imagem e roda o contêiner na porta 80 (8) |
| `aws_cloudfront_distribution.painel` | o endereço público HTTPS (`*.cloudfront.net`); sem cache, métodos completos (o Dash usa POST) |
| `aws_eip.painel` | IP fixo, para o CloudFront achar a instância depois de ela desligar à noite |
| `aws_security_group.painel` | porta 80 só para os IPs do CloudFront (lista gerenciada da AWS); saída livre (8) |
| `aws_ecr_repository.painel` | repositório `visor-maria`, as 10 imagens mais novas (8) |
| `aws_secretsmanager_secret.github` | `visor-maria/github-token`, sem valor no estado (8) |
| `visor-maria-painel` | papel da instância, **só leitura**: Logs Insights, métricas, alarmes, ECR, o token do GitHub e o Session Manager (6) |
| `visor-maria-deploy` | papel do GitHub por OIDC (só a `main`): push no ECR do painel e `ssm:SendCommand` na instância (7) |
| `aws_scheduler_schedule` (2) | desliga às 21:00 e liga às 08:00, horário de Brasília |
| `aws_budgets_budget.painel` | aviso a 80% do gasto e a 100% da previsão de US$ 20 por mês (9) |

O papel da instância já inclui a leitura de `/ecs/visor-maria/renovador`, de onde a tela Credencial lê as renovações (#14).
`ce:GetCostAndUsage` só entra com `ler_custo = true`: é decisão do Ícaro (custo da conta toda, README principal, item 3).

## Login com a conta Google

O painel só abre depois do login com uma conta Google, e só para os e-mails da lista (decisão da Nicole, 24/11). O
caminho: o painel manda ao Cognito (`login.tf`), que manda direto ao Google; o Google volta ao Cognito, e o Cognito ao
painel, que pergunta o e-mail e confere a lista. Sem a configuração ou a lista, o painel **fecha** (503), nunca abre.

**Quem pode abrir: a lista de e-mails.** Fica no Parameter Store, e não no repositório (que é público):

1. Console da AWS, região **São Paulo (sa-east-1)**, **Systems Manager > Parameter Store**.
2. Abrir `/visor-maria/emails-com-acesso` e clicar em **Editar**.
3. Os e-mails, separados por vírgula, sem espaço dentro deles: `pessoa.um@gmail.com,pessoa.dois@gmail.com`.
4. Salvar. Vale em até um minuto, para entrar e para sair: tirar um e-mail fecha o painel para aquela pessoa sem esperar o
   login dela vencer. O `terraform apply` não desfaz a edição.

Para editar, o usuário precisa da política `visor-maria-editar-emails` (`terraform output politica_para_editar_a_lista`),
que o Ícaro anexa: ela só lê e edita esse parâmetro.

**O Cognito é o `coilab-users` (us-east-1, domínio `coilab-auth`), que já tem o Google.** Ele é do projeto CoiLab:
o Visor tem um **cliente próprio** nele e não mexe no cliente `coilab-web`. Os usuários do CoiLab estão no mesmo grupo,
mas só entra no Visor quem está na lista de e-mails. O que falta, na ordem:

1. **Cognito, no `coilab-users`:**
   - **Clientes da aplicação > Criar:** tipo **Aplicação de página única (SPA)** (sem segredo), nome `visor-maria`;
     URL de retorno e URL de saída de `terraform output retorno_e_saida_no_cognito` (e, para testar na máquina,
     `http://localhost:8060/auth/callback` e `http://localhost:8060/saiu`); provedor **só o Google**; escopos
     `openid` e `email`;
   - **Provedores sociais e externos > Google:** acrescentar ao mapeamento `email_verified` ← `email_verified`. Sem ele,
     o Visor recusa todo login (só aceita e-mail confirmado). Não muda nada para o CoiLab, mas o grupo é dele: combinar
     com o Ícaro.
   - O grupo tem um gatilho **PreAuthentication** (Lambda do CoiLab), que roda para todo cliente do grupo. Se ele
     barrar quem não é do CoiLab, o login do Visor falha: conferir com o Ícaro.
2. **Terraform** (quem tem o papel do painel): o cliente `visor-maria` já está em `cliente_do_login`
   (`5f9m55vv6uo9g8m1gsp9raemmh`). Num arquivo local `login.auto.tfvars` (fora do git), a primeira versão da lista,
   `emails_com_acesso = ["pessoa.um@gmail.com"]`; depois `terraform apply`. Ele cria `/visor-maria/login`,
   `/visor-maria/emails-com-acesso`, a política `visor-maria-editar-emails` e a leitura dos dois pelo painel.
3. **Publicar a imagem nova**: ela já vem com `PAINEL_LOGIN=cognito`. Imagem nova antes do passo 2 deixa o painel
   fechado (503) até o apply.

O Google Cloud Console não muda: o domínio `coilab-auth` já está autorizado lá. Se o app do Google estiver "em teste",
só as contas cadastradas como usuárias de teste entram.

O login dura 8 horas, e todo mundo entra de novo a cada dia (a chave da sessão é recriada quando a instância liga). Rodando
na máquina (`uv run`), sem `PAINEL_LOGIN`, o painel continua abrindo sem login.

Cada abertura de tela faz consultas pagas ao CloudWatch; com o login, só quem está na lista dispara essas consultas, e o
alarme de orçamento continua como aviso.

**Por que `cloudfront.net` e não `sslip.io`:** o `sslip.io` (DNS dinâmico) é bloqueado por firewalls corporativos, como o
FortiGuard da Defensoria, e o Let's Encrypt recusa nomes `ec2-*.amazonaws.com`. O endereço do CloudFront é da AWS e tem
certificado próprio, sem precisar de domínio.

**Limite conhecido:** o trecho CloudFront → EC2 é HTTP, e a lista de IPs do CloudFront é de todos os clientes dele: quem criar
uma distribuição própria apontando para o IP da instância também chega à porta 80. Para fechar isso, um cabeçalho secreto
conferido na instância, ou um WAF. Quem chegar por esse caminho cai no mesmo login, que é conferido pelo próprio painel.
Com um domínio da Defensoria, o certificado fica no lugar certo.

## Custo (estimativa, sem conferir os preços de São Paulo)

Com a instância ligada 13 h por dia: EC2 `t3.micro` cerca de US$ 8, disco cerca de US$ 1, IPv4 público fixo cerca de
US$ 3,6 (cobrado também com a instância parada), consultas ao CloudWatch cerca de US$ 1 a 3, token no Secrets Manager
US$ 0,40, CloudFront centavos. **Total na casa de US$ 14 a 17 por mês.** Parada, a instância só cobra disco e IP.

## Como aplicar

**Quem aplica é o Ícaro.** Os e-mails ficam num arquivo local, fora do git (o repositório é público):

```sh
cd infra/painel
cat > painel.auto.tfvars <<'EOF2'
emails_do_orcamento = ["equipe@exemplo.org"]
# ler_custo         = true                 # depois da decisão do item 3
EOF2
terraform init
terraform plan    # conferir: só recursos visor-maria*; na Maria, nada é alterado
terraform apply
```

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
`horario_comercial = false` para ficar sempre ligado). Ao ligar, o serviço sobe sozinho, e a tela abre com o cache frio.

## Acesso à máquina (para quem tem conta AWS)

Sem SSH nem porta de administração: o acesso é pelo Session Manager, e cada sessão fica no CloudTrail com o nome da pessoa.

```sh
aws ssm start-session --target <id-da-instancia>     # terminal; o id sai de `terraform output instancia`
sudo journalctl -u visor-maria                      # log do serviço do painel
```

## Não está aqui

- O **papel para aplicar o Terraform do painel** (item 5), restrito a `visor-maria*`, é da conta e fica com o Ícaro.
- O **workflow de deploy** (build, push e `ssm send-command` com `visor-maria-deploy`) fica para um PR próprio.
- A leitura do **banco da Maria** continua bloqueada até a #309.
