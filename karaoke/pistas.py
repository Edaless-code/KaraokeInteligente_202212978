"""Pistas de audio de la biblioteca (sin NumPy: sirve también en Android)."""

from __future__ import annotations

from .config import Config
from .db import BaseDatos

FORMATOS = (".mp3", ".wav", ".flac", ".ogg")


def vincular_ejemplos(bd: BaseDatos, config: Config) -> int:
    """Asocia los audios de ``ejemplos/`` a su canción (por el nombre del
    archivo) para poder reproducirlos sin configurar nada. Devuelve cuántas
    pistas nuevas se asociaron."""
    from .nombres_audio import nombre_desde_archivo

    carpeta = config.carpeta / "ejemplos"
    if not carpeta.is_dir():
        return 0
    con_pista = {c for c, _, _ in bd.listar_pistas()}
    nuevas = 0
    for ruta in sorted(carpeta.iterdir()):
        if ruta.suffix.lower() not in FORMATOS:
            continue
        encontradas = bd.buscar_por_nombre(nombre_desde_archivo(ruta), limite=1)
        if encontradas and encontradas[0][0] not in con_pista:
            bd.guardar_pista(encontradas[0][0], ruta.relative_to(config.carpeta).as_posix())
            con_pista.add(encontradas[0][0])
            nuevas += 1
    return nuevas
