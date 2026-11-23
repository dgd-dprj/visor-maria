import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from painel.renovador import RenovacaoInterrompida, Resultado, decidir, renovar_ambiente, validade_do_token

AGORA = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
TOKEN_ANTIGO = "token-antigo-ficticio"  # não é credencial


def jwt(valida_ate: datetime) -> str:
    carga = base64.urlsafe_b64encode(json.dumps({"exp": valida_ate.timestamp()}).encode()).decode().rstrip("=")
    return f"cabecalho.{carga}.assinatura"


class SegredosFalsos:
    def __init__(self, token: str, trava_livre: bool = True, falhas_na_gravacao: int = 0) -> None:
        self.segredo = {"VERDE_API_URL": "https://verde.invalido", "VERDE_JWT_TOKEN": token, "VERDE_CLIENT_ID": "cliente-ficticio", "OUTRA": "x"}
        self.trava_livre = trava_livre
        self.falhas = falhas_na_gravacao
        self.gravacoes = 0
        self.travas_soltas = 0

    def ler(self, nome):
        return dict(self.segredo)

    def gravar(self, nome, valor):
        if self.falhas > 0:
            self.falhas -= 1
            raise OSError("falhou")
        self.gravacoes += 1
        self.segredo = dict(valor)

    def pegar_trava(self, nome, agora):
        return self.trava_livre

    def soltar_trava(self, nome):
        self.travas_soltas += 1


class VerdeFalso:
    def __init__(self, codigo=200, corpo=None):
        self.chamadas = 0
        self.codigo, self.corpo = codigo, corpo if corpo is not None else {"token": "token-novo-ficticio"}

    def renovar(self, api_url, token, client_id):
        self.chamadas += 1
        return self.codigo, self.corpo


class EcsFalso:
    def __init__(self, falha=False):
        self.chamadas, self.falha = [], falha

    def redeploy(self, cluster, servico):
        self.chamadas.append(servico)
        if self.falha:
            raise RuntimeError("segredo-no-erro")


def rodar(segredos, verde=None, ecs=None, **kw):
    verde, ecs = verde or VerdeFalso(), ecs or EcsFalso()
    return renovar_ambiente("prod", segredos=segredos, verde=verde, servico=ecs, agora=AGORA, esperar=lambda _: None, **kw), verde, ecs


def test_decidir_limites():
    assert decidir(AGORA + timedelta(days=1, minutes=1), AGORA) is Resultado.NAO_PRECISA
    assert decidir(AGORA + timedelta(days=1), AGORA) is None
    assert decidir(AGORA - timedelta(days=4), AGORA) is None
    assert decidir(AGORA - timedelta(days=5), AGORA) is Resultado.FORA_DO_PRAZO


def test_validade_do_token_ilegivel():
    assert validade_do_token("lixo") is None
    assert validade_do_token(jwt(AGORA)) == AGORA


def test_com_7_dias_nao_renova():
    s = SegredosFalsos(jwt(AGORA + timedelta(days=7)))
    relato, verde, _ = rodar(s)
    assert relato.resultado is Resultado.NAO_PRECISA and verde.chamadas == 0 and s.gravacoes == 0


def test_com_1_dia_renova_grava_e_faz_redeploy():
    s = SegredosFalsos(jwt(AGORA + timedelta(hours=20)))
    relato, verde, ecs = rodar(s)
    assert relato.resultado is Resultado.RENOVADA
    assert s.segredo["VERDE_JWT_TOKEN"] == "token-novo-ficticio" and s.segredo["OUTRA"] == "x"
    assert ecs.chamadas == ["api-prod-sp"] and s.travas_soltas == 1


def test_simular_nao_chama_nada():
    s = SegredosFalsos(jwt(AGORA + timedelta(hours=20)))
    relato, verde, ecs = rodar(s, simular=True)
    assert relato.resultado is Resultado.SIMULADA and verde.chamadas == 0 and ecs.chamadas == [] and s.gravacoes == 0


def test_trava_ocupada_nao_chama_o_verde():
    s = SegredosFalsos(jwt(AGORA + timedelta(hours=20)), trava_livre=False)
    relato, verde, _ = rodar(s)
    assert relato.resultado is Resultado.OCUPADA and verde.chamadas == 0 and s.travas_soltas == 0


def test_revogado_nao_grava():
    s = SegredosFalsos(jwt(AGORA + timedelta(hours=20)))
    relato, _, ecs = rodar(s, VerdeFalso(401, {"mensagem": "Token revogado"}))
    assert relato.resultado is Resultado.REVOGADA and s.gravacoes == 0 and ecs.chamadas == [] and s.travas_soltas == 1


def test_resposta_sem_token_nao_grava():
    s = SegredosFalsos(jwt(AGORA + timedelta(hours=20)))
    relato, _, _ = rodar(s, VerdeFalso(200, {"dados": {}}))
    assert relato.resultado is Resultado.SEM_TOKEN_NA_RESPOSTA and s.gravacoes == 0


def test_gravacao_tenta_de_novo():
    s = SegredosFalsos(jwt(AGORA + timedelta(hours=20)), falhas_na_gravacao=2)
    relato, _, _ = rodar(s)
    assert relato.resultado is Resultado.RENOVADA and s.gravacoes == 1


def test_gravacao_que_nunca_funciona():
    s = SegredosFalsos(jwt(AGORA + timedelta(hours=20)), falhas_na_gravacao=99)
    relato, _, ecs = rodar(s)
    assert relato.resultado is Resultado.GRAVACAO_FALHOU and ecs.chamadas == []


def test_redeploy_falho_nao_vaza_a_mensagem(caplog):
    s = SegredosFalsos(jwt(AGORA + timedelta(hours=20)))
    relato, _, _ = rodar(s, ecs=EcsFalso(falha=True))
    assert relato.resultado is Resultado.REDEPLOY_FALHOU
    assert "segredo-no-erro" not in caplog.text


def test_token_ilegivel_interrompe():
    with pytest.raises(RenovacaoInterrompida):
        rodar(SegredosFalsos("lixo"))


def test_nenhum_log_leva_token_ou_client_id(caplog):
    s = SegredosFalsos(jwt(AGORA + timedelta(hours=20)), falhas_na_gravacao=1)
    rodar(s)
    assert "token-novo-ficticio" not in caplog.text and "cliente-ficticio" not in caplog.text


def test_linha_do_historico_leva_so_ambiente_resultado_e_validade():
    from painel.renovador import linha_do_historico

    s = SegredosFalsos(jwt(AGORA + timedelta(hours=20)))
    relato, _, _ = rodar(s)
    linha = json.loads(linha_do_historico(relato))
    assert set(linha) == {"evento", "ambiente", "resultado", "validaAte"}
    assert linha["resultado"] == "renovada" and "token" not in linha_do_historico(relato)
    assert datetime.fromisoformat(linha["validaAte"]) == datetime.fromisoformat(linha["validaAte"]).astimezone(UTC)


def test_sem_renovar_o_historico_traz_a_validade_que_vale():
    from painel.renovador import linha_do_historico

    valida = AGORA + timedelta(days=7)
    relato, _, _ = rodar(SegredosFalsos(jwt(valida)))
    assert json.loads(linha_do_historico(relato))["validaAte"] == valida.isoformat()
