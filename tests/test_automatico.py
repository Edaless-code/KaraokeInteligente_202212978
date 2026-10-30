import numpy as np
import pytest

from karaoke.audio.motores import MotorSimulado
from karaoke.automatico import (APRENDIENDO, ESPERANDO, FIN, PAUSA, SIGUIENDO,
                                ControladorAutomatico, sugerir_nombre)
from karaoke.buscador import Buscador
from karaoke.config import cargar_config
from karaoke.db import BaseDatos
from karaoke.programa import cargar_programa
from karaoke.sesion import SesionKaraoke

SOUND = [
    "I heard the sound of you",
    "in every thing I do",
    "It seems that you follow me everywhere",
    "It seems that you was made for me",
    "I am afraid to fall in love again",
]
# Canción de prueba inventada para estas pruebas.
LLUVIA = [
    "La lluvia cae sobre la ciudad dormida",
    "y las farolas cuentan historias de papel",
    "camino solo buscando tu sonrisa perdida",
    "mientras la noche pinta luces en la piel",
]


def _crear_entorno(carpeta, con_whisper=False):
    config = cargar_config(carpeta)
    bd = BaseDatos(config.ruta_bd)
    sound = bd.agregar_cancion("Sound of You", SOUND)
    lluvia = bd.agregar_cancion("Lluvia de papel", LLUVIA)
    buscador = Buscador(bd, config)
    sesion = SesionKaraoke(bd, "automatico")
    control = ControladorAutomatico(bd, buscador, config, sesion, "simulado", con_whisper=con_whisper)
    return control, bd, {"sound": sound, "lluvia": lluvia}


@pytest.fixture
def entorno(tmp_path):
    control, bd, codigos = _crear_entorno(tmp_path)
    yield control, bd, codigos
    bd.cerrar()


@pytest.fixture
def entorno_hibrido(tmp_path):
    """Como en Windows: Vosk (libre) y Whisper trabajando a la vez."""
    control, bd, codigos = _crear_entorno(tmp_path, con_whisper=True)
    yield control, bd, codigos
    bd.cerrar()


def correr(control, guion, hasta, desde=0.0, paso=0.1):
    """Avanza el tiempo entregando las transcripciones del guion."""
    motor = MotorSimulado(guion, segundos_por_palabra=0.4)
    motor.segundo = desde
    bloque = np.zeros(int(16000 * paso), dtype=np.float32)
    segundo = desde
    while segundo < hasta and control.estado != FIN:
        segundo = round(segundo + paso, 3)
        for t in motor.procesar(bloque):
            control.recibir(t)
        hablando = any(f.inicio <= segundo <= f.inicio + len(f.palabras) * 0.4 + 0.3 for f in motor.frases)
        control.tic(segundo, hablando)


def test_identifica_y_sigue_hasta_el_final(entorno):
    control, bd, codigos = entorno
    guion = "\n".join(f"0:{2 + 3 * i:02d} {linea}" for i, linea in enumerate(SOUND))
    correr(control, guion, 20)
    assert control.sesion.cantadas[0].codigo == codigos["sound"]
    assert control.sesion.cantadas[0].completada
    assert control.estado == ESPERANDO


def test_empieza_a_mitad_de_la_cancion(entorno):
    control, _, codigos = entorno
    correr(control, "0:01 camino solo buscando tu sonrisa", 5)
    assert control.estado == SIGUIENDO
    assert control.cancion.codigo == codigos["lluvia"]
    assert control.seguidor.mostrada in (2, 3)


def test_pausa_sola_y_reanuda(entorno):
    control, _, _ = entorno
    guion = "0:01 La lluvia cae sobre la ciudad dormida\n0:20 y las farolas cuentan historias de papel"
    correr(control, guion, 12)
    assert control.estado == PAUSA
    correr(control, guion, 26, desde=12)
    assert control.estado == SIGUIENDO
    assert control.seguidor.mostrada >= 2


def test_programa_tiene_prioridad_y_se_marca(entorno):
    control, bd, codigos = entorno
    cargar_programa(bd, ["Lluvia de papel", "Sound of You"])
    control.sesion.programa.bd.vincular_programa()
    control.comando("n")  # siguiente del programa sin tener que cantar
    assert control.cancion.codigo == codigos["lluvia"]
    for _ in range(len(LLUVIA)):
        control.comando("c")
    assert control.sesion.programa.siguiente().codigo == codigos["sound"]


def test_aprende_una_cancion_nueva(entorno):
    control, bd, _ = entorno
    guion = ("0:01 esta es una cancion que nadie conoce todavia\n"
             "0:06 el coro dice volveremos a bailar\n"
             "0:11 el coro dice volveremos a bailar\n"
             "0:16 y termina con un adios muy largo")
    correr(control, guion, 24)
    assert control.estado == APRENDIENDO or bd.listar_temporales()
    correr(control, guion, 40, desde=24)
    temporales = bd.listar_temporales()
    assert len(temporales) == 1
    assert len(temporales[0].lineas) >= 3
    assert "volveremos a bailar" in temporales[0].nombre_sugerido.lower()


def test_teclas_manuales_en_modo_automatico(entorno):
    control, _, _ = entorno
    correr(control, "0:01 La lluvia cae sobre la ciudad", 4)
    linea = control.seguidor.mostrada
    control.comando("c")
    assert control.seguidor.mostrada == linea + 1
    control.comando("a")
    assert control.seguidor.mostrada == linea
    control.comando("g")
    correr(control, "0:05 y las farolas cuentan historias de papel", 10, desde=4)
    assert control.seguidor.mostrada == linea  # ignorando: no avanza
    control.comando("s")
    assert control.estado == SIGUIENDO
    assert control.comando("f") is False
    assert control.estado == FIN


def test_sugerir_nombre():
    assert sugerir_nombre(["hola", "el coro es este", "el coro es este"]) == "El coro es este"
    assert sugerir_nombre(["una sola línea larga de verdad muy larga"]) == "Una sola linea larga de verdad"


def test_descarta_aprendizajes_muy_cortos(entorno):
    control, bd, _ = entorno
    correr(control, "0:01 im not going to do it oh no no no no no no no no no no no", 30)
    assert bd.listar_temporales() == []


def test_no_mezcla_motores_y_no_aprende_una_cancion_conocida(entorno_hibrido):
    """El caso real que se vio en Windows: Vosk entrega mucho ruido mientras
    Whisper entrega la letra correcta con segundos de retraso. Debe
    identificar la canción y NUNCA tratarla como nueva."""
    from karaoke.transcripcion import Transcripcion

    control, bd, codigos = entorno_hibrido
    basura = "the and you may good oh hey yeah do that the thing".split()
    segundo = 0.0
    for paso in range(60):
        segundo += 0.5
        control.tic(segundo, True)
        control.recibir(Transcripcion("final", " ".join(basura[paso % 6: paso % 6 + 4]), "libre", "en"))
        if paso == 20:
            control.recibir(Transcripcion("final", "And everything I do, it seems that you follow me everywhere",
                                          "whisper", "en"), retraso=4.0)
        if control.estado == SIGUIENDO:
            break
    assert control.estado == SIGUIENDO
    assert control.cancion.codigo == codigos["sound"]
    assert bd.listar_temporales() == []


def test_no_aprende_si_se_parece_a_una_cancion_de_la_base(entorno):
    from karaoke.transcripcion import Transcripcion

    control, bd, _ = entorno
    control.tic(0.5, True)
    for numero in range(8):  # frases muy parecidas a Sound of You, pero con errores
        control.tic(1 + numero * 3, True)
        control.recibir(Transcripcion("final", "I hear the sound of oh you in every ring I do", "whisper", "en"))
    assert control.estado != APRENDIENDO
    assert bd.listar_temporales() == []


def test_censura_groserias_en_lo_escuchado(entorno):
    from karaoke.texto import censurar
    from karaoke.transcripcion import Transcripcion

    control, _, _ = entorno
    control.recibir(Transcripcion("final", "I don't wanna lose, yeah, but I am a bitch.", "whisper", "en"))
    assert "bitch" not in control.escuchado and "b****" in control.escuchado
    assert censurar("Eres una PUTA mierda") == "Eres una P*** m*****"
    assert censurar("Bitchin is not filtered but bitch is") == "Bitchin is not filtered but b**** is"
