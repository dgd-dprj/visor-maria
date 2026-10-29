# Visor Maria

Painel de acompanhamento da Maria, a assistente de atendimento da Defensoria
Pública do Estado do Rio de Janeiro. Feito em Dash e Plotly (Python), roda em
Docker. A Maria em si mora em outro repositório,
[dgd-dprj/maria-langgraph-pp](https://github.com/dgd-dprj/maria-langgraph-pp);
o painel só lê os logs, as métricas e as rotinas dela, sem nunca mexer nela.

Cada tela responde a uma pergunta, e todo número aparece com a fonte e a hora
da leitura ao lado:

| Tela | Pergunta | Endereço |
|---|---|---|
| Agora | Está funcionando? | `/` |
| Credencial do Verde | Está valendo, e por quanto tempo? | `/credencial` |
| Atendimento | Como as conversas terminam? | `/atendimento` |
| Fluxos | Por onde as conversas passam, e onde travam? | `/fluxos` |
| Sistema | Por que está assim? | `/sistema` |
| Relatório do dia | Como foi o dia? | `/dia` |
| Relatório da Aplicação | De onde vem o gasto, em que dia e em que mês? | `/aplicacao` |
| Observatório da IA | A IA está respondendo bem, e onde ela erra? | `/ia` |

> **Estado em 28/10/2026:** as oito telas leem **dados reais** (CloudWatch e
> GitHub), com as credenciais de quem roda o painel. Toda tela tem, à direita,
> a coluna "Mais sinais" (embaixo, em tela menor que 1600 px), menos a Agora,
> que usa a largura toda para os gráficos de hora em hora. Para ir ao ar
> numa tarefa própria, faltam as permissões de [Permissões](#permissões). Por que
> o painel tem repositório próprio está em [docs/decisoes.md](docs/decisoes.md).

### O que o painel precisa para ler os dados reais

- **AWS:** credencial com leitura de Logs Insights nos dois grupos de logs da
  Maria e de métricas do CloudWatch (lista em [Permissões](#permissões), item 6).
  O painel usa a cadeia padrão do boto3: o perfil padrão da máquina, as
  variáveis `AWS_*` ou o papel da tarefa. Na máquina da Nicole, o perfil padrão
  funciona; o perfil `maria`, com login pelo `aws login`, precisa do pacote
  `botocore[crt]` (já nas dependências) e de um login válido.
- **GitHub:** `GITHUB_TOKEN` com leitura do `dgd-dprj/maria-langgraph-pp` ou,
  sem ele, o login do `gh` da máquina. Serve para as rotinas, a validade da
  credencial do Verde (do log da conferência diária) e as mudanças na IA.
- **Nada mais:** o painel não lê o banco da Maria nem o segredo da credencial.

A primeira abertura de cada tela, com o cache vazio, leva de 10 a 40 segundos
(as consultas reais vão juntas, até 8 por vez). Depois, os dias e os meses
fechados ficam guardados, e só o período em curso é relido. Trocar de tela não
espera a releitura: a leitura vencida há menos de 30 minutos aparece na hora,
com a hora em que foi lida, e a nova vem por trás (ver `docs/decisoes.md`).

Todo gráfico filtra a tela, como no Power BI: um dia, uma hora (nos gráficos hora
a hora), um resultado do Verde (no segmento da barra ou na legenda) ou um motivo
de "Como terminaram". Clicar de novo no mesmo ponto, ou em "Tirar o filtro",
volta ao normal. Um link com `?dia=2026-10-22` abre a tela já filtrada no dia.

## Como rodar

### Com Docker

Precisa do Docker com o Compose.

```sh
docker compose up --build
```

Abra http://localhost:8050. O container roda o painel com o gunicorn, sem modo
de depuração.

> **Atenção:** a imagem Docker só foi testada à mão antes da mudança de visual de
> 26/10. O job `imagem` do CI passa a conferir que ela constrói e responde, mas
> só depois que este repositório estiver publicado no GitHub.

### Sem Docker (para desenvolver)

Precisa do [uv](https://docs.astral.sh/uv/) 0.13 ou mais novo. O uv baixa o
Python 3.12 sozinho, se faltar.

```sh
uv sync                        # instala as dependências
uv run python -m painel.app    # http://127.0.0.1:8050
```

Com recarregamento automático e a barra de depuração do Dash:

```sh
# bash
PAINEL_DEPURACAO=1 uv run python -m painel.app
```

```powershell
# PowerShell
$env:PAINEL_DEPURACAO = "1"; uv run python -m painel.app
```

### Variáveis de ambiente

| Variável | Valores | Para quê |
|---|---|---|
| `PAINEL_FONTE` | `real` (padrão), `simulado` | De onde vêm os dados. `simulado` inventa os números, para conferir o desenho sem credencial, e põe a faixa "Dados simulados" no topo de toda tela. Um valor desconhecido faz o painel falhar na subida, e não no meio de uma tela. |
| `GITHUB_TOKEN` | um token | Leitura do repositório da Maria no GitHub. Sem ele, o painel usa o login do `gh` da máquina. |
| `PAINEL_CENARIO` | `normal` (padrão), `vazio`, `falha` | O que o simulado devolve em todas as leituras. `vazio` e `falha` servem para conferir o texto próprio de cada estado. |
| `PAINEL_DEPURACAO` | `1` | Liga o modo de depuração do Dash (só fora do Docker). |
| `PAINEL_CACHE` | uma pasta | Onde o cache das leituras fica em disco, dividido pelos processos do servidor. Sem ela, uma pasta `visor-maria-cache` na área temporária do sistema. |

Exemplo, para ver todas as telas com a fonte fora do ar:

```sh
PAINEL_CENARIO=falha docker compose up --build
```

## Verificação

```sh
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
```

O CI (`.github/workflows/ci.yml`) roda três jobs:

| Job | Quando | O que confere |
|---|---|---|
| `verificar` | todo PR e push para `main` | lint, formatação, tipos e testes |
| `contrato` | todo PR, push e **todo dia às 07:00** | os nomes que o painel lê dos logs da Maria ainda existem no código dela, em `main` e em `develop` |
| `imagem` | todo PR e push para `main` | a imagem constrói, sobe e as oito telas respondem |

Os testes cobrem as regras do painel em todas as telas e nos três cenários
(normal, vazio e falha):

- nenhum texto que a pessoa lê tem hífen; nomes técnicos vão como código;
- nenhum texto diz "sem dados": o vazio tem texto próprio;
- todo indicador e todo quadro mostra a fonte e a hora da leitura;
- "buscas que não acharam a pessoa" só aparece junto da credencial do Verde;
- quando uma fonte falta, os quadros de regra dizem qual faltou;
- a camada de dados só devolve agregados, sem dado de conversa;
- nada no código lê o banco da Maria (bloqueado até a #309 dela);
- a marca do corte de versão (23/10, 12:31) só aparece em série de produção que cruza o corte;
- nenhum arquivo JavaScript ou TypeScript: o código de navegador fica em `painel/navegador.py`;
- as regras de renovação, linha do tempo, frase do dia e custo, com o caso real de 25/10.

## O contrato com os logs da Maria

O painel lê os logs da Maria pelo nome do evento (`verde_chamada`) e do campo
(`tipoErro`, `tokensGastos`). Como a Maria mora em outro repositório, uma
renomeação lá faria as consultas do painel devolverem zero, sem erro nenhum. Por
isso o acoplamento é tratado como contrato:

- `src/painel/dados/contrato.py` declara todo evento e campo que o painel lê.
  **Toda consulta nova a log entra ali primeiro**; um teste acusa evento citado
  numa fonte e ausente do contrato.
- `scripts/extrair_contrato_da_maria.py` tira um retrato do que a Maria registra,
  lendo o código dela (`src/maria`) e as linhas que a conferência diária da
  credencial imprime. O retrato fica em `tests/fixtures/maria/contrato_extraido.json`.
- `tests/fixtures/maria/logs/` tem a cópia dos logs de referência da Maria. Eles
  são da versão TypeScript e ainda não mostram alguns eventos; as lacunas estão
  declaradas em `FORA_DOS_LOGS_DE_REFERENCIA`, e o teste avisa quando elas fecham.
- `tests/test_contrato_da_maria.py` falha quando um nome some. O job `contrato`
  refaz o retrato todo dia, a partir de `main` e de `develop` da Maria, e roda o
  teste. As linhas da conferência diária só são cobradas de `develop`, que é a
  branch de onde a rotina agendada roda.

Para atualizar o retrato à mão, a partir de um clone da Maria:

```sh
uv run python scripts/extrair_contrato_da_maria.py ../maria-langgraph-pp --branch develop
```

## Estrutura

```
visor-maria/
├─ .github/workflows/ci.yml        verificar, contrato e imagem
├─ Dockerfile, compose.yaml        imagem e execução em container
├─ pyproject.toml, uv.lock         dependências (uv) e configuração de pytest, ruff e mypy
├─ docs/decisoes.md                decisões do painel, com data, motivo e custo
├─ scripts/
│  └─ extrair_contrato_da_maria.py retrato do que a Maria registra nos logs
├─ src/painel/
│  ├─ app.py                       moldura: menu, tema, relógio de 1 minuto, Dash Pages
│  ├─ navegador.py                 o código que roda no navegador (menu, tema, relógio)
│  ├─ pages/                       uma tela por arquivo (Dash Pages)
│  ├─ componentes/                 peças repetidas
│  │  ├─ blocos.py                 indicador, quadro, selo, barra, espaço reservado,
│  │  │                            "De onde vem cada número"
│  │  ├─ cabecalho.py, menu.py     cabeçalho com os três temas; barra lateral e hambúrguer
│  │  ├─ filtro_de_dia.py          o clique num dia de um gráfico filtra a tela
│  │  ├─ formato.py                números, datas e durações, sem hífen
│  │  ├─ graficos.py               cores dos gráficos por tema e a marca do corte de versão
│  │  └─ grafico_do_verde.py       o gráfico do Verde da tela Agora
│  ├─ dados/
│  │  ├─ modelo.py                 Leitura: valor, fonte, hora e estado de todo número
│  │  ├─ fontes.py                 o contrato da camada de dados e a fonte de cada consulta
│  │  ├─ contrato.py               os eventos e campos que o painel lê dos logs da Maria
│  │  ├─ real.py                   a fonte real: Logs Insights, métricas e GitHub, só agregado
│  │  ├─ simulado.py               fonte inventada, com a mesma forma da real
│  │  ├─ consultas.py              a janela e a validade de cada consulta (o cache lê daqui)
│  │  ├─ cache.py                  cache em disco, dividido pelos processos do servidor
│  │  └─ telas.py                  o que cada tela lê numa rodada, lido uma vez só e em paralelo
│  ├─ lateral.py                   a coluna da direita ("Mais sinais") de cada tela
│  ├─ funcoes_de_ia.py             as funções de IA da Maria, como o código as descreve
│  ├─ periodo.py, gasto.py         filtro de dia e contas da tela financeira
│  ├─ atencao.py                   regra do "Exige atenção" e dos incidentes abertos
│  ├─ renovacao.py                 quando a conferência diária renova a credencial
│  ├─ linha_do_tempo.py            a linha do tempo da credencial, a partir dos dados
│  ├─ frase_do_dia.py              "o dia em uma frase", a partir dos dados
│  ├─ precos.py                    preço por milhão de tokens, com a fonte de cada um
│  └─ assets/painel.css            temas e layout
└─ tests/
   └─ fixtures/maria/              retrato do código e logs de referência da Maria
```

### Como acrescentar uma tela

1. Crie `src/painel/pages/<nome>.py` com `dash.register_page(...)` e uma função `layout`.
2. Ponha as leituras da tela em `dados/telas.py` (`ler_<tela>()`), para cada fonte ser lida uma vez por rodada.
3. Se a tela lê um evento ou campo novo dos logs da Maria, declare em `dados/contrato.py`.
4. Monte a tela com os blocos de `componentes/blocos.py`. Todo número entra por um `indicador` ou um `quadro`, que já mostram a fonte e a hora.
5. Atualize pelo `Input("relogio", "n_intervals")`. Filtros ficam fora da área que se refaz, senão voltam ao padrão a cada minuto.
6. Ligue o filtro (`componentes/filtro_de_dia.py`): `registrar` o que ele filtra, `armazem` e `faixa` no topo, todo gráfico por `grafico` (com `por="dia"`, `"hora"` ou `"categoria"`), `entrada` em cada callback que refaz um quadro, `layout(dia=...)` para o link com `?dia=`, e `preparar` para os dias passados do gráfico. As consultas com janela recebem o `quando` do filtro (`dados/fontes.py`).
7. Acrescente o nome em `TELAS`, em `componentes/menu.py`. Os testes de regra passam a valer para a tela sozinhos, também filtrada num dia.

## Padrões que valem para todas as telas

- **A fonte e a hora ao lado de cada número**, e a lista "De onde vem cada número", com o nome técnico, no pé da tela.
- **Listas de alerta saem de regra sobre o dado**, nunca de texto fixo: "Exige atenção", "O que fica para amanhã", a linha do tempo e a frase do dia.
- **O quadro diz qual fonte não foi lida**, em vez de parecer tranquilo.
- **Ambiente é filtro**, nunca duas séries no mesmo gráfico; a tela Agora compara os dois de propósito, em tabela.
- **Todo gráfico filtra a tela** (dia, hora ou categoria), e o que não tem dia (saúde agora, validade da credencial) diz que continua sendo de agora.
- **Nunca listar conversa**: só agregados.
- **Nada lê o banco da Maria antes da #309.**

## Acesso

**Etapa 1, hoje: túnel da AWS, sem endereço público.** O painel roda em subrede
privada, sem balanceador e sem CloudFront. Quem vê abre um túnel pelo Session
Manager e acessa `http://localhost:8050`:

```sh
aws ssm start-session --target ecs:<cluster>_<id-da-tarefa>_<id-do-container> \
  --document-name AWS-StartPortForwardingSession --parameters portNumber=8050,localPortNumber=8050
```

Precisa de credencial AWS com `ssm:StartSession` só na tarefa do painel, da AWS
CLI com o plugin do Session Manager e do ECS Exec ligado no serviço. Cada sessão
fica no CloudTrail com o nome da pessoa.

**É etapa, não solução:** o túnel atende as duas pessoas com conta AWS, e o painel
foi desenhado para três públicos. A etapa 2 é CloudFront com *VPC origin* para um
balanceador interno do painel, mais login no próprio painel; a etapa 3, login
individual (Cognito), que exige domínio e certificado. Ver `docs/decisoes.md`.

## Permissões

O que o painel precisa para trocar o simulado pelos dados reais e ir ao ar. Nada
disso existe ainda. O Terraform do painel tem estado próprio e não toca o estado
da Maria (as três regras estão em `docs/decisoes.md`).

### A Nicole faz (administra o repositório)

1. **Criar `dgd-dprj/visor-maria`**, público, com ruleset em `main` exigindo os checks `verificar`, `contrato` e `imagem`.
2. **Token só de leitura para as execuções do Actions** do `maria-langgraph-pp`: fine-grained, com `Actions: read` e `Metadata: read`, de uma conta de serviço, e não pessoal. Serve para listar as execuções e baixar o log da conferência diária, que exige autenticação mesmo em repositório público. Se a organização exigir aprovação de token, o dono dela aprova.

### O Ícaro decide

3. **Ler o custo da conta: `ce:GetCostAndUsage`.** É decisão, e não só execução, porque a conta tem outros projetos (coilab, tesseract, a API de consulta de processo, Amplify, knowledge bases), e a permissão lê o custo de todos. Se a resposta for sim, a execução vem junto: ativar a etiqueta `Project` como etiqueta de custo no Billing, e, se preferir no lugar do Cost Explorer, uma exportação CUR 2.0 para o S3. Se for não, a tela Relatório da Aplicação continua mostrando só o consumo de IA, com a fatura em espaço reservado.

### O Ícaro executa

4. **Chave nova no bucket de estado** (`maria-tfstate-185327115563`, chave `visor-maria/terraform.tfstate`) e uso da trava `maria-tf-lock`, que são do stack antigo.
5. **Um papel para aplicar o Terraform do painel**, restrito a recursos com prefixo `visor-maria`. Com ele, a Nicole aplica dali em diante sem acesso a nada da Maria. (A credencial dela hoje não cria recursos na AWS, pelo que os testes de leitura mostraram; ela não tem permissão nem para simular a própria política.)
6. **Papel da tarefa do painel, só leitura:**
   - Logs Insights nos grupos `/ecs/maria-langgraph-pp/api` e `/ecs/maria-langgraph-pp-release/api`: `logs:StartQuery`, `logs:GetQueryResults`, `logs:StopQuery` e `logs:DescribeLogGroups`;
   - métricas: `cloudwatch:GetMetricData` e `cloudwatch:ListMetrics` (`AWS/ApplicationELB`, `ECS/ContainerInsights`, `AWS/Bedrock`); o `GetMetricData` exige `"Resource": "*"`;
   - opcionais: `pricing:GetProducts`, para conferir preço, e `rds:DescribeDBInstances`, para o rateio do stack antigo.
7. **Papel de deploy do GitHub** que confie em `repo:dgd-dprj/visor-maria:ref:refs/heads/main`, usando o provedor OIDC que já existe (consultado por nome, sem mexer nele nem no papel da Maria), com push só no ECR do painel e `ecs:UpdateService`/`ecs:DescribeServices` só no serviço do painel.
8. **Infraestrutura da etapa 1:** repositório ECR `visor-maria`, cluster ECS próprio (sem Container Insights), tarefa e serviço Fargate em subrede privada com ECS Exec ligado, grupo de segurança sem entrada, grupo de logs, segredo do token do GitHub e papel de execução que o lê. Sem balanceador e sem CloudFront.
9. **Alarme de orçamento** no AWS Budgets para o painel (por exemplo, US$ 20 por mês), por causa do custo das consultas (ver abaixo).

**O que o painel não precisa:** acesso ao banco da Maria (bloqueado até a #309),
ao segredo da credencial do Verde (a validade vem do log da conferência diária)
e a qualquer recurso dentro do estado da Maria.

## Custo mensal estimado (etapa 1, túnel)

Com o que se sabe em 26/10/2026. Preços de tabela de `us-east-1`; o do Fargate
foi conferido na página da AWS em 26/10, os outros não.

| Item | Por mês | Como chegou |
|---|---|---|
| Fargate, 0,25 vCPU e 0,5 GB, ligado 24 horas | **US$ 9,01** | 730 h × (0,25 × US$ 0,0404784 + 0,5 × US$ 0,004446); em ARM, US$ 7,21 |
| Logs Insights, com cache das janelas longas | **US$ 0,30** | cerca de 0,7 GB varridos por hora de tela aberta × 88 h × US$ 0,005/GB |
| Logs Insights da tela Fluxos, só quando aberta | **até US$ 1,30** | 5 consultas de 7 dias a cada 5 minutos e 2 de 30 dias a cada 15: cerca de 3 GB por hora × 88 h × US$ 0,005/GB, se ela ficar aberta o tempo todo |
| Métricas do CloudWatch (`GetMetricData`) | **US$ 0,50** | cerca de 6 métricas por minuto de tela aberta, 2 pessoas, a US$ 0,01 por mil |
| Segredo do token do GitHub | **US$ 0,40** | 1 segredo no Secrets Manager |
| Tráfego pelo NAT, imagem no ECR, logs do painel | **US$ 0,30** | centavos cada; o NAT por hora já é pago pelo stack antigo |
| Túnel (Session Manager, ECS Exec) | US$ 0 | sem cobrança própria |
| **Total** | **cerca de US$ 11 a 12** | o máximo com a tela Fluxos aberta o tempo todo |

**Premissas e o que muda o número:**

- **Uso:** duas pessoas, cerca de 2 horas por dia útil cada (88 horas de tela aberta por mês). Os volumes de log são os do levantamento de 23/10 (cerca de 8 MB por dia, somando os dois ambientes).
- **Cache é o que segura o Logs Insights.** Desde 26/10 toda consulta passa pelo cache em disco (`dados/cache.py`), com a janela e a validade declaradas em `dados/consultas.py`; um teste falha se alguma consulta nova não declarar. Dia e mês fechados são lidos uma vez e guardados. As janelas que andam com o relógio (30 dias de reinícios, 8 dias do Verde) ainda são relidas na validade de cada uma, até virarem soma de dias fechados nas telas que vêm depois da financeira. Sem cache nas janelas longas (30 dias de reinícios, 8 dias do Verde), uma tela aberta varre cerca de 21 GB por hora: com o mesmo uso, o Logs Insights sobe para cerca de US$ 10, e o total, para uns **US$ 20**. Uma tela esquecida aberta 24 horas sem cache passaria de **US$ 80** só de consulta. A fonte real precisa nascer com cache, e o alarme de orçamento cobre o esquecimento.
- **Se o Ícaro aprovar a leitura de custo:** mais cerca de US$ 1 (Cost Explorer consultado no máximo de hora em hora, só com tela aberta) a US$ 7 (de hora em hora, o mês inteiro).
- **Se a tarefa só subir quando alguém for olhar:** o Fargate cai para cerca de US$ 2, e o total, para uns US$ 4, ao custo de esperar a tarefa subir.
- **Etapa 2 (link para os outros públicos):** mais um balanceador interno, cerca de US$ 16 por mês mais uso (US$ 0,0225 por hora, preço não conferido), e uma CloudFront, que nesse volume cabe na camada gratuita. Algo como **US$ 29 por mês** no total.
- A conta não conta com a camada gratuita do CloudWatch: ela é da conta AWS inteira e, provavelmente, já é usada pelos outros projetos.

## O que ainda falta

- **Ir ao ar numa tarefa própria**, com o papel só de leitura da lista de permissões. Hoje o painel lê os dados reais com a credencial de quem o roda.
- **O contrato com os logs da Maria ainda não confere as mensagens** que a fonte real lê pela linha (`MENSAGENS` em `dados/contrato.py`): o retrato do código só extrai eventos. A conferência dessas foi manual, em 26/10.
- **Temas Claro e Noturno: PROVISÓRIOS.** As cores de verdade estão na tabela do `painel-maria-LEIA.md`, que ainda não está neste repositório. Até ele chegar, os dois temas ficam com as cores atuais, sem novas aproximações, e não devem ser tomados como definitivos. O tema Escuro foi tirado do rascunho. A fonte é Archivo; a mono (JetBrains Mono) também é provisória.
- **Fontes da internet.** As fontes vêm do Google Fonts. Sem internet, o painel cai nas fontes do sistema.
- **Logs de referência da Maria** da versão Python, para fechar as lacunas de `FORA_DOS_LOGS_DE_REFERENCIA`. Isso depende de a Maria gravar amostras novas.
- **O export do rascunho** (`Painel da Maria.html`, 1,5 MB, quase tudo fonte em base64) fica na pasta e fora do controle de versão, por decisão (veja `docs/decisoes.md`).
