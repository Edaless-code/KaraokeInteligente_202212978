"""Modelos de reconocimiento de voz de Vosk (gratuitos y sin conexión).

Se usan los modelos "small" (unos 40 MB cada uno) porque funcionan en tiempo
real en cualquier computadora y también en Android, y porque permiten cambiar
el vocabulario en tiempo de ejecución (vocabulario restringido a la letra).

La carpeta de cada modelo se configura en ``karaoke.ini`` (sección
``[audio]``, claves ``modelo_vosk_es`` y ``modelo_vosk_en``). Si no existe, el
programa ofrece descargarlo de https://alphacephei.com/vosk/models.
"""

from __future__ import annotations

import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from ..config import Config

URL_BASE = "https://alphacephei.com/vosk/models/"
MODELOS = {
    "es": "vosk-model-small-es-0.42",
    "en": "vosk-model-small-en-us-0.15",
}
NOMBRES_IDIOMA = {"es": "español", "en": "inglés"}


def ruta_modelo(config: Config, idioma: str) -> Path:
    clave = f"modelo_vosk_{idioma}"
    try:
        return config.ruta("audio", clave)
    except KeyError:
        return config.carpeta / "modelo" / MODELOS.get(idioma, "")


def modelo_valido(ruta: Path) -> bool:
    """Un modelo de Vosk tiene, al menos, las carpetas ``am`` y ``conf``."""
    return ruta.is_dir() and (ruta / "am").is_dir() and (ruta / "conf").is_dir()


def idiomas_disponibles(config: Config) -> list[str]:
    return [idioma for idioma in MODELOS if modelo_valido(ruta_modelo(config, idioma))]


def descargar_modelo(
    idioma: str,
    destino: Path,
    progreso: Callable[[int, int], None] | None = None,
) -> Path:
    """Descarga y descomprime el modelo del idioma dentro de ``destino``.

    ``destino`` es la carpeta del modelo (por ejemplo
    ``modelo/vosk-model-small-es-0.42``)."""
    nombre = MODELOS[idioma]
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporal:
        archivo_zip = Path(temporal) / f"{nombre}.zip"
        with urllib.request.urlopen(URL_BASE + nombre + ".zip", timeout=60) as respuesta:
            total = int(respuesta.headers.get("Content-Length") or 0)
            leidos = 0
            with open(archivo_zip, "wb") as salida:
                while bloque := respuesta.read(1 << 16):
                    salida.write(bloque)
                    leidos += len(bloque)
                    if progreso:
                        progreso(leidos, total)
        with zipfile.ZipFile(archivo_zip) as comprimido:
            comprimido.extractall(temporal)
        extraido = Path(temporal) / nombre
        if destino.exists():
            shutil.rmtree(destino)
        shutil.move(str(extraido), str(destino))
    if not modelo_valido(destino):
        raise RuntimeError(f"El modelo descargado en {destino} no es válido.")
    return destino
