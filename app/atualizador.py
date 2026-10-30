"""Atualização automática pelas Releases do GitHub.

Fluxo: consulta a última release, baixa o DevMasterBot.exe novo, confere o SHA-256 e,
quando nenhum comando está rodando, troca o executável e reabre o programa já na
bandeja. Só funciona no .exe (fora dele apenas avisa que há versão nova).
"""
import hashlib
import json
import logging
import os
import re
import subprocess
import ssl

import certifi
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

from versao import REPOSITORY, VERSION

log = logging.getLogger("atualizador")

ASSET = "DevMasterBot.exe"
INTERVALO = 6 * 3600     # consulta a cada 6 horas
LIMITE = 300 * 1024 * 1024


def versao_tupla(valor) -> tuple:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(valor))
    return tuple(map(int, m.groups())) if m else (0, 0, 0)


class Atualizador:
    def __init__(self, pasta, ocupado=lambda: False, ao_reiniciar=lambda: None):
        self._pasta = Path(pasta) / "atualizacoes"
        self._ocupado = ocupado
        self._ao_reiniciar = ao_reiniciar  # fecha o programa para a troca do .exe
        self._parar = threading.Event()
        self._pronto: Path | None = None
        self.status = "ainda não verificado"
        self.ao_mudar = lambda: None
        self.congelado = bool(getattr(sys, "frozen", False))

    # ---------------- Rede ----------------
    @staticmethod
    def _abrir(url):
        req = urllib.request.Request(url, headers={"User-Agent": f"BotDevMaster/{VERSION}",
                                                   "Accept": "application/vnd.github+json"})
        contexto = ssl.create_default_context()
        contexto.load_verify_locations(cafile=certifi.where())
        return urllib.request.urlopen(req, timeout=60, context=contexto)

    def _definir(self, texto):
        if texto != self.status:
            self.status = texto
            log.info("Atualização: %s", texto)
            self.ao_mudar()

    def verificar(self):
        """Consulta, baixa e confere a versão nova. Devolve True se há versão pronta."""
        self._definir("verificando…")
        try:
            with self._abrir(f"https://api.github.com/repos/{REPOSITORY}/releases/latest") as r:
                release = json.loads(r.read(2_000_000))
            tag = release.get("tag_name", "")
            if release.get("draft") or release.get("prerelease") or versao_tupla(tag) <= versao_tupla(VERSION):
                self._definir(f"na versão mais recente ({VERSION})")
                return False
            assets = release.get("assets", [])
            asset = next((a for a in assets if a.get("name") == ASSET), None)
            if not asset:
                self._definir(f"{tag} publicada, mas sem o {ASSET}")
                return False
            prefixo = f"https://github.com/{REPOSITORY}/releases/download/"
            if not asset["browser_download_url"].startswith(prefixo):
                raise ValueError("origem do arquivo não reconhecida")
            esperado = self._hash_esperado(asset, assets, prefixo)
            self._pasta.mkdir(parents=True, exist_ok=True)
            destino = self._pasta / f"DevMasterBot-{tag}.exe"
            if not (destino.exists() and self._sha256(destino) == esperado):
                self._definir(f"baixando {tag}…")
                self._baixar(asset, destino, esperado)
            self._pronto = destino
            self._definir(f"{tag} pronta para instalar")
            return True
        except urllib.error.HTTPError as e:
            self._definir("nenhuma versão publicada ainda" if e.code == 404 else f"erro {e.code} ao consultar")
        except Exception as e:
            self._definir(f"indisponível agora ({e})")
        return False

    def _hash_esperado(self, asset, assets, prefixo) -> str:
        digest = asset.get("digest", "")
        if re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest):
            return digest.split(":")[1].lower()
        sums = next((a for a in assets if a.get("name") == "SHA256SUMS.txt"), None)
        if not sums or not sums["browser_download_url"].startswith(prefixo):
            raise ValueError("versão sem verificação SHA-256")
        with self._abrir(sums["browser_download_url"]) as r:
            for linha in r.read(64_000).decode("utf-8").splitlines():
                m = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?" + re.escape(ASSET), linha.strip())
                if m:
                    return m[1].lower()
        raise ValueError("SHA-256 da versão não encontrado")

    @staticmethod
    def _sha256(caminho: Path) -> str:
        h = hashlib.sha256()
        with caminho.open("rb") as f:
            while bloco := f.read(1024 * 1024):
                h.update(bloco)
        return h.hexdigest()

    def _baixar(self, asset, destino: Path, esperado: str):
        parcial = destino.with_suffix(".part")
        h, total = hashlib.sha256(), 0
        with self._abrir(asset["browser_download_url"]) as r, parcial.open("wb") as saida:
            while bloco := r.read(1024 * 1024):
                total += len(bloco)
                if total > LIMITE:
                    raise ValueError("arquivo maior que o esperado")
                saida.write(bloco)
                h.update(bloco)
        with parcial.open("rb") as f:
            executavel = f.read(2) == b"MZ"
        if h.hexdigest() != esperado or not executavel:
            parcial.unlink(missing_ok=True)
            raise ValueError("o arquivo baixado não passou na verificação de integridade")
        parcial.replace(destino)

    # ---------------- Troca do executável ----------------
    @property
    def pronta(self) -> bool:
        return bool(self._pronto and self._pronto.exists() and self.congelado)

    def aplicar(self) -> bool:
        """Troca o .exe pela versão baixada e reabre. Devolve False se não for possível."""
        if not self.pronta or self._ocupado():
            return False
        alvo = Path(sys.executable)
        bat = self._pasta / "atualizar.bat"
        bat.write_text(self._script(self._pronto, alvo, os.getpid()), encoding="utf-8")
        flags = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        # sem console (programa em janela): o script precisa de handles nulos válidos
        subprocess.Popen(["cmd", "/c", str(bat)], creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.info("Atualização: reiniciando para instalar %s", self._pronto.name)
        self._ao_reiniciar()
        return True

    @staticmethod
    def _script(novo: Path, alvo: Path, pid: int) -> str:
        return f"""@echo off
set "NOVO={novo}"
set "ALVO={alvo}"
set "PID={pid}"
set /a n=0
:espera
"%SystemRoot%\\System32\\tasklist.exe" /FI "PID eq %PID%" 2>nul | "%SystemRoot%\\System32\\find.exe" "%PID%" >nul || goto copia
"%SystemRoot%\\System32\\timeout.exe" /t 1 /nobreak >nul
goto espera
:copia
copy /y "%NOVO%" "%ALVO%" >nul 2>nul && goto pronto
set /a n+=1
if %n% geq 40 exit /b 1
"%SystemRoot%\\System32\\timeout.exe" /t 1 /nobreak >nul
goto copia
:pronto
del "%NOVO%" >nul 2>nul
start "" "%ALVO%" --minimizado
(goto) 2>nul & del "%~f0"
"""

    # ---------------- Laço ----------------
    def run(self):
        """Bloqueia até parar(); chame em uma thread."""
        self._parar.wait(30)  # deixa o programa terminar de abrir
        while not self._parar.is_set():
            self.verificar()
            self._parar.wait(INTERVALO)

    def parar(self):
        self._parar.set()
