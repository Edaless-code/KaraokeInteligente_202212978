"""Crea el borrador de la letra de un archivo de audio (como f → m) y, si la
canción está en canciones.txt, mide cuánto se parece a la letra real.

Uso:
    python herramientas/borrador_desde_audio.py ejemplos/Ghost_of_you_Remastered.mp3
"""

from __future__ import annotations

import argparse
import difflib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from karaoke.audio.desde_audio import crear_borrador  # noqa: E402
from karaoke.config import cargar_config  # noqa: E402
from karaoke.importador import analizar_texto  # noqa: E402
from karaoke.texto import leer_texto, palabras  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio")
    parser.add_argument("--idioma", default=None, choices=["es", "en"])
    parser.add_argument("--canciones", default="ejemplos/canciones.txt")
    parser.add_argument("--carpeta", default=".")
    opciones = parser.parse_args()

    config = cargar_config(Path(opciones.carpeta), crear=False)
    inicio = time.monotonic()
    borrador = crear_borrador(Path(opciones.audio), config, opciones.idioma)
    segundos = time.monotonic() - inicio
    print(f"Nombre sugerido: {borrador.nombre} · idioma {borrador.idioma} · {borrador.motor} · "
          f"{len(borrador.lineas)} líneas · {borrador.duracion:.0f} s de audio en {segundos:.0f} s")
    for numero, linea in enumerate(borrador.lineas, 1):
        print(f"{numero:>3}. {linea}")

    referencia = None
    for nombre, lineas in analizar_texto(leer_texto(opciones.canciones)):
        if palabras(nombre)[:2] == palabras(borrador.nombre)[:2]:
            referencia = (nombre, lineas)
    if referencia:
        real = palabras(" ".join(referencia[1]))
        obtenido = palabras(" ".join(borrador.lineas))
        parecido = difflib.SequenceMatcher(None, real, obtenido, autojunk=False).ratio()
        print(f"\nParecido con la letra real de «{referencia[0]}»: {parecido:.0%} "
              f"({len(obtenido)} palabras transcritas, {len(real)} en la letra)")
    return 0 if borrador.lineas else 1


if __name__ == "__main__":
    sys.exit(main())
