"""O login com Google pelo Cognito (login.py), com o Cognito e o Parameter Store falsos."""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from painel import login
from painel.login import PARAMETRO_DA_CONFIGURACAO, PARAMETRO_DOS_EMAILS, Configuracao, FalhaDoLogin, Fontes

CONFIG = {"dominio": "visor-maria-teste.auth.sa-east-1.amazoncognito.com", "cliente": "cliente123", "endereco": "https://exemplo.cloudfront.net"}


class Falsos:
    """O Parameter Store e o Cognito, controlados pelo teste."""

    def __init__(self) -> None:
        self.parametros: dict[str, str] = {PARAMETRO_DA_CONFIGURACAO: json.dumps(CONFIG), PARAMETRO_DOS_EMAILS: "pessoa.um@gmail.com, Pessoa.Dois@gmail.com"}
        self.usuario: dict[str, object] = {"email": "pessoa.um@gmail.com", "email_verified": "true"}
        self.trocas: list[tuple[str, str]] = []
        self.falhar_parametros = False

    def ler_parametro(self, nome: str) -> str:
        if self.falhar_parametros:
            raise FalhaDoLogin("sem acesso ao SSM")
        return self.parametros[nome]

    def trocar_codigo(self, config: Configuracao, codigo: str, verificador: str) -> str:
        self.trocas.append((codigo, verificador))
        return "token-de-acesso"

    def ler_usuario(self, config: Configuracao, token: str) -> dict[str, object]:
        assert token == "token-de-acesso"
        return self.usuario

    def fontes(self) -> Fontes:
        return Fontes(self.ler_parametro, self.trocar_codigo, self.ler_usuario)


@pytest.fixture
def falsos() -> Falsos:
    return Falsos()


@pytest.fixture
def cliente(falsos: Falsos, tmp_path: Path) -> FlaskClient:
    app = Flask(__name__)

    @app.route("/")
    def inicio() -> str:
        return "tela"

    @app.route("/infra")
    def infra() -> str:
        return "infra"

    @app.route("/_dash-update-component", methods=["POST"])
    def callback() -> str:
        return "{}"

    @app.route("/assets/painel.css")
    def css() -> str:
        return "body{}"

    assert login.instalar(app, modo="cognito", fontes=falsos.fontes(), pasta_da_chave=tmp_path)
    return app.test_client()


def _entrar(cliente: FlaskClient, volta: str = "/") -> TestResponse:
    """Faz o caminho /login -> Cognito -> /auth/callback e devolve o Location final."""
    resposta = cliente.get("/login/google?" + urllib.parse.urlencode({"volta": volta}))
    assert resposta.status_code == 302
    destino = urllib.parse.urlparse(resposta.headers["Location"])
    estado = urllib.parse.parse_qs(destino.query)["state"][0]
    return cliente.get("/auth/callback?" + urllib.parse.urlencode({"code": "codigo-1", "state": estado}))


def test_desligado_nao_muda_nada(tmp_path: Path) -> None:
    app = Flask(__name__)

    @app.route("/")
    def inicio() -> str:
        return "tela"

    assert login.instalar(app, modo="desligado", pasta_da_chave=tmp_path) is False
    assert app.test_client().get("/").status_code == 200


def test_modo_desconhecido_falha_na_subida(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        login.instalar(Flask(__name__), modo="google", pasta_da_chave=tmp_path)


def test_sem_login_a_tela_manda_para_o_login(cliente: FlaskClient) -> None:
    resposta = cliente.get("/infra?dia=hoje")
    assert resposta.status_code == 302
    assert resposta.headers["Location"].startswith("/login?")
    assert urllib.parse.parse_qs(urllib.parse.urlparse(resposta.headers["Location"]).query)["volta"] == ["/infra?dia=hoje"]


def test_sem_login_o_callback_do_dash_recebe_401(cliente: FlaskClient) -> None:
    assert cliente.post("/_dash-update-component").status_code == 401


def test_css_e_arquivos_do_dash_abrem_sem_login(cliente: FlaskClient) -> None:
    assert cliente.get("/assets/painel.css").status_code == 200


def test_login_vai_direto_ao_google_com_pkce(cliente: FlaskClient) -> None:
    resposta = cliente.get("/login/google")
    destino = urllib.parse.urlparse(resposta.headers["Location"])
    parametros = urllib.parse.parse_qs(destino.query)
    assert destino.netloc == CONFIG["dominio"] and destino.path == "/oauth2/authorize"
    assert parametros["identity_provider"] == ["Google"]
    assert parametros["client_id"] == ["cliente123"]
    assert parametros["redirect_uri"] == ["https://exemplo.cloudfront.net/auth/callback"]
    assert parametros["code_challenge_method"] == ["S256"]
    assert parametros["scope"] == ["openid email"]
    assert len(parametros["state"][0]) >= 32


def test_email_da_lista_entra_e_volta_para_a_tela_pedida(cliente: FlaskClient, falsos: Falsos) -> None:
    resposta = _entrar(cliente, volta="/infra")
    assert resposta.status_code == 302 and resposta.headers["Location"] == "/infra"
    assert falsos.trocas and falsos.trocas[0][0] == "codigo-1"
    assert cliente.get("/infra").status_code == 200
    assert cliente.post("/_dash-update-component").status_code == 200


def test_email_compara_sem_maiusculas(cliente: FlaskClient, falsos: Falsos) -> None:
    falsos.usuario = {"email": "PESSOA.DOIS@gmail.com", "email_verified": True}
    assert _entrar(cliente).status_code == 302
    assert cliente.get("/").status_code == 200


def test_email_fora_da_lista_nao_entra(cliente: FlaskClient, falsos: Falsos) -> None:
    falsos.usuario = {"email": "outra.pessoa@gmail.com", "email_verified": "true"}
    resposta = _entrar(cliente)
    assert resposta.status_code == 403
    assert "não está na lista" in resposta.get_data(as_text=True)
    assert cliente.get("/").status_code == 302


def test_email_nao_confirmado_nao_entra(cliente: FlaskClient, falsos: Falsos) -> None:
    falsos.usuario = {"email": "pessoa.um@gmail.com", "email_verified": "false"}
    assert _entrar(cliente).status_code == 403


def test_estado_errado_nao_entra(cliente: FlaskClient) -> None:
    cliente.get("/login/google")
    resposta = cliente.get("/auth/callback?code=codigo-1&state=outro")
    assert resposta.status_code == 400
    assert cliente.get("/").status_code == 302


def test_volta_para_outro_site_vira_o_inicio(cliente: FlaskClient) -> None:
    assert _entrar(cliente, volta="//site-malicioso.example/x").headers["Location"] == "/"


def test_tirar_da_lista_fecha_em_ate_um_minuto(falsos: Falsos, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agora = [1000.0]
    monkeypatch.setattr("painel.login.time.monotonic", lambda: agora[0])
    app = Flask(__name__)

    @app.route("/")
    def inicio() -> str:
        return "tela"

    login.instalar(app, modo="cognito", fontes=falsos.fontes(), pasta_da_chave=tmp_path)
    cliente = app.test_client()
    assert _entrar(cliente).status_code == 302
    assert cliente.get("/").status_code == 200
    falsos.parametros[PARAMETRO_DOS_EMAILS] = "pessoa.dois@gmail.com"
    assert cliente.get("/").status_code == 200  # ainda na lista lida há menos de um minuto
    agora[0] += login.RELER_A_LISTA_A_CADA_S
    assert cliente.get("/").status_code == 403


def test_sem_configuracao_o_painel_fecha(cliente: FlaskClient, falsos: Falsos) -> None:
    falsos.falhar_parametros = True
    assert cliente.get("/login").status_code == 200  # a tela abre; o botão é que fecha
    assert cliente.get("/login/google").status_code == 503
    assert cliente.get("/").status_code == 302  # sem sessão, nunca abre


def test_sair_limpa_a_sessao_e_sai_do_cognito(cliente: FlaskClient) -> None:
    _entrar(cliente)
    resposta = cliente.get("/sair")
    destino = urllib.parse.urlparse(resposta.headers["Location"])
    assert destino.netloc == CONFIG["dominio"] and destino.path == "/logout"
    assert urllib.parse.parse_qs(destino.query)["logout_uri"] == ["https://exemplo.cloudfront.net/saiu"]
    assert cliente.get("/").status_code == 302


def test_a_chave_da_sessao_e_a_mesma_para_os_dois_workers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAINEL_CHAVE_DA_SESSAO", raising=False)
    primeira = login.chave_da_sessao(tmp_path)
    assert len(primeira) >= 32
    assert login.chave_da_sessao(tmp_path) == primeira


def test_a_tela_de_login_tem_o_botao_do_google_e_guarda_a_volta(cliente: FlaskClient) -> None:
    resposta = cliente.get("/login?volta=/infra")
    html = resposta.get_data(as_text=True)
    assert resposta.status_code == 200
    assert 'href="/login/google?volta=%2Finfra"' in html
    assert "Entrar com o Google" in html and 'lang="pt-BR"' in html


def test_a_tela_de_login_mostra_a_maria_e_a_logo_da_defensoria(cliente: FlaskClient) -> None:
    html = cliente.get("/login").get_data(as_text=True)
    assert f'src="{login.IMAGEM_DA_MARIA}"' in html and f'src="{login.LOGO_DA_DEFENSORIA}"' in html
    assert '<p class="boas-vindas-titulo">Boas-vindas</p>' in html
    # a imagem está em assets/, que o Dash serve e o login deixa livre
    assert login.IMAGEM_DA_MARIA.startswith(login.PREFIXOS_LIVRES[0])
    assert (Path(login.__file__).parent / login.IMAGEM_DA_MARIA.lstrip("/")).is_file()


def test_sem_acesso_oferece_sair_para_trocar_de_conta(cliente: FlaskClient, falsos: Falsos) -> None:
    falsos.usuario = {"email": "outra.pessoa@gmail.com", "email_verified": "true"}
    html = _entrar(cliente).get_data(as_text=True)
    assert 'href="/sair"' in html and "outra.pessoa@gmail.com" in html


def test_na_maquina_a_configuracao_pode_vir_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    local = {"dominio": "d.auth.sa-east-1.amazoncognito.com", "cliente": "c", "endereco": "http://localhost:8050"}
    monkeypatch.setenv("PAINEL_LOGIN_CONFIGURACAO", json.dumps(local))
    monkeypatch.setenv("PAINEL_EMAILS_COM_ACESSO", "pessoa.um@gmail.com")
    leitor = login.Leitor(login.FONTES_REAIS)
    assert leitor.configuracao().retorno == "http://localhost:8050/auth/callback"
    assert leitor.emails_com_acesso() == frozenset({"pessoa.um@gmail.com"})


def test_http_fora_da_propria_maquina_e_recusado(falsos: Falsos) -> None:
    falsos.parametros[PARAMETRO_DA_CONFIGURACAO] = json.dumps(CONFIG | {"endereco": "http://exemplo.cloudfront.net"})
    with pytest.raises(FalhaDoLogin):
        login.Leitor(falsos.fontes()).configuracao()


def test_provedor_de_teste_pelo_ambiente(cliente: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAINEL_LOGIN_PROVEDOR", "COGNITO")
    destino = urllib.parse.urlparse(cliente.get("/login/google").headers["Location"])
    assert urllib.parse.parse_qs(destino.query)["identity_provider"] == ["COGNITO"]
