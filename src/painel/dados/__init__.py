"""Camada de dados: escolhe a fonte pelo ambiente do processo, sempre com cache.

`PAINEL_FONTE=real` (o padrão desde 26/10) lê o CloudWatch e o GitHub, com as
credenciais da máquina ou da tarefa. `PAINEL_FONTE=simulado` usa a fonte
inventada, para conferir o desenho e para os testes; com ela, toda tela mostra
a faixa "Dados simulados". Um nome desconhecido falha na subida, e não no meio
de uma tela.

Toda fonte passa pelo cache em disco (dados/cache.py), na pasta `PAINEL_CACHE`
ou, sem ela, numa pasta da área temporária do sistema.
"""

from __future__ import annotations

import os
from functools import cache
from typing import cast

from painel.dados.fontes import FonteDeDados


def _nome_da_fonte() -> str:
    return os.environ.get("PAINEL_FONTE", "real")


def fonte_simulada_ligada() -> bool:
    """A faixa "Dados simulados" aparece enquanto isto for verdade."""
    return _nome_da_fonte() == "simulado"


@cache
def sem_credencial_da_aws() -> bool:
    """A faixa "Sem acesso à AWS" aparece quando a fonte é a real e a máquina não
    tem credencial nenhuma. Olhada uma vez, na subida: o login feito depois só vale
    com o painel reiniciado, porque os clientes da AWS guardam a credencial da subida."""
    if _nome_da_fonte() != "real":
        return False
    import boto3
    from botocore.exceptions import BotoCoreError

    try:
        return boto3.Session().get_credentials() is None
    except BotoCoreError:
        return True


@cache
def obter_fonte() -> FonteDeDados:
    from painel.dados.cache import CacheEmDisco, FonteComCache, pasta_padrao

    nome = _nome_da_fonte()
    guardado = CacheEmDisco(pasta_padrao())
    fonte: FonteDeDados
    if nome == "simulado":
        from painel.dados.simulado import FonteSimulada

        fonte = FonteSimulada(os.environ.get("PAINEL_CENARIO", "normal"))
    elif nome == "real":
        from painel.dados.real import FonteReal

        fonte = FonteReal(guardado)
    else:
        raise RuntimeError(f"PAINEL_FONTE={nome!r}: use 'real' ou 'simulado'")
    # O cache responde pelas mesmas consultas da fonte, com a validade de cada uma.
    return cast(FonteDeDados, FonteComCache(fonte, guardado))
