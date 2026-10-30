"""Transcribe un archivo de audio con Vosk y muestra qué canción y qué línea
reconoce en cada frase. Sirve para medir qué tan bien funciona el modo
automático con una canción real.

Uso:
    python herramientas/transcribir.py ejemplos/Sound_of_You.mp3 --idioma en
    python herramientas/transcribir.py audio.mp3 --idioma es --sin-limpieza
    python herramientas/transcribir.py audio.mp3 --motor whisper --aislar-voz
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from karaoke.audio.fuentes import FuenteArchivo  # noqa: E402
from karaoke.audio.limpieza import LimpiadorAudio  # noqa: E402
from karaoke.audio.modelos import ruta_modelo  # noqa: E402
from karaoke.audio.motores import MotorVosk, MotorWhisper  # noqa: E402
from karaoke.buscador import Buscador  # noqa: E402
from karaoke.config import cargar_config  # noqa: E402
from karaoke.db import BaseDatos  # noqa: E402
from karaoke.importador import importar_archivo  # noqa: E402
from karaoke.texto import palabras as normalizar_palabras  # noqa: E402
from karaoke.texto import vocabulario  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio")
    parser.add_argument("--idioma", default="es", choices=["es", "en", "auto"],
                        help="auto: Whisper detecta el idioma (canciones bilingües)")
    parser.add_argument("--canciones", default="ejemplos/canciones.txt",
                        help="archivo de canciones contra el que se busca")
    parser.add_argument("--carpeta", default=".", help="carpeta con karaoke.ini y modelo/")
    parser.add_argument("--sin-limpieza", action="store_true")
    parser.add_argument("--restringido", action="store_true",
                        help="restringe el vocabulario a las letras (Vosk) o lo sugiere (Whisper)")
    parser.add_argument("--motor", default="vosk", choices=["vosk", "whisper"])
    parser.add_argument("--modelo-whisper", default="base")
    parser.add_argument("--aislar-voz", action="store_true",
                        help="realza la voz del centro de una mezcla estéreo")
    opciones = parser.parse_args()

    config = cargar_config(Path(opciones.carpeta), crear=False)
    with tempfile.TemporaryDirectory() as temporal:
        bd = BaseDatos(Path(temporal) / "CANCIONES.db")
        importar_archivo(bd, opciones.canciones, config)
        buscador = Buscador(bd, config)
        if opciones.motor == "vosk":
            motor = MotorVosk({opciones.idioma: ruta_modelo(config, opciones.idioma)},
                              canal_libre=not opciones.restringido)
        else:
            motor = MotorWhisper(opciones.modelo_whisper, opciones.idioma, sincrono=True)
        letras = set()
        for cancion in bd.todas_las_letras().values():
            letras |= set(normalizar_palabras(" ".join(cancion.lineas)))
        if opciones.restringido:
            palabras = set()
            for cancion in bd.todas_las_letras().values():
                palabras |= vocabulario(cancion.lineas, opciones.idioma)
            motor.restringir(palabras, opciones.idioma)
        limpiador = None if opciones.sin_limpieza else LimpiadorAudio.desde_config(config)
        fuente = FuenteArchivo(opciones.audio, tiempo_real=False, aislar_voz=opciones.aislar_voz)
        fuente.iniciar()
        inicio = time.monotonic()
        frases = identificadas = reconocidas = de_la_letra = 0
        print(f"Archivo: {opciones.audio} ({fuente.duracion:.0f} s) · motor {opciones.motor} · "
              f"idioma {opciones.idioma} · limpieza {'no' if limpiador is None else 'sí'} · "
              f"aislar voz {'sí' if opciones.aislar_voz else 'no'} · "
              f"{'restringido' if opciones.restringido else 'libre'}")

        def transcripciones():
            while (bloque := fuente.leer()) is not None:
                if limpiador is not None:
                    bloque = limpiador.procesar(bloque)
                yield from motor.procesar(bloque)
            if hasattr(motor, "vaciar"):
                yield from motor.vaciar()

        for t in transcripciones():
            if t.tipo != "final" or not t.palabras:
                continue
            frases += 1
            normales = normalizar_palabras(t.texto)
            reconocidas += len(normales)
            de_la_letra += sum(1 for p in normales if p in letras)
            resultado = buscador.identificar(t.palabras)
            if resultado:
                identificadas += 1
                destino = f"→ [{resultado.codigo}] línea {resultado.linea_actual + 1} ({resultado.puntaje:.2f})"
            else:
                mejores = buscador.buscar(t.palabras, limite=1)
                destino = f"   sin identificar ({mejores[0].puntaje:.2f})" if mejores else "   sin coincidencia"
            print(f"{int(t.segundo // 60)}:{t.segundo % 60:04.1f}  {t.texto:<60} {destino}")
        segundos = time.monotonic() - inicio
        print(f"\nFrases: {frases} · identificadas: {identificadas} · palabras reconocidas: "
              f"{reconocidas} (de la letra: {de_la_letra}) · "
              f"procesado en {segundos:.0f} s ({fuente.duracion / max(segundos, 0.1):.1f}x tiempo real)")
        bd.cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
