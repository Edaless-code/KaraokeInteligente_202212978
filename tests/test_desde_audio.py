"""Agregar canciones desde archivos de audio (f → m)."""

import wave

import numpy as np
import pytest

from karaoke.audio import desde_audio
from karaoke.audio.desde_audio import (Palabra, buscar_audios, frases_por_pausas, crear_borrador, guardar_pista, lineas_desde_frases,
                                       nombre_desde_archivo, nombre_seguro)
from karaoke.config import cargar_config
from karaoke.db import BaseDatos


def escribir_wav(ruta, segundos=1.0, frecuencia=16000):
    muestras = (np.sin(np.arange(int(segundos * frecuencia)) * 0.05) * 8000).astype(np.int16)
    with wave.open(str(ruta), "wb") as archivo:
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(frecuencia)
        archivo.writeframes(muestras.tobytes())


def test_nombre_sugerido_desde_el_archivo(tmp_path):
    assert nombre_desde_archivo(tmp_path / "Ghost_of_you_Remastered.mp3") == "Ghost of you Remastered"
    assert nombre_desde_archivo(tmp_path / "Sound of You (Official Audio).mp3") == "Sound of You"
    assert nombre_desde_archivo(tmp_path / "Mi canción - lyrics.wav") == "Mi canción"


def test_nombre_seguro_para_archivos():
    assert nombre_seguro('¿Qué? <dime> "ya"') == "¿Qué dime ya"
    assert nombre_seguro("...") == "pista"


def test_lineas_desde_frases():
    frases = [
        " I heard the sound of you. In every thing I do",
        "Music",                       # alucinación típica de Whisper
        "♪",
        "x " * 60,                     # demasiado larga: se divide en varias
        "oh no", "oh no", "oh no", "oh no", "oh no",  # bucle de la IA
        "you bitch",                    # error de transcripción
    ]
    lineas = lineas_desde_frases(frases, 80)
    assert lineas[:2] == ["I heard the sound of you", "In every thing I do"]
    assert "Music" not in lineas
    assert all(len(linea) <= 80 for linea in lineas)
    assert lineas.count("oh no") == 3
    assert lineas[-1] == "you b****"


def test_lineas_por_pausas_y_mayusculas():
    def palabras(texto, inicio):
        return [Palabra(p, inicio + i * 0.3, inicio + i * 0.3 + 0.25) for i, p in enumerate(texto.split())]

    # Whisper junta dos versos en un segmento; el segundo empieza con mayúscula.
    entrada = (palabras("I am afraid to fall in love again", 10.0)
               + palabras("But it's hard to resist", 12.5)   # sin pausa larga
               + palabras("seems that you follow me", 17.0))  # después de una pausa
    assert frases_por_pausas(entrada) == [
        ("I am afraid to fall in love again", 10.0),
        ("But it's hard to resist", 12.5),
        ("seems that you follow me", 17.0),
    ]
    # "I" con mayúscula no parte el verso.
    assert len(frases_por_pausas(palabras("and everything I do I feel", 0.0))) == 1


def test_buscar_audios_en_una_carpeta(tmp_path):
    for nombre in ("b.mp3", "a.WAV", "notas.txt", "c.flac"):
        (tmp_path / nombre).write_bytes(b"")
    assert [p.name for p in buscar_audios(tmp_path)] == ["a.WAV", "b.mp3", "c.flac"]
    assert buscar_audios(tmp_path / "notas.txt") == []
    assert buscar_audios(tmp_path / "no_existe.mp3") == []


def test_guardar_pista_y_base_de_datos(tmp_path):
    config = cargar_config(tmp_path)
    bd = BaseDatos(config.ruta_bd)
    codigo = bd.agregar_cancion("Lluvia de papel", ["la lluvia cae", "sobre la ciudad"])
    origen = tmp_path / "entrada" / "lluvia.wav"
    origen.parent.mkdir()
    escribir_wav(origen)
    relativa = guardar_pista(origen, config, codigo, "Lluvia de papel")
    assert relativa == f"pistas/{codigo:03d} - Lluvia de papel.wav"
    assert (tmp_path / relativa).exists()
    bd.guardar_pista(codigo, relativa)
    assert bd.obtener_pista(codigo) == relativa
    assert bd.listar_pistas() == [(codigo, "Lluvia de papel", relativa)]
    bd.borrar_cancion(codigo)  # en la papelera no se ofrece
    assert bd.listar_pistas() == []
    bd.eliminar_definitivamente(codigo)
    assert bd.obtener_pista(codigo) is None
    bd.cerrar()


def test_crear_borrador_con_la_ia(tmp_path, monkeypatch):
    """La transcripción se simula: se prueba todo lo demás del recorrido."""
    config = cargar_config(tmp_path)
    archivo = tmp_path / "Lluvia_de_papel.wav"
    escribir_wav(archivo, segundos=2.0)
    vistos = {}

    def falso(muestras, config, idioma, progreso, modelo=None):
        vistos["segundos"] = len(muestras) / 16000
        progreso(1.0)
        texto = "La lluvia cae sobre la ciudad dormida y las farolas cuentan historias de papel"
        palabras = []
        for i, p in enumerate(texto.split()):
            inicio = i * 0.4 + (1.0 if i >= 7 else 0.0)  # pausa de 1 s antes de "y las farolas"
            palabras.append(Palabra(p, inicio, inicio + 0.3))
        return palabras, "es", "Whisper small"

    monkeypatch.setattr(desde_audio, "_con_whisper", falso)
    monkeypatch.setattr("karaoke.audio.proceso.whisper_disponible", lambda: True)
    borrador = crear_borrador(archivo, config, progreso=lambda f: vistos.setdefault("progreso", f))
    assert borrador.nombre == "Lluvia de papel"
    assert borrador.lineas == ["La lluvia cae sobre la ciudad dormida", "y las farolas cuentan historias de papel"]
    assert borrador.idioma == "es"
    assert borrador.tiempos == [0.0, pytest.approx(3.8)]
    assert vistos["segundos"] == pytest.approx(2.0, abs=0.05)


def test_flujo_completo_en_el_menu(tmp_path, monkeypatch):
    """f → m con un archivo: se revisa el borrador, se guarda y queda la pista."""
    from karaoke.audio.desde_audio import Borrador
    from karaoke.ui.consola import Teclado
    from karaoke.ui.desde_audio import AgregarDesdeAudio
    from karaoke.ui.menus import Aplicacion

    config = cargar_config(tmp_path)
    bd = BaseDatos(config.ruta_bd)
    archivo = tmp_path / "Mi_cancion.wav"
    escribir_wav(archivo)
    monkeypatch.setattr(desde_audio, "crear_borrador", lambda ruta, *a, **k: Borrador(
        ruta, "Mi cancion", ["primera línea", "segunda línea"], "es", 1.0, "Whisper"))

    class Teclas(Teclado):
        def __init__(self, respuestas):
            self.interactivo = False
            self.respuestas = list(respuestas)

        def linea(self, mensaje=""):
            return self.respuestas.pop(0)

        def tecla(self, espera=None):
            return "\n"

    teclado = Teclas([str(archivo), "", "n", "Mi canción nueva", "g"])
    AgregarDesdeAudio(Aplicacion(config, bd, teclado)).ejecutar()
    codigo = bd.existe_nombre("Mi canción nueva")
    assert codigo is not None
    assert bd.obtener_cancion(codigo).lineas == ["primera línea", "segunda línea"]
    assert (tmp_path / bd.obtener_pista(codigo)).exists()
    bd.cerrar()
