from karaoke.seguimiento import Seguidor

LETRA = [
    "I heard the sound of you",
    "in every thing I do",
    "It seems that you follow me everywhere",
    "It seems that you was made for me",
    "I am afraid to fall in love again",
]


def cantar(seguidor, texto, desde, paso=0.4):
    """Entrega las palabras de una en una como lo hace Vosk."""
    eventos = []
    for numero, palabra in enumerate(texto.split()):
        evento = seguidor.escuchar([palabra], desde + numero * paso)
        if evento:
            eventos.append(evento)
    return eventos


def test_avanza_linea_por_linea():
    s = Seguidor(LETRA)
    cantar(s, "I heard the sound of you", 0)
    assert s.mostrada == 1  # ya pasó el 70 % de la línea 1
    cantar(s, "in every thing I do", 3)
    assert s.mostrada == 2


def test_tolera_palabras_mal_reconocidas():
    s = Seguidor(LETRA, linea_inicial=2)
    cantar(s, "it seams that ewe follow me everywhere", 0)
    assert s.mostrada == 3


def test_ignora_palabras_que_no_son_de_la_letra():
    s = Seguidor(LETRA, linea_inicial=1)
    cantar(s, "uno dos tres probando", 0)
    assert s.mostrada == 1


def test_detecta_linea_igual():
    s = Seguidor(LETRA, linea_inicial=2)
    cantar(s, "It seems that you follow me everywhere", 0)
    eventos = cantar(s, "It seems that you follow", 4)
    assert any(e.tipo == "igual" for e in eventos)
    assert s.mostrada == 2


def test_detecta_repeticion_de_la_cancion():
    s = Seguidor(LETRA, linea_inicial=3)
    cantar(s, "It seems that you was made for me", 0)
    eventos = cantar(s, "I heard the sound", 5)
    assert any(e.tipo == "repetir" for e in eventos)
    assert s.mostrada == 0


def test_termina_la_cancion():
    s = Seguidor(LETRA, linea_inicial=4)
    eventos = cantar(s, "I am afraid to fall in love again", 0)
    assert eventos[-1].tipo == "fin"
    assert s.terminada


def test_prediccion_por_tempo_y_limite():
    s = Seguidor(LETRA, segundos_por_palabra=0.5)
    assert s.tic(1.0, hay_voz=True) is None  # todavía es pronto
    assert s.tic(6.0, hay_voz=True).tipo == "prediccion"
    assert s.mostrada == 1
    assert s.tic(12.0, hay_voz=True).tipo == "prediccion"
    assert s.tic(20.0, hay_voz=True) is None  # máximo dos sin confirmar
    assert s.tic(40.0, hay_voz=False) is None  # sin voz no avanza


def test_ancla_de_whisper_compensa_retraso():
    s = Seguidor(LETRA, segundos_por_palabra=0.5)
    evento = s.escuchar("Seems that you follow me everywhere it seems that", 10.0, retraso=1.0)
    assert evento is not None
    assert s.mostrada == 3


def test_aprende_el_tempo():
    s = Seguidor(LETRA, segundos_por_palabra=0.45)
    cantar(s, "I heard the sound of you", 0, paso=0.8)
    cantar(s, "in every thing I do", 5, paso=0.8)
    assert s.segundos_por_palabra > 0.45
