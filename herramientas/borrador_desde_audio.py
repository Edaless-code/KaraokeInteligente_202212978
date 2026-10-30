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

from karaoke.alineacion import PalabraConTiempo, sincronia  # noqa: E402
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
    parser.add_argument("--modelo", default=None, help="tiny, base, small, medium… (por omisión el de karaoke.ini)")
    parser.add_argument("--aislar", action="store_true", help="realzar la voz del centro antes de transcribir")
    opciones = parser.parse_args()

    config = cargar_config(Path(opciones.carpeta), crear=False)
    inicio = time.monotonic()
    borrador = crear_borrador(Path(opciones.audio), config, opciones.idioma, modelo=opciones.modelo,
                              aislar=opciones.aislar or None)
    segundos = time.monotonic() - inicio
    print(f"Nombre sugerido: {borrador.nombre} · idioma {borrador.idioma} · {borrador.motor} · "
          f"{len(borrador.lineas)} líneas · {borrador.duracion:.0f} s de audio en {segundos:.0f} s")
    for numero, (linea, tiempo) in enumerate(zip(borrador.lineas, borrador.tiempos), 1):
        marca = f"{int(tiempo // 60)}:{tiempo % 60:04.1f}" if tiempo is not None else "     "
        print(f"{numero:>3}. [{marca}] {linea}")

    referencia = None
    for nombre, lineas in analizar_texto(leer_texto(opciones.canciones)):
        if palabras(nombre)[:2] == palabras(borrador.nombre)[:2]:
            referencia = (nombre, lineas)
    if referencia:
        real = palabras(" ".join(referencia[1]))
        obtenido = palabras(" ".join(borrador.lineas))
        comparacion = difflib.SequenceMatcher(None, real, obtenido, autojunk=False)
        iguales = sum(b.size for b in comparacion.get_matching_blocks())
        print(f"\nParecido con la letra real de «{referencia[0]}»: {comparacion.ratio():.0%} "
              f"({len(obtenido)} palabras transcritas, {len(real)} en la letra)")
        print(f"  Palabras de la letra que la IA escribió bien: {iguales / max(1, len(real)):.0%} · "
              f"palabras escritas que son de la letra: {iguales / max(1, len(obtenido)):.0%}")

        # Sincronía: la letra real con los tiempos de lo que oyó la IA.
        oidas = [PalabraConTiempo(p.texto, p.inicio, p.fin) for p in borrador.palabras]
        tiempos, directas = sincronia(referencia[1], oidas, borrador.duracion)
        print(f"\nLetra real sincronizada con la pista ({sum(directas)} de {len(directas)} líneas "
              f"con tiempo directo de la IA = {sum(directas) / max(1, len(directas)):.0%}):")
        for linea, tiempo, directa in zip(referencia[1], tiempos, directas):
            print(f"  [{int(tiempo // 60)}:{tiempo % 60:04.1f}]{' ' if directa else '~'} {linea}")
    return 0 if borrador.lineas else 1


if __name__ == "__main__":
    sys.exit(main())
