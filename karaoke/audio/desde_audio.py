"""Agregar canciones a partir de archivos de audio (MP3, WAV, FLAC u OGG).

1. Se lee la pista completa y se realza la voz del centro de la mezcla.
2. Whisper la transcribe de una sola vez: cada segmento que entrega suele ser
   una frase cantada, y se convierte en una línea (se dividen las de más de
   80 caracteres). Si Whisper no está instalado se usa Vosk.
3. El resultado es un **borrador**: el usuario lo revisa, corrige y le pone
   nombre antes de guardarlo. La pista se copia a la carpeta ``pistas/`` para
   cantarla después en el modo automático.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import Config
from ..texto import ajustar_linea, censurar, detectar_idioma
from .fuentes import ErrorAudio, leer_archivo_audio
from .limpieza import aislar_voz_estereo
from .motores import ErrorMotor, es_alucinacion

FORMATOS = (".mp3", ".wav", ".flac", ".ogg")
FRECUENCIA = 16000
MAX_SEGUNDOS = 20 * 60  # una canción no dura más; protege la memoria

Progreso = Callable[[float], None]


@dataclass
class Borrador:
    archivo: Path
    nombre: str
    lineas: list[str]
    idioma: str
    duracion: float
    motor: str


def buscar_audios(ruta: Path) -> list[Path]:
    """El archivo indicado o los archivos de audio de una carpeta."""
    if ruta.is_dir():
        return sorted(p for p in ruta.iterdir() if p.is_file() and p.suffix.lower() in FORMATOS)
    return [ruta] if ruta.is_file() and ruta.suffix.lower() in FORMATOS else []


_RUIDO_NOMBRE = re.compile(
    r"[\(\[]?\b(official|audio|video|lyrics?|letra|hq|hd|mp3|final|mix|master)\b[\)\]]?", re.IGNORECASE)


def nombre_desde_archivo(ruta: Path) -> str:
    """"Ghost_of_you (Official Audio).mp3" -> "Ghost of you"."""
    nombre = ruta.stem.replace("_", " ").replace(".", " ")
    nombre = _RUIDO_NOMBRE.sub(" ", nombre)
    nombre = re.sub(r"[\(\[]\s*[\)\]]", " ", nombre)
    nombre = re.sub(r"\s*-\s*$", "", " ".join(nombre.split()))
    return nombre.strip(" -") or ruta.stem


def nombre_seguro(texto: str) -> str:
    """Nombre válido para un archivo en Windows, Linux y Android."""
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", texto).strip(" .")
    return limpio[:80] or "pista"


def lineas_desde_frases(frases: list[str], maximo: int, ocultar_groserias: bool = True) -> list[str]:
    """Convierte las frases de la IA en líneas de la letra.

    * descarta lo que Whisper "inventa" en la música ("Music", "♪");
    * separa las oraciones (". ", "? ", "! ") y divide lo que pase de ``maximo``;
    * corta los bucles de la IA: una misma línea más de 3 veces seguidas
      (en una letra real casi nunca pasa).
    """
    lineas: list[str] = []
    for frase in frases:
        frase = " ".join(frase.replace("♪", " ").split())
        if not frase or es_alucinacion(frase):
            continue
        for oracion in re.split(r"(?<=[.!?¿¡])\s+", frase):
            oracion = oracion.strip(" .")
            if not oracion:
                continue
            if ocultar_groserias:
                oracion = censurar(oracion)
            for parte in ajustar_linea(oracion, maximo, "dividir"):
                if len(lineas) >= 3 and all(l.lower() == parte.lower() for l in lineas[-3:]):
                    continue
                lineas.append(parte)
    return lineas


def leer_voz(ruta: Path) -> np.ndarray:
    """La pista en mono a 16 kHz con la voz del centro realzada."""
    estereo = leer_archivo_audio(ruta, FRECUENCIA, canales=2)
    if len(estereo) > MAX_SEGUNDOS * FRECUENCIA:
        raise ErrorAudio(f"El audio dura más de {MAX_SEGUNDOS // 60} minutos; no parece una canción.")
    return aislar_voz_estereo(estereo).astype(np.float32)


def _con_whisper(muestras: np.ndarray, config: Config, idioma: str | None,
                 progreso: Progreso | None) -> tuple[list[str], str]:
    from .motores import MotorWhisper
    from .proceso import modelo_whisper

    motor = MotorWhisper(modelo_whisper(config), idioma or "auto", FRECUENCIA, sincrono=True)
    segmentos, informacion = motor.modelo.transcribe(
        muestras, language=idioma, beam_size=5, vad_filter=False,
        condition_on_previous_text=False,
    )
    duracion = max(len(muestras) / FRECUENCIA, 0.1)
    frases = []
    for segmento in segmentos:
        frases.append(segmento.text)
        if progreso:
            progreso(min(1.0, segmento.end / duracion))
    return frases, informacion.language or idioma or "es"


def _con_vosk(muestras: np.ndarray, config: Config, idioma: str | None,
              progreso: Progreso | None) -> tuple[list[str], str]:
    from .modelos import idiomas_disponibles, ruta_modelo
    from .motores import MotorVosk

    disponibles = idiomas_disponibles(config)
    if not disponibles:
        raise ErrorMotor("No hay modelos de voz instalados (use el diagnóstico de audio, opción d).")
    idioma = idioma if idioma in disponibles else disponibles[0]
    motor = MotorVosk({idioma: ruta_modelo(config, idioma)}, FRECUENCIA)
    bloque = FRECUENCIA // 2
    frases = []
    for inicio in range(0, len(muestras), bloque):
        for t in motor.procesar(muestras[inicio:inicio + bloque]):
            if t.tipo == "final" and t.palabras:
                frases.append(t.texto)
        if progreso:
            progreso(min(1.0, (inicio + bloque) / len(muestras)))
    for t in getattr(motor, "vaciar", lambda: [])():
        if t.tipo == "final" and t.palabras:
            frases.append(t.texto)
    return frases, idioma


def crear_borrador(ruta: Path, config: Config, idioma: str | None = None,
                   progreso: Progreso | None = None) -> Borrador:
    """Transcribe ``ruta`` y devuelve el borrador de la canción."""
    from .proceso import whisper_disponible

    muestras = leer_voz(ruta)
    if whisper_disponible():
        frases, idioma_final = _con_whisper(muestras, config, idioma, progreso)
        motor = "Whisper"
    else:
        frases, idioma_final = _con_vosk(muestras, config, idioma, progreso)
        motor = "Vosk"
    lineas = lineas_desde_frases(frases, config.caracteres_por_linea,
                                 config.booleano("automatico", "censurar_transcripcion"))
    if idioma_final not in ("es", "en") and lineas:
        idioma_final = detectar_idioma(lineas)
    return Borrador(ruta, nombre_desde_archivo(ruta), lineas, idioma_final,
                    len(muestras) / FRECUENCIA, motor)


def guardar_pista(ruta: Path, config: Config, codigo: int, nombre: str) -> str:
    """Copia la pista a ``pistas/`` y devuelve su ruta relativa a la carpeta
    del programa (así la base de datos sigue sirviendo si se mueve la carpeta)."""
    carpeta = config.carpeta / "pistas"
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{codigo:03d} - {nombre_seguro(nombre)}{ruta.suffix.lower()}"
    if ruta.resolve() != destino.resolve():
        shutil.copy2(ruta, destino)
    return destino.relative_to(config.carpeta).as_posix()
