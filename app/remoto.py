"""Cliente do servidor de gestão (console web): busca a configuração deste sistema
(empresa, comandos, números e IDs permitidos), avisa que está online e registra as
execuções. Sem servidor configurado o programa segue só com a configuração local."""
import json
import logging
import os
import socket
import ssl

import certifi
import threading
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

from configuracao import CONFIG

log = logging.getLogger("gestao")

INTERVALO = 15  # segundos entre consultas


class Gestao:
    def __init__(self, url: str, chave: str, pasta, versao: str, estado=lambda: {}):
        self.url = url.rstrip("/")
        self.chave = chave
        self.versao = versao
        self._estado = estado
        self._cache = Path(pasta) / "config_remota.json"
        self._pendentes: deque = deque(maxlen=50)
        self._parar = threading.Event()
        self._acordar = threading.Event()
        self.status = "iniciando"   # texto mostrado no painel
        self.ao_mudar = lambda: None  # a GUI atribui um callback

    # ---------------- HTTP ----------------
    def _pedir(self, metodo: str, caminho: str, corpo: dict | None = None) -> dict:
        req = urllib.request.Request(
            f"{self.url}/api/v1{caminho}", method=metodo,
            headers={"Authorization": f"Bearer {self.chave}", "Content-Type": "application/json",
                     "User-Agent": f"BotDevMaster/{self.versao}"},
            data=json.dumps(corpo).encode("utf-8") if corpo is not None else None)
        contexto = ssl.create_default_context()
        contexto.load_verify_locations(cafile=certifi.where())
        with urllib.request.urlopen(req, timeout=20, context=contexto) as r:
            return json.loads(r.read().decode("utf-8") or "{}")

    # ---------------- Ciclo ----------------
    def _atualizar_config(self):
        try:
            dados = self._pedir("GET", "/config")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                # chave revogada ou sistema excluído: bloqueia os comandos
                CONFIG.definir_remota({"sistema": {"ativo": False}, "comandos": [],
                                       "whatsapp": {"numeros": []}, "telegram": {"ids": []}})
                self._definir_status("chave inválida ou revogada: sistema bloqueado")
            else:
                self._usar_cache(f"erro {e.code} no servidor")
            return
        except Exception as e:
            self._usar_cache(f"sem conexão ({type(e).__name__})")
            return
        mudou = CONFIG.remota != dados
        CONFIG.definir_remota(dados)
        if mudou:
            log.info("Permissoes sincronizadas: WhatsApp %d numeros; Telegram %d IDs.",
                     len(CONFIG.numeros_whatsapp()), len(CONFIG.ids_telegram()))
            self.ao_mudar()
        try:
            self._cache.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        nome = (dados.get("sistema") or {}).get("nome", "")
        empresa = (dados.get("empresa") or {}).get("nome", "")
        self._definir_status(f"conectado · {nome}" + (f" · {empresa}" if empresa else ""))

    def _usar_cache(self, motivo: str):
        if CONFIG.remota is None:
            try:
                CONFIG.definir_remota(json.loads(self._cache.read_text(encoding="utf-8")))
                self._definir_status(f"offline ({motivo}); usando a última configuração salva")
                return
            except (OSError, ValueError):
                pass
        self._definir_status(f"offline ({motivo})")

    def _definir_status(self, texto: str):
        if texto != self.status:
            self.status = texto
            log.info("Servidor de gestão: %s", texto)
            self.ao_mudar()

    def _heartbeat(self):
        try:
            self._pedir("POST", "/heartbeat", {"versao": self.versao, "host": socket.gethostname(),
                                               "estado": self._estado()})
            while self._pendentes:
                self._pedir("POST", "/execucoes", self._pendentes[0])
                self._pendentes.popleft()
        except Exception as e:
            log.debug("heartbeat falhou: %s", e)

    def registrar_execucao(self, resumo: dict):
        """Chamado após cada comando (ver comandos.observar)."""
        self._pendentes.append(resumo)
        self._acordar.set()

    def run(self):
        """Bloqueia até parar(); chame em uma thread."""
        while not self._parar.is_set():
            self._atualizar_config()
            self._heartbeat()
            self._acordar.wait(INTERVALO)
            self._acordar.clear()
        log.info("Servidor de gestão: desconectado.")

    def parar(self):
        self._parar.set()
        self._acordar.set()
