"""Configuración del programa.

Todos los valores ajustables se leen del archivo ``karaoke.ini`` que está junto
al programa (junto a ``main.py`` o junto a ``KaraokeInteligente.exe``). Si el
archivo no existe se crea con los valores por omisión definidos en
``VALORES_POR_OMISION``. Para cambiar, por ejemplo, la longitud máxima de una
línea (80 caracteres) o el promedio de líneas por canción (10), basta con editar
``karaoke.ini``; no hace falta recompilar el ejecutable.
"""

from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

NOMBRE_INI = "karaoke.ini"

# Valores por omisión. La clave de primer nivel es la sección del .ini.
VALORES_POR_OMISION: dict[str, dict[str, str]] = {
    "base_datos": {
        # Nombre del archivo SQLite (la especificación pide "CANCIONES").
        "archivo": "CANCIONES.db",
    },
    "letras": {
        # Longitud promedio/máxima de una línea de la letra. Las líneas más
        # largas se dividen (o se truncan, o se conservan) según la acción.
        "caracteres_por_linea": "80",
        # dividir | truncar | conservar
        "accion_linea_larga": "dividir",
        # Promedio de líneas que tiene una canción (sirve para estimaciones y
        # advertencias) y máximo de líneas que se aceptan por canción.
        "lineas_promedio_cancion": "10",
        "lineas_maximas_cancion": "500",
        # Cuántos elementos se despliegan por pantalla en las opciones (w) y (x).
        "elementos_por_pagina": "10",
    },
    "programa": {
        # Archivo de texto con la lista preplaneada de canciones.
        "archivo": "PROGRAMA.txt",
    },
    "busqueda": {
        # Puntaje mínimo (0..1) para aceptar que unas palabras pertenecen a
        # una canción, y semejanza mínima entre dos palabras para considerarlas
        # iguales (tolera errores de dedo y de transcripción).
        "puntaje_minimo": "0.55",
        "semejanza_palabra": "0.78",
        "resultados_maximos": "5",
        # Evidencia mínima para identificar una canción: suma de los pesos de
        # las palabras que coincidieron (una palabra común pesa ~0.4 y una
        # poco frecuente ~1.5). Evita identificar con una sola palabra.
        "evidencia_minima": "2.5",
    },
    "audio": {
        # Motor de transcripción:
        #   hibrido  Vosk sigue la letra en tiempo real y Whisper (si está
        #            instalado) identifica la canción y confirma la posición.
        #   vosk     solo Vosk (más ligero).
        #   whisper  solo Whisper (más preciso con música, más lento).
        #   simulado lee el guion de texto "guion_simulado" (demostración sin
        #            micrófono ni modelos de voz).
        "motor": "hibrido",
        "guion_simulado": "ejemplos/guion_sound_of_you.txt",
        # Carpetas de los modelos de Vosk de cada idioma (relativas a la
        # carpeta del programa). Si faltan, el programa ofrece descargarlos.
        "modelo_vosk_es": "modelo/vosk-model-small-es-0.42",
        "modelo_vosk_en": "modelo/vosk-model-small-en-us-0.15",
        # Modelo de faster-whisper (tiny, base, small...). Si existe la carpeta
        # "carpeta_whisper" se usa sin internet; si no, se descarga la primera vez.
        "modelo_whisper": "base",
        "carpeta_whisper": "modelo/whisper-base",
        "idioma": "es",
        "frecuencia_muestreo": "16000",
        # Índice o nombre del micrófono; vacío = micrófono predeterminado.
        "dispositivo": "",
        # Limpieza del sonido.
        "filtro_pasa_altos_hz": "100",
        "filtro_pasa_bajos_hz": "4000",
        "reduccion_ruido": "si",
        # Al leer una canción estéreo ya mezclada (MP3) realza la voz que está
        # al centro de la mezcla.
        "aislar_voz_archivo": "si",
        "factor_sustraccion": "1.0",
        "segundos_calibracion": "1.5",
        "control_ganancia": "si",
        "nivel_objetivo_db": "-20",
    },
    "automatico": {
        # Palabras mínimas de la muestra para intentar identificar la canción.
        "palabras_muestra": "4",
        # Si después de tantas palabras no se reconoce la canción se considera
        # una canción nueva y se empieza a aprender en las tablas temporales.
        "palabras_cancion_nueva": "14",
        # Fracción de las palabras de la línea que se deben escuchar para pasar
        # a la siguiente línea (se adelanta un poco para que el público no se
        # atrase).
        "avance_linea": "0.70",
        # Segundos de silencio para suspender (ignorar) y para terminar la
        # canción que se aprende.
        "segundos_silencio_pausa": "6",
        "segundos_silencio_fin_aprendizaje": "8",
        # Segundos de silencio para terminar la sesión automáticamente (0 = no).
        "segundos_silencio_fin_sesion": "0",
        # Avance por tempo cuando hay voz pero la transcripción no coincide.
        "prediccion_tempo": "si",
        # Restringe el vocabulario de Vosk a las palabras de la letra.
        "vocabulario_restringido": "si",
    },
    "pantalla": {
        # Líneas de contexto que se muestran antes y después de la actual.
        "lineas_previas": "1",
        "lineas_siguientes": "2",
        "colores": "si",
    },
}


def carpeta_programa() -> Path:
    """Carpeta donde viven el .ini, la base de datos y los archivos de texto.

    Con PyInstaller ``sys.executable`` apunta al .exe; en desarrollo se usa la
    carpeta del proyecto (la que contiene ``main.py``).
    """
    variable = os.environ.get("KARAOKE_HOME")
    if variable:
        return Path(variable).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _a_bool(texto: str) -> bool:
    return texto.strip().lower() in {"si", "sí", "s", "1", "true", "yes", "y", "on"}


@dataclass
class Config:
    carpeta: Path
    valores: dict[str, dict[str, str]] = field(default_factory=dict)

    def texto(self, seccion: str, clave: str) -> str:
        return self.valores.get(seccion, {}).get(
            clave, VALORES_POR_OMISION[seccion][clave]
        )

    def entero(self, seccion: str, clave: str) -> int:
        try:
            return int(self.texto(seccion, clave))
        except ValueError:
            return int(VALORES_POR_OMISION[seccion][clave])

    def decimal(self, seccion: str, clave: str) -> float:
        try:
            return float(self.texto(seccion, clave))
        except ValueError:
            return float(VALORES_POR_OMISION[seccion][clave])

    def booleano(self, seccion: str, clave: str) -> bool:
        return _a_bool(self.texto(seccion, clave))

    def ruta(self, seccion: str, clave: str) -> Path:
        ruta = Path(self.texto(seccion, clave))
        return ruta if ruta.is_absolute() else self.carpeta / ruta

    # Atajos para los valores más usados.
    @property
    def ruta_bd(self) -> Path:
        return self.ruta("base_datos", "archivo")

    @property
    def caracteres_por_linea(self) -> int:
        return max(10, self.entero("letras", "caracteres_por_linea"))

    @property
    def por_pagina(self) -> int:
        return max(1, self.entero("letras", "elementos_por_pagina"))

    def establecer(self, seccion: str, clave: str, valor: str) -> None:
        self.valores.setdefault(seccion, {})[clave] = valor

    def guardar(self) -> Path:
        parser = configparser.ConfigParser()
        for seccion, claves in VALORES_POR_OMISION.items():
            parser[seccion] = {c: self.texto(seccion, c) for c in claves}
        ruta = self.carpeta / NOMBRE_INI
        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write(
                "; Configuración del Karaoke Inteligente.\n"
                "; Edite los valores y vuelva a abrir el programa.\n\n"
            )
            parser.write(archivo)
        return ruta


def cargar_config(carpeta: Path | None = None, crear: bool = True) -> Config:
    carpeta = Path(carpeta) if carpeta else carpeta_programa()
    config = Config(carpeta=carpeta)
    ruta = carpeta / NOMBRE_INI
    if ruta.exists():
        parser = configparser.ConfigParser()
        parser.read(ruta, encoding="utf-8")
        for seccion in parser.sections():
            config.valores[seccion] = dict(parser[seccion])
    elif crear:
        try:
            config.guardar()
        except OSError:
            pass
    return config
