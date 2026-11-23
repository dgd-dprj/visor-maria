"""Extrai, do código da Maria, os nomes de evento e de campo que ela registra nos logs.

O painel lê os logs da Maria pelo nome do evento (`evento="verde_chamada"`) e do
campo (`tipoErro`, `tokensGastos`...). Os dois moram em repositórios diferentes:
se a Maria renomear um campo, o painel quebra em silêncio. Este script tira um
retrato do que a Maria registra, e `tests/test_contrato_da_maria.py` confere o
retrato contra o que o painel lê (`painel/dados/contrato.py`).

Lê, de um checkout do maria-langgraph-pp:
- toda chamada de log em `src/maria` com `evento="..."` e os campos passados por
  nome (os que chegam por `**extra` não aparecem: o painel só lê campos fixos);
- todo dicionário montado com a chave `"evento"` e passado depois por `**campos`
  (`whatsapp_envio_falhou`, em `integracoes/whatsapp.py`), com as chaves fixas dele;
- as linhas que `verificar-token-verde.yml` imprime e que o painel lê.

Uso:
    python scripts/extrair_contrato_da_maria.py CAMINHO_DO_CHECKOUT [--saida ARQUIVO]

Só a biblioteca padrão: roda no CI sem instalar nada.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SAIDA_PADRAO = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "maria" / "contrato_extraido.json"
WORKFLOW = Path(".github") / "workflows" / "verificar-token-verde.yml"
# Pedaços das linhas que o painel procura no log da conferência diária.
LINHAS_PROCURADAS = ("status atual:", "expiraEm=", "token renovado, gravado no Secrets Manager", "container novo no ar")


def eventos_do_codigo(raiz: Path) -> dict[str, list[str]]:
    eventos: dict[str, set[str]] = {}
    for arquivo in sorted((raiz / "src" / "maria").rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Dict):
                chaves = {k.value: v for k, v in zip(no.keys, no.values, strict=True) if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                evento_do_dicionario = chaves.get("evento")
                if isinstance(evento_do_dicionario, ast.Constant) and isinstance(evento_do_dicionario.value, str):
                    eventos.setdefault(evento_do_dicionario.value, set()).update(c for c in chaves if c != "evento")
                continue
            if not isinstance(no, ast.Call):
                continue
            nomes = {k.arg: k.value for k in no.keywords if k.arg is not None}
            evento = nomes.get("evento")
            if isinstance(evento, ast.Constant) and isinstance(evento.value, str):
                eventos.setdefault(evento.value, set()).update(n for n in nomes if n != "evento")
    return {evento: sorted(campos) for evento, campos in sorted(eventos.items())}


def linhas_do_workflow(raiz: Path) -> list[str]:
    texto = (raiz / WORKFLOW).read_text(encoding="utf-8")
    return [linha for linha in LINHAS_PROCURADAS if linha in texto]


def commit_do_checkout(raiz: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(raiz), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "desconhecido"


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("checkout", type=Path, help="pasta de um clone do maria-langgraph-pp")
    argumentos.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    argumentos.add_argument("--branch", default="develop", help="branch da Maria de onde saiu o checkout")
    argumentos.add_argument("--commit", help="commit de origem, quando o checkout não é um repositório git (git archive)")
    lidos = argumentos.parse_args(argv)
    raiz: Path = lidos.checkout.resolve()
    if not (raiz / "src" / "maria").is_dir():
        print(f"{raiz} não parece um checkout do maria-langgraph-pp (falta src/maria)", file=sys.stderr)
        return 2
    retrato: dict[str, Any] = {
        "origem": {
            "repositorio": "dgd-dprj/maria-langgraph-pp",
            "branch": lidos.branch,
            "commit": lidos.commit or commit_do_checkout(raiz),
            "extraido_em": datetime.now(UTC).strftime("%Y-%m-%d"),
        },
        "eventos": eventos_do_codigo(raiz),
        "linhas_do_workflow": linhas_do_workflow(raiz),
    }
    lidos.saida.parent.mkdir(parents=True, exist_ok=True)
    lidos.saida.write_text(json.dumps(retrato, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(retrato['eventos'])} eventos de {retrato['origem']['commit'][:7]} em {lidos.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
