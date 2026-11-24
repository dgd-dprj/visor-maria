"""Login do Visor: conta Google, pelo Amazon Cognito, só para os e-mails da lista.

Ligado com `PAINEL_LOGIN=cognito` (o padrão da imagem Docker). Rodando na máquina, sem
a variável, o painel abre sem login, como antes.

O caminho: `/login` mostra a tela com o botão "Entrar com o Google"; o botão (`/login/google`) manda ao
Cognito, que manda direto ao Google (`identity_provider=Google`);
o Google volta ao Cognito, e o Cognito a `/auth/callback` com um código. O painel troca o
código por um token (PKCE, sem segredo de cliente no painel), pergunta o e-mail ao Cognito
(`/oauth2/userInfo`) e só abre se o e-mail estiver em `/visor-maria/emails-com-acesso`, no
Parameter Store. A lista é lida de novo a cada minuto e conferida em toda requisição: tirar
um e-mail dela fecha o painel para aquela pessoa em até um minuto, sem esperar o login vencer.

Fechado por padrão: se a configuração ou a lista não puderem ser lidas, o painel responde 503
e não abre. Nada aqui grava o e-mail em log.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from html import escape
from pathlib import Path

from flask import Flask, Response, redirect, request, session
from werkzeug.wrappers import Response as Resposta

from painel.dados.cache import pasta_padrao

registro = logging.getLogger(__name__)

PARAMETRO_DA_CONFIGURACAO = "/visor-maria/login"
PARAMETRO_DOS_EMAILS = "/visor-maria/emails-com-acesso"
RELER_A_LISTA_A_CADA_S = 60
DURACAO_DO_LOGIN = timedelta(hours=8)
PRAZO_DAS_CHAMADAS_S = 10

ROTAS_LIVRES = frozenset({"/login", "/login/google", "/auth/callback", "/sair", "/saiu"})
# Só o que o painel usa: o e-mail. Precisam estar liberados no cliente do Cognito.
ESCOPOS = "openid email"
# Arquivos do próprio Dash e o CSS do painel: código público, sem dado nenhum.
PREFIXOS_LIVRES = ("/assets/", "/_dash-component-suites/", "/_favicon.ico")


class FalhaDoLogin(Exception):
    """A configuração, a lista ou o Cognito não responderam como esperado."""


@dataclass(frozen=True)
class Configuracao:
    dominio: str  # visor-maria-xxx.auth.sa-east-1.amazoncognito.com
    cliente: str  # id do cliente do Cognito (público, sem segredo)
    endereco: str  # https://xxxx.cloudfront.net, sem barra no fim

    @property
    def retorno(self) -> str:
        return f"{self.endereco}/auth/callback"


@dataclass(frozen=True)
class Fontes:
    """O que o login lê de fora. Os testes trocam por funções falsas."""

    ler_parametro: Callable[[str], str]
    trocar_codigo: Callable[[Configuracao, str, str], str]  # (configuração, código, verificador) -> access_token
    ler_usuario: Callable[[Configuracao, str], dict[str, object]]  # (configuração, access_token) -> userInfo


def modo_do_login() -> str:
    return os.environ.get("PAINEL_LOGIN", "desligado").strip().lower()


# ── Fontes reais: Parameter Store e os endpoints do Cognito ─────────────────


# Para testar na máquina, antes de os parâmetros existirem: o mesmo conteúdo em variáveis de ambiente.
# Na imagem Docker elas não existem, e o painel lê o Parameter Store.
VARIAVEL_DO_PARAMETRO = {PARAMETRO_DA_CONFIGURACAO: "PAINEL_LOGIN_CONFIGURACAO", PARAMETRO_DOS_EMAILS: "PAINEL_EMAILS_COM_ACESSO"}


def _ler_parametro_na_aws(nome: str) -> str:
    local = os.environ.get(VARIAVEL_DO_PARAMETRO.get(nome, ""), "")
    if local.strip():
        return local
    import boto3  # só no login ligado: a máquina sem login não precisa do SSM

    regiao = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "sa-east-1"
    try:
        valor = boto3.client("ssm", region_name=regiao).get_parameter(Name=nome)["Parameter"]["Value"]
    except Exception as erro:  # noqa: BLE001  (qualquer falha fecha o painel)
        raise FalhaDoLogin(f"não consegui ler o parâmetro {nome}: {type(erro).__name__}") from erro
    return str(valor)


def _json_de(pedido: urllib.request.Request) -> dict[str, object]:
    try:
        with urllib.request.urlopen(pedido, timeout=PRAZO_DAS_CHAMADAS_S) as resposta:  # noqa: S310  (só https do Cognito)
            dados = json.loads(resposta.read().decode("utf-8"))
    except Exception as erro:  # noqa: BLE001
        raise FalhaDoLogin(f"o Cognito não respondeu: {type(erro).__name__}") from erro
    if not isinstance(dados, dict):
        raise FalhaDoLogin("resposta do Cognito fora do formato")
    return dados


def _trocar_codigo_no_cognito(config: Configuracao, codigo: str, verificador: str) -> str:
    corpo = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": config.cliente,
            "code": codigo,
            "redirect_uri": config.retorno,
            "code_verifier": verificador,
        }
    ).encode("ascii")
    pedido = urllib.request.Request(
        f"https://{config.dominio}/oauth2/token",
        data=corpo,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    token = _json_de(pedido).get("access_token")
    if not isinstance(token, str) or not token:
        raise FalhaDoLogin("o Cognito não devolveu o token")
    return token


def _ler_usuario_no_cognito(config: Configuracao, token: str) -> dict[str, object]:
    pedido = urllib.request.Request(f"https://{config.dominio}/oauth2/userInfo", headers={"Authorization": f"Bearer {token}"})
    return _json_de(pedido)


FONTES_REAIS = Fontes(_ler_parametro_na_aws, _trocar_codigo_no_cognito, _ler_usuario_no_cognito)


# ── Configuração e lista, com a lista relida a cada minuto ──────────────────


class Leitor:
    def __init__(self, fontes: Fontes, relogio: Callable[[], float] | None = None) -> None:
        self.fontes = fontes
        self._relogio = relogio or (lambda: time.monotonic())
        self._trava = threading.Lock()
        self._config: Configuracao | None = None
        self._emails: frozenset[str] = frozenset()
        self._emails_lidos_em: float | None = None

    def configuracao(self) -> Configuracao:
        with self._trava:
            if self._config is None:
                bruto = self.fontes.ler_parametro(PARAMETRO_DA_CONFIGURACAO)
                try:
                    dados = json.loads(bruto)
                    config = Configuracao(dominio=str(dados["dominio"]), cliente=str(dados["cliente"]), endereco=str(dados["endereco"]).rstrip("/"))
                except (ValueError, KeyError, TypeError) as erro:
                    raise FalhaDoLogin(f"{PARAMETRO_DA_CONFIGURACAO} fora do formato") from erro
                # https sempre; http só no teste na própria máquina (o Cognito também só aceita http em localhost).
                endereco_ok = config.endereco.startswith(("https://", "http://localhost:", "http://127.0.0.1:"))
                if not (config.dominio and config.cliente and endereco_ok):
                    raise FalhaDoLogin(f"{PARAMETRO_DA_CONFIGURACAO} incompleto")
                self._config = config
            return self._config

    def emails_com_acesso(self) -> frozenset[str]:
        with self._trava:
            agora = self._relogio()
            if self._emails_lidos_em is None or agora - self._emails_lidos_em >= RELER_A_LISTA_A_CADA_S:
                bruto = self.fontes.ler_parametro(PARAMETRO_DOS_EMAILS)
                self._emails = frozenset(e.strip().lower() for e in bruto.split(",") if e.strip())
                self._emails_lidos_em = agora
            return self._emails


# ── Chave da sessão ─────────────────────────────────────────────────────────


def chave_da_sessao(pasta: Path | None = None) -> bytes:
    """A mesma para os workers do gunicorn: vem do ambiente ou de um arquivo criado por quem chegar primeiro.

    O arquivo fica no cache do contêiner, que some a cada reinício (a instância desliga à noite): todo mundo
    entra de novo no dia seguinte, o que é de propósito.
    """
    do_ambiente = os.environ.get("PAINEL_CHAVE_DA_SESSAO")
    if do_ambiente:
        return do_ambiente.encode("utf-8")
    pasta = pasta or pasta_padrao()
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / "chave-da-sessao"
    try:
        descritor = os.open(arquivo, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        for _ in range(50):  # o outro worker pode estar no meio da escrita
            conteudo = arquivo.read_bytes()
            if len(conteudo) >= 32:
                return conteudo
            time.sleep(0.02)
        raise FalhaDoLogin("a chave da sessão ficou vazia") from None
    with os.fdopen(descritor, "wb") as saida:
        saida.write(secrets.token_hex(32).encode("ascii"))
    return arquivo.read_bytes()


# ── As páginas de aviso (fora do Dash, simples de propósito) ────────────────


# Identidade da Defensoria (o verde, o dourado, a logo oficial e as fontes do portal de 2025: League Spartan nos
# títulos, DM Sans no texto), enquanto o visual novo do Visor não fica pronto: só esta moldura muda quando ele chegar.
LOGO_DA_DEFENSORIA = "https://sistemas.rj.def.br/publico/sarova.ashx/Portal/sarova/imagem-dpge/public/imagens/brand-20240202-101353.png"
# O rosto da Maria, na moldura redonda da parte verde. Fica em assets/ (servido sem login, como o CSS): recortado e
# reduzido da arte original (18 MB) para 960x960 em WebP, com os ombros encostados embaixo do círculo.
IMAGEM_DA_MARIA = "/assets/maria-rosto.webp"

_ESTILO = """
:root{--verde:#114e2f;--verde-claro:#1d6a43;--verde-escuro:#0b3520;--dourado:#9b8748;--palha:#ccc692;--fundo:#f4f5f0;--texto:#1d2a24;--apagado:#55605a;--borda:#e3e6de}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:var(--fundo);color:var(--texto);font-family:"DM Sans","Segoe UI",system-ui,sans-serif;line-height:1.5}
.tela{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);min-height:100vh}
.marca{position:relative;overflow:hidden;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:44px;padding:48px;background:radial-gradient(80% 65% at 50% 42%,var(--verde-claro) 0%,var(--verde) 55%,var(--verde-escuro) 100%);border-right:4px solid var(--dourado)}
.retrato{position:relative;width:min(56%,340px);aspect-ratio:1}
.retrato::before,.retrato::after{content:"";position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);aspect-ratio:1;border-radius:50%;pointer-events:none;animation:pulsar 6s ease-in-out infinite}
.retrato::before{width:124%;border:1px solid rgba(204,198,146,.5);background:radial-gradient(circle,rgba(204,198,146,.20) 0%,rgba(204,198,146,0) 70%)}
.retrato::after{width:152%;border:1px solid rgba(204,198,146,.18);animation-delay:-3s}
.boas-vindas{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;gap:12px;max-width:440px;margin-top:52px;text-align:center;color:#fff;animation:entrar .9s cubic-bezier(.2,.7,.2,1) .3s both}
.boas-vindas-titulo{position:relative;z-index:1;margin:0 0 56px;font-family:"League Spartan","DM Sans",sans-serif;font-size:38px;font-weight:700;line-height:1.1;letter-spacing:.06em;text-transform:uppercase;color:var(--palha);text-align:center;text-shadow:0 2px 12px rgba(0,0,0,.35);animation:entrar .9s cubic-bezier(.2,.7,.2,1) .1s both}
.boas-vindas-texto{margin:0;font-size:16px;line-height:1.55;color:#eef2ea;text-wrap:pretty;text-shadow:0 1px 2px rgba(0,0,0,.55),0 0 14px rgba(11,53,32,.9)}
.boas-vindas-texto strong{color:var(--palha);font-weight:600}
.moldura{position:relative;z-index:1;width:100%;aspect-ratio:1;border-radius:50%;overflow:hidden;border:6px solid var(--dourado);background:radial-gradient(circle at 50% 38%,#fbf8ec 0%,#ece6cb 100%);box-shadow:0 0 0 12px rgba(204,198,146,.14),0 34px 60px -24px rgba(0,0,0,.5);animation:entrar .9s cubic-bezier(.2,.7,.2,1) both,flutuar 6s ease-in-out .9s infinite}
.maria{display:block;width:100%;height:100%;object-fit:cover}
@keyframes entrar{from{opacity:0;transform:translateY(18px) scale(.94)}to{opacity:1;transform:none}}
@keyframes flutuar{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
@keyframes pulsar{0%,100%{transform:translate(-50%,-50%) scale(1);opacity:.6}50%{transform:translate(-50%,-50%) scale(1.05);opacity:1}}
.area{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:48px 24px;gap:20px;background:radial-gradient(70% 60% at 85% 10%,rgba(155,135,72,.10),transparent 70%),var(--fundo)}
.cartao{width:100%;max-width:440px;background:#fff;border:1px solid var(--borda);border-radius:18px;padding:40px 36px;display:flex;flex-direction:column;gap:14px;box-shadow:0 1px 2px rgba(16,40,28,.05),0 30px 60px -30px rgba(16,40,28,.30);animation:entrar .8s cubic-bezier(.2,.7,.2,1) .15s both}
.topo{padding-bottom:18px;border-bottom:1px solid var(--borda)}
.logo{display:block;width:210px;max-width:100%;height:auto}
h1{margin:6px 0 0;font-family:"League Spartan","DM Sans",sans-serif;font-size:28px;font-weight:700;line-height:1.1;letter-spacing:.03em;text-transform:uppercase;color:var(--verde)}
.cartao p{margin:0;color:var(--apagado);font-size:15px}
.cartao p strong{color:var(--texto)}
.acoes{display:flex;flex-direction:column;gap:12px;margin-top:14px}
.botao{display:flex;align-items:center;justify-content:center;gap:12px;min-height:52px;padding:12px 20px;border-radius:12px;background:var(--verde);color:#fff;font-weight:600;font-size:16px;text-decoration:none;border:1px solid var(--verde);transition:background .15s,box-shadow .15s,transform .15s}
.botao:hover{background:var(--verde-escuro);box-shadow:0 8px 20px -10px rgba(16,40,28,.45);transform:translateY(-1px)}
.botao:focus-visible,.secundaria:focus-visible{outline:3px solid var(--dourado);outline-offset:3px}
.botao-google{background:#fff;color:var(--texto);border-color:#c9cec5}
.botao-google:hover{background:#fafbf8;border-color:var(--verde)}
.secundaria{align-self:center;color:var(--verde);font-size:14px}
.cartao .nota{margin:4px 0 0;font-size:13px;color:var(--apagado);text-align:center}
@media (prefers-reduced-motion:reduce){.botao{transition:none}.botao:hover{transform:none}.moldura,.cartao,.boas-vindas,.boas-vindas-titulo,.retrato::before,.retrato::after{animation:none}}
@media (max-width:760px){.tela{grid-template-columns:1fr;grid-template-rows:auto 1fr}.marca{gap:18px;padding:28px 20px 30px;border-right:0;border-bottom:4px solid var(--dourado)}.retrato{width:140px}.moldura{border-width:4px;box-shadow:0 0 0 8px rgba(204,198,146,.14),0 20px 40px -20px rgba(0,0,0,.5)}.topo{padding-bottom:16px}.logo{width:180px}.boas-vindas{gap:8px;margin-top:22px}.boas-vindas-titulo{font-size:24px;margin-bottom:22px}.boas-vindas-texto{font-size:14.5px}.area{justify-content:flex-start;padding:28px 16px}.cartao{padding:28px 22px;border-radius:16px}h1{font-size:24px}}
"""

_G_DO_GOOGLE = (
    '<svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">'
    '<path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>'
    '<path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>'
    '<path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>'
    '<path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>'
    "</svg>"
)


def _pagina(
    titulo: str,
    texto: str,
    acao: tuple[str, str] | None,
    status: int,
    *,
    google: bool = False,
    secundaria: tuple[str, str] | None = None,
    nota: str = "Acesso só para a equipe da Maria.",
) -> Response:
    """As telas fora do Dash: entrar, sem acesso, saiu, expirou e indisponível. `texto` já vem escapado."""
    botao = ""
    if acao:
        classe = "botao botao-google" if google else "botao"
        botao = f'<a class="{classe}" href="{escape(acao[0])}">{_G_DO_GOOGLE if google else ""}{escape(acao[1])}</a>'
    link = f'<a class="secundaria" href="{escape(secundaria[0])}">{escape(secundaria[1])}</a>' if secundaria else ""
    corpo = (
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(titulo)} · Visor Maria</title>"
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=League+Spartan:wght@600;700&display=swap">'
        f"<style>{_ESTILO}</style></head><body>"
        '<main class="tela">'
        '<section class="marca">'
        '<p class="boas-vindas-titulo">Boas-vindas</p>'
        '<div class="retrato">'
        f'<div class="moldura"><img class="maria" src="{IMAGEM_DA_MARIA}" alt="Maria, a assistente da Defensoria" width="960" height="960"></div>'
        "</div>"
        '<div class="boas-vindas">'
        '<p class="boas-vindas-texto"><strong>O painel onde a equipe acompanha a Maria:</strong> como estão os atendimentos e os fluxos, '
        "quanto ela gasta e se tudo está funcionando.</p>"
        "</div>"
        "</section>"
        '<section class="area"><div class="cartao">'
        f'<div class="topo"><img class="logo" src="{LOGO_DA_DEFENSORIA}" alt="Defensoria Pública do Estado do Rio de Janeiro" width="220" height="47"></div>'
        f"<h1>{escape(titulo)}</h1><p>{texto}</p>"
        f'<div class="acoes">{botao}{link}</div>'
        f'<p class="nota">{escape(nota)}</p></div></section>'
        "</main></body></html>"
    )
    return Response(corpo, status=status, mimetype="text/html")


def _indisponivel() -> Response:
    return _pagina("Login indisponível", "O login do Visor não está respondendo agora. Tente de novo em alguns minutos.", ("/login", "Tentar de novo"), 503)


def _sem_acesso(email: str) -> Response:
    return _pagina(
        "Sem acesso",
        f"A conta <strong>{escape(email)}</strong> não está na lista de quem pode abrir o Visor. Peça à equipe da Maria para incluir o seu e-mail.",
        None,
        403,
        secundaria=("/sair", "Sair e entrar com outra conta"),
    )


def _caminho_seguro(caminho: str | None) -> str:
    # Só caminhos do próprio painel: nada de "//outro-site" nem endereço completo.
    if caminho and caminho.startswith("/") and not caminho.startswith("//") and "\\" not in caminho:
        return caminho
    return "/"


def _desafio(verificador: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verificador.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


# ── Instalação no servidor Flask do Dash ────────────────────────────────────


def instalar(servidor: Flask, modo: str | None = None, fontes: Fontes | None = None, pasta_da_chave: Path | None = None) -> bool:
    """Liga o login no servidor, se o modo pedir. Devolve se ligou."""
    modo = modo if modo is not None else modo_do_login()
    if modo in ("", "desligado"):
        return False
    if modo != "cognito":
        raise ValueError(f"PAINEL_LOGIN={modo!r}: use 'cognito' ou 'desligado'")

    leitor = Leitor(fontes or FONTES_REAIS)
    servidor.secret_key = chave_da_sessao(pasta_da_chave)
    servidor.config.update(
        SESSION_COOKIE_NAME="visor_sessao",
        SESSION_COOKIE_SECURE=True,  # o navegador fala HTTPS com o CloudFront
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",  # a volta do Cognito é um GET de outro site
        PERMANENT_SESSION_LIFETIME=DURACAO_DO_LOGIN,
    )

    @servidor.before_request
    def exigir_login() -> Resposta | None:
        caminho = request.path
        if caminho in ROTAS_LIVRES or caminho.startswith(PREFIXOS_LIVRES):
            return None
        email = session.get("email")
        if not isinstance(email, str):
            if request.method == "GET" and not caminho.startswith("/_dash"):
                volta = caminho + (f"?{request.query_string.decode('utf-8', 'replace')}" if request.query_string else "")
                return redirect("/login?" + urllib.parse.urlencode({"volta": volta}))
            return Response("Faça o login de novo: recarregue a página.", status=401, mimetype="text/plain")
        try:
            lista = leitor.emails_com_acesso()
        except FalhaDoLogin as erro:
            registro.warning("Login: %s", erro)
            return _indisponivel()
        if email not in lista:
            session.clear()
            return _sem_acesso(email)
        return None

    @servidor.route("/login")
    def tela_de_login() -> Resposta:
        volta = _caminho_seguro(request.args.get("volta"))
        return _pagina(
            "Entrar no Visor",
            "Use a sua conta Google. Só entra quem está na lista de acesso da equipe da Maria.",
            ("/login/google?" + urllib.parse.urlencode({"volta": volta}), "Entrar com o Google"),
            200,
            google=True,
        )

    @servidor.route("/login/google")
    def entrar() -> Resposta:
        # O botão de login: abre a autorização no provedor OIDC do grupo de usuários (Cognito), que segue para o Google.
        try:
            config = leitor.configuracao()
        except FalhaDoLogin as erro:
            registro.warning("Login: %s", erro)
            return _indisponivel()
        estado = secrets.token_urlsafe(32)
        verificador = secrets.token_urlsafe(64)
        session["pendente"] = {"estado": estado, "verificador": verificador, "volta": _caminho_seguro(request.args.get("volta"))}
        parametros = {
            "response_type": "code",
            "client_id": config.cliente,
            "redirect_uri": config.retorno,
            "scope": ESCOPOS,
            "state": estado,
            "code_challenge": _desafio(verificador),
            "code_challenge_method": "S256",
            # Vai direto ao Google, sem a tela do Cognito. PAINEL_LOGIN_PROVEDOR=COGNITO só para testar com e-mail e senha.
            "identity_provider": os.environ.get("PAINEL_LOGIN_PROVEDOR") or "Google",
        }
        return redirect(f"https://{config.dominio}/oauth2/authorize?" + urllib.parse.urlencode(parametros))

    @servidor.route("/auth/callback")
    def voltar_do_google() -> Resposta:
        pendente = session.pop("pendente", None)
        estado = request.args.get("state", "")
        if not isinstance(pendente, dict) or not hmac.compare_digest(str(pendente.get("estado", "")), estado):
            return _pagina("O login expirou", "Comece de novo.", ("/login/google", "Entrar com o Google"), 400, google=True)
        codigo = request.args.get("code")
        if request.args.get("error") or not codigo:
            return _pagina("Login não concluído", "O Google não confirmou a conta.", ("/login", "Tentar de novo"), 400)
        try:
            config = leitor.configuracao()
            token = leitor.fontes.trocar_codigo(config, codigo, str(pendente["verificador"]))
            usuario = leitor.fontes.ler_usuario(config, token)
            lista = leitor.emails_com_acesso()
        except FalhaDoLogin as erro:
            registro.warning("Login: %s", erro)
            return _indisponivel()
        email = str(usuario.get("email") or "").strip().lower()
        verificado = usuario.get("email_verified") in (True, "true", "True")
        if not email or not verificado:
            return _pagina("Login não concluído", "A conta do Google não tem um e-mail confirmado.", ("/sair", "Entrar com outra conta"), 403)
        if email not in lista:
            return _sem_acesso(email)
        session.clear()
        session.permanent = True
        session["email"] = email
        return redirect(_caminho_seguro(str(pendente.get("volta", "/"))))

    @servidor.route("/sair")
    def sair() -> Resposta:
        session.clear()
        try:
            config = leitor.configuracao()
        except FalhaDoLogin:
            return redirect("/saiu")
        # Sai também do Cognito; senão o próximo /login entra direto, sem perguntar a conta.
        return redirect(f"https://{config.dominio}/logout?" + urllib.parse.urlencode({"client_id": config.cliente, "logout_uri": f"{config.endereco}/saiu"}))

    @servidor.route("/saiu")
    def saiu() -> Response:
        return _pagina("Você saiu do Visor", "Para voltar, entre de novo com a sua conta Google.", ("/login/google", "Entrar com o Google"), 200, google=True)

    registro.info("Login do Visor ligado (Cognito com Google).")
    return True


def login_ligado() -> bool:
    return modo_do_login() == "cognito"
