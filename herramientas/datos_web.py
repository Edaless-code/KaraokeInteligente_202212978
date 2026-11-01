"""Prepara los datos de la versión web: las canciones de ejemplo (letra ya
limpia por el importador), sus tiempos (ejemplos/tiempos.json) y sus MP3.

Uso:  python herramientas/datos_web.py      → web/datos/canciones.json y web/audio/
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from karaoke.importador import analizar_texto  # noqa: E402
from karaoke.nombres_audio import nombre_desde_archivo  # noqa: E402
from karaoke.texto import detectar_idioma, leer_texto, palabras  # noqa: E402


def main() -> int:
    ejemplos = RAIZ / "ejemplos"
    web = RAIZ / "web"
    canciones = analizar_texto(leer_texto(ejemplos / "canciones.txt"))
    tiempos = {}
    if (ejemplos / "tiempos.json").exists():
        tiempos = json.loads((ejemplos / "tiempos.json").read_text(encoding="utf-8"))
    audios = {tuple(palabras(nombre_desde_archivo(a))[:2]): a for a in ejemplos.glob("*.mp3")}
    salida = []
    (web / "audio").mkdir(parents=True, exist_ok=True)
    for codigo, (nombre, lineas) in enumerate(canciones, 1):
        lineas = [" ".join(l.split()) for l in lineas]
        audio = audios.get(tuple(palabras(nombre)[:2]))
        datos = tiempos.get(nombre, {})
        t = datos.get("tiempos") if datos.get("lineas") == len(lineas) else None
        cancion = {"id": f"ejemplo-{codigo}", "codigo": codigo, "nombre": nombre, "lineas": lineas,
                   "idioma": detectar_idioma(lineas), "tiempos": t, "audio": None,
                   "autor": "Edgar Alessandro Chocon Oliva", "ejemplo": True}
        if audio:
            shutil.copy2(audio, web / "audio" / audio.name)
            cancion["audio"] = f"audio/{audio.name}"
        salida.append(cancion)
        print(f"{nombre}: {len(lineas)} líneas · tiempos {'exactos' if t else 'aproximados'} · "
              f"audio {'sí' if audio else 'no'}")
    (web / "datos" / "canciones.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n",
                                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
