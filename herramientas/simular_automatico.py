"""Ejecuta el modo automático sin pantalla (ver karaoke/simulacion.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from karaoke.simulacion import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
