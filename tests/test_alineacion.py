from karaoke.alineacion import PalabraConTiempo, alinear_palabras, linea_en, tiempos_de_lineas

LETRA = [
    "I heard the sound of you",
    "in every thing I do",
    "It seems that you follow me everywhere",
    "It seems that you was made for me",
]


def oir(texto, inicio, paso=0.4):
    return [PalabraConTiempo(p, inicio + i * paso, inicio + i * paso + 0.3) for i, p in enumerate(texto.split())]


def test_alinea_con_errores_de_la_ia_y_palabras_de_mas():
    letra = "it seems that you follow me everywhere".split()
    oidas = "yeah it seem that you folow me every where oh".split()
    pareja = alinear_palabras(letra, oidas)
    assert pareja[0] == 1 and pareja[1] == 2 and pareja[4] == 5


def test_tiempos_de_cada_linea():
    oidas = (oir("oh yeah", 2.0)                                   # intro que no está en la letra
             + oir("I heard the sound of you", 10.0)
             + oir("in everything I do", 13.0)                     # "every thing" junto
             + oir("it seems that you folow me everywhere", 16.0)
             + oir("it seems that you were made for me", 20.0))
    tiempos = tiempos_de_lineas(LETRA, oidas)
    assert tiempos[0] == 10.0
    assert abs(tiempos[1] - 13.0) < 0.01
    assert abs(tiempos[2] - 16.0) < 0.01
    assert abs(tiempos[3] - 20.0) < 0.01


def test_linea_no_escuchada_se_reparte_entre_sus_vecinas():
    oidas = oir("I heard the sound of you", 10.0) + oir("it seems that you was made for me", 20.0)
    tiempos = tiempos_de_lineas(LETRA, oidas)
    assert tiempos[0] == 10.0 and tiempos[3] == 20.0
    assert 10.0 < tiempos[1] < tiempos[2] < 20.0


def test_sin_nada_que_alinear_reparte_en_la_duracion():
    tiempos = tiempos_de_lineas(LETRA, [], duracion=40.0)
    assert tiempos[0] == 0.0 and tiempos == sorted(tiempos) and tiempos[-1] < 40.0


def test_linea_en_con_adelanto():
    tiempos = [10.0, 13.0, 16.0]
    assert linea_en(tiempos, 9.0) == -1
    assert linea_en(tiempos, 9.6, adelanto=0.5) == 0   # se muestra medio segundo antes
    assert linea_en(tiempos, 12.4, adelanto=0.5) == 0
    assert linea_en(tiempos, 12.6, adelanto=0.5) == 1
    assert linea_en(tiempos, 99.0) == 2
