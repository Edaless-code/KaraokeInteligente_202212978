"""Pistas de audio de la biblioteca (sin NumPy: sirve también en Android)."""

from __future__ import annotations

from .config import Config
from .db import BaseDatos

FORMATOS = (".mp3", ".wav", ".flac", ".ogg")


def punto_de_entrada(tiempos: list[float], linea: int, fraccion: float = 0.0,
                     latencia: float = 0.0) -> float:
    """Segundo de la pista que corresponde a lo que el cantante va cantando:
    el inicio de ``linea`` más la ``fraccion`` (0 a 1) de la línea ya cantada,
    más la ``latencia`` del reconocimiento (mientras la IA reconocía, el
    cantante siguió cantando)."""
    if not tiempos:
        return 0.0
    linea = min(max(linea, 0), len(tiempos) - 1)
    inicio = tiempos[linea]
    fin = tiempos[linea + 1] if linea + 1 < len(tiempos) else inicio + 4.0
    fraccion = min(max(fraccion, 0.0), 1.0)
    return max(0.0, inicio + fraccion * (fin - inicio) + max(latencia, 0.0))


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
    _tiempos_de_ejemplo(bd, carpeta)
    return nuevas


def _tiempos_de_ejemplo(bd: BaseDatos, carpeta) -> None:
    """Carga ``ejemplos/tiempos.json`` (tiempos ya calculados de las canciones
    de ejemplo) para que suenen a tiempo desde la primera vez, sin esperar a la
    IA. Solo se usan si la letra tiene el mismo número de líneas."""
    import json

    ruta = carpeta / "tiempos.json"
    if not ruta.is_file():
        return
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for codigo, _, archivo in bd.listar_pistas():
        if bd.obtener_tiempos(codigo):
            continue
        for info in datos.values():
            if archivo.endswith("/" + info.get("archivo", "\0")):
                cancion = bd.obtener_cancion(codigo)
                tiempos = info.get("tiempos") or []
                if cancion and len(cancion.lineas) == len(tiempos):
                    bd.guardar_tiempos(codigo, [float(t) for t in tiempos])
