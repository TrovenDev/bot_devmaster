"""Gera dist/DevMasterBot.exe (e SHA256SUMS.txt). Rode no Windows: python scripts/build_windows.py"""
import hashlib
import os
import site
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "app"
DIST = RAIZ / "dist"


def main():
    sep = os.pathsep  # separador de --add-data (";" no Windows)
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
        "--name", "DevMasterBot", "--icon", str(APP / "assets" / "troven-app.ico"),
        "--paths", str(APP),
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

    exe = DIST / "DevMasterBot.exe"
    with exe.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    (DIST / "SHA256SUMS.txt").write_text(f"{digest}  {exe.name}\n", encoding="utf-8")
    print("PRONTO:", exe, f"({exe.stat().st_size / 1e6:.1f} MB)  sha256={digest}")


if __name__ == "__main__":
    main()
