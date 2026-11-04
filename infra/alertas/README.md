# Alertas da Maria (visor-maria#2)

Os avisos por e-mail que o Grafana mandava até 29/10, agora no Visor. Quem avalia é
o CloudWatch, o tempo todo; o Visor só consulta com a tela aberta, e por isso não
pode ser ele a avisar.

| Alarme | Métrica | Dispara quando | Sem dado |
|---|---|---|---|
| `visor-maria-<ambiente>-sem-host-saudavel` | `HealthyHostCount` (média) | menor que 1 por 2 min | **dispara** |
| `visor-maria-<ambiente>-erros-5xx` | `HTTPCode_Target_5XX_Count` (soma em 5 min) | maior que 10 em dois períodos seguidos | não dispara |
| `visor-maria-<ambiente>-cpu-alta` | `AWS/ECS` `CPUUtilization` (média) | maior que 80% por 5 min | não dispara |
| `visor-maria-<ambiente>-latencia-p99` | `TargetResponseTime` (p99) | maior que 3 s por 15 min | não dispara |
| `visor-maria-producao-verde-recusou` | respostas 401 e 403 em `verde_chamada` | 3 ou mais em 10 min, ou seja, uma consulta (a Maria tenta cada consulta 3 vezes) | não dispara |

Os quatro primeiros existem em `producao` e `release` (8 alarmes, como no Grafana). O do
Verde só em produção (`ambientes_do_verde`), pelo custo: o release não tem uso. São 9
alarmes e 1 métrica própria, cerca de US$ 1,20 por mês.
O aviso chega quando o alarme dispara e quando volta ao normal. A mensagem é a padrão
da AWS: ambiente, métrica e valor, sem dado de pessoa atendida.

## Como aplicar

**Quem aplica é o Ícaro**, para ele ter controle do que muda na conta da Maria (decisão
da Nicole, 2026-11-03). A credencial precisa criar alarmes, tópico SNS e o filtro de
métrica no grupo de logs de produção da Maria; a do Visor só lê.

Os e-mails ficam num arquivo local, fora do git, porque o repositório é público. Hoje
recebem o Ícaro, a Marcelle e a Nicole; o arquivo vai ao Ícaro junto com o pedido:

```sh
cd infra/alertas
cat > alertas.auto.tfvars <<'EOF'
destinatarios      = ["equipe@exemplo.org"]
alerta_do_verde    = true
ambientes_do_verde = ["producao"]
EOF
terraform init
terraform plan    # conferir: só recursos visor-maria-*; na Maria, só o filtro no grupo de logs de produção
terraform apply
```

Cada destinatário recebe um e-mail da AWS para confirmar a inscrição. Sem confirmar, não
recebe nada.

## Como testar

Sem derrubar nada, force o estado de um alarme do release e veja o e-mail chegar:

```sh
aws cloudwatch set-alarm-state --alarm-name visor-maria-release-cpu-alta \
  --state-value ALARM --state-reason "teste do aviso (visor-maria#2)"
```

O alarme volta sozinho ao estado real na avaliação seguinte. Anote o resultado na
visor-maria#2.

## O que ficou de fora

- **A latência p99 vai disparar muito.** Em 29/10, o p99 de produção ficou acima de 3 s
  em 16 das 24 horas (`docs/decisoes.md`): a Maria espera o Verde por até 30 s. O limite
  de 3 s foi mantido por decisão da Nicole (2026-11-03), como no Grafana.
- **O alerta do Verde encosta num recurso da Maria.** O filtro de métrica fica no grupo
  de logs dela, uma exceção à regra 3 do isolamento, aceita pela Nicole em 2026-11-03.
  Para gastar pouco: só produção, uma métrica sem dimensões, e o filtro só grava quando
  há recusa.
- **A falha da conferência diária do token** (o workflow `verificar-token-verde.yml` da
  Maria) roda no GitHub, fora da AWS, e não vira alarme por aqui.
