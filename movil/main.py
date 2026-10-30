"""Punto de entrada de la app móvil (Android) del Karaoke Inteligente."""

import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
# En la APK el paquete "karaoke" se copia junto a este archivo; al desarrollar
# se usa el de la carpeta superior del proyecto.
if not (AQUI / "karaoke").exists():
    sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI))
os.environ.setdefault("KIVY_LOG_MODE", "PYTHON")

from app.aplicacion import KaraokeApp  # noqa: E402

if __name__ == "__main__":
    KaraokeApp().run()
