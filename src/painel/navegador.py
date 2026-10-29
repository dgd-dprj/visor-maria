"""O código que roda no navegador: menu móvel, tema e relógio da barra lateral.

Fica em Python, como texto passado ao `clientside_callback`, e não num arquivo
.js em `assets/`: o painel nasceu dentro do maria-langgraph-pp, cujo teste
`test_sem_typescript` não aceita JavaScript no repositório, e um projeto Python
sem arquivo .js é mais simples de manter.
"""

from __future__ import annotations

from painel.componentes.cabecalho import TEMAS

_LISTA_DE_TEMAS = "[" + ", ".join(f'"{valor}"' for valor, _, _ in TEMAS) + "]"

# Abre pelo botão; fecha pelo botão, pelo fundo escuro ou ao trocar de tela.
ALTERNAR_MENU = """
function (_botao, _fundo, _caminho, classeAtual) {
  var origem = window.dash_clientside.callback_context.triggered_id;
  var aberto = (classeAtual || "").indexOf("aberto") !== -1;
  var abrir = origem === "menu-botao" ? !aberto : false;
  return [abrir ? "menu aberto" : "menu", abrir ? "menu-fundo aberto" : "menu-fundo", abrir ? "true" : "false"];
}
"""

# O dcc.Link não marca a tela aberta; a classe "atual" faz esse papel.
MARCAR_TELA_ATUAL = """
function (caminho, ids) {
  return ids.map(function (id) {
    return id.caminho === caminho ? "menu-item atual" : "menu-item";
  });
}
"""

# Devolve o tema e, para cada botão, a classe e o aria-pressed. Quando o
# cabeçalho sobe, o Dash dá um botão como "disparado" mesmo sem clique: só vale
# como escolha o botão que tem clique de verdade.
ESCOLHER_TEMA = (
    """
function () {
  var temas = LISTA_DE_TEMAS;
  var cliques = Array.prototype.slice.call(arguments, 0, temas.length);
  var guardado = arguments[temas.length];
  var origem = window.dash_clientside.callback_context.triggered_id;
  var clicado = typeof origem === "string" && origem.indexOf("tema-") === 0 ? origem.slice(5) : null;
  var tema = clicado && cliques[temas.indexOf(clicado)] > 0 ? clicado : guardado;
  if (temas.indexOf(tema) === -1) tema = document.documentElement.dataset.tema || "escuro";
  document.documentElement.dataset.tema = tema;
  var classes = temas.map(function (t) { return t === tema ? "tema-opcao ativo" : "tema-opcao"; });
  var pressionados = temas.map(function (t) { return t === tema ? "true" : "false"; });
  return [tema].concat(classes, pressionados);
}
"""
).replace("LISTA_DE_TEMAS", _LISTA_DE_TEMAS)

# "26/10, 11:58", no fuso de Brasília.
MOSTRAR_RELOGIO = """
function () {
  var partes = new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  }).formatToParts(new Date());
  var p = {};
  partes.forEach(function (x) { p[x.type] = x.value; });
  return p.day + "/" + p.month + ", " + p.hour + ":" + p.minute;
}
"""

# Roda antes da primeira pintura: aplica o tema guardado (o mesmo localStorage
# que o dcc.Store "tema" grava, para a tela não piscar no tema errado; o padrão
# é o escuro, como no rascunho) e liga o Esc para fechar o menu móvel.
NO_CABECALHO_DA_PAGINA = (
    """
(function () {
  var tema = null;
  try { tema = JSON.parse(window.localStorage.getItem("tema")); } catch (e) {}
  if (LISTA_DE_TEMAS.indexOf(tema) === -1) { tema = "escuro"; }
  document.documentElement.dataset.tema = tema;
  document.addEventListener("keydown", function (evento) {
    if (evento.key !== "Escape") return;
    var fundo = document.getElementById("menu-fundo");
    if (fundo && fundo.classList.contains("aberto")) fundo.click();
  });
})();
"""
).replace("LISTA_DE_TEMAS", _LISTA_DE_TEMAS)
