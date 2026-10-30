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
from dataclasses import dataclass, field
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
    # Segundo en que empieza cada línea en la pista (None si no se sabe).
    tiempos: list[float | None] = field(default_factory=list)
    # Todo lo que oyó la IA con su tiempo: sirve para sincronizar otra letra.
    palabras: list[Palabra] = field(default_factory=list)

    def usar_letra(self, lineas: list[str]) -> None:
        """Reemplaza el borrador por la letra real (la del autor) y calcula
        en qué segundo empieza cada una de sus líneas."""
        self.lineas = list(lineas)
        self.tiempos = tiempos_para(lineas, self.palabras, self.duracion)
        if "letra del autor" not in self.motor:
            self.motor += " + letra del autor"


@dataclass
class Palabra:
    texto: str
    inicio: float
    fin: float


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


_SIMBOLOS = re.compile(r"[^\w\s'’,.!?¿¡-]")
# Palabras que en inglés van con mayúscula a mitad de una frase.
_MAYUSCULA_NORMAL = {"i", "i'm", "i'll", "i've", "i'd", "god", "oh"}


def frases_por_pausas(palabras: list[Palabra], pausa: float = 0.55, maximo: int = 80) -> list[tuple[str, float]]:
    """Agrupa las palabras con tiempo en líneas cantadas: una línea termina
    cuando el cantante hace una pausa, cuando termina una oración o cuando
    la siguiente palabra empieza con mayúscula (así escribe Whisper el inicio
    de un verso). Devuelve (texto, segundo de inicio)."""
    frases: list[tuple[str, float]] = []
    actual: list[Palabra] = []

    def cerrar() -> None:
        if actual:
            frases.append((" ".join(p.texto for p in actual), actual[0].inicio))
            actual.clear()

    for palabra in palabras:
        texto = palabra.texto.strip()
        if not texto:
            continue
        if actual:
            anterior = actual[-1]
            limpio = texto.strip("¿¡\"'(").lower()
            nuevo_verso = (texto[:1].isupper() and limpio not in _MAYUSCULA_NORMAL and len(actual) >= 3)
            largo_actual = len(" ".join(p.texto for p in actual))
            largo = largo_actual + 1 + len(texto) > maximo
            # Una línea que ya es larga se corta también en un respiro corto.
            silencio = palabra.inicio - anterior.fin
            respiro = largo_actual >= 40 and silencio >= pausa * 0.4
            if (silencio >= pausa or respiro or anterior.texto.rstrip().endswith((".", "?", "!"))
                    or nuevo_verso or largo):
                cerrar()
        actual.append(Palabra(texto, palabra.inicio, palabra.fin))
    cerrar()
    return frases


def lineas_con_tiempo(frases: list[tuple[str, float | None]], maximo: int,
                      ocultar_groserias: bool = True) -> list[tuple[str, float | None]]:
    """Convierte las frases de la IA en líneas de la letra (con su tiempo).

    * descarta lo que Whisper "inventa" en la música ("Music", "♪", emojis);
    * separa las oraciones (". ", "? ", "! ") y divide lo que pase de ``maximo``;
    * corta los bucles de la IA: una misma línea más de 3 veces seguidas
      (en una letra real casi nunca pasa).
    """
    lineas: list[tuple[str, float | None]] = []
    for frase, tiempo in frases:
        frase = " ".join(_SIMBOLOS.sub(" ", frase).split())
        if not frase or es_alucinacion(frase):
            continue
        for oracion in re.split(r"(?<=[.!?])\s+", frase):
            oracion = oracion.strip(" .,")
            if not oracion:
                continue
            if ocultar_groserias:
                oracion = censurar(oracion)
            for parte in ajustar_linea(oracion, maximo, "dividir"):
                if len(lineas) >= 3 and all(l.lower() == parte.lower() for l, _ in lineas[-3:]):
                    continue
                lineas.append((parte, tiempo))
                tiempo = None  # solo la primera parte conoce su inicio exacto
    return lineas


def lineas_desde_frases(frases: list[str], maximo: int, ocultar_groserias: bool = True) -> list[str]:
    """Igual que ``lineas_con_tiempo`` para frases sin tiempo."""
    return [l for l, _ in lineas_con_tiempo([(f, None) for f in frases], maximo, ocultar_groserias)]


def leer_voz(ruta: Path, aislar: bool = True) -> np.ndarray:
    """La pista en mono a 16 kHz (con la voz del centro realzada)."""
    estereo = leer_archivo_audio(ruta, FRECUENCIA, canales=2)
    if len(estereo) > MAX_SEGUNDOS * FRECUENCIA:
        raise ErrorAudio(f"El audio dura más de {MAX_SEGUNDOS // 60} minutos; no parece una canción.")
    if aislar:
        return aislar_voz_estereo(estereo).astype(np.float32)
    return estereo.mean(axis=1).astype(np.float32)


def cargar_whisper_letras(config: Config, modelo: str | None = None):
    """El modelo grande para letras; si no se puede, el de tiempo real."""
    from .motores import MotorWhisper
    from .proceso import modelo_whisper

    candidatos = []
    if modelo:
        candidatos.append(modelo)
    else:
        carpeta = config.ruta("audio", "carpeta_whisper_letras")
        candidatos.append(str(carpeta) if (carpeta / "model.bin").exists()
                          else config.texto("audio", "modelo_whisper_letras"))
    candidatos.append(modelo_whisper(config))
    error = None
    for candidato in candidatos:
        try:
            return MotorWhisper(candidato, "auto", FRECUENCIA, sincrono=True), Path(candidato).name
        except ErrorMotor as ex:
            error = ex
    raise error


def _con_whisper(muestras: np.ndarray, config: Config, idioma: str | None,
                 progreso: Progreso | None, modelo: str | None = None) -> tuple[list[Palabra], str, str]:
    motor, nombre = cargar_whisper_letras(config, modelo)
    segmentos, informacion = motor.modelo.transcribe(
        muestras, language=idioma, beam_size=5, vad_filter=False,
        condition_on_previous_text=False, word_timestamps=True,
    )
    duracion = max(len(muestras) / FRECUENCIA, 0.1)
    palabras: list[Palabra] = []
    for segmento in segmentos:
        if es_alucinacion(segmento.text):
            continue
        for palabra in segmento.words or []:
            palabras.append(Palabra(palabra.word.strip(), palabra.start, palabra.end))
        if progreso:
            progreso(min(1.0, segmento.end / duracion))
    return palabras, informacion.language or idioma or "es", f"Whisper {nombre}"


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
                   progreso: Progreso | None = None, modelo: str | None = None,
                   aislar: bool | None = None) -> Borrador:
    """Transcribe ``ruta`` y devuelve el borrador de la canción."""
    from .proceso import whisper_disponible

    if aislar is None:
        aislar = config.booleano("audio", "aislar_voz_letras")
    muestras = leer_voz(ruta, aislar)
    palabras: list[Palabra] = []
    if whisper_disponible():
        palabras, idioma_final, motor = _con_whisper(muestras, config, idioma, progreso, modelo)
        frases = frases_por_pausas(palabras, config.decimal("audio", "pausa_entre_lineas"),
                                   config.caracteres_por_linea)
    else:
        textos, idioma_final = _con_vosk(muestras, config, idioma, progreso)
        frases, motor = [(t, None) for t in textos], "Vosk"
    pares = lineas_con_tiempo(frases, config.caracteres_por_linea,
                              config.booleano("automatico", "censurar_transcripcion"))
    lineas = [l for l, _ in pares]
    if idioma_final not in ("es", "en") and lineas:
        idioma_final = detectar_idioma(lineas)
    duracion = len(muestras) / FRECUENCIA
    tiempos = [t for _, t in pares]
    if palabras and any(t is None for t in tiempos):
        # las partes de una línea dividida no conocen su inicio: se alinean
        tiempos = tiempos_para(lineas, palabras, duracion)
    return Borrador(ruta, nombre_desde_archivo(ruta), lineas, idioma_final, duracion, motor,
                    tiempos, palabras)


def tiempos_para(lineas: list[str], palabras: list[Palabra], duracion: float) -> list[float]:
    """Segundo en que empieza cada línea de una letra conocida."""
    from ..alineacion import PalabraConTiempo, tiempos_de_lineas

    return tiempos_de_lineas(lineas, [PalabraConTiempo(p.texto, p.inicio, p.fin) for p in palabras], duracion)


def letra_junto_al_audio(ruta: Path) -> list[str] | None:
    """Si junto al audio hay un .txt con el mismo nombre ("Mi canción.mp3" y
    "Mi canción.txt"), es la letra escrita por el autor: una línea por renglón;
    se ignoran las etiquetas ([Coro], (Verso 2)), los comentarios // y un
    encabezado "# Nombre"."""
    from ..texto import es_etiqueta, leer_texto

    texto = ruta.with_suffix(".txt")
    if not texto.is_file():
        return None
    lineas = [r.strip() for r in leer_texto(texto).splitlines()
              if r.strip() and not es_etiqueta(r) and not r.lstrip().startswith(("//", "#"))]
    return lineas or None


def sincronizar(ruta: Path, config: Config, lineas: list[str], progreso: Progreso | None = None,
                idioma: str | None = None) -> list[float]:
    """Tiempos de una letra ya conocida con su pista (la IA solo escucha cuándo)."""
    from .proceso import whisper_disponible

    if not whisper_disponible():
        raise ErrorMotor("Para sincronizar la letra hace falta Whisper (pip install faster-whisper).")
    muestras = leer_voz(ruta, config.booleano("audio", "aislar_voz_letras"))
    palabras, _, _ = _con_whisper(muestras, config, idioma, progreso)
    return tiempos_para(lineas, palabras, len(muestras) / FRECUENCIA)


def guardar_pista(ruta: Path, config: Config, codigo: int, nombre: str) -> str:
    """Copia la pista a ``pistas/`` y devuelve su ruta relativa a la carpeta
    del programa (así la base de datos sigue sirviendo si se mueve la carpeta)."""
    carpeta = config.carpeta / "pistas"
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{codigo:03d} - {nombre_seguro(nombre)}{ruta.suffix.lower()}"
    if ruta.resolve() != destino.resolve():
        shutil.copy2(ruta, destino)
    return destino.relative_to(config.carpeta).as_posix()
