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
    opciones = parser.parse_args(argumentos)

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
