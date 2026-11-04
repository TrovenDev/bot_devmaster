"""Comandos disponíveis (iguais para Telegram e WhatsApp) e a trava de execução.

Para criar um comando novo: escreva a função em devmaster.py (ela devolve o caminho
do arquivo gerado) e registre aqui em COMANDOS. No servidor de gestão basta liberar
o comando para o sistema.
"""
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable

import devmaster

SemLicenca = devmaster.SemLicenca
from configuracao import CONFIG, PADRAO_ARQUIVO


@dataclass(frozen=True)
class Opcoes:
    empresa: str = ""     # empresa do login do DevMaster
    modulo: str = ""
    arquivo: str = ""     # nome do arquivo gerado


@dataclass(frozen=True)
class Comando:
    nome: str                  # palavra que a pessoa digita (ex.: "estoque")
    titulo: str                # texto do botão/linha do menu
    descricao: str
    funcao: Callable[[Opcoes], str]  # devolve o caminho do arquivo a ser enviado
    mimetype: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    arquivo_padrao: str = PADRAO_ARQUIVO


COMANDOS: dict[str, Comando] = {
    "estoque": Comando(
        nome="estoque",
        titulo="Estoque Geral",
        descricao="Gera o Saldos em Estoque (Excel) e envia aqui",
        funcao=lambda o: devmaster.gerar_estoque(empresa=o.empresa, modulo=o.modulo, nome_arquivo=o.arquivo),
    ),
}


def disponiveis() -> dict[str, Comando]:
    """Comandos liberados agora: os do programa filtrados (e renomeados) pelo servidor."""
    remotos = CONFIG.comandos_remotos()
    if remotos is None:
        return dict(COMANDOS)
    saida = {}
    for nome, cmd in COMANDOS.items():
        if nome in remotos:
            r = remotos[nome]
            saida[nome] = replace(cmd, titulo=r.get("titulo") or cmd.titulo,
                                  descricao=r.get("descricao") or cmd.descricao,
                                  arquivo_padrao=r.get("arquivo") or cmd.arquivo_padrao)
    return saida


# O DevMaster só pode ser operado por um comando por vez, venha de onde vier.
_trava = threading.Lock()
_observadores: list[Callable[[dict], None]] = []


class Ocupado(Exception):
    """Já existe um comando rodando no DevMaster."""


class Desativado(Exception):
    """O sistema foi desativado no servidor de gestão."""


def ocupado() -> bool:
    return _trava.locked()


def observar(funcao: Callable[[dict], None]):
    """Recebe um resumo de cada execução (usado para avisar o servidor de gestão)."""
    _observadores.append(funcao)


def executar(nome: str, canal: str = "", solicitante: str = "") -> str:
    if not CONFIG.ativo():
        raise Desativado()
    cmd = disponiveis().get(nome)
    if cmd is None:
        raise KeyError(nome)
    if not _trava.acquire(blocking=False):
        raise Ocupado()
    inicio = time.time()
    erro = ""
    try:
        opcoes = Opcoes(empresa=CONFIG.empresa_login(), modulo=CONFIG.modulo_login(),
                        arquivo=cmd.arquivo_padrao)
        return cmd.funcao(opcoes)
    except Exception as e:
        erro = str(e)[:300]
        raise
    finally:
        _trava.release()
        resumo = {"comando": nome, "canal": canal, "solicitante": solicitante, "ok": not erro,
                  "erro": erro, "duracao_ms": int((time.time() - inicio) * 1000)}
        for f in _observadores:
            try:
                f(resumo)
            except Exception:
                pass
