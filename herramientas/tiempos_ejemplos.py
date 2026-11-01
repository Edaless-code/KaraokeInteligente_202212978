"""Calcula en qué segundo empieza cada línea de las canciones de ejemplo
(su letra de canciones.txt con su MP3 de ejemplos/) y lo guarda en
ejemplos/tiempos.json. Con ese archivo la consola, la app y la web muestran
la letra sincronizada sin necesitar Whisper.

Uso:  python herramientas/tiempos_ejemplos.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from karaoke.audio.desde_audio import sincronizar  # noqa: E402
from karaoke.config import cargar_config  # noqa: E402
from karaoke.importador import analizar_texto  # noqa: E402
from karaoke.nombres_audio import nombre_desde_archivo  # noqa: E402
from karaoke.texto import leer_texto, palabras  # noqa: E402


def main() -> int:
    config = cargar_config(RAIZ, crear=False)
    canciones = analizar_texto(leer_texto(RAIZ / "ejemplos" / "canciones.txt"))
    resultado = {}
    for audio in sorted((RAIZ / "ejemplos").glob("*.mp3")):
        clave = palabras(nombre_desde_archivo(audio))[:2]
        cancion = next(((n, l) for n, l in canciones if palabras(n)[:2] == clave), None)
        if cancion is None:
            continue
        nombre, lineas = cancion
        tiempos = sincronizar(audio, config, lineas)
        resultado[nombre] = {"archivo": audio.name, "lineas": len(lineas), "tiempos": tiempos}
        print(f"{nombre}: {len(lineas)} líneas")
        for linea, t in zip(lineas, tiempos):
            print(f"  [{int(t // 60)}:{t % 60:04.1f}] {linea}")
    texto = json.dumps(resultado, ensure_ascii=False, indent=1)
    (RAIZ / "ejemplos" / "tiempos.json").write_text(texto + "\n", encoding="utf-8")
    print("===TIEMPOS_JSON_INICIO===")
    print(json.dumps(resultado, ensure_ascii=False))
    print("===TIEMPOS_JSON_FIN===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
