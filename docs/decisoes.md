# Decisões do Visor Maria

Cada decisão com a data, quem decidiu, o motivo e o que ela custa.

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
