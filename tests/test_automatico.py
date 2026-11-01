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


def test_posicion_cantada_y_entrada_de_la_pista(entorno):
    from karaoke.pistas import punto_de_entrada

    control, _, codigos = entorno
    assert control.posicion_cantada() == (0, 0.0)
    correr(control, "0:01 camino solo buscando tu sonrisa", 5)
    linea, fraccion = control.posicion_cantada()
    assert linea in (2, 3) and 0.0 <= fraccion <= 1.0
    tiempos = [10.0, 14.0, 18.0, 22.0]
    assert punto_de_entrada(tiempos, 2) == 18.0
    assert punto_de_entrada(tiempos, 2, 0.5) == 20.0
    assert punto_de_entrada(tiempos, 2, 0.5, latencia=1.0) == 21.0
    assert punto_de_entrada(tiempos, 3, 1.0) == 26.0  # la última línea dura ~4 s
    assert punto_de_entrada([], 0) == 0.0


def test_al_reconocer_con_microfono_entra_la_pista(entorno, tmp_path):
    from karaoke.ui.menus import Aplicacion
    from karaoke.ui.modo_automatico import ModoAutomatico

    control, bd, codigos = entorno
    (tmp_path / "pista.mp3").write_bytes(b"")
    bd.guardar_pista(codigos["lluvia"], "pista.mp3")
    bd.guardar_tiempos(codigos["lluvia"], [10.0, 14.0, 18.0, 22.0])
    modo = ModoAutomatico(Aplicacion(control.config, bd, teclado=object()))
    modo._revisada = None

    class FuenteMicrofono:  # basta el nombre de la clase
        pass

    class FuentePista:
        pass

    class Procesador:
        fuente = FuentePista()

    correr(control, "0:01 camino solo buscando tu sonrisa", 5)
    assert not modo.revisar_entrada_pista(Procesador(), control)  # con pista ya suena la música
    modo._revisada = None
    Procesador.fuente = FuenteMicrofono()
    assert modo.revisar_entrada_pista(Procesador(), control)
    codigo, archivo, desde, entrada = modo.entrada_pista
    assert (codigo, archivo) == (codigos["lluvia"], "pista.mp3")
    assert 18.0 <= desde <= 27.0 and entrada[0] in (2, 3)
    assert not modo.revisar_entrada_pista(Procesador(), control)  # una sola vez por canción


def test_al_reconocer_entra_la_pista_aunque_no_tenga_tiempos(entorno, tmp_path):
    from karaoke.ui.menus import Aplicacion
    from karaoke.ui.modo_automatico import ModoAutomatico

    control, bd, codigos = entorno
    (tmp_path / "pista.mp3").write_bytes(b"")
    bd.guardar_pista(codigos["lluvia"], "pista.mp3")          # sin tiempos todavía
    modo = ModoAutomatico(Aplicacion(control.config, bd, teclado=object()))
    modo._revisada = None

    class FuenteMicrofono:
        pass

    class Procesador:
        fuente = FuenteMicrofono()

    correr(control, "0:01 camino solo buscando tu sonrisa", 5)
    assert modo.revisar_entrada_pista(Procesador(), control)
    codigo, archivo, desde, entrada = modo.entrada_pista
    assert codigo == codigos["lluvia"] and desde is None       # se calcula con los aproximados al sonar
    assert entrada[0] in (2, 3) and 0.0 <= entrada[1] <= 1.0


def test_escucha_en_espanol_aunque_las_canciones_sean_en_ingles(tmp_path):
    from karaoke.audio.proceso import idiomas_escucha

    config = cargar_config(tmp_path)
    assert idiomas_escucha(config, ["en"]) == ["es", "en"]           # antes: solo ["en"]
    assert idiomas_escucha(config, []) == ["es", "en"]
    config.establecer("audio", "idiomas_automatico", "en")
    assert idiomas_escucha(config, ["es", "en"]) == ["en", "es"]


def test_whisper_elige_entre_los_idiomas_permitidos():
    from karaoke.audio.motores import elegir_idioma

    permitidos = ["es", "en"]
    assert elegir_idioma([("en", 0.9), ("es", 0.05)], permitidos) == "en"          # inglés claro
    assert elegir_idioma([("en", 0.5), ("es", 0.4), ("pt", 0.1)], permitidos) == "es"  # duda: español
    assert elegir_idioma([("es", 0.3), ("en", 0.1), ("pt", 0.6)], permitidos) == "es"  # nunca portugués
    assert elegir_idioma([("pt", 0.9)], permitidos) == "es"
    assert elegir_idioma(None, permitidos) == "es"
    assert elegir_idioma([("en", 0.9)], []) is None                                  # sin lista: libre


def test_whisper_transcribe_de_nuevo_si_detecto_otro_idioma():
    import numpy as np
    import queue
    from types import SimpleNamespace

    from karaoke.audio.motores import MotorWhisper

    pedidos = []

    class Modelo:
        def transcribe(self, muestras, language=None, **_):
            pedidos.append(language)
            segmento = SimpleNamespace(text="la lluvia cae sobre la ciudad", avg_logprob=-0.2)
            if language is None:  # detectó inglés con poca seguridad
                return iter([segmento]), SimpleNamespace(language="en", all_language_probs=[("en", 0.5), ("es", 0.45)])
            return iter([segmento]), SimpleNamespace(language=language, all_language_probs=None)

    motor = MotorWhisper.__new__(MotorWhisper)
    motor.modelo, motor.idioma, motor.permitidos = Modelo(), "auto", ["es", "en"]
    motor.filtro_vad, motor.sugerencia, motor._resultados = False, None, queue.Queue()
    motor._transcribir(np.zeros(16000, dtype=np.float32), 1.0)
    assert pedidos == [None, "es"]
    assert motor._resultados.get_nowait().idioma == "es"


def test_vosk_en_dos_idiomas_no_mezcla_sus_palabras(entorno):
    from karaoke.transcripcion import Transcripcion

    control, _, codigos = entorno

    def oir(tipo, texto, idioma, confianza, segundo):
        control.recibir(Transcripcion(tipo, texto, "libre", idioma, confianza, segundo))
        control.tic(segundo, True)

    # El canal en inglés "oye" basura mientras se canta en español; sus
    # parciales no deben cortar ni repetir las palabras del canal en español.
    oir("parcial", "la lluvia cae", "es", 1.0, 1.0)
    oir("parcial", "the movie", "en", 1.0, 1.2)
    oir("parcial", "la lluvia cae sobre la ciudad", "es", 1.0, 1.6)
    oir("parcial", "the movie car so", "en", 1.0, 1.8)
    oir("final", "la lluvia cae sobre la ciudad dormida", "es", 0.9, 2.4)
    oir("final", "the movie car so bread the see that", "en", 0.4, 2.5)
    assert control.cancion is not None and control.cancion.codigo == codigos["lluvia"]
    assert control.seguidor.mostrada in (0, 1)


def test_aprende_solo_del_idioma_en_que_se_canta(entorno):
    from karaoke.transcripcion import Transcripcion

    control, _, _ = entorno
    t_es = Transcripcion("final", "hola", "libre", "es", 0.9, 1.0)
    t_en = Transcripcion("final", "hello", "libre", "en", 0.3, 1.1)
    control.recibir(t_es)
    control.recibir(t_en)
    assert control._canal_confiable(t_es) and not control._canal_confiable(t_en)
