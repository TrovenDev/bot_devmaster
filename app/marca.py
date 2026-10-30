"""Identidade oficial Troven: https://marca.troven.com.br/ (manual 2026).
Logos, ícone e fontes ficam em assets/ (copiados do pacote oficial da marca)."""
import sys
from pathlib import Path

COBALTO = "#2B35F0"
LIMA = "#C6F432"
NOITE = "#0F1020"
NOITE_2 = "#191A30"
PAPEL = "#F7F5F1"
BRANCO = "#FFFFFF"
LINHA = "#E4E1DA"
GRAFITE = "#5E5F6E"
NEVOA = "#A3A5BE"
COBALTO_ESCURO = "#1F28C9"   # hover/pressionado dos botões cobalto

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "assets"
ICONE_ICO = ASSETS / "troven-app.ico"
ICONE_PNG = ASSETS / "troven-icone-cobalto-quadrado-192px.png"
LOGO_NEGATIVO = ASSETS / "troven-horizontal-negativo-ui.png"

# Atualizadas por carregar_fontes(): Inter/Unbounded se carregarem, senão Segoe UI
FONTE = ("Segoe UI", 10)
FONTE_FORTE = ("Segoe UI Semibold", 10)
FONTE_TITULO = ("Segoe UI Semibold", 15)
FONTE_SOBRE = ("Segoe UI Semibold", 8)


def carregar_fontes(raiz):
    """Carrega Inter e Unbounded de assets/ só para este programa (sem instalar no Windows)."""
    global FONTE, FONTE_FORTE, FONTE_TITULO, FONTE_SOBRE
    if sys.platform == "win32":
        import ctypes
        for ttf in ASSETS.glob("*.ttf"):
            ctypes.windll.gdi32.AddFontResourceExW(str(ttf), 0x10, 0)  # FR_PRIVATE
    from tkinter import font
    familias = set(font.families(raiz))
    corpo = "Inter" if "Inter" in familias else "Segoe UI"
    forte = "Inter SemiBold" if "Inter SemiBold" in familias else ("Segoe UI Semibold")
    titulo = "Unbounded SemiBold" if "Unbounded SemiBold" in familias else forte
    FONTE = (corpo, 10)
    FONTE_FORTE = (forte, 10)
    FONTE_TITULO = (titulo, 14)
    FONTE_SOBRE = (forte, 8)


def definir_icone(raiz):
    """Ícone na janela e na barra de tarefas (o do .exe vem do --icon do PyInstaller)."""
    if sys.platform == "win32":
        import ctypes
        try:  # agrupa na barra de tarefas com o ícone da Troven, não o do Python
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Troven.DevMasterBot")
        except Exception:
            pass
    try:
        raiz.iconbitmap(default=str(ICONE_ICO))
    except Exception:
        pass
    try:
        import tkinter as tk
        raiz._icone_png = tk.PhotoImage(file=str(ICONE_PNG))  # guarda a referência
        raiz.iconphoto(True, raiz._icone_png)  # versão grande, nítida na barra de tarefas
    except Exception:
        pass
