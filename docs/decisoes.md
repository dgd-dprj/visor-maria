# Decisões do Visor Maria

Cada decisão com a data, quem decidiu, o motivo e o que ela custa.

## 2026-11-24: login com a conta Google, só para os e-mails da lista

**Decisão (Nicole).** O painel deixa de abrir para qualquer pessoa com o endereço:
entra quem fizer login com a conta Google e estiver na lista de e-mails. Fecha o
item "autenticação" pendente da decisão do mesmo dia (painel online, abaixo).

**Como.** O grupo do Cognito é o `coilab-users` (us-east-1), do CoiLab, que já
tem o Google configurado: o Visor ganha um cliente próprio nele (público, só o
Google) e não toca no cliente do CoiLab. Um grupo só do Visor chegou a ser criado
em São Paulo e foi deixado de lado, porque faltava configurar o Google nele. O
painel manda direto ao Google (`identity_provider=Google`), troca o código com
PKCE (cliente público, sem segredo no painel) e pergunta o e-mail ao Cognito. A
lista fica no Parameter Store (`/visor-maria/emails-com-acesso`), editada no
console, porque o repositório é público; o painel a relê a cada minuto e a confere
em toda requisição, então tirar um e-mail fecha o acesso em até um minuto. Sem a
configuração ou a lista, o painel fecha (503). O login vale 8 horas e é refeito a
cada dia (a chave da sessão é recriada quando a instância liga).

**Alternativas.** Código por e-mail no Cognito, sem Google (fica fácil de somar
depois, no mesmo Cognito); Cloudflare Access (exige o domínio na Cloudflare). O
Google ganhou porque a equipe já tem conta Google.

**A tela de login (Nicole).** Fica fora do Dash e já com a identidade da
Defensoria, enquanto o visual novo do Visor não chega: à esquerda, "Boas-vindas",
o rosto da Maria numa moldura redonda com borda dourada e uma animação leve
(desligada para quem pede menos movimento no sistema) e uma frase sobre para que
serve o Visor; à direita, o cartão com a logo oficial da
Defensoria e o botão do Google. As fontes são as do portal da Defensoria de 2025
(League Spartan nos títulos, DM Sans no texto). A imagem fica em `assets/`,
reduzida da arte original (18 MB) para 108 KB.

**Custo.** O Cognito é gratuito nesse volume (menos de dez pessoas); o Parameter
Store padrão também. O cliente OAuth do Google é gratuito.

## 2026-11-17: o tom das conversas de verdade, só em números

**Decisão (Nicole).** O quadro "Tom da IA" mostra primeiro as métricas das perguntas de
desambiguação **de verdade**, e a comparação com relatos inventados fica recolhida, como
teste. "Não faz sentido o painel com tudo fictício." Não é trazer os dados das pessoas: a
Maria mede o tom de cada pergunta na hora (maria-langgraph-pp #508, `maria.ia.tom`) e
registra **só os números** no evento `desambiguacao_tom`, nunca a pergunta nem o relato.

- **Onde lê:** a produção (Virgínia), a produção nova em São Paulo (`/ecs/maria-langgraph-pp-prod-sp/api`,
  #509, até o corte) e o release, nos 30 dias de logs, por modelo.
- **Quando aparecem números:** depois que a #508 entrar. No release, depois da promoção para a staging; na
  produção, depois do corte para São Paulo (a Virgínia não recebe mais versão nova). Até lá, o quadro diz isso.
- **Contrato:** o evento entra em `dados/contrato.py`. O retrato do código foi tirado da branch da #508; este
  trabalho só pode ir para a `visor-maria` depois que a #508 estiver na `develop` da Maria, senão o job diário
  `contrato` falha.

**O que custa.** Três consultas ao Logs Insights a cada 15 minutos com a tela aberta, só no evento do tom.

## 2026-11-16: o tom da IA no Observatório e o gasto fora do atendimento

**Decisão (Nicole).** A comparação do tom da pergunta de desambiguação (Haiku, Qwen sem
o tom e Qwen com o tom; maria-langgraph-pp #508) aparece no Observatório da IA, no quadro
"Tom da IA" (visor-maria#12). O quadro mostra as regras automáticas por versão, as
palavras em média, o emoji, o gasto de cada versão, as notas da equipe e a amostra lado
a lado. O gasto da comparação e o do QA da staging também aparecem no Relatório da
Aplicação, no quadro "Gasto fora do atendimento", sem o detalhe, que fica nas outras
duas telas.

- **Fonte:** o comentário mais novo da #508 com a marca `<!-- visor:tom-da-ia -->`, um
  bloco JSON que o `scripts/avaliacao/tom_desambiguacao.py` produz. O Visor lê o
  comentário, e não o arquivo do repositório, para mostrar a comparação antes do merge.
- **A nota humana é cega e o Visor continua só lendo.** O botão "Dar notas" abre no
  GitHub uma issue já preenchida (`[nota de tom]`) com 8 relatos. Cada pergunta vai com
  um código (`c3-1`, `c3-2`), sem o nome do modelo, e a ordem troca a cada caso. O
  Visor lê as notas dessas issues. Entram só a produção de hoje e a proposta da #508.
- **Tela financeira:** sem nome de modelo nos rótulos (regra da tela). A parte do Haiku
  da comparação fica dentro do gasto de produção que a tela mede, e o texto explica isso.

**O que custa.** Nada na AWS. No GitHub, duas leituras a cada 5 minutos com a tela
aberta: os comentários da #508 e a lista de issues. O link "Dar notas" tem cerca de 6 mil
caracteres, abaixo do limite do GitHub; por isso o relato vai só na primeira linha de
cada caso.

## 2026-11-16: a tela QA

**Decisão (Nicole).** O QA da Maria entra no Visor numa tela própria (`/qa`,
visor-maria#10). Ela mostra o gasto e o que o QA pegou para acertar, sem repetir
o que as outras telas já mostram:

- a contagem das execuções do CI ("Testes a cada mudança") continua na Agora, no
  Sistema e no Relatório do dia; o QA mostra só o que foi conferido, conferência
  por conferência;
- o gasto total do release continua no Relatório da Aplicação; o QA mostra o gasto
  de cada rodada, contra o teto de US$ 0,10 por rodada da staging.

As fontes são só do GitHub: o log do job `ponta_a_ponta` do CI (maria-langgraph-pp
#502), os comentários "QA da staging" nos PRs para a staging e os alertas abertos
do CodeQL. Um defeito fica resolvido na primeira rodada seguinte que passa inteira:
do mesmo PR, no ponta a ponta; qualquer uma, no QA da staging. A tela usa a largura
toda, como a Agora e a Infra, porque as tabelas pedem espaço.

**Por quê.** O QA precisa ter o gasto e mostrar o que deu defeito para acertar.

**O que custa.** Nada na AWS. No GitHub, uma leitura dos jobs por execução do CI
desde 13/11 (o que uma execução terminada disse fica guardado) e uma por PR para a
staging, a cada 5 minutos com a tela aberta. O gasto da staging é o que o roteiro
somou no preço do Haiku, o teto seguro (o Qwen do release custa menos). Quando a
depuração com IA (maria-langgraph-pp #503) existir, o gasto dela entra aqui.

## 2026-11-16: o release é lido em São Paulo

**Decisão (Nicole).** O release da Maria passou para `sa-east-1` em 16/11 e o da
Virgínia foi desligado (maria-langgraph-pp, `docs/infra-sa-east-1.md`, #463 e
#500). O Visor lê cada ambiente na região dele (`fontes.REGIAO`): produção na
Virgínia, release em São Paulo, com os nomes terminados em `-sp` (grupo de logs,
cluster, serviço, target group, banco, NAT) e o modelo Qwen. O CloudFront, a
Lambda do e-mail, os alarmes de `infra/alertas` e o gasto de IA da tela
financeira continuam lidos na Virgínia.

**Por quê.** Com o grupo de logs do release apagado na Virgínia, toda leitura do
release voltava recusada, não ficava no cache e era refeita a cada troca de
tela: a credencial do release levava cerca de 60 s por tela.

**O que custa.** Os 30 dias de logs do release na Virgínia saíram junto com o
grupo: o histórico do release começa em 11/11, quando o de São Paulo foi criado.
O Terraform de `infra/alertas` (ainda não aplicado) aponta o release da
Virgínia, e o gasto do Qwen não entra na tela financeira.

## 2026-11-23: o Visor renova a credencial do Verde com 1 dia para vencer (issue #14)

**Decisão (Ícaro).** O Visor ganha a renovação, e só a executa quando precisa:
com 1 dia ou menos para o token vencer (ou vencido há menos de 5 dias, o grace
period do Verde). Depois de renovar, grava o token novo em `VERDE_JWT_TOKEN`
(segredo `maria-langgraph-pp-<amb>/app`) e força o redeploy do serviço ECS,
porque a Maria só lê o token no boot. As demais credenciais seguem só no
histórico.

**Como.** `src/painel/renovador.py`, comando `python -m painel.renovador`
(`--simular` só decide; `--ambiente` limita). Roda uma vez por dia, fora do
servidor web: é o único código do Visor que lê e escreve o segredo, e a regra
"o painel nunca lê o segredo" continua valendo para o resto.

**Proteções.** Trava por ambiente (`visor-maria/trava-renovacao-<amb>`, criada
de forma atômica; trava com mais de 15 min é de uma execução que morreu);
releitura do segredo sob a trava; gravação com 5 tentativas; o token e o client
id nunca vão para log, tela, cache ou mensagem de erro (só o tipo da exceção).
Token revogado, fora do grace period ou resposta sem `token`: nada é gravado e o
comando sai com erro.

**Convivência com o workflow.** O `verificar-token-verde.yml` do
maria-langgraph-pp (#187) renova com 7 dias ou menos, bem antes do 1 dia do
Visor, então o Visor só age se o workflow falhar. Duas renovações ao mesmo
tempo invalidariam o token uma da outra: o agendamento do Visor deve ficar
desligado enquanto o workflow não for desativado, ou ligado só como rede de
segurança, nunca rodando junto na mesma hora.

**Permissão mínima do papel que roda o comando** (`sa-east-1`), no papel `visor-maria-renovador`:
`secretsmanager:GetSecretValue` e `PutSecretValue` em
`maria-langgraph-pp-{prod,release}/app`; `secretsmanager:CreateSecret`,
`DescribeSecret` e `DeleteSecret` em `visor-maria/trava-renovacao-*`;
`ecs:UpdateService` nos serviços `api-prod-sp` e `api-release-sp`. Não é o
papel da tarefa do painel, que segue só leitura.

**Onde roda.** Num workflow agendado do próprio visor-maria
(`.github/workflows/renovar-token-verde.yml`), com um papel OIDC só dele, em vez de
uma tarefa Fargate: assim não depende do cluster, da imagem e das subredes da etapa 1
(Ícaro, 23/11). `infra/renovador` (Terraform, estado próprio) cria o papel, que só a
`main` deste repositório assume, com a permissão acima mais escrever no grupo de
logs `/ecs/visor-maria/renovador`. O agendamento fica **desligado** até a variável
do repositório `RENOVADOR_LIGADO` valer `true`; o disparo manual começa em
simulação. Sem repetição automática: o refresh invalida o token antigo.

**Na tela Credencial.** O comando grava uma linha JSON por ambiente e por dia em
`/ecs/visor-maria/renovador` (evento `renovacao_verde`: ambiente, resultado,
`validaAte`; nunca o token), mesmo quando não renova. A tela lê esse grupo pelo
Logs Insights e usa a validade mais recente entre ele e o log do workflow; as
renovações do Visor entram na linha do tempo. Escolhido no lugar de uma chamada
ao Verde na abertura da página, para o token não entrar no servidor web (Ícaro,
23/11). Se o grupo não existe ou o papel do painel não o lê, a tela segue só com
o workflow. A validade atualiza uma vez por dia, não ao vivo.

**Pendente.** Aplicar o Terraform e guardar o papel em `AWS_ROLE_ARN_RENOVADOR`;
dar ao papel da tarefa do painel a leitura do grupo `/ecs/visor-maria/renovador`
(README, "Permissões", item 6); decidir o que fazer com o workflow da Maria antes
de ligar `RENOVADOR_LIGADO`.

## 2026-11-24: o painel online numa EC2 simples, atrás do CloudFront, aberto e sem login

**Decisão (Ícaro).** Vai ter gente sem conta AWS usando o painel (menos de dez
pessoas), então ele fica online. O pedido é o mais simples possível: sem VPC
própria, sem balanceador e sem ECS; a imagem fica no ECR e roda com Docker numa
instância Linux. Login (Cognito ou outro) fica para depois.

**Como.** `infra/painel`: uma EC2 `t3.micro` na **VPC padrão** da conta, com IP
fixo, que puxa a imagem do ECR num serviço do systemd e a publica na porta 80. Na
frente, um **CloudFront** com o endereço `*.cloudfront.net` e o certificado da
AWS, sem domínio nosso; a porta 80 da instância só aceita os IPs do CloudFront
(lista gerenciada da AWS). Liga às 08:00 e desliga às 21:00. Custo estimado de
US$ 14 a 17 por mês, contra cerca de US$ 30 de Fargate mais o balanceador.

**O que não deu certo.** Primeiro, o HTTPS pelo próprio Caddy da instância, com
certificado do Let's Encrypt para `<ip>.sslip.io`: funcionou, mas o firewall da
Defensoria (FortiGuard) bloqueia o `sslip.io` como "Dynamic DNS". Depois, o nome
`ec2-*.amazonaws.com`: o Let's Encrypt recusa emitir para ele ("proibido por
política"). O CloudFront resolve as duas coisas sem domínio nosso.

**O risco, aceito.** Sem login, qualquer pessoa com o endereço abre o painel e
dispara consultas pagas ao CloudWatch. Ele só mostra agregados (a regra 4
continua: nenhuma conversa identificada), mas expõe validade de credencial, gasto
e infraestrutura. O trecho CloudFront → EC2 é HTTP, e quem criar uma distribuição
própria apontando para o IP da instância também chega à porta 80. O alarme de
orçamento avisa se o gasto subir. **Pendente:** autenticação; cabeçalho secreto
ou WAF; e, se a Defensoria der um domínio, um subdomínio com certificado próprio.

## 2026-11-10: a regra 4 passa a ser "nunca identificar a conversa"

**Decisão (Nicole).** Para entender os bugs, a tela Atendimento mostra uma linha
por ocorrência de problema, e não só contagens. A regra 4 ("nunca listar
conversa") passa a ser "nunca identificar a conversa": nenhuma linha traz
`chatId`, telefone, IP ou texto digitado.

**O que cada linha traz.** A hora; o tipo; a etapa (a rota, com o `chatId` do
caminho trocado por `:chatId`, a consulta ao Verde, a função de IA); o fluxo; o
código (status HTTP, tipo da exceção, `tipoErro`; nunca a mensagem da exceção, que
pode levar dado digitado); a demora; a tentativa; e o que aconteceu com a
conversa depois (encerrou, com o motivo; seguiu; expirou; parou; já estava
encerrada). O `reqId` da requisição entra na consulta sugerida para o Logs
Insights: é aleatório e não diz de quem é a conversa.

**Como o "depois" sai sem identificar ninguém.** O `chatId` volta da consulta
para a fonte (`dados/real.py`, `ocorrencias`), que busca o encerramento, a
expiração e a última resposta de cada conversa, em lotes de 150, e o descarta:
ele não entra no que a fonte devolve, nem no cache, nem na tela. Um teste confere
(`tests/test_problemas_e_infra.py`).

**Os tipos.** Erro da Maria (5xx), resposta depois de 30 s (o corte do
CloudFront, #344), falha dentro do fluxo, falha do email ao NUDECON, o Verde
falhou (sem contar a pessoa ou o processo que não existem), a IA falhou, o
WhatsApp falhou, conversa cortada, triagem que se contradisse e pedido recusado
(4xx). A varredura de robô (`/webhooks`, `/.env`) fica de fora.

**Levantamento de 10/11, produção, de 23/10 (corte de versão) a 10/11.** 306
ocorrências em 91 conversas: 208 do Verde (198 sem resposta em 30 s), 83
respostas que passaram de 30 s (56 delas perto de 90 s, as 3 tentativas ao Verde
da #172), 10 pedidos recusados (409 e 404) e as 5 conversas cortadas no corte.
Picos às 16h e às 9h. No release, 10 em 7 dias: recusas e uma falha do email (429).

**Os graves, um a um (Nicole, mesmo dia).** Em vez de um número só, um cartão por
tipo grave (erro da Maria, resposta depois de 30 s, falha dentro do fluxo, email
ao NUDECON), com a última vez, onde, o código, o fluxo, a demora, o pico, o que
aconteceu depois e o motivo do encerramento; "Ver na lista" escolhe o tipo no filtro.
Os quatro aparecem sempre, mesmo sem ocorrência ("nenhum").

**Para a tela não demorar nem ficar apagada (mesmo dia).** A tela abre sem esperar
os problemas (espera até 1,5 s; depois disso, o quadro diz que está lendo e se
preenche sozinho); os pedidos e os eventos são consultados juntos (a leitura fria
caiu de cerca de 9 s); o quadro tem relógio próprio de 5 minutos, a validade da
leitura, e não refaz a lista a cada minuto; e a lista começa nas 100 mais novas
(com 300, eram cerca de 300 KB por volta).

**O que custa.** Duas consultas ao trecho da origem por leitura, mais uma por lote
de conversas, relidas a cada 5 minutos com a tela aberta. Em produção, cerca de
4,5 MB de logs por dia de janela (medido em 10/11: 31 MB em 7 dias).

## 2026-11-10: a tela Infra

**Pedido (Nicole).** Uma aba só para a infraestrutura da AWS: a instabilidade e a
saúde dela, em produção e no release (homologação).

**O que mostra.** A saúde agora nos dois ambientes lado a lado (a única parte sem
filtro de ambiente); a instabilidade por dia em 14 dias (clique num dia); os
trechos de horas seguidas com problema, do mais novo; cada parte hora a hora, na
cor do estado, com os picos; e os gráficos da entrada, do tempo de resposta, dos
containers, do banco e dos serviços de fora. Usa a largura toda, como a Agora.

**As partes e as fontes.** Entrada (CloudFront `E3AYMLBF0ZRZL3` em produção e
`EMY0HA3227AG0` no release, pela quantidade de pedidos em 7 dias: 4.107 e 286);
tempo de resposta (p99 do balanceador e as respostas acima de 30 s nos logs);
containers (no ar, CPU, memória e reinícios); e, os mesmos nos dois ambientes, o
banco (`maria-chat-prod-pg`), a saída para a internet (NAT), o modelo de IA e a
função de email. O Verde entra pelo que a Maria registrou. Tudo com
`GetMetricData` (uma chamada por leitura) e uma consulta de logs.

**Os limites de cada hora (para começar, ajustáveis em `dados/modelo.py`).**
Entrada: instável com 1 erro 5xx, com problema com 5 ou 5% dos pedidos. Tempo:
instável a partir de 10 s de p99, com problema a partir de 30 s ou com uma
resposta cortada. Containers: com problema sem nenhum no ar; instável com menos
que o desejado, reinício, CPU de 80% ou memória de 90%. Banco: CPU de 60% e 80%.
Saída: instável com 1 erro, com problema com 100. Verde: 1 e 5 falhas. Modelo de
IA: 1 e 10 recusas. Email: com problema com 1 erro.

**Levantamento de 10/11, produção, 14 dias.** 60 respostas 5xx no CloudFront, 59
respostas cortadas aos 30 s, 147 falhas do Verde e 2 reinícios. O p99 chegou a
29 s; o banco não passou de 44% de CPU. Os trechos com problema coincidem com o
Verde sem resposta (09/11, das 16h às 18h: 16 falhas, 6 respostas cortadas e 6
erros 5xx).

**O que custa.** Com a tela aberta: cerca de 20 métricas por leitura, relidas a cada
5 minutos (24 horas) e 15 minutos (14 dias), e duas consultas de logs de uma linha
por hora. Abaixo de US$ 1 por mês nas 88 horas de uso.

## 2026-11-09: Credencial com os gráficos embaixo, vencimento e causa dos incidentes

**Decisão (Nicole).** Na tela Credencial:

- "Consultas ao Verde" e "A que horas a conferência rodou" saem da coluna da direita
  (até 440 px) e vão para o fim da tela, na largura inteira, com todo dia no eixo e,
  na conferência, toda hora de 8h a 19h. A Credencial deixa de ter coluna da direita
  e ocupa a largura toda do monitor, sem o limite de 1180 px das outras telas.
- Acima dos dois gráficos, um filtro só para eles: Dias (os últimos 30, um por dia) ou
  Mês (a lista de meses desde setembro de 2026, e o gráfico mostra os dias do mês). A AWS
  guarda os logs por 30 dias (retenção conferida em 09/11 nos dois grupos): no Verde, o
  mês aparece só a partir do dia que os logs alcançam, com o aviso, e um mês que já saiu
  deles diz isso em vez de mostrar zero. A conferência vem do GitHub e mostra o mês
  inteiro. Mês fechado fica guardado sem prazo. Retenção mantida em 30 dias (Nicole).
- A linha do tempo vira tabela: data, hora, tipo, vencimento e o que aconteceu. O
  vencimento é até quando valia a credencial do evento. A conferência diária lê o
  segredo antes de renovar, então o vencimento da credencial renovada é o da
  conferência do dia seguinte; no dia da renovação, a célula diz "na próxima conferência".
- Os incidentes ganham data e hora em colunas separadas, a causa, as conversas que
  bateram na recusa (antes "não medido") e, só em produção, a marca "atinge o público".

**Como sai a causa** (`linha_do_tempo.causa`): uma renovação do mesmo ambiente sem
container novo, de 3 horas antes a 1 hora depois da primeira recusa, é "container com a
credencial antiga"; senão, a validade da última conferência antes da recusa diz se a
credencial estava vencida ou no prazo; sem conferência antes, "sem validade conferida".
Nos 30 dias até 09/11: produção, 22/10, container com a credencial antiga (91
atendimentos); produção, 20/10, e release, 29/10, recusa no prazo; release, 22/10, sem
validade conferida (a conferência do release falhava desde 28/09).

**O que custa.** As conversas afetadas saem da mesma consulta que já achava o horário
exato de cada incidente (`count_distinct(chatId)`, que não sai da consulta). O cache
subiu para a versão 3, porque a credencial guardada mudou de forma: a primeira leitura
depois de atualizar é refeita.

## 2026-11-05: as outras telas são montadas por trás

**Decisão.** Ao abrir o painel, e ao trocar de tela, as telas que não estão abertas
são montadas por trás, uma de cada vez (`dados/telas.py`, `aquecer`). De novo só depois
de 30 minutos (`VENCIDA_AINDA_SERVE`): antes disso, a leitura guardada ainda aparece na
hora.

**Motivo.** Pedido da Nicole: trocar de tela ainda estava lento. A decisão de 26/10
resolve a segunda visita, mas de manhã, ou depois de meia hora numa tela só, o
primeiro clique em cada tela esperava as consultas dela. Medido em 05/11, com dados
reais e o cache como estaria de manhã, clicando assim que a Agora aparece: antes, de
2,7 a 6,6 s por tela (Fluxos, a pior); depois, de 0,5 a 3,1 s. Com alguns segundos na
Agora antes do primeiro clique, todas abaixo de 0,6 s.

**O que custa.** As consultas de todas as telas, mesmo das que ninguém abrir, no
máximo uma vez a cada 30 minutos, e só enquanto alguém navega: o relógio de uma aba
parada não monta nada. Também os dias passados de todas as telas (`preparar`), uma vez
só, porque ficam guardados sem prazo.

**O que fica de fora.** A primeira tela que abre de manhã ainda leva uns 11 s; a
leitura mais lenta é a da credencial, 9,5 s no GitHub.

## 2026-11-03: o quadro Alertas na Agora

**Decisão (Nicole).** A Agora mostra os alertas, logo abaixo do caminho do atendimento:
uma linha por alerta (o que vigia e quando avisa), uma coluna por ambiente, com o estado
de agora (normal, disparado, sem dado), desde quando e quantas vezes disparou em 7 dias.
Fica fora do filtro de dia, como a credencial: é sempre de agora. Antes de o Ícaro
aplicar `infra/alertas`, o quadro diz que os alertas ainda não existem e quem cria.

**De onde sai.** `DescribeAlarms` com o prefixo `visor-maria-` e `DescribeAlarmHistory`
de cada alarme (pedir o histórico sem o nome traria os alarmes de ajuste automático do
ECS, que mudam o dia todo). Relido a cada minuto; as duas chamadas não são cobradas por
métrica.

**Teste de 03/11, sem criar nada, contra 14 dias de métricas e logs reais.** As regras
aplicadas aos dados de 20/10 a 03/11:

- sem host saudável, 5xx e CPU: nenhum disparo, nos dois ambientes;
- latência p99 de produção: 62 disparos (13 horas em alarme), cerca de 4 por dia, cada
  um com o aviso de ida e o de volta;
- Verde recusado em produção: teria avisado às 13:20 de 22/10, minutos depois do começo
  do incidente que ficou 23 horas sem ser visto, e também em 20/10, das 16:20 às 17:20.
  De noite, com pouco tráfego, as recusas ficam abaixo de 3 linhas a cada 10 minutos, ou seja, nenhuma consulta inteira, e o alarme
  abriria e fecharia 16 vezes no incidente. Por isso ele só volta ao normal depois de 2
  horas sem recusa: cerca de 4 avisos no mesmo incidente.

## 2026-11-03: os alertas da Maria ficam no Visor, avaliados pelo CloudWatch (issue #2)

**Decisão (Nicole).** Os alertas da Maria ficam no Visor (registrado na #308 e na
#208 da Maria). Quem avalia é o CloudWatch Alarms, e o aviso sai por e-mail pelo SNS.
O código fica neste repositório, em `infra/alertas/`, com estado próprio
(`visor-maria/alertas/terraform.tfstate`).

**Por que o CloudWatch, e não o Visor.** O Visor só consulta com alguém olhando a tela
(5 consultas a cada 5 minutos e 2 a cada 15). Um alerta precisa ser avaliado o tempo
todo, inclusive com o Visor fora do ar.

**O que entrou.** As 8 regras do Grafana (sem host saudável, 5xx, CPU e latência p99,
em produção e no release), com os mesmos limites. Também entrou o alerta da credencial
do Verde recusada (401 e 403 em `verde_chamada`), que motivou a #308 da Maria e não
estava na lista da #2.

**O que custa.** O alerta do Verde precisa de um filtro de métrica dentro do grupo de
logs da Maria, a única exceção à regra 3 do isolamento (nada dentro de recurso da
Maria). A exceção foi aceita pela Nicole no mesmo dia, com o menor custo: só em
produção (o release não tem uso), uma métrica sem dimensões, e o filtro só grava
quando há recusa. A latência p99 continua com o limite de 3 s, como no Grafana, mesmo
disparando boa parte do dia. São 9 alarmes e 1 métrica própria: cerca de US$ 1,20 por
mês. Aplicar pede permissão de escrita em CloudWatch,
SNS e, para o Verde, logs, que a credencial do Visor não tem (com o Ícaro).

## 2026-10-29: CPU e latência p99 no Sistema (issue #3)

**Decisão.** Os dois gráficos do painel "Maria — Observabilidade" do Grafana
(`infra/grafana/dashboards/observabilidade.json`) vão para o corpo do Sistema,
logo abaixo dos indicadores, em dois quadros: CPU média do serviço ECS
(`AWS/ECS` `CPUUtilization`) e p99 do balanceador (`TargetResponseTime`), hora a
hora, produção e release juntos, como no Grafana, e por isso fora do filtro de
ambiente. O clique numa hora filtra a tela; com um dia escolhido, o quadro mostra
o dia inteiro. A linha tracejada é o limite do alerta do Grafana (80% e 3 s) e só
aparece quando os valores chegam à metade dele: CPU de 0,5% contra 80% viraria
uma linha reta no chão.

**Levantamento de 29/10, 16h, em produção.** A CPU não passa de 2% nos dois
ambientes. O p99 de produção ficou acima de 3 s em 16 das últimas 24 horas, com
pico de 29,1 s às 14h: a regra "latência p99 alta" do Grafana (acima de 3 s por
15 minutos) estaria disparando boa parte do dia. Vale conferir na #2 se o limite
faz sentido para a Maria, que espera o Verde por até 30 s.

## 2026-10-29: o Visor substitui o Grafana

**Decisão.** O Grafana vai ser desligado; o monitoramento da Maria passa a ser o
Visor Maria. Informado por Nicole.

**O que isso pede.** Hoje o Visor lê com a credencial pessoal de quem o roda: no
mesmo dia, a usuária da Nicole perdeu a consulta aos logs da Maria (`logs:StartQuery`
e `logs:FilterLogEvents` negados desde cerca de 16h; métricas e GitHub seguem) e
todos os números que vêm dos logs pararam. O Ícaro devolveu a permissão às 16:40,
e as leituras voltaram na atualização seguinte. Para ser o monitoramento, o Visor
precisa rodar na tarefa própria, com o papel só de leitura (README, Permissões),
e não depender do login de uma pessoa.

## 2026-10-29: quem roda sem credencial da AWS vê o porquê

**Problema.** Outras pessoas baixaram o painel e viram a Agora quase sem números.
Reproduzido nesta máquina, sem credencial da AWS: 21 das 23 leituras da Agora
falham (só as do GitHub passam), cada quadro dizia "A fonte não respondeu.", e o
caminho do atendimento dizia "tudo o que rodou funciona", com 1 de 11 etapas lida.

**Decisão.** Uma faixa "Sem acesso à AWS" no topo de toda tela, olhada na
subida; nos quadros, "Esta máquina não tem credencial da AWS, ou o login venceu"
quando o erro é de credencial (falta, login vencido ou chave que não vale); e o
caminho diz "faltou ler N etapas" quando nenhuma etapa lida está ruim. O README
ganhou "Primeira vez", com o acesso, o login e o que cada aviso pede.

**Custo.** O login feito com o painel aberto só vale depois de reiniciar, porque
os clientes da AWS guardam a credencial da subida; a faixa e o README dizem isso.

## 2026-10-29: o nome passa a ser Visor Maria

**Decisão.** O painel se chama Visor Maria, no menu, no título das abas e na
documentação, e o repositório passa a ser `visor-maria`. Decidido por Nicole.

**O que não mudou.** O pacote Python continua `painel` e as variáveis de
ambiente continuam `PAINEL_*`, para não quebrar a configuração de quem já roda.
Nos textos das telas, "o painel" segue como nome comum do que a ferramenta é.

## 2026-10-26: repositório próprio, fora do maria-langgraph-pp

**Decisão.** O painel sai de dentro do `maria-langgraph-pp` (onde estava em
`relatorio-maria/`, sem controle de versão) e vai para um repositório próprio,
`dgd-dprj/visor-maria`, público como o da aplicação, com CI e imagem
separados. Decidido por Nicole, com o Ícaro.

**Motivo.** Versionar o painel dentro do repositório da aplicação exigiria mexer
no pipeline de produção, e não vamos mexer em pipeline de produção com a equipe
testando. Os três custos que pesaram:

1. **Filtro de caminho no `deploy-prod.yml`.** Ele dispara em todo push para
   `main`, sem filtro: sem `paths-ignore: relatorio-maria/**`, todo merge do
   painel reconstruiria e reiniciaria a Maria em produção.
2. **Filtro de caminho no `deploy-release.yml`.** O mesmo para `develop`: todo
   merge do painel reiniciaria o release no meio do teste da equipe.
3. **Job novo no CI** (`ci.yml`). O `mypy` e o `pytest` da aplicação não
   enxergam a pasta (`files` e `testpaths` olham só `src`, `tests` e `scripts`),
   então os testes do painel não rodariam em lugar nenhum. E, se o job virasse
   check obrigatório no ruleset, uma falha do painel travaria merge da Maria.

**Verificado antes de decidir (26/10, só leitura):**

- a imagem da Maria **não** levaria o painel: o Dockerfile dela copia só
  `pyproject.toml`, `uv.lock`, `.python-version`, `README.md` e `src/`;
- o `ruff format --check` do CI da aplicação falhava em 3 arquivos do painel;
- o `test_sem_typescript` da aplicação falhava por causa de `assets/painel.js`,
  mesmo com a pasta fora do controle de versão (o teste varre o disco). O
  JavaScript passou para `painel/navegador.py`, e o teste voltou a passar;
- a credencial OIDC do GitHub para a AWS só confia em
  `dgd-dprj/maria-langgraph-pp`, em `main` e `develop`: o deploy deste
  repositório precisa de mudança no Terraform (ver o README, "Permissões").

**O que a separação traz de risco, e como fica coberto.** O painel lê os logs da
Maria pelo nome do evento e do campo. Em repositórios separados, uma renomeação
na Maria quebraria o painel em silêncio. Por isso o acoplamento é parte da
decisão: `painel/dados/contrato.py` declara o que o painel lê, e
`tests/test_contrato_da_maria.py` confere contra o código da Maria (retrato
refeito todo dia pelo CI, em `main` e `develop`) e contra os logs de referência
dela, copiados para `tests/fixtures/maria/`.

**Decidido junto (Nicole, 26/10):**

- o export do rascunho (`Painel da Maria.html`, 1,5 MB) fica fora do git;
- o job `imagem` do CI fica: hoje é o único lugar onde a imagem é conferida;
- a decisão também vai para a #208 do `maria-langgraph-pp`, porque afeta o
  repositório da aplicação (a pasta `relatorio-maria/` sai de lá).

## 2026-10-26: Terraform com estado próprio, isolado da Maria

**Decisão (Nicole).** O Terraform do painel tem estado próprio, mesmo custando
mais trabalho, com três regras de isolamento:

1. **Estado próprio**, numa chave só do painel (por exemplo,
   `visor-maria/terraform.tfstate`), nunca a chave da Maria
   (`maria-langgraph-pp/terraform.tfstate`);
2. **os recursos da Maria são consultados por nome** (`data` sources: VPC,
   subredes, provedor OIDC do GitHub), nunca por `terraform_remote_state` do
   estado dela;
3. **nada é acrescentado dentro de recurso da Maria**: nem regra no
   balanceador, nem serviço no cluster, nem mudança no papel de deploy dela.

Assim, nenhum `terraform apply` do painel toca o estado da Maria.

## 2026-10-26: acesso pelo túnel da AWS, como etapa

**Decisão (Nicole).** Hoje o painel não tem endereço público: roda em subrede
privada, sem balanceador e sem CloudFront, e quem vê abre um túnel pelo Session
Manager (`AWS-StartPortForwardingSession`) até a tarefa.

**É etapa, não solução.** O túnel atende duas pessoas, as que têm conta AWS. O
painel foi desenhado para três públicos, e os outros dois não alcançam o painel
por ele. A etapa seguinte, quando eles precisarem, é uma CloudFront ligada a um
balanceador interno do painel (*VPC origin*), mais login no próprio painel; e
depois, login individual (Cognito), que exige domínio e certificado.

**Por que o túnel agora:** é a restrição mais simples que resolve sem endereço
público, sem código de login e sem balanceador, e cada sessão fica no CloudTrail
com o nome da pessoa.

## 2026-10-26: trocar de tela não espera a consulta

**Decisão.** Uma leitura vencida há menos de 30 minutos aparece na hora, e a
nova é lida por trás, para a volta seguinte do relógio (`dados/cache.py`,
`VENCIDA_AINDA_SERVE`). Passado isso, a tela espera a leitura nova. Junto: duas
telas que pedem a mesma consulta ao mesmo tempo esperam a mesma leitura; o corpo
e a coluna da direita de cada tela são lidos juntos; e as rotinas do GitHub e os
incidentes da credencial deixaram de ler uma coisa depois da outra.

**Motivo.** Trocar de tela levava até 15 segundos: o `layout` de cada tela
esperava todas as consultas, e o cache, de 1 a 5 minutos, já tinha vencido para
a tela que não estava aberta. Medido em 26/10, com dados reais: a Agora e a
Credencial levavam 15 s com o cache vencido; depois, menos de 0,1 s. As rotinas
caíram de 14 s para 6 s, e os incidentes, de 13 s para 6 s, na primeira leitura.

**O que custa.** Um número pode aparecer com até 30 minutos, mais a validade da
consulta, de atraso. A hora da leitura, ao lado de cada número, mostra isso. A
quantidade de consultas pagas não muda: a releitura por trás é a mesma que a
tela faria.

## 2026-10-26: o clique num dia filtra a tela

**Decisão.** Como no Power BI, clicar num dia de um gráfico refaz a tela inteira
naquele dia, sem mexer nos outros filtros (ambiente, origem); o mesmo dia de novo,
ou "Tirar o filtro", volta à janela padrão (`componentes/filtro_de_dia.py`). Cada
tela tem um gráfico de dia para clicar; Atendimento e Relatório do dia ganharam o
seu. A Relatório da Aplicação continua com o filtro de período dela, que já
filtrava pelo clique.

**O que não tem dia continua sendo de agora**: a saúde do serviço, a validade da
credencial, CPU e memória, as rotinas, o "Exige atenção" e o "O que fica para
amanhã". A faixa no topo da tela filtrada diz quais quadros são esses.

**O que custa.** Cada consulta com dia varre um dia de logs, cerca de 8 MB
(levantamento de 23/10), menos que a janela padrão de 7 ou 30 dias. Dia que já
passou fica guardado sem prazo: clicar nele de novo não consulta nada.

**Ampliado no mesmo dia (26/10), depois do pente fino no navegador.** O filtro
passou a ter três partes: o dia, a hora (os gráficos hora a hora) e a categoria
(o resultado do Verde, pelo segmento da barra ou pela legenda, e o motivo de
"Como terminaram"). A hora chega às consultas como o começo dela, e cada uma lê
só aquela hora. O Verde é contado por dia, então, com uma hora escolhida, os
quadros do Verde dizem que o número é do dia inteiro. Ao abrir uma tela, os dias
passados do gráfico dela são lidos por trás, dois de cada vez (`preparar`, em
`dados/telas.py`): o clique num dia encontra a leitura pronta. Cada dia é lido
uma vez só, porque fica guardado sem prazo; na tela Sistema, a mais cara, são
cerca de 65 consultas de um dia, uma vez, por volta de US$ 0,001. Enquanto um
quadro se refaz, ele fica esmaecido.

## 2026-10-28: tela Fluxos, o caminho das conversas em gráficos

**Decisão.** Uma tela nova, Fluxos (`/fluxos`), para acompanhar como as conversas
andam sem ler nenhuma: quais fluxos são mais procurados, se a triagem por escrita
livre consegue direcionar a pessoa, até que resposta cada conversa chega, como
cada fluxo termina, quanto a conversa leva e onde o caminho dá problema (o Verde
falhou, a conversa expirou ou foi cortada, a triagem se contradisse, a mensagem
não chegou pelo WhatsApp). Pedido de 27 e 28/10: histórico em gráficos, nada do
que foi escrito na conversa.

**Como fica dentro da regra 4 (nunca listar conversa).** As consultas juntam os
eventos de cada conversa pelo `chatId` só para contá-la, e devolvem contagens
por fluxo, por número de respostas e por como terminou. O identificador nunca
sai da consulta, como já era em "origem do processo não atendida". Nenhum texto
é lido: o número de respostas sai do evento `resposta_recebida`, não do que a
pessoa escreveu.

**O que entrou no contrato com os logs da Maria.** `atendimento_expirado`,
`resposta_recebida`, `orquestrador_inconsistencia` e os eventos de envio pelo
WhatsApp. O retrato do código passou a ler também o evento montado num
dicionário (`whatsapp_envio_falhou`), que antes escapava.

**Levantamento de 28/10, nos logs reais (30 dias).** Produção só tem o fluxo
pessoa presa e não usa a triagem: 2.716 conversas, cerca de 470 paradas no meio.
O release tem os três fluxos (pessoa presa, violência doméstica e problemas com
plano de saúde, que o orquestrador ainda não oferece) e a triagem, que devolve à
Tykhe por tipo de caso. É no release que aparecem as falhas de entrega pelo
WhatsApp.

**O que custa.** Só com a tela aberta: 5 consultas de 7 dias, relidas a cada 5
minutos, e 2 de 30 dias, relidas a cada 15. Aberta o tempo todo nas 88 horas de
uso por mês, até cerca de US$ 1,30 de Logs Insights.

**O que não dá para mostrar ainda.** Em que pergunta a pessoa para: o registro
de cada pergunta não guarda qual foi feita, então a tela mostra o número da
resposta em que a conversa parou, e não o nome da pergunta. Com esse campo no
log da Maria, o gráfico "Onde as conversas param" passa a dizer a pergunta.

## 2026-10-28: a tela Agora na largura toda, e o Verde explicado

**Decisão.** A Agora deixa a coluna da direita: "Atendimentos por hora" e
"Requisições por hora" vão para baixo, cada um na largura inteira, com toda hora
no eixo (os atendimentos mostram também os que terminaram). "CPU e memória" fica
ao lado de "Os dois ambientes", e o Verde ocupa a largura toda, com o gráfico à
esquerda e o que cada cor quer dizer à direita: cada linha da tela tem quadros
de altura parecida, sem buraco.

**O Verde, em cinco resultados.** "Aceitou, recusou e outro" não dizia o que era
o outro. Pelo levantamento de 28/10 (30 dias em produção), o outro era quase
todo processo que não existe no Verde (400, 404 e 422, cerca de 480 consultas),
consulta que não voltou (cerca de 140) e erro do próprio Verde (500 e 503, cerca
de 70). O gráfico passa a mostrar: Respondeu, Credencial recusada, Não achou o
processo, Erro do Verde e Sem resposta, cada um com a explicação embaixo da
legenda (`RESULTADOS_DO_VERDE`, em `dados/modelo.py`). O cache subiu de versão,
porque a forma de `DiaDoVerde` mudou.

## 2026-10-28: Dash 4 e Plotly 7

**Decisão.** O painel passou do Dash 3.4 para o 4.4.1 e do Plotly 6.9 para o 7.1.0
(`pyproject.toml` agora pede `dash>=4,<5` e `plotly>=7,<8`). São versões maiores:
a trava de versão maior continua, para a próxima também passar por esta conferência.

**Conferido antes de ficar.** Lint, tipos e os 343 testes, sem aviso de função
obsoleta; o pente fino no navegador, clicando em todo gráfico e toda legenda das
oito telas, com dados reais; e o visual nos temas escuro e claro.

**O que o Dash 4 mudou, e foi ajustado (`assets/painel.css`).** Os seletores
(ambiente, período e origem) marcam a opção escolhida de outro jeito: a regra
nova olha o `aria-selected` da opção. A caixa de data e de mês virou outro
componente, que pinta com as variáveis `--Dash-*`: elas foram ligadas às cores
do painel e seguem os três temas. Os textos da busca da caixa, que vinham em
inglês, foram postos em português (`TEXTOS_DA_LISTA`, em `componentes/cabecalho.py`).

**O que ficou diferente.** Ao abrir a caixa de data, o foco vai para a lista, e
não para a busca: para procurar um dia digitando, clica-se primeiro no campo
"Procurar um dia". Escolher com o mouse ou com as setas segue igual.

## 2026-10-29: na tela financeira, o período escolhido muda os números

**O defeito.** Em 7 dias, 30 dias e Mês, os três números do topo e o gráfico por
dia ficavam presos ao último dia do período, que nesses casos é hoje: saíam
iguais aos de Hoje, e parecia que o filtro não funcionava.

**Decisão.** Com um período de vários dias, os três números passam a ser: o gasto
do período, comparado com o período anterior do mesmo tamanho (`gasto.anterior_ao_periodo`:
os mesmos tantos dias logo antes, ou, num mês, o mesmo trecho do mês anterior, ou
o mês anterior inteiro se o escolhido já fechou); a média por dia, com quanto era
o dia antes; e o dia mais caro do período. Os gráficos por dia e por mês destacam
o período inteiro. Hoje e Data específica seguem como eram: o dia, os 7 dias até
ele e o mês até ele.

## 2026-10-29: o que é cada gasto, e quanto dele é da Maria

**Pedido.** Saber o que é cada gasto da tela financeira e de onde ele vem.

**O que a tela passou a mostrar.** "De onde vem o gasto" diz, em cada linha, o
que o gasto é e quantos tokens teve no período; embaixo, como a AWS mede, quais
funções da Maria chamam a inteligência artificial e o preço usado. O quadro novo
"Quanto do gasto é da Maria" divide, dia a dia, o gasto medido na conta entre o
que as conversas da Maria registraram (`tokens_registrados`, nos dois ambientes)
e o que veio de fora delas com o mesmo modelo (`gasto.dividir`).

**O achado (levantamento de 29/10).** Nos dias comuns, a medição da conta bate
com o que as conversas da Maria registram: de centavos a US$ 0,42 por dia. Em
27 e 28/10, a conta mediu 5,9 e 3,6 milhões de tokens lidos, e a Maria registrou
cerca de 100 mil em cada dia: uns 97% dos US$ 12,72 desses dois dias vieram de
fora das conversas. Foram de 500 a 900 chamadas por hora, de uns 3 mil tokens
cada, em horário de expediente, com os logs da Maria em produção e no release no
ritmo de sempre: outro programa da conta usou o mesmo modelo (Claude Haiku 4.5).
A conta também usa Claude Sonnet 4.5 e Amazon Nova Lite, que o painel não conta.

**O que falta para saber quem foi.** O registro de chamadas do Bedrock não está
ligado, e a credencial do painel não lê o CloudTrail. Ficou como pendência na
tela ("Saber quem chama o modelo de fora da Maria", com o Ícaro). O jeito de
separar de vez é a Maria usar um perfil de inferência próprio.

## 2026-10-29: a Agora com mais números, quadros e o filtro de ambiente

**Pedido.** Revisar a Agora para trazer mais informação, dados, gráficos e filtros.

**Decisão.** O filtro de ambiente sai do quadro do Verde e vai para o cabeçalho:
vale para a tela toda (os números, o Verde, os fluxos, como terminaram, o que
aconteceu e os gráficos de hora em hora). Só "Os dois ambientes" fica sem filtro,
de propósito. Os números passam de cinco para oito: entram o tempo de resposta
(metade e nove em dez), os erros de servidor (com as recusas a pessoas e a robôs
na legenda) e as requisições da última hora inteira (a hora corrente acabou de
começar e diria zero). Quadros novos: "O que aconteceu hoje" (minutos fora do ar,
versões novas, erros, reinícios, credencial que passou a ser recusada ou voltou,
renovações, com a hora), ao lado de "Exige atenção"; "Fluxos hoje" (cada fluxo
por como as conversas terminaram, clicável) e "Como terminaram hoje" (clicável).
O gráfico de atendimentos por hora ganha a linha do mesmo dia da semana anterior.
O clique num fluxo filtra "Começaram" e "Terminaram"; num motivo, "Terminaram".

## 2026-10-29: atendimento humano no Relatório da Aplicação

**Pedido.** Acompanhar os motivos de ir para atendimento humano, quantos
atendimentos a IA resolveu e quantos foram para pessoa, e que problemas levaram
a isso.

**De onde sai.** Consulta nova `encaminhamentos_por_dia`: os encerramentos
(`atendimento_finalizado`) dos 30 dias do registro, contados por dia, fluxo,
`destino` e `motivoHandoff`, mais a triagem que manda direto para pessoa
(`orquestrador_finalizado_sem_fluxo` e `orquestrador_inconsistencia` com destino
de atendimento humano). Nenhuma conversa é listada: só contagens. O destino
`atendimento_humano` conta como pessoa; `sessao_expirada` e `saida_manual`, como
a pessoa saiu; o resto (`agendamento`, vazio) a Maria resolveu.

**Os tipos de problema.** Cada um dos motivos dos três fluxos
(`MotivoHandoff*` em `src/maria/fluxos/*/state.py`) entra num tipo, em
`TIPO_DO_MOTIVO`: falha técnica (Verde, cadastro, envio ao órgão, nenhum órgão
disponível, triagem que se contradisse), pessoa ou processo não identificados,
a Maria não entendeu, fora do que a Maria atende. Motivo novo aparece com o
código em "sem motivo, ou motivo novo" até entrar na lista; um teste garante que
todo motivo com nome tem tipo.

**Na tela.** Segue o período do cabeçalho e o ambiente do filtro de "Qual
atendimento custa mais": quatro números (terminaram, resolvidos pela Maria, foram
para pessoa, por falha técnica), o gráfico dos 30 dias por destino com o período
em destaque (o clique num dia escolhe a data, como nos outros gráficos da tela),
os motivos coloridos pelo tipo, a tabela dos tipos com o que cada um quer dizer
e os motivos mais comuns, e a tabela por fluxo. Período antes dos 30 dias do
registro diz até onde dá para ver.

**Levantamento de 29/10, em produção.** Em 30 dias, 2.194 atendimentos
terminaram: 307 (14%) resolvidos pela Maria e 1.887 (86%) foram para pessoa, 28
deles por falha técnica. No release, 37, com 8 das 28 idas para pessoa por falha
ao consultar o Verde.

## 2026-10-29: o caminho do atendimento na Agora

**Pedido.** Na Agora, ver a estrutura inteira do atendimento: o que funciona e o
que não funciona.

**Decisão.** Um quadro logo abaixo dos números, "O caminho do atendimento: o que
funciona e o que não", com uma linha por etapa, na ordem em que a mensagem passa:
a Maria recebe (containers, erros de servidor, minutos fora do ar), responde a
tempo, a triagem acha o assunto, o fluxo anda até o fim, a credencial do Verde
vale, o Verde responde, a inteligência artificial funciona, o cadastro e o envio
ao órgão não falham, a resposta chega pelo WhatsApp, a troca de versão não corta
conversa e as rotinas automáticas passam. Cada etapa diz o estado (funciona, com
problema, não funciona, sem uso), os números que levaram a ele e a tela onde ver
mais. Segue o filtro de ambiente e o de dia ou hora.

**Regras.** Leitura que falhou é "sem leitura", nunca "funciona": o quadro não
parece tranquilo quando falta uma fonte. Leitura vazia é "sem uso" (a triagem
por escrita livre não roda em produção; o envio direto pelo WhatsApp só no
release). Os limites de cada estado ficam em `pages/agora.py`, uma função por
etapa: tempo de resposta acima de 5 s para nove em dez é problema, acima de 10 s
não funciona; o Verde com recusas da credencial, ou mais de 10% de erro ou sem
resposta, é problema; mais de 30% dos atendimentos indo para pessoa por falha de
sistema não funciona.

## 2026-10-29: cada tela com o seu papel, sem repetir gráfico

**Pedido.** Revisar as telas para agregar sem repetir gráfico nem dado, com um
diferencial em cada uma, e mais informação sobre o gasto, cada parte da
arquitetura e os problemas das conversas e como se resolveram.

**O que se repetia.** "Como terminaram" estava em quatro telas; as requisições por
hora, na Agora e no Sistema; o dia hora a hora do Relatório do dia era o gráfico
de atendimentos por hora da Agora; o gasto de IA por dia estava no Sistema e no
Relatório da Aplicação; a demora do modelo, no Sistema e no Observatório da IA;
CPU e memória, na Agora e no Sistema.

**O papel de cada tela, e o que entrou.**
- **Agora**: o que está acontecendo, hoje (sem mudança nesta rodada).
- **Sistema, por que está assim?**: "Cada parte da arquitetura" (balanceador,
  containers, banco das conversas, modelo de conversa, funções de IA, busca por
  semelhança, Verde, credencial, WhatsApp, GitHub), cada uma com uso, demora,
  erros e custo do dia, no lugar do gasto de IA por dia. Na coluna da direita, o
  tempo de resposta dia a dia, em 14 dias (em que dia a Maria ficou lenta), e os
  erros de servidor hora a hora, no lugar das requisições, de CPU e memória e da
  demora do modelo.
- **Relatório do dia**: na coluna da direita, "O dia contra a semana anterior"
  (terminaram, a parte resolvida pela Maria, a parte que foi para pessoa e as
  falhas técnicas, contra a média dos 7 dias antes; com o dia em curso, as
  contagens dizem "dia em curso" em vez de alarme) e "Os problemas do dia", cada
  um com o que aconteceu com a conversa. Saem o dia hora a hora e como terminaram.
- **Fluxos**: "Quanto a Maria resolve sozinha, dia a dia", a parte resolvida sem
  pessoa em cada fluxo, em 30 dias. O histórico mostra quantas conversas; este, o
  resultado delas.
- **Credencial**: em cima da tabela de incidentes, como eles se resolveram: tempo
  médio até resolver, o mais longo, as recusas e os atendimentos afetados.
- **Relatório da Aplicação**: "Quanto custa cada atendimento": o gasto das
  conversas por atendimento, por atendimento resolvido pela Maria e, pela média,
  nos que foram para pessoa. Para dizer quanto a Maria economiza, falta o custo de
  um atendimento feito por uma pessoa da equipe.

**Levantamento de 29/10, em produção.** Hoje, até 12h, cada atendimento custou US$ 0,0011
de inteligência artificial; cada um resolvido pela Maria, US$ 0,0052. Em 30 dias, a
Maria resolveu sozinha 14% dos atendimentos de Pessoa presa (307 de 2.198). Os
cinco incidentes de credencial levaram, em média, 32 horas para ser resolvidos;
o mais longo, 3 dias, com 941 recusas no total.

## Pendências de registro

**Enquanto o repositório no GitHub não existe**, o código está
em dois lugares nesta máquina: `Documents/Maria/maria-painel` (esta cópia, que
vira o repositório) e `maria-langgraph-pp/relatorio-maria` (a pasta original,
que só sai depois que o código estiver no repositório novo).
