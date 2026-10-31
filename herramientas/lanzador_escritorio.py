"""Lanzador de la versión de escritorio (se compila a KaraokeEscritorio.exe).

La interfaz gráfica corre con un Python portátil incluido en la carpeta
``escritorio/`` (sin PyInstaller: su análisis de librerías se atora con Kivy en
Windows). Este lanzador solo la abre sin ventana de consola y le indica que
use esta misma carpeta para los datos, la de la versión de consola (comparten
CANCIONES.db, karaoke.ini, modelos de voz y pistas).
"""

import os
import subprocess
import sys
from pathlib import Path

carpeta = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
python = carpeta / "escritorio" / "python" / "pythonw.exe"
programa = carpeta / "escritorio" / "programa" / "main.py"
if not python.exists() or not programa.exists():
    import ctypes

    ctypes.windll.user32.MessageBoxW(0, f"No se encontró la versión de escritorio en:\n{carpeta / 'escritorio'}\n\n"
                                        "Descomprima el ZIP completo.", "Karaoke Inteligente", 0x10)
    sys.exit(1)
entorno = dict(os.environ, KARAOKE_HOME=str(carpeta), KIVY_NO_CONSOLELOG="1")
subprocess.Popen([str(python), str(programa)], cwd=str(programa.parent), env=entorno,
                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
