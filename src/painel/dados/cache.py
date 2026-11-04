"""O cache das leituras, em disco, dividido pelos processos do servidor.

O gunicorn sobe mais de um processo, e cada um teria o seu cache em memória: a
mesma consulta paga duas vezes. Em disco, na pasta da tarefa, os processos leem
o que o outro já guardou.

Cada leitura vira um arquivo, gravado inteiro e trocado de uma vez
(`os.replace`), para nenhum processo ler um arquivo pela metade. A leitura que
falhou não é guardada: na volta seguinte, a fonte é consultada de novo.

O arquivo é pickle, lido só desta pasta, que o painel cria e só ele usa. Um
arquivo que não abre (versão antiga do painel, gravação interrompida) conta
como ausente.

Trocar de tela não espera a consulta: a leitura vencida há pouco aparece na
hora, com a hora em que foi lida ao lado de cada número, e a nova é lida por
trás, para a volta seguinte do relógio. Passado `VENCIDA_AINDA_SERVE`, a tela
espera a leitura nova. Duas telas que pedem a mesma consulta ao mesmo tempo
esperam a mesma leitura, em vez de pagar duas.
"""

from __future__ import annotations

import hashlib
import logging
import os
import pickle
import tempfile
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from painel.dados.consultas import CONSULTAS
from painel.dados.fontes import FonteDeDados
from painel.dados.modelo import FUSO, Estado, Leitura

registro = logging.getLogger(__name__)

# Mudou a forma de algum tipo guardado (dados/modelo.py)? Suba este número.
VERSAO = 2
VENCIDA_AINDA_SERVE = timedelta(minutes=30)
# As leituras por trás têm o seu próprio conjunto, abaixo do limite de consultas
# simultâneas do Logs Insights, como as leituras das telas (dados/telas.py).
_POR_TRAS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="por-tras")


def pasta_padrao() -> Path:
    return Path(os.environ.get("PAINEL_CACHE") or Path(tempfile.gettempdir()) / "visor-maria-cache")


class CacheEmDisco:
    def __init__(self, pasta: Path) -> None:
        self._pasta = pasta
        self._pasta.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _arquivo(self, chave: str) -> Path:
        return self._pasta / f"{hashlib.sha256(chave.encode()).hexdigest()}.pickle"

    def ler(self, chave: str, agora: datetime) -> Any | None:
        guardada = self.ler_mesmo_vencida(chave)
        if guardada is None:
            return None
        valor, valido_ate = guardada
        return None if valido_ate is not None and agora >= valido_ate else valor

    def ler_mesmo_vencida(self, chave: str) -> tuple[Any, datetime | None] | None:
        """O valor guardado e até quando ele vale (None: para sempre)."""
        try:
            with self._arquivo(chave).open("rb") as arquivo:
                guardada_chave, valido_ate, valor = pickle.load(arquivo)
        except Exception:
            return None
        return (valor, valido_ate) if guardada_chave == chave else None

    def gravar(self, chave: str, valor: Any, valido_ate: datetime | None) -> None:
        destino = self._arquivo(chave)
        # Um temporário por processo e por thread: duas threads gravando a mesma chave não dividem arquivo.
        temporario = destino.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        with temporario.open("wb") as arquivo:
            pickle.dump((chave, valido_ate, valor), arquivo)
        try:
            os.replace(temporario, destino)
        except PermissionError:
            # No Windows, a troca falha enquanto outro lê o arquivo. Guardar é só ganho:
            # a leitura vale do mesmo jeito, e a próxima volta grava de novo.
            temporario.unlink(missing_ok=True)


class FonteComCache:
    """Põe o cache na frente de qualquer `FonteDeDados`, com a janela e a
    validade de cada consulta tiradas de dados/consultas.py."""

    def __init__(
        self,
        fonte: FonteDeDados,
        cache: CacheEmDisco,
        agora: Callable[[], datetime] | None = None,
        por_tras: Callable[[Callable[[], None]], object] | None = None,
    ) -> None:
        self._fonte = fonte
        self._cache = cache
        self._agora = agora or (lambda: datetime.now(FUSO))
        self._por_tras = por_tras or _POR_TRAS.submit
        self._em_curso: dict[str, Future[Leitura[Any]]] = {}
        self._trava = threading.Lock()

    @property
    def nome(self) -> str:
        return self._fonte.nome

    def __getattr__(self, nome: str) -> Callable[..., Leitura[Any]]:
        if nome.startswith("_"):
            raise AttributeError(nome)
        consulta = CONSULTAS.get(nome)
        if consulta is None:
            raise AttributeError(f"{nome}: consulta sem janela e validade declaradas em dados/consultas.py")
        metodo: Callable[..., Leitura[Any]] = getattr(self._fonte, nome)

        def ler(*argumentos: Any) -> Leitura[Any]:
            # Sem o dia escolhido (None no fim), a chave é a mesma de quem não passou o dia.
            while argumentos and argumentos[-1] is None:
                argumentos = argumentos[:-1]
            chave = f"v{VERSAO}:{self._fonte.nome}:{nome}({', '.join(map(str, argumentos))})"

            def consultar() -> Leitura[Any]:
                leitura = metodo(*argumentos)
                if leitura.estado is Estado.INDISPONIVEL:
                    return leitura
                fecha_em = consulta.fecha_em(*argumentos) if consulta.fecha_em is not None else None
                fechada = fecha_em is not None and leitura.lido_em >= fecha_em
                self._cache.gravar(chave, leitura, None if fechada else leitura.lido_em + consulta.validade)
                return leitura

            agora = self._agora()
            guardada = self._cache.ler_mesmo_vencida(chave)
            if guardada is not None:
                valor, valido_ate = guardada
                if valido_ate is None or agora < valido_ate:
                    return valor  # type: ignore[no-any-return]
                if agora < valido_ate + VENCIDA_AINDA_SERVE:
                    self._uma_vez(chave, consultar, por_tras=True)
                    return valor  # type: ignore[no-any-return]
            return self._uma_vez(chave, consultar, por_tras=False).result()

        return ler

    def _uma_vez(self, chave: str, consultar: Callable[[], Leitura[Any]], por_tras: bool) -> Future[Leitura[Any]]:
        """A leitura em curso desta chave ou, sem nenhuma, uma nova."""
        with self._trava:
            em_curso = self._em_curso.get(chave)
            if em_curso is not None:
                return em_curso
            futuro: Future[Leitura[Any]] = Future()
            self._em_curso[chave] = futuro

        def rodar() -> None:
            try:
                futuro.set_result(consultar())
            except BaseException as erro:
                if por_tras:
                    registro.exception("leitura por trás falhou: %s", chave)
                futuro.set_exception(erro)
            finally:
                with self._trava:
                    del self._em_curso[chave]

        if por_tras:
            self._por_tras(rodar)
        else:
            rodar()
        return futuro
