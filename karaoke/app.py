"""Arranque del programa: configuración, base de datos y menú principal."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import cargar_config
from .db import BaseDatos
from .ui import consola


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="KaraokeInteligente", description="Karaoke Inteligente")
    parser.add_argument("--carpeta", help="carpeta con karaoke.ini, CANCIONES.db y PROGRAMA.txt")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--simular", nargs=argparse.REMAINDER, metavar="AUDIO",
                        help="ejecuta el modo automático sin pantalla sobre un archivo de audio")
    opciones = parser.parse_args(argumentos)
    # UTF-8 en la consola de Windows desde el inicio (también al redirigir la salida).
    consola.inicializar(colores=opciones.simular is None)
    if opciones.simular is not None:
        from .simulacion import main as simular

        extra = ["--carpeta", opciones.carpeta] if opciones.carpeta else []
        return simular(opciones.simular + extra)

    config = cargar_config(opciones.carpeta)
    consola.inicializar(config.booleano("pantalla", "colores"))
    bd = BaseDatos(config.ruta_bd)
    if bd.existia:
        estado = bd.integridad()
        print(f"Base de datos CANCIONES encontrada ({bd.contar_canciones()} canciones). "
              f"Revisión: {estado}.")
    else:
        print(f"Base de datos CANCIONES creada en {config.ruta_bd} con todas sus tablas.")

    from .ui.menus import Aplicacion

    try:
        Aplicacion(config, bd).ejecutar()
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        bd.cerrar()
    print("¡Gracias por usar el Karaoke Inteligente!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
