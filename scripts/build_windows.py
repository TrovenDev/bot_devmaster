"""Gera dist/DevMasterBot.exe, o instalador dist/BotDevMaster-Setup.exe (Inno Setup 6) e SHA256SUMS.txt.
Rode no Windows: python scripts/build_windows.py [--sem-instalador]"""
import argparse
import hashlib
import os
import runpy
import shutil
import site
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "app"
DIST = RAIZ / "dist"
INSTALADOR = RAIZ / "installer" / "BotDevMaster.iss"
IMAGENS = RAIZ / "build" / "instalador"

# Identidade Troven (app/marca.py)
NOITE, NOITE_2, LIMA, NEVOA, BRANCO, COBALTO = "#0F1020", "#191A30", "#C6F432", "#A3A5BE", "#FFFFFF", "#2B35F0"


def _sha256(caminho: Path) -> str:
    with caminho.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def imagens_instalador():
    """Lateral (boas-vindas/fim) e ícone do topo do assistente, em 100% e 200% de escala."""
    from PIL import Image, ImageDraw, ImageFont
    assets = APP / "assets"
    IMAGENS.mkdir(parents=True, exist_ok=True)
    simbolo = Image.open(assets / "troven-simbolo-negativo-ui.png").convert("RGBA")
    logo = Image.open(assets / "troven-horizontal-negativo-600px.png").convert("RGBA")
    for escala, sufixo in ((1, ""), (2, "@2x")):
        w, h = 164 * escala, 314 * escala
        img = Image.new("RGB", (w, h), NOITE)
        d = ImageDraw.Draw(img)
        d.ellipse([w * 0.35, h * 0.55, w * 1.6, h * 1.25], fill=NOITE_2)
        d.rectangle([0, h - 6 * escala, w, h], fill=LIMA)                     # faixa lima da marca
        lg = logo.copy()
        lg.thumbnail((w - 36 * escala, 60 * escala))
        img.paste(lg, (18 * escala, 28 * escala), lg)
        try:
            titulo = ImageFont.truetype(str(assets / "unbounded-600.ttf"), 13 * escala)
            corpo = ImageFont.truetype(str(assets / "inter-400.ttf"), 10 * escala)
        except OSError:
            titulo = corpo = ImageFont.load_default()
        y = 28 * escala + lg.height + 22 * escala
        d.text((18 * escala, y), "Bot", font=titulo, fill=BRANCO)
        d.text((18 * escala, y + 18 * escala), "DevMaster", font=titulo, fill=LIMA)
        d.text((18 * escala, y + 44 * escala), "Relatórios do DevMaster\nno WhatsApp e no Telegram.",
               font=corpo, fill=NEVOA, spacing=3 * escala)
        img.save(IMAGENS / f"lateral{sufixo}.bmp")

        lado = 55 * escala
        peq = Image.new("RGB", (lado, lado), COBALTO)
        sb = simbolo.copy()
        sb.thumbnail((lado - 16 * escala, lado - 16 * escala))
        peq.paste(sb, ((lado - sb.width) // 2, (lado - sb.height) // 2), sb)
        peq.save(IMAGENS / f"icone{sufixo}.bmp")


def achar_iscc():
    for c in (shutil.which("iscc"),
              Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
              Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"):
        if c and Path(c).exists():
            return str(c)
    return None


def instalador():
    iscc = achar_iscc()
    if not iscc:
        sys.exit("Inno Setup 6 não encontrado (winget install JRSoftware.InnoSetup) ou use --sem-instalador")
    imagens_instalador()
    versao = runpy.run_path(str(APP / "versao.py"))["VERSION"]
    subprocess.run([iscc, "/Q", f"/DVersao={versao}", str(INSTALADOR)], cwd=RAIZ, check=True)




def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--sem-instalador", action="store_true", help="gera só o DevMasterBot.exe")
    opcoes = args.parse_args()
    # Nao publique um executavel sem interface: o sandbox pode impedir a leitura de Tcl/Tk.
    subprocess.run([sys.executable, "-c", "import tkinter; r=tkinter.Tk(); r.withdraw(); r.update_idletasks(); r.destroy()"], check=True)
    sep = os.pathsep  # separador de --add-data (";" no Windows)
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "DevMasterBot", "--icon", str(APP / "assets" / "troven-app.ico"),
        "--paths", str(APP),
        "--collect-data", "certifi",
        "--hidden-import", "tkinter", "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.messagebox", "--hidden-import", "tkinter.scrolledtext",
        "--add-data", f"{APP / 'assets'}{sep}assets",
        "--hidden-import", "win32ui", "--hidden-import", "pystray._win32",
        "--distpath", str(DIST), "--workpath", str(RAIZ / "build"), "--specpath", str(RAIZ / "build"),
    ]
    # O win32ui (pywinauto) precisa de mfc140u.dll; vai junto para funcionar sem o Visual C++
    # Redistributable instalado. As DLLs do pywin32 também.
    extras = [Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "mfc140u.dll"]
    for pasta in site.getsitepackages():
        extras += [p for p in (Path(pasta) / "pywin32_system32").glob("*.dll")]
    for dll in extras:
        if dll.exists():
            cmd += ["--add-binary", f"{dll}{sep}."]
        else:
            print("aviso: não achei", dll)
    subprocess.run(cmd + [str(APP / "gui.py")], cwd=RAIZ, check=True)

    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
    pacote = CArchiveReader(str(DIST / "DevMasterBot.exe"))
    modulos = ZlibArchiveReader(str(RAIZ / "build" / "DevMasterBot" / "PYZ-00.pyz"))
    obrigatorios = {"tkinter", "tkinter.ttk", "tkinter.messagebox", "tkinter.scrolledtext"}
    if not obrigatorios.issubset(modulos.toc) or not any(n.endswith("init.tcl") for n in pacote.toc):
        raise RuntimeError("Build incompleto: Tkinter/Tcl nao foram incluidos. Nao publique este executavel.")

    arquivos = [DIST / "DevMasterBot.exe"]
    if not opcoes.sem_instalador:
        instalador()
        arquivos.append(DIST / "BotDevMaster-Setup.exe")
    # o atualizador confere o SHA-256 do DevMasterBot.exe por este arquivo
    (DIST / "SHA256SUMS.txt").write_text("".join(f"{_sha256(a)}  {a.name}\n" for a in arquivos), encoding="utf-8")
    for a in arquivos:
        print("PRONTO:", a, f"({a.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
