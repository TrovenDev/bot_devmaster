"""Bandeja do sistema (gaveta de apps), instância única e início com o Windows."""
import ctypes
import logging
import sys
import threading
from pathlib import Path

import marca as M
from versao import NOME

log = logging.getLogger("bandeja")

_MUTEX = "Local\\TrovenBotDevMaster"
_EVENTO = "Local\\TrovenBotDevMaster.Abrir"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALOR = "BotDevMaster"


# ---------------- Instância única ----------------
def instancia_unica(ao_pedirem_para_abrir) -> bool:
    """True se esta é a primeira instância. Se já existe outra, pede para ela abrir a
    janela (que pode estar escondida na bandeja) e devolve False."""
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = wintypes.HANDLE
    k.CreateEventW.restype = wintypes.HANDLE
    k.OpenEventW.restype = wintypes.HANDLE
    k.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    k.SetEvent.argtypes = (wintypes.HANDLE,)
    k.CreateMutexW(None, False, _MUTEX)
    if ctypes.get_last_error() != 183:  # 183 = ERROR_ALREADY_EXISTS
        evento = k.CreateEventW(None, False, False, _EVENTO)

        def vigiar():
            while k.WaitForSingleObject(evento, 0xFFFFFFFF) == 0:
                ao_pedirem_para_abrir()
        threading.Thread(target=vigiar, daemon=True).start()
        return True
    ev = k.OpenEventW(0x0002, False, _EVENTO)  # EVENT_MODIFY_STATE
    if ev:
        k.SetEvent(ev)
    return False


# ---------------- Iniciar com o Windows ----------------
def _comando_inicio() -> str:
    exe = Path(sys.executable) if getattr(sys, "frozen", False) else None
    return f'"{exe}" --minimizado' if exe else ""


def inicio_com_windows() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _RUN_VALOR)
            return True
    except OSError:
        return False


def definir_inicio_com_windows(ativo: bool) -> bool:
    """Liga/desliga a abertura automática (só no .exe). Devolve o estado final."""
    import winreg
    comando = _comando_inicio()
    if ativo and not comando:
        return False
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if ativo:
            winreg.SetValueEx(k, _RUN_VALOR, 0, winreg.REG_SZ, comando)
        else:
            try:
                winreg.DeleteValue(k, _RUN_VALOR)
            except OSError:
                pass
    return inicio_com_windows()


# ---------------- Ícone da bandeja ----------------
class Bandeja:
    """Ícone na gaveta de apps. Fechar ou minimizar a janela só a esconde: o programa
    continua atendendo. 'Sair' no menu do ícone encerra de verdade."""

    def __init__(self, janela, ao_sair, itens_extra=()):
        self.janela = janela
        self.ao_sair = ao_sair
        self.itens_extra = itens_extra   # [(texto, funcao)]
        self._icone = None
        self._avisou = False

    def iniciar(self):
        import pystray
        from PIL import Image
        imagem = Image.open(M.ICONE_PNG)
        itens = [pystray.MenuItem("Abrir", self._abrir, default=True)]
        for texto, funcao in self.itens_extra:
            itens.append(pystray.MenuItem(texto, self._chamar(funcao)))
        itens += [pystray.Menu.SEPARATOR, pystray.MenuItem("Sair", self._sair)]
        self._icone = pystray.Icon("bot-devmaster", imagem, NOME, pystray.Menu(*itens))
        self._icone.run_detached()

    def _chamar(self, funcao):
        # o pystray exige callbacks com até 2 parâmetros (sem valores padrão)
        return lambda _icone, _item: self.janela.after(0, funcao)

    def _abrir(self, *_):
        self.janela.after(0, self.mostrar)

    def _sair(self, *_):
        self.janela.after(0, self.ao_sair)

    def mostrar(self):
        self.janela.deiconify()
        self.janela.state("normal")
        self.janela.lift()
        self.janela.focus_force()

    def esconder(self):
        self.janela.withdraw()
        if self._icone and not self._avisou:
            self._avisou = True  # avisa só na primeira vez
            try:
                self._icone.notify(f"O {NOME} continua rodando aqui na bandeja. "
                                   "Clique no ícone para abrir; para encerrar, use Sair.", NOME)
            except Exception:
                pass

    def encerrar(self):
        if self._icone:
            try:
                self._icone.stop()
            except Exception:
                pass
